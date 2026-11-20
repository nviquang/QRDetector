"""Bộ phát hiện QR YOLOv8n detect (chuyển từ qrdet-n, ``tools/export_qrdet_detect.py``) chạy ONNX Runtime hoặc OpenVINO.

Không cần torch/ultralytics lúc chạy. Ảnh được thu theo **tỉ lệ cố định** ``scale`` (không theo imgsz) rồi đệm về bội
32: QR ~57 px ở 0,56 mm/px còn ~34 px ở scale 0,6. Giao diện giống ``qr.detector.QRDetector`` (``detect``, ``warmup``,
``set_device``, ``device``, ``gpu_available``) để ``ImprovePipeline(detector=...)`` nhận thẳng. Không có mask nên quad
lấy từ ``qr.quad_estimate``.
"""

from __future__ import annotations

import logging
import os

import cv2
import numpy as np

from .detection import Detection
from .quad_estimate import PAD, estimate_quad, scale_quad

logger = logging.getLogger("solution.qr")

DEFAULT_MODEL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models", "qrdet_n_detect.onnx")
STRIDE = 32
PAD_VALUE = 114
BACKENDS = ("onnxruntime", "openvino")


def letterbox_shape(h: int, w: int, scale: float) -> tuple[int, int, int, int]:
    """(cao, rộng) sau khi thu và (cao, rộng) sau khi đệm lên bội 32."""
    rh, rw = max(1, int(round(h * scale))), max(1, int(round(w * scale)))
    return rh, rw, -(-rh // STRIDE) * STRIDE, -(-rw // STRIDE) * STRIDE


def preprocess(image_bgr: np.ndarray, scale: float) -> tuple[np.ndarray, tuple[int, int]]:
    """BGR uint8 → (tensor 1×3×H×W float32 RGB 0..1, (lề trái, lề trên)). Giống LetterBox của ultralytics: thu
    ``scale`` lần bằng INTER_LINEAR, đệm màu 114 chia đều hai phía lên bội 32 — để kết quả khớp bản chạy torch."""
    h, w = image_bgr.shape[:2]
    rh, rw, ph, pw = letterbox_shape(h, w, scale)
    small = image_bgr if (rh, rw) == (h, w) else cv2.resize(image_bgr, (rw, rh), interpolation=cv2.INTER_LINEAR)
    top, left = int(round((ph - rh) / 2 - 0.1)), int(round((pw - rw) / 2 - 0.1))
    canvas = np.full((ph, pw, 3), PAD_VALUE, np.uint8)
    canvas[top:top + rh, left:left + rw] = small
    rgb = canvas[..., ::-1]
    return np.ascontiguousarray(rgb.transpose(2, 0, 1)[None], np.float32) / 255.0, (left, top)


def postprocess(out: np.ndarray, scale: float, conf_th: float, iou_th: float,
                shape: tuple[int, int], pad: tuple[int, int] = (0, 0)) -> list[tuple[np.ndarray, float]]:
    """Đầu ra YOLOv8 1×(5+…)×N (cx, cy, w, h, điểm, [hệ số mask nếu là model seg]) → [(bbox xyxy tọa độ ảnh gốc,
    điểm)] sau NMS. ``pad``: lề (trái, trên) của ``preprocess``."""
    pred = np.asarray(out)[0]
    if pred.shape[0] != 5 and pred.shape[1] == 5:
        pred = pred.T
    scores = pred[4]
    keep = scores >= conf_th
    if not np.any(keep):
        return []
    cx, cy, bw, bh = pred[0][keep], pred[1][keep], pred[2][keep], pred[3][keep]
    scores = scores[keep]
    rects = np.column_stack([cx - bw / 2 - pad[0], cy - bh / 2 - pad[1], bw, bh]) / scale
    idx = cv2.dnn.NMSBoxes(rects.tolist(), scores.tolist(), conf_th, iou_th)
    h, w = shape
    found = []
    for i in np.asarray(idx).reshape(-1):
        x, y, rw, rh = rects[i]
        box = np.array([max(0.0, x), max(0.0, y), min(float(w), x + rw), min(float(h), y + rh)], np.float32)
        if box[2] > box[0] and box[3] > box[1]:
            found.append((box, float(scores[i])))
    return found


class _OrtRunner:
    def __init__(self, path: str, threads: int | None):
        import onnxruntime as ort
        opts = ort.SessionOptions()
        if threads:
            opts.intra_op_num_threads = threads
        self._session = ort.InferenceSession(path, opts, providers=["CPUExecutionProvider"])
        self._input = self._session.get_inputs()[0].name

    def __call__(self, tensor: np.ndarray) -> np.ndarray:
        return self._session.run(None, {self._input: tensor})[0]


class _OpenVinoRunner:
    """OpenVINO đọc thẳng file ONNX; biên dịch riêng cho mỗi kích thước đầu vào (thường chỉ một: dải ROI cố định)."""

    def __init__(self, path: str, threads: int | None):
        import openvino as ov
        self._core = ov.Core()
        self._model = self._core.read_model(path)
        self._config = {"INFERENCE_NUM_THREADS": int(threads)} if threads else {}
        self._compiled = {}

    def __call__(self, tensor: np.ndarray) -> np.ndarray:
        shape = tuple(tensor.shape)
        compiled = self._compiled.get(shape)
        if compiled is None:
            model = self._model.clone()
            model.reshape({model.inputs[0].any_name: list(shape)})
            compiled = self._compiled[shape] = self._core.compile_model(model, "CPU", self._config)
        return compiled(tensor)[compiled.outputs[0]]


class OnnxQRDetector:
    def __init__(self, model_path: str = DEFAULT_MODEL, scale: float = 0.75, conf_th: float = 0.3,
                 iou_th: float = 0.3, backend: str = "onnxruntime", threads: int | None = None):
        """scale: tỉ lệ thu ảnh trước khi đưa vào mạng (QR ~57 px → ~43 px ở 0,75).
        backend: "onnxruntime" hoặc "openvino". threads: số luồng CPU (None = mặc định của thư viện)."""
        if backend not in BACKENDS:
            raise ValueError(f"backend phải là một trong {BACKENDS}")
        if not os.path.isfile(model_path):
            raise FileNotFoundError(f"thiếu model {model_path} — chạy tools/export_qrdet_detect.py")
        self.scale, self.conf_th, self.iou_th, self.backend = scale, conf_th, iou_th, backend
        self._run = (_OrtRunner if backend == "onnxruntime" else _OpenVinoRunner)(model_path, threads)
        logger.info("qr_detector backend=%s scale=%.2f conf=%.2f model=%s", backend, scale, conf_th,
                    os.path.basename(model_path))

    # cùng giao diện QRDetector -------------------------------------------------
    @property
    def device(self) -> str:
        return "cpu"

    @property
    def gpu_available(self) -> bool:
        return False

    def set_device(self, device: str):
        """Chỉ chạy CPU; giữ để ImprovePipeline.set_device không lỗi."""
        if device not in ("auto", "cpu"):
            logger.warning("OnnxQRDetector chỉ chạy CPU, bỏ qua device=%s", device)

    def warmup(self, shape: tuple[int, int] = (1072, 2856)):
        self.detect(np.zeros((shape[0], shape[1], 3), np.uint8))

    def detect(self, image_bgr: np.ndarray) -> list[Detection]:
        if image_bgr.ndim == 2:
            image_bgr = cv2.cvtColor(image_bgr, cv2.COLOR_GRAY2BGR)
        tensor, pad = preprocess(image_bgr, self.scale)
        found = postprocess(self._run(tensor), self.scale, self.conf_th, self.iou_th, image_bgr.shape[:2], pad)
        if not found:
            return []
        gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
        results = []
        for box, score in found:
            quad = estimate_quad(gray, box)
            results.append(Detection(bbox_xyxy=box, quad_xy=scale_quad(quad, PAD), confidence=score,
                                     polygon_xy=quad))
        return results
