"""Đo tốc độ đọc QR theo từng bước (detect / cascade) và đếm lượt — ảnh mẫu hoặc video quay từ app.

Chạy (từ gốc repo). Ảnh mẫu lấy từ QR_SAMPLES_DIR, mặc định ../QRDetector-research/data/images:
  python tools/bench_decode.py                              # ảnh mẫu *.bmp, GPU nếu có
  python tools/bench_decode.py --device cpu                 # so sánh với CPU
  python tools/bench_decode.py --band 1024 768              # cắt dải như chế độ băng chuyền
  python tools/bench_decode.py --half                       # thử FP16 (chỉ GPU)
  python tools/bench_decode.py --video recordings/<phiên>/video.avi --every 5
Warm-up model chạy trước, không tính vào thống kê.
"""

from __future__ import annotations

import argparse
import glob
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
SAMPLES_DIR = os.environ.get("QR_SAMPLES_DIR", os.path.join(ROOT, "..", "QRDetector-research", "data", "images"))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from qr import ImprovePipeline, PassReader  # noqa: E402
from qr.tracker import PassTracker  # noqa: E402


def _frames(args):
    if args.video:
        cap = cv2.VideoCapture(args.video)
        idx = 0
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if idx % args.every == 0:
                yield idx, frame
            idx += 1
        cap.release()
    else:
        for i, path in enumerate(sorted(glob.glob(os.path.join(SAMPLES_DIR, "*.bmp")))):
            yield i * 1000, cv2.imread(path)     # cách nhau > max_gap → mỗi ảnh là lượt riêng


def _pct(values, q):
    return float(np.percentile(values, q)) if values else 0.0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--video", help="file video (AVI quay từ app)")
    ap.add_argument("--every", type=int, default=1, help="chỉ xử lý mỗi N frame của video")
    ap.add_argument("--band", type=int, nargs=2, metavar=("Y", "H"), help="cắt dải hàng [Y, Y+H)")
    ap.add_argument("--imgsz", type=int, default=1280)
    ap.add_argument("--device", default="auto", help="auto / cpu / cuda:0")
    ap.add_argument("--half", action="store_true", help="FP16 (chỉ có tác dụng trên GPU)")
    ap.add_argument("--max-frames", type=int, default=0, help="0 = không giới hạn")
    args = ap.parse_args()

    pipeline = ImprovePipeline(imgsz=args.imgsz, device=args.device, half=args.half, multi_frame=False)
    pipeline.warmup((args.band[1], 2448) if args.band else (2048, 2448))
    reader = PassReader(pipeline, PassTracker(max_gap=max(100, 3 * args.every)))
    rows, passes = [], []
    for idx, frame in _frames(args):
        if frame is None:
            continue
        if args.band:
            y, h = args.band
            frame = np.ascontiguousarray(frame[y:y + h])
        t = time.perf_counter()
        r = reader.process(frame, idx)
        rows.append((r.detect_ms, r.cascade_ms, (time.perf_counter() - t) * 1000.0,
                     len(r.detections), len(r.results), r.skipped))
        passes += r.finished
        if args.max_frames and len(rows) >= args.max_frames:
            break
    passes += reader.flush()
    if not rows:
        sys.exit("Không có frame nào (kiểm tra --video hoặc biến QR_SAMPLES_DIR).")

    print(f"device={pipeline.device} half={args.half} imgsz={args.imgsz} band={args.band}")
    for name, col in (("detect", 0), ("cascade", 1), ("tổng", 2)):
        vals = [row[col] for row in rows]
        print(f"{name:8s} mean={np.mean(vals):7.0f} ms  p50={_pct(vals, 50):7.0f}  p95={_pct(vals, 95):7.0f}")
    print(f"frame={len(rows)}  frame đọc được={sum(1 for row in rows if row[4])}  "
          f"detection={sum(row[3] for row in rows)}  bỏ cascade={sum(row[5] for row in rows)}")
    print(f"lượt={len(passes)}  đọc được={sum(1 for p in passes if p.text)}  "
          f"mâu thuẫn={sum(1 for p in passes if p.conflicting)}")


if __name__ == "__main__":
    main()
