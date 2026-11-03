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


def warp_matrix(detection: Detection, out_size: int = _DEFAULT_SIZE) -> np.ndarray:
    """Ma trận perspective đưa quad của detection về hình vuông out_size × out_size."""
    src = _order_points(detection.quad_xy)
    dst = np.array([
        [0, 0],
        [out_size - 1, 0],
        [out_size - 1, out_size - 1],
        [0, out_size - 1],
    ], dtype=np.float32)
    return cv2.getPerspectiveTransform(src, dst)


def warp_qr(
    image_bgr: np.ndarray,
    detection: Detection,
    out_size: int = _DEFAULT_SIZE,
    pad_px: int = 0,
) -> np.ndarray:
    """Warp perspective vùng QR về ảnh vuông out_size x out_size (tuỳ chọn đệm Quiet Zone viền trắng)."""
    warped = cv2.warpPerspective(image_bgr, warp_matrix(detection, out_size), (out_size, out_size),
                                 flags=cv2.INTER_LANCZOS4)
    if pad_px > 0:
        return add_quiet_zone(warped, pad_px=pad_px)
    return warped


def display_quad(detection: Detection, corners: np.ndarray | None = None) -> np.ndarray:
    """Quad để VẼ lên màn hình.

    Ưu tiên 4 góc decoder trả về (khớp QR chính xác). Chưa đọc được → hình chữ nhật xoay nhỏ nhất bao
    mask: padded quad của qrdet khớp trên mask thô (~8×8 điểm cho QR 60px) nên hay thành hình diều /
    to hơn QR. Không có mask → bbox.
    """
    if corners is not None:
        return np.asarray(corners, np.float32)
    poly = detection.polygon_xy
    if poly is not None and len(poly) >= 3:
        return cv2.boxPoints(cv2.minAreaRect(np.asarray(poly, np.float32))).astype(np.float32)
    x1, y1, x2, y2 = (float(v) for v in detection.bbox_xyxy)
    return np.array([[x1, y1], [x2, y1], [x2, y2], [x1, y2]], np.float32)
