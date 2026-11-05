"""Tem thật đã nắn phẳng: chịu được bao nhiêu vệt mờ dọc băng ở từng mức sáng?

Mỗi frame thử 19 phép nắn đã đọc được (flatten_tem.py). Vệt mờ là mô phỏng trên frame thật, nên nhiễu bị giảm nhẹ so với thực tế.
"""
import sys

sys.argv = ["flatten_tem.py"]
import importlib.util  # noqa: E402
import os  # noqa: E402

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))
sys.stdout.reconfigure(encoding="utf-8")
import torch  # noqa: F401,E402
import cv2  # noqa: E402
import numpy as np  # noqa: E402

src = open(os.path.join(_HERE, "flatten_tem.py"), encoding="utf-8").read().split('mean = np.uint8(np.mean(roi_of("g06_e16"')[0]
ns: dict = {"__file__": os.path.join(_HERE, "flatten_tem.py")}
exec(compile(src, "flatten_head", "exec"), ns)
flatten, read, roi_of, BOXES = ns["flatten"], ns["read"], ns["roi_of"], ns["BOXES"]

CODE = "000000585545"
mean = np.uint8(np.mean(roi_of("g06_e16", BOXES["T2"]), axis=0))
warps = []
for angle in np.arange(-10, 10.1, 1.0):
    for sy in np.arange(0.70, 1.051, 0.03):
        for a in np.arange(-0.6, 0.61, 0.1):
            if read(flatten(mean, float(a), float(sy), float(angle))) == CODE:
                warps.append((float(a), float(sy), float(angle)))
print("số phép nắn", len(warps), flush=True)


def motion(img, length):
    if length <= 0:
        return img
    n = int(np.ceil(length))
    k = np.ones((n, 1), np.float32)
    k[-1, 0] = length - (n - 1)
    return cv2.filter2D(img, -1, k / k.sum(), borderType=cv2.BORDER_REPLICATE)


def ok(img):
    return any(read(flatten(img, *w)) == CODE for w in warps)


print("gain exp | vệt mờ px: 0 1 2 3 4 (frame đơn /16; xếp 8 ảnh ở hai bộ /2)")
for folder in ("g06_e04", "g06_e08", "g06_e16", "g06_e23", "g12_e02", "g12_e04", "g12_e08", "g12_e12",
               "g18_e01", "g18_e02", "g18_e04", "g18_e06"):
    rois = roi_of(folder, BOXES["T2"])
    cells = []
    for blur in (0, 1, 2, 3, 4):
        single = sum(ok(motion(r, blur)) for r in rois)
        stack = sum(ok(motion(np.uint8(np.mean(part, axis=0)), blur)) for part in (rois[:8], rois[8:16]))
        cells.append(f"{single:>2}/{stack}")
    print(folder, " ".join(cells), flush=True)
