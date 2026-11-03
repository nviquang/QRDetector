"""Mô phỏng tỉ lệ decode theo px/ô và mờ chuyển động — thử thuật toán không cần quay video.

Chạy:
  python tools/sim_qr.py                                   # bảng mặc định
  python tools/sim_qr.py --ppm 1.8 2.4 2.8 --motion 0 1 3 5 -n 40
  python tools/sim_qr.py --jpeg 30 --sigma 0.9               # thêm nén JPEG, quang học mềm hơn

QR version 1 (12 chữ số, EC M), xoay ngẫu nhiên, render ở độ phân giải cao rồi thu nhỏ có lệch
subpixel (mô phỏng lấy mẫu sensor). Mờ chuyển động theo trục x (hướng băng chạy). Giải mã bằng đúng
cascade của ImprovePipeline trên Detection dựng từ 4 góc thật (không phụ thuộc YOLO).
"""

from __future__ import annotations

import argparse
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # gốc repo
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import cv2  # noqa: E402
import numpy as np  # noqa: E402

HI = 16          # hệ số render độ phân giải cao
BORDER = 8       # viền trắng (ô) quanh QR — nhãn


def make_modules(text: str) -> np.ndarray:
    import zxingcpp
    bc = zxingcpp.create_barcode(text, zxingcpp.BarcodeFormat.QRCode, ec_level="M")
    return np.array(bc.to_image(scale=1, add_quiet_zones=False))


def render(modules: np.ndarray, ppm: float, angle: float, sigma: float, motion_px: float,
           noise: float, jpeg: int, contrast: tuple[int, int], rng) -> tuple[np.ndarray, np.ndarray]:
    """Trả về (ảnh BGR, quad 4 góc QR float32)."""
    n = modules.shape[0]
    big = cv2.resize(modules, (n * HI, n * HI), interpolation=cv2.INTER_NEAREST).astype(np.float32)
    pad = BORDER * HI
    big = cv2.copyMakeBorder(big, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=255)
    c = big.shape[0] / 2
    rot = cv2.getRotationMatrix2D((c, c), angle, 1.0)
    big = cv2.warpAffine(big, rot, big.shape[::-1], flags=cv2.INTER_LINEAR, borderValue=255)
    corners = np.float32([[pad, pad], [pad + n * HI, pad], [pad + n * HI, pad + n * HI], [pad, pad + n * HI]])
    corners = cv2.transform(corners[None], rot)[0]
    if motion_px > 0:
        length = max(1, int(round(motion_px * HI / ppm)))
        big = cv2.filter2D(big, -1, np.ones((1, length), np.float32) / length)
    out = int(round(big.shape[0] * ppm / HI))
    shift = rng.uniform(0, 1, 2)
    down = np.float32([[ppm / HI, 0, shift[0]], [0, ppm / HI, shift[1]]])
    small = cv2.warpAffine(big, down, (out, out), flags=cv2.INTER_AREA, borderValue=255)
    quad = cv2.transform(corners[None], down)[0]
    if sigma > 0:
        small = cv2.GaussianBlur(small, (0, 0), sigma)
    lo, hi = contrast
    small = lo + small * ((hi - lo) / 255.0) + rng.normal(0, noise, small.shape)
    gray = np.clip(small, 0, 255).astype(np.uint8)
    if jpeg:
        ok, buf = cv2.imencode(".jpg", gray, [cv2.IMWRITE_JPEG_QUALITY, jpeg])
        gray = cv2.imdecode(buf, cv2.IMREAD_GRAYSCALE)
    return np.ascontiguousarray(cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)), quad.astype(np.float32)


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):   # console Windows mặc định cp1252
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--ppm", type=float, nargs="+", default=[1.5, 1.8, 2.4, 2.8, 3.6])
    p.add_argument("--motion", type=float, nargs="+", default=[0, 1, 3, 5], help="vệt mờ ngang (px)")
    p.add_argument("--sigma", type=float, default=0.6, help="mờ quang học Gaussian (px)")
    p.add_argument("--noise", type=float, default=4.0)
    p.add_argument("--jpeg", type=int, default=0, help="chất lượng JPEG (0 = không nén)")
    p.add_argument("--contrast", type=int, nargs=2, default=[40, 210], help="mức đen / trắng")
    p.add_argument("-n", type=int, default=30, help="số mẫu mỗi ô bảng")
    p.add_argument("--seed", type=int, default=0)
    a = p.parse_args(argv)

    from qr import Detection, ImprovePipeline
    pipe = ImprovePipeline()
    rng = np.random.default_rng(a.seed)

    print(f"σ={a.sigma} nhiễu={a.noise} jpeg={a.jpeg or 'không'} tương phản={a.contrast[0]}..{a.contrast[1]} n={a.n}")
    print("px/ô  | " + " | ".join(f"mờ {m:g}px" for m in a.motion))
    for ppm in a.ppm:
        cells = []
        for motion in a.motion:
            ok = 0
            for _ in range(a.n):
                text = "%012d" % rng.integers(0, 10 ** 12)
                img, quad = render(make_modules(text), ppm, rng.uniform(0, 360), a.sigma, motion,
                                   a.noise, a.jpeg, tuple(a.contrast), rng)
                x1, y1 = quad.min(axis=0)
                x2, y2 = quad.max(axis=0)
                det = Detection(np.float32([x1, y1, x2, y2]), quad, 1.0)
                hit = pipe.decode_detection(img, det)
                ok += hit is not None and hit.text == text
            cells.append(f"{100 * ok // a.n:>6d}%")
        print(f"{ppm:4.1f}  | " + " | ".join(cells), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
