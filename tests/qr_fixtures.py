"""Ảnh QR tổng hợp và Detection giả cho test — không cần camera hay model YOLO."""

import cv2
import numpy as np

from qr.detector import Detection

_BORDER_MODULES = 2      # QRCodeEncoder của OpenCV đệm 2 ô trắng mỗi phía (25×25 cho QR 21 ô)


_LEVELS = {"L": cv2.QRCodeEncoder_CORRECT_LEVEL_L, "M": cv2.QRCodeEncoder_CORRECT_LEVEL_M,
           "Q": cv2.QRCodeEncoder_CORRECT_LEVEL_Q, "H": cv2.QRCodeEncoder_CORRECT_LEVEL_H}


def qr_image(text: str, scale: int = 4, version: int | None = None, level: str | None = None) -> np.ndarray:
    """QR xám (đã gồm viền trắng của encoder) phóng ``scale`` lần, giữ cạnh sắc.
    version/level: ép version và mức sửa lỗi (ví dụ 2, "M" như tem hiện trường); None = encoder tự chọn."""
    params = cv2.QRCodeEncoder.Params()
    if version is not None:
        params.version = version
    if level is not None:
        params.correction_level = _LEVELS[level]
    code = cv2.QRCodeEncoder.create(params).encode(text)
    return cv2.resize(code, None, fx=scale, fy=scale, interpolation=cv2.INTER_NEAREST)


def symbol_corners(x: int, y: int, text: str = "000000585545", scale: int = 4) -> np.ndarray:
    """4 góc ngoài của ký hiệu QR (không gồm viền trắng) khi đặt qr_image ở góc trái-trên (x, y)."""
    size = qr_image(text, scale).shape[0]
    b = _BORDER_MODULES * scale
    return np.array([[x + b, y + b], [x + size - b, y + b], [x + size - b, y + size - b],
                     [x + b, y + size - b]], np.float32)


def frame_with_qrs(items, shape=(600, 900), scale=4):
    """Frame BGR nền trắng; ``items`` = [(text, (x, y))] với (x, y) là góc trái-trên.

    Trả (frame, detections) — Detection thứ i bao đúng ảnh QR thứ i (quad = polygon = khung ảnh QR).
    """
    frame = np.full((shape[0], shape[1], 3), 255, np.uint8)
    detections = []
    for text, (x, y) in items:
        code = qr_image(text, scale)
        h, w = code.shape
        frame[y:y + h, x:x + w] = code[..., None]
        quad = np.array([[x, y], [x + w, y], [x + w, y + h], [x, y + h]], np.float32)
        detections.append(Detection(bbox_xyxy=np.array([x, y, x + w, y + h], np.float32),
                                    quad_xy=quad, confidence=0.9, polygon_xy=quad.copy()))
    return frame, detections


def detection_at(cx: float, cy: float, size: float = 60.0) -> Detection:
    """Detection vuông cạnh ``size`` tâm (cx, cy) — dùng khi chỉ cần vị trí, không cần ảnh."""
    r = size / 2
    quad = np.array([[cx - r, cy - r], [cx + r, cy - r], [cx + r, cy + r], [cx - r, cy + r]],
                    np.float32)
    return Detection(bbox_xyxy=np.array([cx - r, cy - r, cx + r, cy + r], np.float32),
                     quad_xy=quad, confidence=0.9, polygon_xy=quad.copy())
