"""Quét độ tối/nhiễu/vệt mờ trên ảnh camera thật, không phụ thuộc YOLO và thời gian: đọc được đến đâu?"""
import glob
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [_ROOT, os.path.dirname(os.path.abspath(__file__))]
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
import torch  # noqa: F401,E402
import cv2  # noqa: E402
import numpy as np  # noqa: E402

from lab_reader import _w, _z, stack_rois, wiener_motion  # noqa: E402
from qr.detector import QRDetector  # noqa: E402
from qr.improved_pipeline import ImprovePipeline  # noqa: E402
from qr.preprocessor import clahe, stretch_contrast, upscale_gray  # noqa: E402
import logging  # noqa: E402

logging.disable(logging.INFO)
det = QRDetector(conf_th=0.3, imgsz=1280, device="auto")
pipe = ImprovePipeline(detector=det)
items = []
for path in sorted(glob.glob("C:/Users/nviquang/Documents/AISTDR/QRDetector-research/data/images/*.bmp")):
    gray = cv2.imread(path, 0)
    bgr = np.ascontiguousarray(cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR))
    for d in det.detect(bgr):
        hit = pipe.decode_detection(bgr, d)
        if hit:
            x1, y1, x2, y2 = (float(v) for v in d.bbox_xyxy)
            cx, cy, s = (x1 + x2) / 2, (y1 + y2) / 2, max(x2 - x1, y2 - y1)
            r = int(s * 0.9)
            pad = r + 30
            big = np.float32(gray[int(cy) - pad:int(cy) + pad, int(cx) - pad:int(cx) + pad])
            white = max(float(np.percentile(gray[int(cy) - int(s):int(cy) + int(s), int(cx) - int(s):int(cx) + int(s)], 97)), 30.0)
            items.append(dict(big=big, text=hit.text, r=r, pad=pad, white=white, size=s))
print("ảnh", len(items), "QR px", [round(i["size"]) for i in items], "trắng", [round(i["white"]) for i in items])


def render(item, blur, lo, hi, noise, rng, sub):
    M = np.float32([[1, 0, sub[0]], [0, 1, sub[1]]])
    img = cv2.warpAffine(item["big"], M, item["big"].shape[::-1], flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    if blur > 1:
        n = int(np.ceil(blur))
        k = np.ones((1, n), np.float32)
        k[0, -1] = blur - (n - 1)
        img = cv2.filter2D(img, -1, k / k.sum(), borderType=cv2.BORDER_REPLICATE)
    img = lo + np.clip(img * 255.0 / item["white"], 0, 255) * ((hi - lo) / 255.0)
    sig = noise * np.sqrt(0.5 + 0.5 * np.clip(img, 0, None) / max(hi, 1))
    nz = cv2.GaussianBlur(rng.standard_normal(img.shape, dtype=np.float32), (0, 0), 0.7)
    nz /= max(float(nz.std()), 1e-6)
    g = np.clip(img + nz * sig, 0, 255).astype(np.uint8)
    p, r = item["pad"], item["r"]
    return g[p - r:p + r, p - r:p + r]


def single(g):
    return _z(upscale_gray(g, 4)) or _w(upscale_gray(clahe(g), 4), False) or _w(upscale_gray(stretch_contrast(g), 4), True) or _w(upscale_gray(g, 3), True)


rng = np.random.default_rng(5)
print("trắng nhiễu mờ | từng frame | xếp 4 | xếp 8 | xếp 8+Wiener")
for hi, noise in ((120, 3), (120, 6), (75, 3), (75, 7), (47, 3), (47, 8), (33, 3), (33, 6)):
    for blur in (0, 3, 6):
        n = s_ok = s4 = s8 = sw = 0
        for item in items:
            n += 1
            frames = [render(item, blur, 8 if hi < 60 else 10, hi, noise, rng, rng.uniform(-3, 3, 2)) for _ in range(8)]
            s_ok += single(frames[0]) == item["text"]
            a4, a8 = stack_rois(frames[:4]), stack_rois(frames)
            pad = lambda g: cv2.copyMakeBorder(g, 64, 64, 64, 64, cv2.BORDER_REPLICATE)  # noqa: E731
            s4 += (_z(pad(a4)) or _w(pad(a4), True)) == item["text"]
            s8 += (_z(pad(a8)) or _w(pad(a8), True)) == item["text"]
            got = _z(pad(a8))
            if blur and got != item["text"]:
                for k in (0.05, 0.02, 0.01):
                    got = _z(pad(wiener_motion(a8, blur * 4, 0.0, k)))
                    if got == item["text"]:
                        break
            sw += got == item["text"]
        print(f"{hi:4} {noise:4} {blur:3} | {s_ok:2}/{n} | {s4:2}/{n} | {s8:2}/{n} | {sw:2}/{n}", flush=True)
