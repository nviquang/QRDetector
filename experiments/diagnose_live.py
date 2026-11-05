"""Kiểm chứng nguyên nhân QR tĩnh không đọc được trên frame thật Basler (experiments/capture_basler.py)."""
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
from qr.multiframe import square_roi, stack_rois  # noqa: E402
from qr.pass_reader import PassReader  # noqa: E402
from qr.tracker import PassTracker  # noqa: E402
from qr.decoder import read_zxing_gray, read_wechat_gray  # noqa: E402

logging.disable(logging.INFO)
OUT = os.path.join(_ROOT, "experiments", "out", "basler_live")
grays = [cv2.imread(p, 0) for p in sorted(glob.glob(os.path.join(OUT, "0*.png")))]
frames = [np.ascontiguousarray(cv2.cvtColor(g, cv2.COLOR_GRAY2BGR)) for g in grays]
det = QRDetector(conf_th=0.3, imgsz=1280, device="auto")
det.detect(frames[0])
dets = sorted(det.detect(frames[0]), key=lambda d: float(d.bbox_xyxy[1]))
pad = lambda g: cv2.copyMakeBorder(g, 64, 64, 64, 64, cv2.BORDER_REPLICATE)  # noqa: E731


def read_any(img):
    z = read_zxing_gray(pad(img))
    if z:
        return z[0]
    w = read_wechat_gray(pad(img), use_cnn=True)
    return w[0] if w else None


def norm(a):
    lo, hi = np.percentile(a, (1, 99))
    return np.uint8(np.clip((a - lo) * 255 / max(hi - lo, 1), 0, 255))


stacks = []
print("== 1. độ nét theo vị trí (Laplacian chuẩn hóa theo tương phản, ảnh trung bình 20 frame)")
for i, d in enumerate(dets):
    x1, y1, x2, y2 = (int(v) for v in d.bbox_xyxy)
    m = np.mean([g[y1:y2, x1:x2] for g in grays[:20]], axis=0).astype(np.float32)
    lo, hi = np.percentile(m, (2, 98))
    n = np.float32((m - lo) / max(hi - lo, 1))
    fft = np.abs(np.fft.fftshift(np.fft.fft2((n - n.mean()) * np.outer(np.hanning(n.shape[0]), np.hanning(n.shape[1])))))
    h, w = n.shape
    yy, xx = np.mgrid[:h, :w]
    rad = np.hypot((yy - h / 2) / h, (xx - w / 2) / w)
    module_f = (21 / max(h, w)) / 2       # tần số Nyquist của lưới ô
    hi_energy = float(fft[(rad > module_f * 0.8) & (rad < module_f * 1.2)].mean() / fft[(rad > 0.02) & (rad < module_f * 0.5)].mean())
    print(f"QR{i} y={(y1 + y2) // 2} cỡ={max(x2 - x1, y2 - y1)} Lap={cv2.Laplacian(n, cv2.CV_32F).var():.4f} năng lượng tại tần số ô={hi_energy:.3f}")
    rois = [square_roi(f, d.bbox_xyxy)[0] for f in frames[:8]]
    stacks.append(stack_rois(rois))

print("== 2. làm mờ dần QR đọc được: mờ bao nhiêu thì hết đọc (không đổi nhiễu, đọc 1 frame)")
d0 = dets[0]
roi0 = square_roi(frames[0], d0.bbox_xyxy)[0]
for sigma in (0, 0.5, 0.8, 1.0, 1.2, 1.5, 2.0):
    blurred = cv2.GaussianBlur(roi0, (0, 0), sigma) if sigma else roi0
    up = cv2.resize(blurred, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
    print(f"sigma={sigma}: {read_any(up)}")

print("== 3. xếp chồng + khử mờ tròn (defocus) trên hai QR không đọc được")


def deconv(img, sigma, k):
    h, w = img.shape
    r = int(np.ceil(sigma * 3))
    g1 = cv2.getGaussianKernel(2 * r + 1, sigma)
    psf = np.zeros((h, w), np.float32)
    psf[:2 * r + 1, :2 * r + 1] = g1 @ g1.T
    psf = np.roll(psf, (-r, -r), axis=(0, 1))
    F = np.fft.rfft2(np.float32(img) - float(img.mean()))
    H = np.fft.rfft2(psf)
    out = np.fft.irfft2(F * np.conj(H) / (np.abs(H) ** 2 + k), s=(h, w)) + float(img.mean())
    return np.clip(out, 0, 255).astype(np.uint8)


for i, st in enumerate(stacks):
    plain = read_any(st)
    hits = []
    for sigma_px in (0.6, 0.8, 1.0, 1.2, 1.5, 1.8, 2.2):
        for k in (0.003, 0.01, 0.03):
            t = read_any(deconv(st, sigma_px * 4, k))
            if t:
                hits.append((sigma_px, k, t))
    print(f"QR{i}: xếp chồng thường={plain}; khử defocus đọc được ở {len(hits)}/21 tổ hợp {hits[:3]}")

print("== 4. tốc độ detect toàn khung và cắt quanh băng")
ys = [float(v) for d in dets for v in d.bbox_xyxy[[1, 3]]]
xs = [float(v) for d in dets for v in d.bbox_xyxy[[0, 2]]]
x0, x1, y0, y1 = int(min(xs)) - 150, int(max(xs)) + 250, int(min(ys)) - 200, int(max(ys)) + 200
print("vùng băng", x0, x1, y0, y1, "=", round((x1 - x0) * (y1 - y0) / (2856 * 2848) * 100, 1), "% khung")
for name, img in (("toàn khung", frames[0]), ("cắt băng", np.ascontiguousarray(frames[0][y0:y1, x0:x1]))):
    ms = []
    for _ in range(6):
        t = time.perf_counter()
        n = len(det.detect(img))
        ms.append((time.perf_counter() - t) * 1000)
    print(f"{name} {img.shape[:2]}: {np.median(ms):.0f} ms, {n} QR")

print("== 5. phát lại 40 frame qua PassReader: cũ và mới")
for name, flag in (("cũ", False), ("mới", True)):
    pipe = ImprovePipeline(detector=det, multi_frame=flag)
    reader = PassReader(pipe)
    t0 = time.perf_counter()
    texts, firsts, jobs, detect_ms, cascade_ms = set(), {}, 0, 0.0, 0.0
    for idx, f in enumerate(frames):
        r = reader.process(f, idx * 5)
        jobs += 1
        detect_ms += r.detect_ms
        cascade_ms += r.cascade_ms
        for tr in r.first_reads:
            firsts.setdefault(tr.text, round(time.perf_counter() - t0, 2))
    reader.flush()
    print(f"{name}: đọc được {firsts}, {jobs} job, detect {detect_ms:.0f} ms, cascade {cascade_ms:.0f} ms, tổng {time.perf_counter() - t0:.1f} s")
