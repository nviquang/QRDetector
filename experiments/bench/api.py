"""Giao diện chung cho mọi phương pháp đọc QR trong bộ chấm điểm.

Mỗi phương pháp là một class có ``read_pass(obs, ctx) -> str | None``: nhận các quan sát của MỘT lượt tem
(k frame, theo thứ tự thời gian) và trả nội dung đã chốt, hoặc None nếu không dám báo.
Không giữ trạng thái giữa các lần gọi. Tự quyết định quy tắc xác nhận; báo sai bị tính riêng và rất nặng.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class Obs:
    gray: np.ndarray            # crop xám uint8 quanh tem, đã áp điều kiện thử
    bbox: np.ndarray            # [x1,y1,x2,y2] của detection, theo tọa độ crop
    quad: np.ndarray            # (4,2) padded quad của qrdet, tọa độ crop
    polygon: np.ndarray | None  # (N,2) đường bao mask, tọa độ crop
    conf: float
    origin: np.ndarray          # gốc crop trong frame gốc (x,y); đã nhân tỉ lệ nếu điều kiện đổi cỡ ảnh
    frame: int                  # chỉ số frame gốc
    t: float                    # giây


@dataclass
class Ctx:
    velocity: tuple[float, float]  # px/frame theo tọa độ crop (đã nhân tỉ lệ)
    fps: float
    exposure_ms: float
    blur_px: float                 # độ dài vệt mờ ước tính (px)
