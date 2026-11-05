"""Kiểm chứng: tem trên đoạn băng cong đọc được không nếu nắn lại trục dọc?

Tìm phép nắn y' = y + a·(y-yc)² (cộng co giãn dọc) trên ảnh trung bình, rồi dùng đúng phép đó quét các mức exposure/gain.
"""
import glob
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
sys.stdout.reconfigure(encoding="utf-8")

import torch  # noqa: F401,E402
import cv2  # noqa: E402
import numpy as np  # noqa: E402

from qr.decoder import read_zxing_gray, read_wechat_gray  # noqa: E402
from qr.preprocessor import upscale_gray  # noqa: E402

OUT = os.path.join(_ROOT, "experiments", "out", "exposure_f4")
meta = json.load(open(f"{OUT}/meta.json", encoding="utf-8"))
X0, Y0 = meta["crop"][:2]
BOXES = {"T2": [1593, 2475, 1655, 2535]}
m = 26
S = 4


def roi_of(folder, box):
    x1, y1, x2, y2 = box[0] - X0 - m, box[1] - Y0 - m, box[2] - X0 + m, box[3] - Y0 + m
    return [cv2.imread(p, 0)[y1:y2, x1:x2] for p in sorted(glob.glob(f"{OUT}/{folder}/c*.png"))]


def flatten(img, a, sy, angle):
    h, w = img.shape
    up = cv2.resize(img, None, fx=S, fy=S, interpolation=cv2.INTER_CUBIC)
    H, W = up.shape
    yy, xx = np.mgrid[:H, :W].astype(np.float32)
    c = (W / 2, H / 2)
    th = np.deg2rad(angle)
    dx, dy = xx - c[0], yy - c[1]
    rx = dx * np.cos(th) - dy * np.sin(th)
    ry = dx * np.sin(th) + dy * np.cos(th)
    my = c[1] + ry * sy + a * ry * ry / H
    return cv2.copyMakeBorder(cv2.remap(up, np.float32(c[0] + rx), np.float32(my), cv2.INTER_LINEAR), 48, 48, 48, 48, cv2.BORDER_REPLICATE)


def read(img):
    z = read_zxing_gray(img)
    return z[0] if z else None


mean = np.uint8(np.mean(roi_of("g06_e16", BOXES["T2"]), axis=0))
hits = []
for angle in np.arange(-10, 10.1, 1.0):
    for sy in np.arange(0.70, 1.051, 0.03):
        for a in np.arange(-0.6, 0.61, 0.1):
            t = read(flatten(mean, float(a), float(sy), float(angle)))
            if t:
                hits.append((round(float(angle), 1), round(float(sy), 2), round(float(a), 2), t))
print("nắn đọc được", len(hits), "tổ hợp", hits[:6], flush=True)
print("đọc thường:", read(upscale_gray(mean, 4)))
if hits:
    from collections import Counter
    print(Counter(h[3] for h in hits))
    code = Counter(h[3] for h in hits).most_common(1)[0][0]
    best = [h for h in hits if h[3] == code]
    angle, sy, a, _ = best[len(best) // 2]
    print("dùng phép nắn", angle, sy, a)
    rows = []
    for run in meta["runs"]:
        folder = f"g{run['gain']:02d}_e{run['ms']:02d}"
        rois = roi_of(folder, BOXES["T2"])
        ok = sum(read(flatten(r, a, sy, angle)) == code for r in rois)
        stack = np.uint8(np.mean(rois[:8], axis=0))
        ok_s = read(flatten(stack, a, sy, angle)) == code
        rows.append((run["gain"], run["ms"], ok, ok_s))
        print(f"g{run['gain']} e{run['ms']}: frame đơn {ok}/16, xếp 8: {ok_s}", flush=True)
