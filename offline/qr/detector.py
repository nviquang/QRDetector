"""Bước 1: Phát hiện QR bằng qrdet (YOLOv8-based)."""

from __future__ import annotations
from dataclasses import dataclass

import numpy as np
from qrdet import QRDetector as _QRDetector
# qrdet.detect() không cho chỉnh imgsz → gọi thẳng model YOLO và dùng lại helper của qrdet
from qrdet.qrdet import _prepare_input, _yolo_v8_results_to_dict


@dataclass
class Detection:
    bbox_xyxy: np.ndarray   # [x1, y1, x2, y2] float32
    quad_xy: np.ndarray     # (4, 2) float32 — 4 góc của QR
    confidence: float


class QRDetector:
    def __init__(self, model_size: str = "s", conf_th: float = 0.5, imgsz: int = 640):
        """
        imgsz: cạnh ảnh đưa vào YOLO. Mặc định qrdet là 640 — frame 2448×2048 bị thu nhỏ ~4 lần,
        QR ~60px còn ~15px và bị bỏ sót. imgsz=1280 giữ QR nhỏ đủ lớn để phát hiện.
        """
        self._detector = _QRDetector(model_size=model_size, conf_th=conf_th)
        self._conf_th = conf_th
        self._imgsz = imgsz

    def detect(self, image_bgr: np.ndarray) -> list[Detection]:
        """Nhận ảnh BGR, trả về danh sách Detection (có thể rỗng)."""
        image = _prepare_input(source=image_bgr, is_bgr=True)
        predictions = self._detector.model.predict(
            source=image, conf=self._conf_th, iou=self._detector._nms_iou, imgsz=self._imgsz,
            half=False, max_det=100, agnostic_nms=True, verbose=False,
        )
        raw = _yolo_v8_results_to_dict(results=predictions[0], image=image)
        results = []
        for d in raw:
            # ưu tiên padded_quad_xy để bao trọn QR; fallback về quad_xy
            quad = d.get("padded_quad_xy", d.get("quad_xy"))
            if quad is None:
                continue
            results.append(Detection(
                bbox_xyxy=d["bbox_xyxy"].astype(np.float32),
                quad_xy=quad.astype(np.float32),
                confidence=float(d["confidence"]),
            ))
        return results
