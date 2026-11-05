"""Phân tích đợt sweep_exposure: mỗi mức exposure/gain, mỗi tem, mỗi phương pháp đọc được bao nhiêu frame.

python experiments/analyze_exposure.py f4 ; kết quả: experiments/out/exposure_f4/results.jsonl
"""
import glob
import json
import os
import sys
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [_ROOT, os.path.dirname(os.path.abspath(__file__))]
sys.stdout.reconfigure(encoding="utf-8")

import torch  # noqa: F401,E402
import cv2  # noqa: E402
import numpy as np  # noqa: E402
import zxingcpp  # noqa: E402
import logging  # noqa: E402

from qr.corrector import add_quiet_zone, warp_qr  # noqa: E402
from qr.decoder import read_wechat_gray, read_zxing_gray  # noqa: E402
from qr.detector import QRDetector  # noqa: E402
from qr.multiframe import stack_rois  # noqa: E402
from qr.preprocessor import clahe, stretch_contrast, upscale_gray  # noqa: E402
from lab_reader import decode_modules, sample_modules  # noqa: E402

logging.disable(logging.INFO)
RUN = sys.argv[1] if len(sys.argv) > 1 else "f4"
OUT = os.path.join(_ROOT, "experiments", "out", "exposure_" + RUN)
meta = json.load(open(os.path.join(OUT, "meta.json"), encoding="utf-8"))
X0, Y0, X1, Y1 = meta["crop"]
det = QRDetector(conf_th=0.15, imgsz=1280, device="auto")
pad64 = lambda g: cv2.copyMakeBorder(g, 64, 64, 64, 64, cv2.BORDER_REPLICATE)  # noqa: E731


def text(hit):
    return hit[0] if hit else None


def z(g):
    return text(read_zxing_gray(g))


def w(g, cnn=True):
    return text(read_wechat_gray(g, use_cnn=cnn))


def gauss_deconv(img, sigma, k):
    h, wd = img.shape
    r = int(np.ceil(sigma * 3))
    g1 = cv2.getGaussianKernel(2 * r + 1, sigma)
    psf = np.zeros((h, wd), np.float32)
    psf[:2 * r + 1, :2 * r + 1] = g1 @ g1.T
    psf = np.roll(psf, (-r, -r), axis=(0, 1))
    mean = float(img.mean())
    F = np.fft.rfft2(np.float32(img) - mean)
    H = np.fft.rfft2(psf)
    return np.clip(np.fft.irfft2(F * np.conj(H) / (np.abs(H) ** 2 + k), s=(h, wd)) + mean, 0, 255).astype(np.uint8)


def unsharp(img, sigma, amount):
    b = cv2.GaussianBlur(img, (0, 0), sigma)
    return np.clip(np.float32(img) * (1 + amount) - np.float32(b) * amount, 0, 255).astype(np.uint8)


# Phương pháp trên MỘT frame: (ROI xám, ROI vuông xám) → nội dung
SINGLE = {
    "z4": lambda g: z(upscale_gray(g, 4)),
    "z4_hist": lambda g: text(read_zxing_gray(upscale_gray(g, 4), zxingcpp.Binarizer.GlobalHistogram)),
    "z4_fixed": lambda g: text(read_zxing_gray(upscale_gray(g, 4), zxingcpp.Binarizer.FixedThreshold)),
    "w_clahe": lambda g: w(upscale_gray(clahe(g), 4), False),
    "w_cnn_stretch": lambda g: w(upscale_gray(stretch_contrast(g), 4)),
    "w_cnn3": lambda g: w(upscale_gray(g, 3)),
    "z_unsharp": lambda g: z(upscale_gray(unsharp(g, 1.2, 1.5), 4)),
    "w_unsharp": lambda g: w(upscale_gray(unsharp(g, 1.2, 1.5), 4)),
    "z_deconv": lambda g: z(pad64(gauss_deconv(cv2.resize(g, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC), 4.0, 0.02))),
}
# Phương pháp trên ảnh xếp chồng 8 frame (ảnh đã phóng 4 lần)
STACKED = {
    "st_z": lambda s: z(pad64(s)),
    "st_w": lambda s: w(pad64(s)),
    "st_deconv_z": lambda s: next((t for t in (z(pad64(gauss_deconv(s, sg * 4, k))) for sg in (0.8, 1.2, 1.6) for k in (0.003, 0.01)) if t), None),
    "st_deconv_w": lambda s: next((t for t in (w(pad64(gauss_deconv(s, sg * 4, k))) for sg in (0.8, 1.2) for k in (0.003,)) if t), None),
}


def find_tems():
    """Tem thật: gom detection cỡ nhỏ qua các frame toàn khung của nhiều mức sáng."""
    clusters = []
    for path in sorted(glob.glob(os.path.join(OUT, "g*_e*", "f00.png"))):
        g = cv2.imread(path, 0)
        if not 15 <= g.mean() <= 110:
            continue
        for d in det.detect(np.ascontiguousarray(cv2.cvtColor(g, cv2.COLOR_GRAY2BGR))):
            x1, y1, x2, y2 = (float(v) for v in d.bbox_xyxy)
            if max(x2 - x1, y2 - y1) > 110:
                continue
            c = ((x1 + x2) / 2, (y1 + y2) / 2)
            for cl in clusters:
                if abs(cl["c"][0] - c[0]) < 50 and abs(cl["c"][1] - c[1]) < 50:
                    cl["n"] += 1
                    if d.confidence > cl["conf"]:
                        cl.update(conf=d.confidence, det=d)
                    break
            else:
                clusters.append(dict(c=c, n=1, conf=d.confidence, det=d))
    clusters = [c for c in clusters if c["n"] >= 3]
    return sorted(clusters, key=lambda c: c["c"][1])


tems = find_tems()
print("tem", [(round(c["c"][0]), round(c["c"][1]), c["n"], round(c["conf"], 2)) for c in tems], flush=True)
result_path = os.path.join(OUT, "results.jsonl")
out = open(result_path, "w", encoding="utf-8")
det.set_device("auto")
for run in meta["runs"]:
    folder = os.path.join(OUT, f"g{run['gain']:02d}_e{run['ms']:02d}")
    crops = [cv2.imread(p, 0) for p in sorted(glob.glob(os.path.join(folder, "c*.png")))]
    fulls = [cv2.imread(p, 0) for p in sorted(glob.glob(os.path.join(folder, "f*.png")))]
    found = [[] for _ in tems]
    false_pos = 0
    t = time.perf_counter()
    for g in fulls:
        hit = det.detect(np.ascontiguousarray(cv2.cvtColor(g, cv2.COLOR_GRAY2BGR)))
        taken = set()
        for d in hit:
            x1, y1, x2, y2 = (float(v) for v in d.bbox_xyxy)
            c = ((x1 + x2) / 2, (y1 + y2) / 2)
            for i, tem in enumerate(tems):
                if abs(tem["c"][0] - c[0]) < 50 and abs(tem["c"][1] - c[1]) < 50:
                    found[i].append(round(float(d.confidence), 2))
                    taken.add(id(d))
            if id(d) not in taken and d.confidence >= 0.3:
                false_pos += 1
    row = dict(gain=run["gain"], ms=run["ms"], mean=run["mean"], fps=run["fps"], false_pos=false_pos, tems=[])
    for i, tem in enumerate(tems):
        x1, y1, x2, y2 = (float(v) for v in tem["det"].bbox_xyxy)
        side = max(x2 - x1, y2 - y1)
        m = int(side * 0.25)
        ax0, ay0, ax1, ay1 = int(x1 - m) - X0, int(y1 - m) - Y0, int(x2 + m) - X0, int(y2 + m) - Y0
        rois = [c[ay0:ay1, ax0:ax1] for c in crops]
        inner = np.stack([c[int(y1) - Y0:int(y2) - Y0, int(x1) - X0:int(x2) - X0] for c in crops]).astype(np.float32)
        lo, hi = np.percentile(inner.mean(axis=0), (3, 97))
        cell = dict(detected=f"{len(found[i])}/{len(fulls)}", conf=max(found[i]) if found[i] else 0,
                    black=round(float(lo), 1), white=round(float(hi), 1),
                    sat=round(float((inner >= 250).mean()) * 100, 2), noise=round(float(inner.std(axis=0).mean()), 2),
                    methods={}, texts={}, ms={})
        for name, fn in SINGLE.items():
            t0 = time.perf_counter()
            hits = [fn(r) for r in rois]
            cell["ms"][name] = round((time.perf_counter() - t0) * 1000 / len(rois), 1)
            cell["methods"][name] = sum(bool(h) for h in hits)
            for h in hits:
                if h:
                    cell["texts"][h] = cell["texts"].get(h, 0) + 1
        warp_hits = []
        for c in crops:
            full_like = np.full((Y1, X1, 3), 0, np.uint8)
            full_like[Y0:Y1, X0:X1] = c[..., None]
            warped = cv2.cvtColor(warp_qr(full_like, tem["det"], out_size=256), cv2.COLOR_BGR2GRAY)
            warp_hits.append(z(add_quiet_zone(warped, pad_px=32)))
        cell["methods"]["warp"] = sum(bool(h) for h in warp_hits)
        for h in warp_hits:
            if h:
                cell["texts"][h] = cell["texts"].get(h, 0) + 1
        # Xếp chồng: 2 bộ 8 frame rời nhau
        for name in STACKED:
            cell["methods"][name] = 0
        for part in (rois[:8], rois[8:16]):
            s = stack_rois(part)
            for name, fn in STACKED.items():
                t0 = time.perf_counter()
                h = fn(s)
                cell["ms"][name] = round((time.perf_counter() - t0) * 1000, 1)
                cell["methods"][name] += bool(h)
                if h:
                    cell["texts"][h] = cell["texts"].get(h, 0) + 1
            sampled = sample_modules(cv2.resize(cv2.resize(s, (rois[0].shape[1], rois[0].shape[0]), interpolation=cv2.INTER_AREA),
                                                None, fx=1, fy=1))
            h = decode_modules(sampled[0]) if sampled is not None else None
            cell["methods"]["st_modules"] = cell["methods"].get("st_modules", 0) + bool(h)
            if h:
                cell["texts"][h] = cell["texts"].get(h, 0) + 1
        row["tems"].append(cell)
    out.write(json.dumps(row, ensure_ascii=False) + "\n")
    out.flush()
    print(f"g{run['gain']} e{run['ms']}: " + " | ".join(
        f"T{i} {c['detected']} {c['black']:.0f}/{c['white']:.0f} sat{c['sat']:.0f} n{c['noise']:.1f} best={max(c['methods'].values())}"
        for i, c in enumerate(row["tems"])), flush=True)
print("xong")
