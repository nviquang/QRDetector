"""Dựng dữ liệu chấm điểm từ thư mục TIFF của pylon: detect mọi frame, gom lượt, gán mã, cắt crop, chia dev/test.

python experiments/bench/build.py --data <gốc chứa gan/xa/cheo> --out experiments/out/bench --test-out <thư mục test>
Đáp án lấy theo đa số các lần cascade đọc được trong lượt (không có nhãn tay); xem meta.json.
"""
import argparse
import collections
import glob
import json
import os
import pickle
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
sys.stdout.reconfigure(encoding="utf-8")

import torch  # noqa: F401,E402
import cv2  # noqa: E402
import numpy as np  # noqa: E402
import logging  # noqa: E402

logging.disable(logging.INFO)
from qr.detector import QRDetector  # noqa: E402
from qr.improved_pipeline import ImprovePipeline  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--data", default=ROOT)
ap.add_argument("--out", default=os.path.join(ROOT, "experiments", "out", "bench"))
ap.add_argument("--test-out", required=True)
ap.add_argument("--clips", default="gan,xa,cheo")
args = ap.parse_args()
os.makedirs(args.out, exist_ok=True)
FPS = 25.0
EDGE = 3          # bỏ detection chạm mép ảnh: QR có thể bị cắt
GATE = 22.0       # px dịch tối đa giữa 2 frame liền nhau khi nối lượt


def clip_files(name):
    """Thư mục pylon <data>/<name>/*.tiff, hoặc bố cục data/field/raw/<tiền tố>_lab_<name>/frame_*.tiff
    (tools/clean_field_data.py; 06/11 các clip gan/xa/cheo đã chuyển vào đây và thư mục gốc bị xóa)."""
    old = sorted(glob.glob(os.path.join(args.data, name, "*.tiff")))
    if old:
        return old
    raw = os.path.join(args.data, "data", "field", "raw") if os.path.isdir(os.path.join(args.data, "data")) else args.data
    return sorted(glob.glob(os.path.join(raw, f"*_lab_{name}", "frame_*.tiff")))


def detect_all(name, files):
    path = os.path.join(args.out, f"dets_{name}.pkl")
    if os.path.exists(path):
        return pickle.load(open(path, "rb"))
    det = QRDetector(conf_th=0.3, imgsz=1280, device="auto")
    out = []
    for i, f in enumerate(files):
        out.append(det.detect(cv2.imread(f, cv2.IMREAD_COLOR)))
        if i % 300 == 0:
            print(name, i, flush=True)
    pickle.dump(out, open(path, "wb"))
    return out


def center(d):
    b = d.bbox_xyxy
    return np.array([(b[0] + b[2]) / 2, (b[1] + b[3]) / 2], np.float64)


def make_tracks(dets):
    live, done = [], []
    for i, ds in enumerate(dets):
        used = set()
        for t in sorted(live, key=lambda t: -len(t)):
            last_i, last_d = t[-1]
            gap = i - last_i
            vel = (center(t[-1][1]) - center(t[max(0, len(t) - 6)][1])) / max(t[-1][0] - t[max(0, len(t) - 6)][0], 1)
            pred = center(last_d) + vel * gap
            best, bd = None, GATE
            for j, d in enumerate(ds):
                if j in used:
                    continue
                dist = float(np.linalg.norm(center(d) - pred))
                if dist < bd:
                    best, bd = j, dist
            if best is not None:
                used.add(best)
                t.append((i, ds[best]))
        for j, d in enumerate(ds):
            if j not in used:
                live.append([(i, d)])
        still = []
        for t in live:
            (done if i - t[-1][0] > 12 else still).append(t)
        live = still
    return [t for t in done + live if len(t) >= 15]


def main():
    summary = {}
    all_tracks = []
    pipe = ImprovePipeline(detector=object(), multi_frame=False)
    for name in args.clips.split(","):
        files = clip_files(name)
        dets = detect_all(name, files)
        tracks = make_tracks(dets)
        tracks.sort(key=lambda t: t[0][0])
        kept = 0
        for t in tracks:
            # gán mã: cascade trên tối đa 25 frame trải đều
            idx = np.linspace(0, len(t) - 1, min(25, len(t))).astype(int)
            votes = collections.Counter()
            for k in idx:
                i, d = t[k]
                hit = pipe.decode_detection(cv2.imread(files[i], cv2.IMREAD_COLOR), d)
                if hit:
                    votes[hit.text] += 1
            code, n = votes.most_common(1)[0] if votes else (None, 0)
            obs = []
            first = center(t[0][1])
            last = center(t[-1][1])
            vel = (last - first) / max(t[-1][0] - t[0][0], 1)
            for i, d in t:
                img = cv2.imread(files[i], cv2.IMREAD_GRAYSCALE)
                h, w = img.shape
                x1, y1, x2, y2 = d.bbox_xyxy
                if x1 < EDGE or y1 < EDGE or x2 > w - EDGE or y2 > h - EDGE:
                    continue
                m = max(45, 0.8 * max(x2 - x1, y2 - y1))
                cx1, cy1 = int(max(0, x1 - m)), int(max(0, y1 - m))
                cx2, cy2 = int(min(w, x2 + m)), int(min(h, y2 + m))
                o = np.array([cx1, cy1], np.float32)
                obs.append(dict(frame=i, t=i / FPS, crop=img[cy1:cy2, cx1:cx2].copy(), origin=o,
                                bbox=np.asarray(d.bbox_xyxy, np.float32) - np.r_[o, o],
                                quad=np.asarray(d.quad_xy, np.float32) - o,
                                polygon=None if d.polygon_xy is None else np.asarray(d.polygon_xy, np.float32) - o,
                                conf=float(d.confidence)))
            all_tracks.append(dict(clip=name, first=t[0][0], last=t[-1][0], code=code, votes=n, nvote=len(idx),
                                   velocity=vel, obs=obs, cx=float(first[0])))
            kept += 1
        summary[name] = dict(frames=len(files), tracks=kept)
        print(name, summary[name], flush=True)
    # chia xen kẽ theo thứ tự thời gian trong mỗi đoạn: 1 dev, 1 test
    for name in args.clips.split(","):
        ts = [t for t in all_tracks if t["clip"] == name]
        for k, t in enumerate(ts):
            t["id"], t["split"] = f"{name}_{k:02d}", "dev" if k % 2 == 0 else "test"
    meta = []
    for split, base in (("dev", args.out), ("test", args.test_out)):
        d = os.path.join(base, "tracks_" + split)
        os.makedirs(d, exist_ok=True)
        for t in all_tracks:
            if t["split"] == split:
                pickle.dump(t, open(os.path.join(d, t["id"] + ".pkl"), "wb"))
    for t in all_tracks:
        meta.append({k: (t[k] if k != "code" else t["code"]) for k in ("id", "split", "clip", "first", "last", "code", "votes", "nvote", "cx")}
                    | {"n_obs": len(t["obs"])})
    json.dump(dict(summary=summary, tracks=meta), open(os.path.join(args.test_out, "meta_all.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for m in meta:
        print(m["id"], m["split"], m["first"], m["last"], m["n_obs"], m["code"], f"{m['votes']}/{m['nvote']}")


main()
