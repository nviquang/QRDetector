"""So độ nhạy và tốc độ các bộ phát hiện QR trên dữ liệu hiện trường (data/field), cắt dải ROI như buồng tối.

Mốc: qrdet-s seg (torch, imgsz 1280 — cấu hình hiện tại). So với: qrdet-n seg (torch), YOLOv8n detect chuyển từ
qrdet-n chạy ONNX Runtime / OpenVINO ở các tỉ lệ thu. Chỉ đo trên CPU.

    python tools/bench_detector.py --data ../QRDetector/data/field              # mặc định tự tìm data/field
    python tools/bench_detector.py --per-pass 20 --scales 0.5,0.6 --out experiments/out

Chỉ số:
- recall: phát hiện của mốc được bộ khác bắt lại (IoU ≥ 0,5), tính trên frame có tem;
- lượt: số đoạn ``pass`` mà bộ đó bắt được ≥ 50% số frame mốc bắt được;
- thêm: hộp bộ đó có mà mốc không có (trên frame có tem) — có thể là bắt thêm thật hoặc nhầm;
- nhầm: hộp trên frame không có tem (đoạn glass_no_det, empty);
- ms p50/p95 mỗi lần detect (bỏ 3 lần đầu).

Dữ liệu quay ở cấu hình cũ (0,673 mm/px, QR 55–75 px) gần cỡ QR mới (~57 px): dùng được để so detect, không kết luận tỉ lệ đọc.
"""
from __future__ import annotations

import argparse
import ast
import csv
import datetime
import os
import sys
import time
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import torch  # noqa: E402,F401  (torch trước cv2)
import cv2  # noqa: E402
import numpy as np  # noqa: E402

from qr.detector import QRDetector  # noqa: E402
from qr.detector_onnx import OnnxQRDetector  # noqa: E402

BAND_H = 1072
IOU_MIN = 0.5


def find_data() -> str:
    for cand in (os.path.join(ROOT, "data", "field"),
                 os.path.join(ROOT, "..", "..", "..", "data", "field")):     # worktree trong .claude/worktrees/
        if os.path.isfile(os.path.join(cand, "segments.csv")):
            return os.path.abspath(cand)
    raise SystemExit("không tìm thấy data/field/segments.csv — truyền --data")


def load_frames(data: str, per_pass: int, per_glass: int, per_empty: int, seed: int = 0):
    """[(đường dẫn, nhãn đoạn, khóa đoạn, y tâm tem hoặc None)]."""
    rng = np.random.default_rng(seed)
    frames = {}
    with open(os.path.join(data, "frames.csv"), encoding="utf-8") as f:
        for row in csv.DictReader(f):
            frames[(row["rec_id"], int(row["idx"]))] = row
    picked = []
    with open(os.path.join(data, "segments.csv"), encoding="utf-8") as f:
        for seg in csv.DictReader(f):
            label, rec = seg["label"], seg["rec_id"]
            idx = range(int(seg["start_idx"]), int(seg["end_idx"]) + 1)
            key = f"{rec}#{seg['seg_no']}"
            if label in ("pass", "static"):
                rows = [frames[(rec, i)] for i in idx if (rec, i) in frames and float(frames[(rec, i)]["ndet"] or 0) > 0]
                n = per_pass if label == "pass" else 3
                take = [rows[int(j)] for j in np.linspace(0, len(rows) - 1, min(n, len(rows)))] if rows else []
                for r in take:
                    boxes = ast.literal_eval(r["det_bboxes"]) if r["det_bboxes"] else []
                    ys = [(b[1] + b[3]) / 2 for b in boxes] if boxes else [None]
                    picked.append((os.path.join(data, r["raw_path"]), label, key, ys[0]))
            elif label in ("glass_no_det", "empty"):
                rows = [frames[(rec, i)] for i in idx if (rec, i) in frames]
                n = per_glass if label == "glass_no_det" else per_empty
                for j in rng.choice(len(rows), min(n, len(rows)), replace=False) if rows else []:
                    picked.append((os.path.join(data, rows[int(j)]["raw_path"]), label, key, None))
    return picked


def band(image, y_center):
    h = image.shape[0]
    if h <= BAND_H:
        return image
    y = int(round((h - BAND_H) / 2 if y_center is None else y_center - BAND_H / 2))
    y = max(0, min(h - BAND_H, y))
    return image[y:y + BAND_H]


def iou(a, b):
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    return inter / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter + 1e-9)


def make_variants(scales, threads):
    yield "qrdet-s seg torch 1280 (mốc)", lambda: QRDetector("s", conf_th=0.3, imgsz=1280, device="cpu")
    yield "qrdet-n seg torch 1280", lambda: QRDetector("n", conf_th=0.3, imgsz=1280, device="cpu")
    for backend in ("onnxruntime", "openvino"):
        for s in scales:
            yield f"n-detect {backend} ×{s}", (lambda b=backend, s=s: OnnxQRDetector(scale=s, backend=b))
        if threads:
            s = scales[len(scales) // 2]
            yield (f"n-detect {backend} ×{s} {threads} luồng",
                   lambda b=backend, s=s: OnnxQRDetector(scale=s, backend=b, threads=threads))


def run(det, images):
    out, ms = [], []
    for img in images:
        t = time.perf_counter()
        found = det.detect(img)
        ms.append((time.perf_counter() - t) * 1000)
        out.append([d.bbox_xyxy.tolist() for d in found])
    return out, ms[3:] if len(ms) > 6 else ms


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default=None)
    ap.add_argument("--per-pass", type=int, default=40)
    ap.add_argument("--per-glass", type=int, default=15)
    ap.add_argument("--per-empty", type=int, default=5)
    ap.add_argument("--scales", default="0.5,0.6,0.75")
    ap.add_argument("--threads", type=int, default=4, help="thêm một phương án giới hạn số luồng (0 = bỏ)")
    ap.add_argument("--out", default=os.path.join(ROOT, "experiments", "out"))
    args = ap.parse_args()
    data = args.data or find_data()
    scales = [float(s) for s in args.scales.split(",")]
    picked = load_frames(data, args.per_pass, args.per_glass, args.per_empty)
    images = []
    for path, _, _, yc in picked:
        img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
        images.append(cv2.cvtColor(band(img, yc), cv2.COLOR_GRAY2BGR))
    pos = [i for i, p in enumerate(picked) if p[1] in ("pass", "static")]
    neg = [i for i, p in enumerate(picked) if p[1] not in ("pass", "static")]
    print(f"{len(images)} frame: {len(pos)} có tem, {len(neg)} không có tem; kích thước dải {images[0].shape[:2]}…", flush=True)

    results = {}
    ref = None
    for name, factory in make_variants(scales, args.threads):
        det = factory()
        det.warmup(images[0].shape[:2])
        boxes, ms = run(det, images)
        results[name] = (boxes, ms)
        if ref is None:
            ref = boxes
        print(f"  xong {name}: p50 {np.percentile(ms, 50):.0f} ms", flush=True)

    passes = defaultdict(list)
    for i in pos:
        passes[picked[i][2]].append(i)
    lines = [f"# So bộ phát hiện QR — {datetime.date.today().isoformat()}", "",
             f"Dữ liệu: `{data}`; {len(pos)} frame có tem ({len(passes)} đoạn), {len(neg)} frame không có tem; dải "
             f"{BAND_H} hàng quanh tem (frame phòng thí nghiệm 992 hàng giữ nguyên). CPU, mốc = qrdet-s seg imgsz 1280.", "",
             "| Bộ phát hiện | recall | lượt | thêm | nhầm | ms p50 | ms p95 |", "|---|---:|---:|---:|---:|---:|---:|"]
    for name, (boxes, ms) in results.items():
        hit = total = extra = 0
        seg_ok = 0
        for key, idxs in passes.items():
            got = want = 0
            for i in idxs:
                for rb in ref[i]:
                    want += 1
                    if any(iou(rb, b) >= IOU_MIN for b in boxes[i]):
                        got += 1
                extra += sum(1 for b in boxes[i] if not any(iou(rb, b) >= IOU_MIN for rb in ref[i]))
            hit, total = hit + got, total + want
            seg_ok += int(want == 0 or got >= 0.5 * want)
        false = sum(len(boxes[i]) for i in neg)
        lines.append(f"| {name} | {hit / max(total, 1):.1%} ({hit}/{total}) | {seg_ok}/{len(passes)} | {extra} | {false} "
                     f"| {np.percentile(ms, 50):.0f} | {np.percentile(ms, 95):.0f} |")
    text = "\n".join(lines) + "\n"
    print(text)
    os.makedirs(args.out, exist_ok=True)
    path = os.path.join(args.out, f"bench_detector_{datetime.datetime.now():%Y%m%d_%H%M}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    print("ghi", path)


if __name__ == "__main__":
    main()
