"""Bước 1: Phát hiện QR bằng qrdet (YOLOv8-based)."""

from __future__ import annotations
from dataclasses import dataclass

import numpy as np
from qrdet import QRDetector as _QRDetector


@dataclass
class Detection:
    bbox_xyxy: np.ndarray   # [x1, y1, x2, y2] float32
    quad_xy: np.ndarray     # (4, 2) float32 — 4 góc của QR
    confidence: float


class QRDetector:
    def __init__(self, model_size: str = "s", conf_th: float = 0.5):
        self._detector = _QRDetector(model_size=model_size, conf_th=conf_th)

    def detect(self, image_bgr: np.ndarray) -> list[Detection]:
        """Nhận ảnh BGR, trả về danh sách Detection (có thể rỗng)."""
        raw = self._detector.detect(image=image_bgr, is_bgr=True)
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
