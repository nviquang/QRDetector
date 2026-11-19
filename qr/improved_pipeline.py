"""ImprovePipeline: luồng QR tối ưu cho QR nhỏ trên frame lớn — KHÔNG dùng Real-ESRGAN.

Thứ tự:
  1. Detect (qrdet / YOLOv8) với imgsz=1280 — imgsz 640 mặc định bỏ sót QR ~60px trên frame 2448×2048
  2. Cascade decode trên ROI cắt từ ảnh gốc, bước rẻ chạy trước, dừng ở bước đầu tiên thành công:
     a. ROI xám × upscale 4x → zxing                   (~1ms)
     b. Warp perspective 256 + Quiet Zone → zxing       (~5ms)
     c. ROI CLAHE × upscale 4x → WeChat                 (~50ms)
     d. ROI stretch × upscale 4x → WeChat CNN + SR      (~55ms)
     e. ROI xám × upscale 3x → WeChat CNN + SR          (~40ms)

Thứ tự cascade chọn từ benchmark trên frame camera thật (images/*.bmp): bỏ pyzbar (yếu với QR
~2px/module) và fallback warp 512 + decode_parallel cũ (~3.6s/frame, gần như không thêm kết quả).

Mỗi bước trả ``Decoded`` gồm cả 4 góc QR quy về tọa độ ảnh gốc (trừ viền đệm của upscale_gray, chia
scale, cộng gốc ROI; bước warp đi ngược qua homography) — UI vẽ quad bằng góc này thay cho padded quad.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable

import cv2
import numpy as np

from .content_filter import CODE_PATTERN, EXPECTED_SYMBOL
from .corrector import add_quiet_zone, warp_matrix, warp_qr
from .decoder import read_wechat_gray, read_zxing_gray
from .detector import Detection, QRDetector
from .preprocessor import UPSCALE_PAD_PER_SCALE, clahe, roi_bounds, stretch_contrast, upscale_gray

_WARP_SIZE = 256
_WARP_PAD = 32


@dataclass
class Decoded:
    text: str
    corners: np.ndarray   # (4, 2) float32 — 4 góc QR trong tọa độ ảnh gốc, thứ tự vòng


Reader = Callable[[np.ndarray], "tuple[str, np.ndarray] | None"]


def _roi_step(preprocess: Callable[[np.ndarray], np.ndarray], scale: int, read: Reader):
    pad = UPSCALE_PAD_PER_SCALE * scale

    def step(image_bgr: np.ndarray, det: Detection, roi_gray: np.ndarray,
             origin: np.ndarray) -> Decoded | None:
        hit = read(upscale_gray(preprocess(roi_gray), scale))
        if hit is None:
            return None
        text, pts = hit
        return Decoded(text, ((pts - pad) / scale + origin).astype(np.float32))
    return step


def _warp_zxing_step(image_bgr: np.ndarray, det: Detection, roi_gray: np.ndarray,
                     origin: np.ndarray, symbol=None) -> Decoded | None:
    warped = cv2.cvtColor(warp_qr(image_bgr, det, out_size=_WARP_SIZE), cv2.COLOR_BGR2GRAY)
    hit = read_zxing_gray(add_quiet_zone(warped, pad_px=_WARP_PAD), symbol=symbol)
    if hit is None:
        return None
    text, pts = hit
    back = np.linalg.inv(warp_matrix(det, _WARP_SIZE))
    corners = cv2.perspectiveTransform((pts - _WARP_PAD).reshape(-1, 1, 2).astype(np.float32), back)
    return Decoded(text, corners.reshape(4, 2).astype(np.float32))


def _identity(gray: np.ndarray) -> np.ndarray:
    return gray


_CASCADE = (
    _roi_step(_identity, 4, read_zxing_gray),
    _warp_zxing_step,
    _roi_step(clahe, 4, read_wechat_gray),
    _roi_step(stretch_contrast, 4, lambda g: read_wechat_gray(g, use_cnn=True)),
    _roi_step(_identity, 3, lambda g: read_wechat_gray(g, use_cnn=True)),
)


def make_detector(model_size: str = "s", conf_th: float = 0.3, imgsz: int = 1280, device: str = "auto",
                  half: bool = False):
    """Chọn bộ phát hiện theo biến môi trường ``QR_DETECTOR``:
    - ``qrdet`` (mặc định): qrdet YOLOv8-seg trên torch (GPU nếu có), ``model_size``/``imgsz`` như cũ;
    - ``onnx`` / ``openvino``: YOLOv8n detect chuyển từ qrdet-n (``qr/models/qrdet_n_detect.onnx``), CPU, không cần
      torch; tỉ lệ thu ``QR_DETECT_SCALE`` (mặc định 0,6), số luồng ``QR_DETECT_THREADS``.
    """
    kind = os.environ.get("QR_DETECTOR", "qrdet").strip().lower()
    if kind in ("onnx", "onnxruntime", "openvino"):
        from .detector_onnx import OnnxQRDetector
        threads = os.environ.get("QR_DETECT_THREADS")
        return OnnxQRDetector(scale=float(os.environ.get("QR_DETECT_SCALE", "0.6")), conf_th=conf_th,
                              backend="openvino" if kind == "openvino" else "onnxruntime",
                              threads=int(threads) if threads else None)
    if kind != "qrdet":
        raise ValueError(f"QR_DETECTOR={kind!r} không hợp lệ (qrdet | onnx | openvino)")
    return QRDetector(model_size=model_size, conf_th=conf_th, imgsz=imgsz, device=device, half=half)


class ImprovePipeline:
    def __init__(
        self,
        model_size: str = "s",
        conf_th: float = 0.3,
        imgsz: int = 1280,
        roi_margin: float = 0.25,
        detector=None,
        device: str = "auto",
        half: bool = False,
        multi_frame: bool = True,
        code_pattern: str | None = CODE_PATTERN,
        expected_symbol: tuple[str, str] | None = EXPECTED_SYMBOL,
    ):
        """detector: object có ``detect(image_bgr) -> list[Detection]`` — mặc định QRDetector (YOLO,
        GPU nếu có); test truyền detector giả để không phải nạp model.
        multi_frame: PassReader đọc nhiều frame (xem qr/multiframe.py); False = cascade từng frame như cũ.
        code_pattern: regex mã hợp lệ cho chế độ nhiều frame (fullmatch); mặc định ``dãy số#dãy số``.
                      None = nhận mọi nội dung (chỉ dùng khi đo dữ liệu cũ).
        expected_symbol: (version, mức sửa lỗi) bắt buộc với kết quả zxing ở chế độ nhiều frame; mặc định V2-M.
                      None = nhận mọi loại."""
        self.multi_frame = multi_frame
        self.code_pattern = code_pattern
        self.expected_symbol = expected_symbol
        self.roi_margin = roi_margin
        self._detector = detector if detector is not None else make_detector(
            model_size=model_size, conf_th=conf_th, imgsz=imgsz, device=device, half=half)
        self._roi_margin = roi_margin

    # ── public ────────────────────────────────────────────────────────────────

    @property
    def device(self) -> str:
        return getattr(self._detector, "device", "cpu")

    @property
    def gpu_available(self) -> bool:
        return getattr(self._detector, "gpu_available", False)

    def set_device(self, device: str):
        """"auto", "cpu" hoặc "cuda:N" — đổi được lúc đang chạy, chỉ ảnh hưởng bước detect."""
        self._detector.set_device(device)

    def warmup(self, shape: tuple[int, int] = (768, 2448)):
        """Chạy detect một lần để lần đầu trên GPU không rơi vào frame thật."""
        self._detector.warmup(shape)

    def detect(self, image_bgr: np.ndarray) -> list[Detection]:
        """Chỉ chạy bước detect — dùng để vẽ quad không cần decode."""
        return self._detector.detect(image_bgr)

    def decode(self, image_bgr: np.ndarray) -> list[str]:
        """
        Nhận ảnh BGR (np.ndarray H×W×3 uint8), trả về list nội dung QR (có thể rỗng).
        """
        results, _ = self.scan(image_bgr)
        return results

    def scan(self, image_bgr: np.ndarray) -> tuple[list[str], list[Detection]]:
        """Detect 1 lần, trả về (list nội dung QR, list Detection TẤT CẢ — dùng để vẽ quad)."""
        detections = self._detector.detect(image_bgr)
        if not detections:
            return [], []

        results: list[str] = []
        for det in detections:
            hit = self.decode_detection(image_bgr, det)
            if hit:
                results.append(hit.text)
        return results, detections

    def decode_detection(self, image_bgr: np.ndarray, det: Detection) -> Decoded | None:
        """Chạy cascade cho MỘT detection, trả nội dung + 4 góc QR (tọa độ ảnh gốc) hoặc None."""
        x1, y1, x2, y2 = roi_bounds(image_bgr.shape, det.bbox_xyxy, self._roi_margin)
        roi = image_bgr[y1:y2, x1:x2]
        if roi.size == 0:
            return None
        roi_gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY) if roi.ndim == 3 else roi
        origin = np.array([x1, y1], np.float32)
        for step in _CASCADE:
            hit = step(image_bgr, det, roi_gray, origin)
            if hit:
                return hit
        return None
