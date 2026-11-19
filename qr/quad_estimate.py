"""Ước lượng tứ giác QR từ ảnh khi bộ phát hiện chỉ trả hộp thẳng (YOLO detect, không có mask).

Vùng QR là vùng có kết cấu dày (ô đen/trắng xen kẽ), nền kính/tem đồng đều thì không: lấy độ lớn Laplacian, làm mượt
theo cỡ vài ô, phân ngưỡng Otsu, giữ vùng liên thông chứa tâm hộp rồi ``minAreaRect``. Không ra hình hợp lý thì trả
hình chữ nhật của hộp. Quad dùng cho warp, cho mẫu finder của bộ giải B và để vẽ.
"""

from __future__ import annotations

import cv2
import numpy as np

EXPAND = 0.25          # nới hộp khi cắt vùng tìm, theo cạnh hộp
PAD = 1.06             # quad "đệm" cho warp: phóng quanh tâm để chắc bao trọn mã
AREA_RANGE = (0.45, 1.6)   # diện tích quad / diện tích hộp được chấp nhận


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


def estimate_quad(gray: np.ndarray, bbox) -> np.ndarray:
    """4 góc QR (tọa độ ``gray``), thứ tự vòng kim đồng hồ; hộp thẳng nếu không ước lượng được."""
    x1, y1, x2, y2 = (float(v) for v in bbox)
    w, h = x2 - x1, y2 - y1
    if w <= 4 or h <= 4:
        return bbox_quad(bbox)
    H, W = gray.shape[:2]
    ex, ey = EXPAND * w, EXPAND * h
    ax, ay = int(max(0, np.floor(x1 - ex))), int(max(0, np.floor(y1 - ey)))
    bx, by = int(min(W, np.ceil(x2 + ex))), int(min(H, np.ceil(y2 + ey)))
    crop = gray[ay:by, ax:bx]
    if crop.size == 0:
        return bbox_quad(bbox)
    if crop.ndim == 3:
        crop = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    side = max(w, h)
    k = max(3, int(round(side / 12)) | 1)          # khoảng 2 ô ở 25 ô/cạnh
    energy = cv2.blur(np.abs(cv2.Laplacian(np.float32(crop), cv2.CV_32F, ksize=3)), (k, k))
    energy = cv2.normalize(energy, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    _, mask = cv2.threshold(energy, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((k, k), np.uint8))
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
    cx, cy = int((x1 + x2) / 2) - ax, int((y1 + y2) / 2) - ay
    if n <= 1 or not (0 <= cy < labels.shape[0] and 0 <= cx < labels.shape[1]):
        return bbox_quad(bbox)
    lab = labels[cy, cx]
    if lab == 0:                                   # tâm rơi vào lỗ: lấy vùng lớn nhất
        lab = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    ys, xs = np.nonzero(labels == lab)
    rect = cv2.minAreaRect(np.column_stack([xs, ys]).astype(np.float32))
    quad = cv2.boxPoints(rect) + np.array([ax, ay], np.float32)
    area = rect[1][0] * rect[1][1]
    if not (AREA_RANGE[0] * w * h <= area <= AREA_RANGE[1] * w * h):
        return bbox_quad(bbox)
    return _order(quad)
