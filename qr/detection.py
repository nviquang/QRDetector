"""Kiểu dữ liệu một QR được phát hiện — tách khỏi qr/detector.py để bộ phát hiện ONNX/OpenVINO không phải nạp torch."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class Detection:
    bbox_xyxy: np.ndarray   # [x1, y1, x2, y2] float32
    quad_xy: np.ndarray     # (4, 2) float32 — quad đệm bao trọn QR, dùng cho warp trong cascade
    confidence: float
    polygon_xy: np.ndarray | None = None   # (N, 2) đường bao mã — nguồn quad hiển thị khi chưa đọc được
