"""Lượt tem V2-M tổng hợp cho bộ đọc nền B/C: QR 25×25 ô ở ~2,3 px/ô qua mô hình camera đơn giản.

Mỗi frame: render ở độ phân giải cao, xoay + thu về ``ppm`` px/ô với lệch dưới-pixel khác nhau (tem trượt trên băng),
làm mờ Gauss (σ theo hai trục), nhiễu cảm biến, độ tương phản như ảnh buồng tối. Trả ``PassObs`` giống
``qr.pass_fallback.make_obs`` (crop quanh tem, bbox/quad theo tọa độ crop) và ``PassCtx``.
"""
from __future__ import annotations

import cv2
import numpy as np

from qr.pass_fallback import PassCtx, PassObs

HI = 16            # độ phân giải render (px cao / ô)
QUIET = 4          # vùng trống quanh mã (ô)


def modules(text: str, version: int = 2, level: str = "M") -> np.ndarray:
    """Ma trận ô (255 = trắng, 0 = đen), không gồm vùng trống."""
    params = cv2.QRCodeEncoder.Params()
    params.version = version
    params.correction_level = {"L": cv2.QRCodeEncoder_CORRECT_LEVEL_L, "M": cv2.QRCodeEncoder_CORRECT_LEVEL_M,
                               "Q": cv2.QRCodeEncoder_CORRECT_LEVEL_Q, "H": cv2.QRCodeEncoder_CORRECT_LEVEL_H}[level]
    code = cv2.QRCodeEncoder.create(params).encode(text)
    return code[2:-2, 2:-2]                     # OpenCV đệm 2 ô mỗi phía


def _label_image(mods: np.ndarray, label_modules: float) -> np.ndarray:
    n = mods.shape[0]
    big = cv2.resize(mods, (n * HI, n * HI), interpolation=cv2.INTER_NEAREST)
    pad = int(round(label_modules * HI))
    return cv2.copyMakeBorder(big, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=255).astype(np.float32)


def render_frame(mods, ppm, angle_deg, center, shape, sigma=(0.7, 0.7), white=200.0, black=40.0, bg=55.0,
                 noise=2.0, label_modules=QUIET + 2.0, rng=None, canvas=None):
    """Vẽ một tem lên ``canvas`` (float32, tạo mới nếu None). Trả (canvas, 4 góc ký hiệu tl, tr, br, bl)."""
    rng = rng or np.random.default_rng()
    n = mods.shape[0]
    img = _label_image(mods, label_modules)
    h, w = img.shape
    s = ppm / HI
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle_deg, s)
    m[:, 2] += np.asarray(center, np.float64) - np.array([w / 2, h / 2])
    if canvas is None:
        canvas = np.full(shape, bg, np.float32)
    mask = cv2.warpAffine(np.ones_like(img), m, (shape[1], shape[0]), flags=cv2.INTER_AREA)
    tem = cv2.warpAffine(img, m, (shape[1], shape[0]), flags=cv2.INTER_AREA)
    tem = black + (white - black) * tem / 255.0
    canvas = canvas * (1 - mask) + tem * mask
    pad = label_modules * HI
    sym = np.array([[pad, pad], [pad + n * HI, pad], [pad + n * HI, pad + n * HI], [pad, pad + n * HI]], np.float64)
    corners = (m[:, :2] @ sym.T).T + m[:, 2]
    return canvas, corners.astype(np.float32)


def finish(canvas, sigma=(0.7, 0.7), noise=2.0, rng=None) -> np.ndarray:
    rng = rng or np.random.default_rng()
    sx, sy = sigma
    out = cv2.GaussianBlur(canvas, (0, 0), sigmaX=max(sx, 1e-3), sigmaY=max(sy, 1e-3))
    out = out + rng.normal(0.0, noise, out.shape)
    return np.clip(out, 0, 255).astype(np.uint8)


def make_obs(gray, corners, frame, t, pad_factor=1.06) -> PassObs:
    """PassObs như ``pass_fallback.make_obs``: crop quanh hộp của ký hiệu, quad/bbox theo tọa độ crop."""
    x1, y1 = corners.min(axis=0)
    x2, y2 = corners.max(axis=0)
    m = max(45.0, 0.8 * max(x2 - x1, y2 - y1))
    h, w = gray.shape
    cx1, cy1, cx2, cy2 = int(max(0, x1 - m)), int(max(0, y1 - m)), int(min(w, x2 + m)), int(min(h, y2 + m))
    origin = np.array([cx1, cy1], np.float32)
    c = corners.mean(axis=0)
    quad = (corners - c) * pad_factor + c - origin
    return PassObs(gray[cy1:cy2, cx1:cx2].copy(), np.array([x1, y1, x2, y2], np.float32) - np.r_[origin, origin],
                   quad.astype(np.float32), (corners - origin).astype(np.float32), 0.9, origin, frame, t)


def make_pass(text="000000585545#000000001612", k=8, ppm=2.3, angle=17.0, sigma=(0.7, 0.7), noise=2.0,
              version=2, level="M", speed_px=15.0, seed=0, neighbor=None, white=200.0, black=40.0):
    """k frame của một lượt; tem trượt theo trục y ``speed_px`` px/frame cộng lệch dưới-pixel ngẫu nhiên.

    neighbor: (text, (dx, dy) tâm so với tem chính theo px) — tem thứ hai lọt một phần vào crop."""
    rng = np.random.default_rng(seed)
    mods = modules(text, version, level)
    other = modules(neighbor[0], version, level) if neighbor else None
    shape = (600, 600)
    obs = []
    for i in range(k):
        center = np.array([300.0, 150.0 + speed_px * i]) + rng.uniform(-0.5, 0.5, 2)
        canvas, corners = render_frame(mods, ppm, angle, center, shape, sigma, white, black, rng=rng)
        if other is not None:
            canvas, _ = render_frame(other, ppm, angle, center + np.asarray(neighbor[1]), shape, sigma, white, black,
                                     rng=rng, canvas=canvas)
        gray = finish(canvas, sigma, noise, rng)
        obs.append(make_obs(gray, corners, i, i / 15.0))
    ctx = PassCtx(velocity=(0.0, speed_px), fps=15.0, exposure_ms=2.0, blur_px=speed_px * 15.0 * 0.002)
    return obs, ctx


def blank_pass(k=8, seed=0, size=150):
    """Crop chỉ có nhiễu và nền tem trắng không mã: bộ giải phải trả None."""
    rng = np.random.default_rng(seed)
    obs = []
    for i in range(k):
        gray = np.clip(rng.normal(120, 40, (size, size)), 0, 255).astype(np.uint8)
        q = np.array([[45, 45], [105, 45], [105, 105], [45, 105]], np.float32)
        obs.append(PassObs(gray, np.array([45, 45, 105, 105], np.float32), q, q.copy(), 0.9,
                           np.zeros(2, np.float32), i, i / 15.0))
    return obs, PassCtx((0.0, 15.0), 15.0, 2.0, 0.45)
