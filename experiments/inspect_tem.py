"""Vì sao tem nét vẫn không đọc được: phóng ảnh trung bình, lấy lưới ô, thử nhiều bộ đọc."""
import glob
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [_ROOT, os.path.dirname(os.path.abspath(__file__))]
sys.stdout.reconfigure(encoding="utf-8")

import torch  # noqa: F401,E402
import cv2  # noqa: E402
import numpy as np  # noqa: E402
import zxingcpp  # noqa: E402
from pyzbar import pyzbar  # noqa: E402

from lab_reader import _PAT, _MASK, decode_modules, pose_search, refine_quad  # noqa: E402

OUT = os.path.join(_ROOT, "experiments", "out", "exposure_f4")
S = sys.argv[1] if len(sys.argv) > 1 else "g06_e16"
BOX = [1593, 2475, 1655, 2535]
files = sorted(glob.glob(f"{OUT}/{S}/c*.png"))
X0, Y0 = 812, 704
frames = [cv2.imread(p, 0) for p in files]
m = 26
x1, y1, x2, y2 = BOX[0] - X0 - m, BOX[1] - Y0 - m, BOX[2] - X0 + m, BOX[3] - Y0 + m
mean = np.mean([f[y1:y2, x1:x2] for f in frames], axis=0).astype(np.float32)
print("ROI", mean.shape, "đen/trắng", np.percentile(mean, (3, 97)).round(1).tolist())
g8 = np.uint8(np.clip(mean, 0, 255))
stretched = cv2.normalize(mean, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)


def attempts(img):
    out = {}
    for scale in (1, 2, 3, 4, 6, 8):
        for interp, iname in ((cv2.INTER_CUBIC, "cubic"), (cv2.INTER_LANCZOS4, "lanczos")):
            up = cv2.resize(img, None, fx=scale, fy=scale, interpolation=interp)
            up = cv2.copyMakeBorder(up, 16 * scale, 16 * scale, 16 * scale, 16 * scale, cv2.BORDER_REPLICATE)
            for bin_name in ("LocalAverage", "GlobalHistogram", "FixedThreshold", "BoolCast"):
                for b in zxingcpp.read_barcodes(up, formats=zxingcpp.BarcodeFormat.QRCode, binarizer=getattr(zxingcpp.Binarizer, bin_name), return_errors=True):
                    key = f"zxing {b.valid} {b.text!r} {b.error}"
                    out[key] = out.get(key, 0) + 1
            for z in pyzbar.decode(up):
                key = f"pyzbar {z.data!r}"
                out[key] = out.get(key, 0) + 1
    return out


for name, img in (("trung bình", g8), ("giãn", stretched)):
    print(name, attempts(img))

found = pose_search(g8)
print("pose", None if found is None else (round(float(found[1]), 3), found[2], found[3]))
values, score, quad = refine_quad(cv2.resize(g8, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC), found[0] * 3, 3)
print("độ khớp mẫu cố định", round(score, 3), "4 góc", (quad / 3).round(1).tolist())
print("decode_modules", decode_modules(values))
dark = float(np.median(values[_MASK & (_PAT == 0)]))
light = float(np.median(values[_MASK & (_PAT == 1)]))
print("đen/trắng tại ô cố định", round(dark, 1), round(light, 1))
n = (values - dark) / max(light - dark, 1)
print("ô cố định sai:", int((((n > 0.5) != (_PAT > 0.5)) & _MASK).sum()), "/", int(_MASK.sum()))
print("ô dữ liệu lưng chừng (0,35–0,65):", int((((n > 0.35) & (n < 0.65)) & ~_MASK).sum()), "/", int((~_MASK).sum()))
print("\n".join("".join("#" if v < 0.5 else "." for v in row) for row in n))
big = cv2.resize(stretched, None, fx=8, fy=8, interpolation=cv2.INTER_CUBIC)
cv2.imwrite(f"{OUT}/tem2_big.png", big)
grid = cv2.resize(np.uint8((n > 0.5) * 255), None, fx=16, fy=16, interpolation=cv2.INTER_NEAREST)
cv2.imwrite(f"{OUT}/tem2_grid.png", grid)
