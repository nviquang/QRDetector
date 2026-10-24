"""Bước 2: Crop + warp perspective QR về hình chữ nhật chuẩn."""

from __future__ import annotations

import cv2
import numpy as np

from .detector import Detection

# Kích thước đầu ra mặc định sau warp
_DEFAULT_SIZE = 512


def _order_points(pts: np.ndarray) -> np.ndarray:
    """Sắp xếp 4 điểm theo thứ tự: top-left, top-right, bottom-right, bottom-left."""
    rect = np.zeros((4, 2), dtype=np.float32)
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]   # top-left: tổng nhỏ nhất
    rect[2] = pts[np.argmax(s)]   # bottom-right: tổng lớn nhất
    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]  # top-right: diff nhỏ nhất
    rect[3] = pts[np.argmax(diff)]  # bottom-left: diff lớn nhất
    return rect


def add_quiet_zone(image_bgr: np.ndarray, pad_px: int = 64, value: int = 255) -> np.ndarray:
    """Đệm viền trắng (Quiet Zone) quanh ảnh theo chuẩn ISO/IEC 18004."""
    color = (value, value, value) if image_bgr.ndim == 3 else value
    return cv2.copyMakeBorder(
        image_bgr, pad_px, pad_px, pad_px, pad_px,
        cv2.BORDER_CONSTANT, value=color
    )


def warp_qr(
    image_bgr: np.ndarray,
    detection: Detection,
    out_size: int = _DEFAULT_SIZE,
    pad_px: int = 0,
) -> np.ndarray:
    """Warp perspective vùng QR về ảnh vuông out_size x out_size (tuỳ chọn đệm Quiet Zone viền trắng)."""
    src = _order_points(detection.quad_xy)
    dst = np.array([
        [0, 0],
        [out_size - 1, 0],
        [out_size - 1, out_size - 1],
        [0, out_size - 1],
    ], dtype=np.float32)

    M = cv2.getPerspectiveTransform(src, dst)
    warped = cv2.warpPerspective(image_bgr, M, (out_size, out_size),
                                 flags=cv2.INTER_LANCZOS4)
    if pad_px > 0:
        return add_quiet_zone(warped, pad_px=pad_px)
    return warped
