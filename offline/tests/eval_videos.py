"""Đo chất lượng detect/decode trên video hoặc ảnh thật — chỉ số theo frame và theo LƯỢT QR đi qua.

Chạy:
  python offline/tests/eval_videos.py videos/*.avi
  python offline/tests/eval_videos.py video/10.mp4 --labels labels.json --out report.json
  python offline/tests/eval_videos.py images                       # mỗi ảnh tĩnh là một mẫu
  python offline/tests/eval_videos.py recordings/run01 --sequence  # thư mục frame = một video

Đầu vào: file video, thư mục (ảnh hoặc video bên trong) hoặc glob. Video tính chỉ số theo lượt bằng
``qr.tracker.PassTracker``; thư mục ảnh mặc định là các ảnh tĩnh độc lập (thêm ``--sequence`` nếu
là chuỗi frame liên tiếp).

labels.json (tùy chọn) — đáp án đúng, khóa là tên nguồn (tên file không đuôi / tên thư mục) hoặc "*":
  {"*": {"pattern": "^\\d{12}$"},
   "run01": {"codes": ["000000585545"], "passes": 20}}
  codes:   danh sách mã hợp lệ — mã đọc được ngoài danh sách tính là ĐỌC SAI.
  pattern: regex định dạng mã — không khớp tính là ĐỌC SAI.
  passes:  số lượt QR thật sự đi qua (để tính tỉ lệ đọc theo lượt khi tracker tách/gộp nhầm).
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # offline/
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from media_source import MediaError, is_image, is_video, read_image  # noqa: E402
from qr.tracker import Observation, PassTracker  # noqa: E402


# ── chỉ số chất lượng ROI ─────────────────────────────────────────────────────

def roi_metrics(roi_gray: np.ndarray) -> dict:
    """Độ nét, hướng mờ, tương phản, cháy sáng của ROI xám.

    blur_ratio = |∂y| / |∂x|: băng chạy theo trục x → mờ chuyển động làm giảm |∂x| → tỉ lệ > 1.
    QR nét thường 0.8–1.2; video băng chạy hiện tại 1.6–2.0.
    """
    g = roi_gray.astype(np.float32)
    gx = float(np.abs(cv2.Sobel(g, cv2.CV_32F, 1, 0)).mean())
    gy = float(np.abs(cv2.Sobel(g, cv2.CV_32F, 0, 1)).mean())
    return dict(
        sharpness=round(float(cv2.Laplacian(roi_gray, cv2.CV_64F).var()), 1),
        blur_ratio=round(gy / max(gx, 1e-6), 2),
        p5=int(np.percentile(roi_gray, 5)),
        p95=int(np.percentile(roi_gray, 95)),
        saturated_pct=round(float((roi_gray >= 250).mean() * 100), 2),
    )


def _median(values) -> float | None:
    return round(float(np.median(values)), 2) if values else None


# ── nguồn dữ liệu ────────────────────────────────────────────────────────────

def source_name(path: str) -> str:
    """Tên nguồn = tên file không đuôi; riêng ``video.avi`` do app camera ghi thì lấy tên thư mục chứa nó
    (mỗi phiên quay một thư mục — đổi tên thư mục, ví dụ ``v30_b2_g24``, để phân biệt cấu hình)."""
    stem = os.path.splitext(os.path.basename(path))[0]
    if stem == "video":
        return os.path.basename(os.path.dirname(os.path.abspath(path)))
    return stem


def expand_inputs(inputs: list[str], sequence: bool) -> list[tuple[str, str, list[str]]]:
    """Trả về list (tên nguồn, loại, danh sách đường dẫn). loại: video | sequence | images."""
    sources = []
    for item in inputs:
        paths = sorted(glob.glob(item)) or [item]
        for path in paths:
            if os.path.isdir(path):
                files = sorted(os.path.join(path, f) for f in os.listdir(path))
                images = [f for f in files if is_image(f)]
                videos = [f for f in files if is_video(f)]
                name = os.path.basename(os.path.normpath(path))
                if images:
                    sources.append((name, "sequence" if sequence else "images", images))
                for v in videos:
                    sources.append((source_name(v), "video", [v]))
            elif is_video(path):
                sources.append((source_name(path), "video", [path]))
            elif is_image(path):
                sources.append((os.path.splitext(os.path.basename(path))[0], "images", [path]))
            else:
                print(f"[WARN] bỏ qua {path}: không phải video/ảnh/thư mục", file=sys.stderr)
    return sources


def iter_frames(kind: str, paths: list[str], step: int, max_frames: int | None):
    """Sinh (chỉ số frame gốc, frame BGR) — lấy mỗi ``step`` frame."""
    count = 0
    if kind == "video":
        cap = cv2.VideoCapture(paths[0])
        idx = 0
        try:
            while True:
                if idx % step == 0:
                    ok, frame = cap.read()
                    if not ok:
                        break
                    yield idx, frame
                    count += 1
                    if max_frames and count >= max_frames:
                        break
                elif not cap.grab():
                    break
                idx += 1
        finally:
            cap.release()
        return
    for idx, path in enumerate(paths):
        if idx % step:
            continue
        try:
            frame = read_image(path)   # chịu đường dẫn tiếng Việt
        except MediaError:
            continue
        yield idx, frame
        count += 1
        if max_frames and count >= max_frames:
            break


def video_info(path: str) -> dict:
    cap = cv2.VideoCapture(path)
    info = dict(width=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), height=int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                fps_header=round(cap.get(cv2.CAP_PROP_FPS), 2), frames=int(cap.get(cv2.CAP_PROP_FRAME_COUNT)))
    cap.release()
    return info


# ── đáp án ───────────────────────────────────────────────────────────────────

def load_labels(path: str | None) -> dict:
    if not path:
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def label_for(labels: dict, name: str) -> dict:
    merged = dict(labels.get("*", {}))
    merged.update(labels.get(name, {}))
    return merged


def is_misread(text: str, label: dict) -> bool:
    codes = label.get("codes")
    if codes and text not in codes:
        return True
    pattern = label.get("pattern")
    return bool(pattern and not re.search(pattern, text))


# ── đánh giá một nguồn ───────────────────────────────────────────────────────

def evaluate_source(pipe, name: str, kind: str, paths: list[str], args, label: dict) -> dict:
    from qr.preprocessor import crop_roi_gray

    tracker = PassTracker(max_gap=args.max_gap * args.step, gate_px=args.gate_px) \
        if kind != "images" else None
    passes = []
    frames = det_frames = dec_frames = 0
    det_count = dec_count = 0
    texts: dict[str, int] = {}
    metrics = {k: [] for k in ("size", "sharpness", "blur_ratio", "p5", "p95", "saturated_pct")}
    t_detect = t_decode = 0.0
    per_image = []

    for idx, frame in iter_frames(kind, paths, args.step, args.max_frames):
        frames += 1
        t0 = time.perf_counter()
        dets = pipe.detect(frame)
        t_detect += time.perf_counter() - t0
        observations = []
        frame_texts = []
        for k, det in enumerate(dets):
            x1, y1, x2, y2 = det.bbox_xyxy
            size = float(max(x2 - x1, y2 - y1))
            roi = crop_roi_gray(frame, det.bbox_xyxy, margin=0.25)
            m = roi_metrics(roi) if roi.size else {}
            t0 = time.perf_counter()
            text = pipe._decode_one(frame, det)
            t_decode += time.perf_counter() - t0
            det_count += 1
            metrics["size"].append(size)
            for key, value in m.items():
                metrics[key].append(value)
            if text:
                dec_count += 1
                texts[text] = texts.get(text, 0) + 1
                frame_texts.append(text)
            cx, cy = det.quad_xy.mean(axis=0)
            observations.append(Observation((float(cx), float(cy)), size, text))
            if args.dump_rois and roi.size:
                os.makedirs(args.dump_rois, exist_ok=True)
                cv2.imwrite(os.path.join(args.dump_rois, f"{name}_f{idx:05d}_d{k}_{'ok' if text else 'fail'}.png"),
                            roi)
        det_frames += bool(dets)
        dec_frames += bool(frame_texts)
        if tracker is not None:
            passes += tracker.update(idx, observations)
        else:
            per_image.append(dict(frame=os.path.basename(paths[idx]), detections=len(dets), texts=frame_texts))

    if tracker is not None:
        passes += tracker.finish()
    passes = [p for p in passes if p.observations >= args.min_track_frames]
    pass_rows = [dict(id=p.track_id, first=p.first_frame, last=p.last_frame, observations=p.observations,
                      decoded_frames=sum(p.texts.values()), text=p.text, conflicting=p.conflicting)
                 for p in passes]

    misreads = sorted({t for t in texts if is_misread(t, label)})
    read_passes = sum(1 for p in passes if p.text and not is_misread(p.text, label))
    expected = label.get("passes")
    summary = dict(
        source=name, kind=kind, frames=frames, det_frames=det_frames, dec_frames=dec_frames,
        detections=det_count, decoded_detections=dec_count,
        frame_decode_rate=round(dec_frames / frames, 3) if frames else None,
        texts=texts, misread_texts=misreads,
        detect_ms=round(1000 * t_detect / max(frames, 1), 1),
        decode_ms_per_det=round(1000 * t_decode / max(det_count, 1), 1),
        **{f"{k}_med": _median(v) for k, v in metrics.items()},
    )
    if kind == "video":
        summary["video"] = video_info(paths[0])
    if tracker is not None:
        summary.update(
            passes_tracked=len(passes), passes_read=read_passes,
            passes_expected=expected,
            pass_read_rate=round(read_passes / (expected or len(passes)), 3) if (expected or passes) else None,
            conflicting_passes=sum(1 for p in passes if p.conflicting),
            pass_list=pass_rows,
        )
    else:
        summary["per_image"] = per_image
    return summary


def print_table(rows: list[dict]):
    head = (f"{'nguồn':<28} {'loại':<8} {'frame':>5} {'det%':>5} {'dec%':>5} "
            f"{'lượt':>9} {'đọc lượt':>8} {'sai':>3} {'QR px':>6} {'nét':>6} {'gy/gx':>5} {'p95':>4} {'ms/det':>6}")
    print(head)
    print("-" * len(head))
    for r in rows:
        frames = max(r["frames"], 1)
        passes = (f"{r['passes_read']}/{r['passes_expected'] or r['passes_tracked']}"
                  if "passes_tracked" in r else "-")
        rate = f"{100 * r['pass_read_rate']:.0f}%" if r.get("pass_read_rate") is not None else "-"
        print(f"{r['source'][:28]:<28} {r['kind']:<8} {r['frames']:>5} "
              f"{100 * r['det_frames'] / frames:>4.0f}% {100 * r['dec_frames'] / frames:>4.0f}% "
              f"{passes:>9} {rate:>8} {len(r['misread_texts']):>3} "
              f"{r['size_med'] or 0:>6.0f} {r['sharpness_med'] or 0:>6.0f} {r['blur_ratio_med'] or 0:>5.2f} "
              f"{r['p95_med'] or 0:>4.0f} {r['decode_ms_per_det']:>6.0f}")


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):   # console Windows mặc định cp1252
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("inputs", nargs="+", help="file video, thư mục hoặc glob")
    parser.add_argument("--step", type=int, default=1, help="lấy mỗi N frame (mặc định 1 — cần cho chỉ số theo lượt)")
    parser.add_argument("--max-frames", type=int, default=None, help="giới hạn số frame mỗi nguồn")
    parser.add_argument("--labels", help="file labels.json (đáp án đúng)")
    parser.add_argument("--out", help="ghi báo cáo JSON đầy đủ")
    parser.add_argument("--dump-rois", help="thư mục lưu ROI từng detection (tên có _ok/_fail)")
    parser.add_argument("--sequence", action="store_true", help="thư mục ảnh là chuỗi frame liên tiếp")
    parser.add_argument("--max-gap", type=int, default=5, help="số frame lấy mẫu được phép mất dấu trong một lượt")
    parser.add_argument("--gate-px", type=float, default=400.0, help="cổng ghép track mới (px)")
    parser.add_argument("--min-track-frames", type=int, default=2, help="bỏ lượt có ít hơn N detection (detect nhiễu)")
    args = parser.parse_args(argv)

    from qr import ImprovePipeline
    pipe = ImprovePipeline()
    labels = load_labels(args.labels)
    rows = []
    for name, kind, paths in expand_inputs(args.inputs, args.sequence):
        print(f"... {name} ({kind}, {len(paths)} file)", flush=True)
        rows.append(evaluate_source(pipe, name, kind, paths, args, label_for(labels, name)))
    if not rows:
        print("Không có nguồn nào để đánh giá.")
        return 1
    print()
    print_table(rows)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(dict(args=vars(args), sources=rows), f, ensure_ascii=False, indent=2)
        print(f"\nĐã ghi {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
