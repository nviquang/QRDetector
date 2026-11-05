"""So phương pháp đọc khi có vệt mờ ngang (hướng chạy của băng) trên frame thật, tem phẳng và nét.

Vệt mờ là mô phỏng; nhiễu bị vệt mờ làm giảm được bù lại theo mức đo được của từng frame.
python experiments/blur_methods.py f4b
"""
import glob
import json
import os
import sys
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
sys.stdout.reconfigure(encoding="utf-8")

import torch  # noqa: F401,E402
import cv2  # noqa: E402
import numpy as np  # noqa: E402
import zxingcpp  # noqa: E402

from qr.decoder import read_wechat_gray, read_zxing_gray  # noqa: E402
from qr.multiframe import WIENER_K, stack_rois, wiener_motion  # noqa: E402
from qr.preprocessor import clahe, stretch_contrast, upscale_gray  # noqa: E402

RUN = sys.argv[1] if len(sys.argv) > 1 else "f4b"
OUT = os.path.join(_ROOT, "experiments", "out", "exposure_" + RUN)
meta = json.load(open(f"{OUT}/meta.json", encoding="utf-8"))
X0, Y0 = meta["crop"][:2]
# (tâm x, tâm y, mã) theo đợt đo; tem đo được ở analyze_exposure
TEMS = [(731, 1733, "000000585546"), (1550, 1724, "000000585623"), (2035, 1756, "000000585545")]
HALF = 62
LEVELS = ("g06_e04", "g06_e08", "g06_e12", "g06_e16", "g12_e02", "g12_e04", "g12_e06", "g12_e08",
          "g18_e01", "g18_e02", "g18_e03", "g18_e04")
BLURS = (0.0, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0)
rng = np.random.default_rng(3)
pad64 = lambda g: cv2.copyMakeBorder(g, 64, 64, 64, 64, cv2.BORDER_REPLICATE)  # noqa: E731


def text(hit):
    return hit[0] if hit else None


def z(g):
    return text(read_zxing_gray(g))


def w(g, cnn=True):
    return text(read_wechat_gray(g, use_cnn=cnn))


def motion(img, length, noise):
    if length <= 1.0:
        return img
    n = int(np.ceil(length))
    k = np.ones((1, n), np.float32)
    k[0, -1] = length - (n - 1)
    k /= k.sum()
    out = cv2.filter2D(np.float32(img), -1, k, borderType=cv2.BORDER_REPLICATE)
    lost = noise * np.sqrt(max(1.0 - float((k ** 2).sum()), 0.0))
    return np.clip(out + rng.normal(0, lost, out.shape), 0, 255).astype(np.uint8)


def wiener_single(g, length, reader):
    if length < 1.5:
        return None
    up = cv2.resize(g, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    return reader(upscale_gray(wiener_motion(up, length * 2, 0.0, WIENER_K), 2))


def wiener_stack(s, length, k, reader):
    if length < 1.5:
        return None
    return reader(pad64(wiener_motion(s, length * 4, 0.0, k)))


SINGLE = {
    "z4": lambda g, L: z(upscale_gray(g, 4)),
    "z_bin3": lambda g, L: z(upscale_gray(g, 4)) or text(read_zxing_gray(upscale_gray(g, 4), zxingcpp.Binarizer.GlobalHistogram))
                           or text(read_zxing_gray(upscale_gray(g, 4), zxingcpp.Binarizer.FixedThreshold)),
    "w_clahe": lambda g, L: w(upscale_gray(clahe(g), 4), False),
    "w_stretch": lambda g, L: w(upscale_gray(stretch_contrast(g), 4)),
    "w_cnn3": lambda g, L: w(upscale_gray(g, 3)),
    "wiener_z": lambda g, L: wiener_single(g, L, z),
    "wiener_w": lambda g, L: wiener_single(g, L, lambda i: w(i)),
}
STACK = {
    "st_z": lambda s, L: z(pad64(s)),
    "st_w": lambda s, L: w(pad64(s)),
    "st_wiener_z": lambda s, L: wiener_stack(s, L, WIENER_K / 4, z),
    "st_wiener_w": lambda s, L: wiener_stack(s, L, WIENER_K / 4, lambda i: w(i)),
}
# Kết hợp để so sánh: hit bất kỳ trong các bước của mỗi cấu hình
COMBOS = {"cũ (z4,warp,3 WeChat)": ["z4", "w_clahe", "w_stretch", "w_cnn3"],
          "mới hiện tại: frame": ["z_bin3", "wiener_z"],
          "đề xuất: frame": ["z_bin3", "wiener_z", "w_clahe", "w_stretch", "w_cnn3"]}

totals = {}
for tem_i, (cx, cy, code) in enumerate(TEMS):
    for level in LEVELS:
        rois_full = [cv2.imread(p, 0) for p in sorted(glob.glob(f"{OUT}/{level}/c*.png"))]
        rois = [c[cy - HALF - Y0:cy + HALF - Y0, cx - HALF - X0:cx + HALF - X0] for c in rois_full]
        noise = float(np.stack(rois).astype(np.float32).std(axis=0).mean())
        for L in BLURS:
            frames = [motion(r, L, noise) for r in rois]
            frame_ok = {}
            for name, fn in SINGLE.items():
                res = [fn(f, L) == code for f in frames]
                frame_ok[name] = res
                key = (name, L, level)
                a = totals.setdefault(key, [0, 0])
                a[0] += sum(res)
                a[1] += len(res)
            for combo, parts in COMBOS.items():
                res = [any(frame_ok[p][i] for p in parts) for i in range(len(frames))]
                a = totals.setdefault((combo, L, level), [0, 0])
                a[0] += sum(res)
                a[1] += len(res)
            for part in (frames[:4], frames[4:8], frames[8:12], frames[12:16]):
                s = stack_rois(part)
                for name, fn in STACK.items():
                    a = totals.setdefault((name + "_4", L, level), [0, 0])
                    a[0] += fn(s, L) == code
                    a[1] += 1
            for part in (frames[:8], frames[8:16]):
                s = stack_rois(part)
                for name, fn in STACK.items():
                    a = totals.setdefault((name + "_8", L, level), [0, 0])
                    a[0] += fn(s, L) == code
                    a[1] += 1
    print("xong tem", tem_i, flush=True)
with open(f"{OUT}/blur_methods.json", "w", encoding="utf-8") as f:
    json.dump([[*k, *v] for k, v in totals.items()], f, ensure_ascii=False)

names = sorted({k[0] for k in totals})
print(f"{'phương pháp':26}" + "".join(f"{b:>10}" for b in BLURS))
for n in names:
    cells = []
    for b in BLURS:
        rows = [v for k, v in totals.items() if k[0] == n and k[1] == b]
        hit, total = sum(r[0] for r in rows), sum(r[1] for r in rows)
        cells.append(f"{100 * hit / max(total, 1):>9.0f}%")
    print(f"{n:26}" + "".join(cells))
print()
print("theo mức sáng, cấu hình đề xuất: frame")
for level in LEVELS:
    cells = []
    for b in BLURS:
        v = totals[("đề xuất: frame", b, level)]
        cells.append(f"{100 * v[0] / v[1]:>9.0f}%")
    print(f"{level:26}" + "".join(cells))
print("theo mức sáng, xếp chồng 8 + WeChat (cả Wiener)")
for level in LEVELS:
    cells = []
    for b in BLURS:
        a, c = totals[("st_w_8", b, level)], totals[("st_wiener_w_8", b, level)]
        cells.append(f"{50 * (a[0] + c[0]) / a[1]:>9.0f}%")
    print(f"{level:26}" + "".join(cells))
