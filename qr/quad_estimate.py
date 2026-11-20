"""Ước lượng tứ giác QR từ ảnh khi bộ phát hiện chỉ trả hộp thẳng (YOLO detect, không có mask).

Kích thước lấy từ hộp của bộ phát hiện, chỉ góc xoay lấy từ ảnh: cạnh ô QR nằm theo hai hướng vuông góc θ và θ + 90°,
nên hướng gradient trong hộp gom về một góc khi nhân 4 (θ, θ + 90°, θ + 180°, θ + 270° trùng nhau). Hình vuông xoay θ có
hộp thẳng cạnh B thì cạnh thật là B / (|cos θ| + |sin θ|). Cách này ổn định hơn tách vùng kết cấu (vùng đó bị lóa và tem
bên cạnh kéo lệch: đo trên 25 tem thật, cạnh lệch 0,71–1,26 lần so với quad của qrdet). Gradient không có hướng rõ thì trả
hộp thẳng. Quad dùng cho warp, cho mẫu finder của bộ giải B và để vẽ.
"""

from __future__ import annotations

import cv2
import numpy as np

PAD = 1.15             # quad "đệm" cho warp: phóng quanh tâm để chắc bao trọn mã (đo trên 14 frame mẫu: 1,0–1,06 đọc 11/14, 1,12–1,25 đọc 12/14 như qrdet-s)
MIN_COHERENCE = 0.15   # |Σ m² e^{4iφ}| / Σ m²: thấp hơn = không có hướng rõ (nền, mờ hẳn) → hộp thẳng


def bbox_quad(bbox) -> np.ndarray:
    x1, y1, x2, y2 = (float(v) for v in bbox)
    return np.array([[x1, y1], [x2, y1], [x2, y2], [x1, y2]], np.float32)


def _order(pts: np.ndarray) -> np.ndarray:
    """Sắp 4 điểm theo chiều kim đồng hồ bắt đầu từ điểm có x + y nhỏ nhất (góc trên-trái trên ảnh)."""
    c = pts.mean(axis=0)
    ang = np.arctan2(pts[:, 1] - c[1], pts[:, 0] - c[0])
    pts = pts[np.argsort(ang)]
    start = int(np.argmin(pts.sum(axis=1)))
    return np.roll(pts, -start, axis=0).astype(np.float32)


def scale_quad(quad: np.ndarray, factor: float) -> np.ndarray:
    c = quad.mean(axis=0)
    return ((quad - c) * factor + c).astype(np.float32)


def dominant_angle(gray: np.ndarray) -> tuple[float, float]:
    """(θ trong [−45°, 45°) tính bằng radian, độ rõ 0..1) của hướng cạnh chiếm ưu thế, theo modulo 90°."""
    g = np.float32(gray)
    gx = cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3)
    m2 = gx * gx + gy * gy
    phi = np.arctan2(gy, gx)
    c, s, tot = float((m2 * np.cos(4 * phi)).sum()), float((m2 * np.sin(4 * phi)).sum()), float(m2.sum())
    if tot <= 0:
        return 0.0, 0.0
    theta = np.arctan2(s, c) / 4.0
    return float((theta + np.pi / 4) % (np.pi / 2) - np.pi / 4), float(np.hypot(c, s) / tot)


def estimate_quad(gray: np.ndarray, bbox) -> np.ndarray:
    """4 góc QR (tọa độ ``gray``), thứ tự vòng kim đồng hồ; hộp thẳng nếu không ước lượng được góc."""
    x1, y1, x2, y2 = (float(v) for v in bbox)
    w, h = x2 - x1, y2 - y1
    if w <= 4 or h <= 4:
        return bbox_quad(bbox)
    H, W = gray.shape[:2]
    ix1, iy1 = int(max(0, np.floor(x1))), int(max(0, np.floor(y1)))
    ix2, iy2 = int(min(W, np.ceil(x2))), int(min(H, np.ceil(y2)))
    crop = gray[iy1:iy2, ix1:ix2]
    if crop.size == 0:
        return bbox_quad(bbox)
    if crop.ndim == 3:
        crop = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    theta, coherence = dominant_angle(crop)
    if coherence < MIN_COHERENCE:
        return bbox_quad(bbox)
    side = (w + h) / 2 / (abs(np.cos(theta)) + abs(np.sin(theta)))
    rect = (((x1 + x2) / 2, (y1 + y2) / 2), (side, side), float(np.degrees(theta)))
    return _order(cv2.boxPoints(rect).astype(np.float32))
