"""Bước 1: Phát hiện QR bằng qrdet (YOLOv8-seg) — chạy GPU NVIDIA nếu torch có CUDA."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import torch
from qrdet import QRDetector as _QRDetector
# qrdet.detect() không cho chỉnh imgsz → gọi thẳng model YOLO và dùng lại helper của qrdet
from qrdet.qrdet import _prepare_input, _yolo_v8_results_to_dict

logger = logging.getLogger("solution.qr")


@dataclass
class Detection:
    bbox_xyxy: np.ndarray   # [x1, y1, x2, y2] float32
    quad_xy: np.ndarray     # (4, 2) float32 — padded quad của qrdet, dùng cho warp trong cascade
    confidence: float
    polygon_xy: np.ndarray | None = None   # (N, 2) đường bao mask — nguồn quad hiển thị khi chưa đọc được


def resolve_device(requested: str, cuda_available: bool) -> str:
    """'auto' → 'cuda:0' nếu có CUDA, ngược lại 'cpu'. Yêu cầu cuda mà không có → 'cpu' + cảnh báo."""
    if requested == "auto":
        return "cuda:0" if cuda_available else "cpu"
    if requested.startswith("cuda") and not cuda_available:
        logger.warning("Không có CUDA — detector chạy CPU thay cho %s", requested)
        return "cpu"
    return requested


class QRDetector:
    def __init__(self, model_size: str = "s", conf_th: float = 0.5, imgsz: int = 640,
                 device: str = "auto", half: bool = False):
        """
        imgsz:  cạnh ảnh đưa vào YOLO. Mặc định qrdet là 640 — frame 2448×2048 bị thu nhỏ ~4 lần,
                QR ~60px còn ~15px và bị bỏ sót. imgsz=1280 giữ QR nhỏ đủ lớn để phát hiện.
        device: "auto" (GPU nếu có), "cpu" hoặc "cuda:N".
        half:   FP16 — chỉ có tác dụng trên GPU; tắt mặc định vì GTX 16xx từng lỗi FP16.
        """
        self._detector = _QRDetector(model_size=model_size, conf_th=conf_th)
        self._conf_th = conf_th
        self._imgsz = imgsz
        self._device = resolve_device(device, torch.cuda.is_available())
        self._half = half and self._device.startswith("cuda")
        gpu = torch.cuda.get_device_name(self._device) if self._device.startswith("cuda") else "-"
        logger.info("qr_detector device=%s half=%s imgsz=%d gpu=%s",
                    self._device, self._half, imgsz, gpu)

    @property
    def device(self) -> str:
        return self._device

    def warmup(self, shape: tuple[int, int] = (768, 2448)):
        """Detect một lần trên ảnh đen — lần đầu trên GPU mất vài giây (nạp kernel CUDA)."""
        self.detect(np.zeros((shape[0], shape[1], 3), np.uint8))

    def detect(self, image_bgr: np.ndarray) -> list[Detection]:
        """Nhận ảnh BGR, trả về danh sách Detection (có thể rỗng)."""
        image = _prepare_input(source=image_bgr, is_bgr=True)
        predictions = self._detector.model.predict(
            source=image, conf=self._conf_th, iou=self._detector._nms_iou, imgsz=self._imgsz,
            device=self._device, half=self._half, max_det=100, agnostic_nms=True, verbose=False,
        )
        raw = _yolo_v8_results_to_dict(results=predictions[0], image=image)
        results = []
        for d in raw:
            # ưu tiên padded_quad_xy để bao trọn QR khi warp; fallback về quad_xy
            quad = d.get("padded_quad_xy", d.get("quad_xy"))
            if quad is None:
                continue
            polygon = d.get("polygon_xy")
            results.append(Detection(
                bbox_xyxy=d["bbox_xyxy"].astype(np.float32),
                quad_xy=quad.astype(np.float32),
                confidence=float(d["confidence"]),
                polygon_xy=None if polygon is None else np.asarray(polygon, np.float32),
            ))
        return results
