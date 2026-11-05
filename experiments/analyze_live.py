"""Đo trên frame thật của experiments/capture_basler.py: kích thước QR, tương phản, nhiễu, độ nét, đọc được đến đâu."""
import glob
import os
import sys
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
sys.stdout.reconfigure(encoding="utf-8")

import torch  # noqa: F401,E402
import cv2  # noqa: E402
import numpy as np  # noqa: E402
import logging  # noqa: E402

from qr.detector import QRDetector  # noqa: E402
from qr.improved_pipeline import ImprovePipeline  # noqa: E402
from qr.multiframe import PassDecoder, square_roi, stack_rois  # noqa: E402
from qr.tracker import Track  # noqa: E402
from qr.decoder import read_zxing_gray, read_wechat_gray  # noqa: E402

logging.disable(logging.INFO)
OUT = os.path.join(_ROOT, "experiments", "out", "basler_live")
paths = sorted(glob.glob(os.path.join(OUT, "0*.png")))
grays = [cv2.imread(p, 0) for p in paths]
frames = [np.ascontiguousarray(cv2.cvtColor(g, cv2.COLOR_GRAY2BGR)) for g in grays]
print("frame", len(frames), grays[0].shape, "sáng TB", round(float(grays[0].mean()), 1),
      "p1/p50/p99", np.percentile(grays[0], (1, 50, 99)).tolist(), "cháy %", round(float((grays[0] >= 250).mean()) * 100, 2))

det = QRDetector(conf_th=0.3, imgsz=1280, device="auto")
pipe = ImprovePipeline(detector=det)
ms = []
for f in frames[:6]:
    t = time.perf_counter()
    dets = det.detect(f)
    ms.append((time.perf_counter() - t) * 1000)
print("detect ms", [round(m) for m in ms], "số QR", len(dets))

small = cv2.resize(grays[0], None, fx=0.4, fy=0.4, interpolation=cv2.INTER_AREA)
vis = cv2.cvtColor(np.clip(small.astype(np.float32) * 2.5, 0, 255).astype(np.uint8), cv2.COLOR_GRAY2BGR)
crops = []
for i, d in enumerate(sorted(dets, key=lambda d: float(d.bbox_xyxy[0]))):
    x1, y1, x2, y2 = (float(v) for v in d.bbox_xyxy)
    side = max(x2 - x1, y2 - y1)
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    r = int(side * 0.5)
    stack_in = np.stack([g[int(cy) - r:int(cy) + r, int(cx) - r:int(cx) + r] for g in grays[:20]]).astype(np.float32)
    patch = stack_in[0]
    temporal_noise = float(stack_in.std(axis=0).mean())
    mean_patch = stack_in.mean(axis=0)
    lo, hi = np.percentile(mean_patch, (2, 98))
    grad = cv2.Sobel(cv2.GaussianBlur(mean_patch, (0, 0), 0.6), cv2.CV_32F, 1, 0, ksize=3) / 8
    edge_px = (hi - lo) / max(float(np.percentile(np.abs(grad), 99.5)), 1e-3)
    t = time.perf_counter()
    old = pipe.decode_detection(frames[0], d)
    old_ms = (time.perf_counter() - t) * 1000
    dec = PassDecoder(None)
    t = time.perf_counter()
    new = dec.read(frames[0], d.bbox_xyxy, d, None, [])
    new_ms = (time.perf_counter() - t) * 1000
    old_n = sum(bool(pipe.decode_detection(f, d)) for f in frames[:12])
    new_n = sum(bool(PassDecoder(None).read(f, d.bbox_xyxy, d, None, [])) for f in frames[:12])
    rois = [square_roi(f, d.bbox_xyxy)[0] for f in frames[:8]]
    t = time.perf_counter()
    st = stack_rois(rois)
    pad = cv2.copyMakeBorder(st, 64, 64, 64, 64, cv2.BORDER_REPLICATE)
    z = read_zxing_gray(pad)
    z_ms = (time.perf_counter() - t) * 1000
    t = time.perf_counter()
    w = read_wechat_gray(pad, use_cnn=True)
    w_ms = (time.perf_counter() - t) * 1000
    print(f"QR{i} x={cx:.0f} y={cy:.0f} cỡ={side:.0f}px conf={d.confidence:.2f} đen/trắng={lo:.0f}/{hi:.0f} nhiễu={temporal_noise:.1f} "
          f"biên={edge_px:.1f}px | cũ: {old.text if old else None} {old_ms:.0f}ms {old_n}/12 frame | "
          f"mới 1 frame: {new.text if new else None} {new_ms:.0f}ms {new_n}/12 | "
          f"xếp 8: zxing={z[0] if z else None} {z_ms:.0f}ms wechat={w[0] if w else None} {w_ms:.0f}ms")
    show = cv2.resize(np.uint8(np.clip((mean_patch - lo) * 255 / max(hi - lo, 1), 0, 255)), (360, 360), interpolation=cv2.INTER_NEAREST)
    raw = cv2.resize(np.uint8(np.clip((patch - lo) * 255 / max(hi - lo, 1), 0, 255)), (360, 360), interpolation=cv2.INTER_NEAREST)
    stk = cv2.resize(st, (360, 360), interpolation=cv2.INTER_AREA)
    crops.append(np.hstack([raw, show, stk]))
    cv2.rectangle(vis, (int(x1 * .4), int(y1 * .4)), (int(x2 * .4), int(y2 * .4)), (0, 255, 0), 2)
    cv2.putText(vis, f"QR{i}", (int(x1 * .4), int(y1 * .4) - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
cv2.imwrite(os.path.join(OUT, "view.jpg"), vis)
if crops:
    cv2.imwrite(os.path.join(OUT, "crops.png"), np.vstack(crops))
