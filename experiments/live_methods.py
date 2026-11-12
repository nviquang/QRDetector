"""So sánh các phương pháp đọc QR trên luồng camera thật (hoặc phát lại thư mục TIFF để thử không cần camera).

python experiments/live_methods.py [--methods baseline,C,B,B+C] [--seconds 120] [--device auto|cpu]
       [--config experiments/benchmark_basler.json] [--roi X Y W H] [--exposure MS] [--gain DB] [--k 5]
       [--codes codes.txt] [--true-passes N] [--name tên] [--serial SN] [--replay thư mục]

Mỗi lượt tem: detect + PassTracker trên luồng → khi tem ra khỏi khung, CÙNG k crop được đưa cho từng phương pháp.
Phương pháp chạy nền (mỗi phương pháp một tiến trình), nên có thể trễ sau băng chuyền: đây là phép so sánh khả năng
đọc, không phải đo thời gian thực của sản phẩm. Hết giờ thì chờ xử lý nốt hàng đợi (Ctrl+C lần nữa để bỏ).

Kết quả: experiments/out/live/<tên>/results.jsonl, passes/*.pkl (định dạng của experiments/bench/run.py, code=None).
"""
import argparse
import collections
import concurrent.futures as cf
import glob
import json
import os
import pickle
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BENCH = os.path.join(ROOT, "experiments", "bench")
METHODS = os.path.join(ROOT, "experiments", "out", "methods")
sys.path[:0] = [ROOT, BENCH]

SPECS = {
    "baseline": os.path.join(BENCH, "readers", "baseline.py") + ":Baseline",
    "A": os.path.join(METHODS, "soft_reader", "reader.py") + ":SoftReader",
    "B": os.path.join(METHODS, "grid_sr", "grid_sr.py") + ":GridSR",
    "C": os.path.join(METHODS, "preproc_sweep", "preproc_sweep.py") + ":PreprocSweep",
    "D": os.path.join(METHODS, "engines", "engines.py") + ":UnionBest",
}
EDGE = 3            # bỏ detection chạm mép ảnh: QR có thể bị cắt
MAX_OBS = 150       # số crop tối đa giữ cho mỗi lượt
MIN_OBS = 2         # lượt ít hơn coi là nhiễu


def resolve(name):
    """'C' → (spec, kwargs); 'B+C' → Combo chạy lần lượt từng phần."""
    if "+" in name:
        parts = [resolve(p)[0] for p in name.split("+")]
        return os.path.join(BENCH, "readers", "combo.py") + ":Combo", {"parts": parts}
    if name in SPECS:
        return SPECS[name], {}
    if ":" in name:
        return name, {}
    sys.exit(f"không biết phương pháp {name!r}; có: {', '.join(SPECS)}, ghép bằng dấu +, hoặc <file.py>:<Class>")


class ReplaySource:
    """Phát lại thư mục TIFF đúng nhịp: frame mới nhất theo đồng hồ, frame cũ bị bỏ như camera thật."""

    def __init__(self, folder, fps):
        import cv2
        self._cv2, self.fps = cv2, fps
        self.files = sorted(glob.glob(os.path.join(folder, "*.tiff")))
        if not self.files:
            sys.exit(f"không có file .tiff trong {folder}")
        self.t0, self.finished = time.monotonic(), False

    def latest(self):
        i = int((time.monotonic() - self.t0) * self.fps)
        if i >= len(self.files):
            self.finished = True
            return None, i
        return self._cv2.imread(self.files[i], self._cv2.IMREAD_COLOR), i

    def close(self):
        pass


class CameraSource:
    finished = False

    def __init__(self, a, cfg):
        from camera.basler_manager import BaslerCameraManager
        from camera.conveyor import RunSettings
        self.mgr = BaslerCameraManager()
        cams = self.mgr.list_cameras()
        index = 0
        if a.serial:
            index = next((i for i, c in enumerate(cams) if c.GetSn() == a.serial), -1)
            if index < 0:
                sys.exit(f"không thấy camera serial {a.serial}; có: {[c.GetSn() for c in cams]}")
        if not cams or not self.mgr.open(index):
            sys.exit("không mở được camera (app hoặc pylon Viewer đang giữ?)")
        if a.roi:
            x, y, w, h = a.roi
            band_x, band_y = (x, w), (y, h)
        else:
            band_y = (cfg["band_y"], cfg["band_h"]) if cfg["band_enabled"] else None
            band_x = (cfg["band_x"], cfg["band_w"]) if cfg["band_x_enabled"] else None
        applied = self.mgr.apply_run_settings(RunSettings(exposure_us=a.exposure * 1000.0, analog_gain=a.gain,
                                                          band_x=band_x, band_y=band_y))
        print("áp dụng", applied, flush=True)
        time.sleep(0.5)

    def latest(self):
        return self.mgr.latest_frame()

    def close(self):
        self.mgr.close()


def make_obs(gray, det, seq, t):
    """Cắt crop quanh detection theo đúng định dạng của bộ chấm điểm; None nếu chạm mép ảnh."""
    import numpy as np
    h, w = gray.shape
    x1, y1, x2, y2 = (float(v) for v in det.bbox_xyxy)
    if x1 < EDGE or y1 < EDGE or x2 > w - EDGE or y2 > h - EDGE:
        return None
    m = max(45, 0.8 * max(x2 - x1, y2 - y1))
    cx1, cy1, cx2, cy2 = int(max(0, x1 - m)), int(max(0, y1 - m)), int(min(w, x2 + m)), int(min(h, y2 + m))
    o = np.array([cx1, cy1], np.float32)
    return dict(frame=seq, t=t, crop=gray[cy1:cy2, cx1:cx2].copy(), origin=o,
                bbox=np.asarray(det.bbox_xyxy, np.float32) - np.r_[o, o], quad=np.asarray(det.quad_xy, np.float32) - o,
                polygon=None if det.polygon_xy is None else np.asarray(det.polygon_xy, np.float32) - o,
                conf=float(det.confidence))


def short(text, n=22):
    if not text:
        return "-"
    return text if len(text) <= n else text[:n - 1] + "…"


def summarize(rows, names, codes, true_passes, path):
    import numpy as np
    lines = [f"\n=== {len(rows)} lượt có đủ quan sát" + (f" / {true_passes} lượt thật" if true_passes else "")]
    n = true_passes or len(rows)
    base = names[0]
    for name in names:
        texts = [r["results"][name]["text"] for r in rows if name in r["results"]]
        ms = [r["results"][name]["ms"] for r in rows if name in r["results"]]
        read = sum(1 for t in texts if t)
        out = sum(1 for t in texts if t and codes and t not in codes)
        only = sum(1 for r in rows if r["results"].get(name, {}).get("text") and not r["results"].get(base, {}).get("text"))
        errs = sum(1 for r in rows if r["results"].get(name, {}).get("error"))
        lines.append(f"{name:<10} đọc {read}/{n} ({100 * read / max(n, 1):.1f}%)  thêm so với {base}: {only}"
                     + (f"  mã ngoài danh sách: {out}" if codes else "")
                     + f"  lỗi {errs}  ms trung vị {np.median(ms) if ms else 0:.0f}, p95 {np.percentile(ms, 95) if ms else 0:.0f}")
    conflict = [r for r in rows if len({v["text"] for v in r["results"].values() if v["text"]}) > 1]
    lines.append(f"Lượt mà các phương pháp ra nội dung khác nhau: {len(conflict)}" +
                 (" → " + ", ".join(str(r["pass"]) for r in conflict[:10]) if conflict else ""))
    text = "\n".join(lines)
    print(text, flush=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--methods", default="baseline,C,B,B+C")
    ap.add_argument("--seconds", type=float, default=120)
    ap.add_argument("--device", default="auto", help="detector: auto (GPU nếu có) hoặc cpu (như máy hiện trường)")
    ap.add_argument("--config", default=os.path.join(ROOT, "experiments", "benchmark_basler.json"))
    ap.add_argument("--roi", type=int, nargs=4, metavar=("X", "Y", "W", "H"), help="vùng đọc, thay cho band trong config")
    ap.add_argument("--exposure", type=float, default=None, help="ms, mặc định theo config")
    ap.add_argument("--gain", type=float, default=None, help="dB, mặc định theo config")
    ap.add_argument("--k", type=int, default=5, help="số frame mỗi lượt đưa cho phương pháp, trải đều")
    ap.add_argument("--codes", default=None, help="file mã hợp lệ, mỗi dòng một mã")
    ap.add_argument("--true-passes", type=int, default=None, help="số lượt tem thật đã thả, làm mẫu số")
    ap.add_argument("--name", default=time.strftime("live_%Y%m%d_%H%M%S"))
    ap.add_argument("--serial", default=None)
    ap.add_argument("--replay", default=None, help="thư mục TIFF, thay cho camera")
    ap.add_argument("--replay-fps", type=float, default=25.0)
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    cfg = json.load(open(a.config, encoding="utf-8"))
    a.exposure = cfg["exposure_ms"] if a.exposure is None else a.exposure
    a.gain = cfg["analog_gain"] if a.gain is None else a.gain
    names = a.methods.split(",")
    specs = {n: resolve(n) for n in names}
    for n, (spec, kw) in specs.items():
        for s in kw.get("parts", [spec]):
            if not os.path.exists(s.rsplit(":", 1)[0]):
                sys.exit(f"thiếu file của phương pháp {n}: {s}")
    codes = None
    if a.codes:
        codes = {x.strip() for x in open(a.codes, encoding="utf-8") if x.strip() and not x.startswith("#")}
    out = os.path.join(ROOT, "experiments", "out", "live", a.name)
    if os.path.exists(out):
        sys.exit(f"đã có {out}, chọn --name khác")
    os.makedirs(os.path.join(out, "passes"))

    import torch  # noqa: F401  (nạp trước cv2/pypylon trên Windows)
    import cv2
    import logging
    import numpy as np
    import run as bench_run
    from api import Ctx, Obs
    from qr.detector import QRDetector
    from qr.tracker import Observation, PassTracker
    logging.disable(logging.INFO)

    print("nạp phương pháp:", ", ".join(names), flush=True)
    pools = {n: cf.ProcessPoolExecutor(1, initializer=bench_run._init, initargs=(s, kw)) for n, (s, kw) in specs.items()}
    detector = QRDetector(conf_th=0.3, imgsz=1280, device=a.device)
    print("detector:", detector.device, flush=True)
    source = ReplaySource(a.replay, a.replay_fps) if a.replay else CameraSource(a, cfg)
    tracker = PassTracker(max_gap=50, max_speed_px=30.0, strict=True)
    store = collections.defaultdict(list)
    pending, rows = [], []
    n_pass = 0
    jsonl = open(os.path.join(out, "results.jsonl"), "w", encoding="utf-8")
    first_seq = first_t = None
    last_seq, last_t = -1, time.monotonic()
    det_ms = []

    def submit(track):
        nonlocal n_pass
        kept = store.pop(track.track_id, [])
        if len(kept) < MIN_OBS:
            return
        n_pass += 1
        fps = (last_seq - first_seq) / max(last_t - first_t, 1e-3)
        speed = float(np.hypot(*track.velocity))
        ctx = Ctx(velocity=tuple(float(v) for v in track.velocity), fps=fps, exposure_ms=a.exposure,
                  blur_px=speed * fps * a.exposure / 1000.0)
        idx = np.linspace(0, len(kept) - 1, min(a.k, len(kept))).astype(int).tolist()
        obs = [Obs(gray=o["crop"], bbox=o["bbox"], quad=o["quad"], polygon=o["polygon"], conf=o["conf"],
                   origin=o["origin"], frame=o["frame"], t=o["t"]) for o in (kept[i] for i in idx)]
        pid = f"{n_pass:04d}"
        with open(os.path.join(out, "passes", pid + ".pkl"), "wb") as f:
            pickle.dump(dict(id=pid, clip=a.name, first=kept[0]["frame"], last=kept[-1]["frame"], code=None,
                             velocity=np.array(track.velocity), cx=float(kept[0]["origin"][0]), obs=kept), f)
        row = dict(**{"pass": n_pass}, first=kept[0]["frame"], last=kept[-1]["frame"], n_obs=len(kept), used=len(obs),
                   fps=round(fps, 1), speed_px_seq=round(speed, 2), blur_px=round(ctx.blur_px, 2), results={})
        futures = {n: (time.perf_counter(), pools[n].submit(bench_run.read_obs, obs, ctx)) for n in names}
        pending.append((row, futures))

    def collect(block=False):
        for item in list(pending):
            row, futures = item
            if not block and not all(f.done() for _, f in futures.values()):
                continue
            for n, (t0, f) in futures.items():
                try:
                    text, ms = f.result()
                    row["results"][n] = dict(text=text, ms=round(ms, 1), error=None)
                except Exception as e:
                    row["results"][n] = dict(text=None, ms=0.0, error=repr(e))
            pending.remove(item)
            rows.append(row)
            jsonl.write(json.dumps(row, ensure_ascii=False) + "\n")
            jsonl.flush()
            parts = [f"{n}: {short(v['text'])} ({v['ms'] / 1000:.1f}s)" + (" LỖI" if v["error"] else "")
                     for n, v in row["results"].items()]
            print(f"lượt {row['pass']:>3} [{row['used']}/{row['n_obs']} frame] " + " | ".join(parts), flush=True)

    print(f"Bắt đầu {a.seconds:g} s. Ctrl+C để dừng sớm.", flush=True)
    t_start = time.monotonic()
    try:
        while time.monotonic() - t_start < a.seconds and not source.finished:
            frame, seq = source.latest()
            if frame is None or seq == last_seq:
                collect()
                time.sleep(0.002)
                continue
            now = time.monotonic()
            first_seq, first_t = (seq, now) if first_seq is None else (first_seq, first_t)
            last_seq, last_t = seq, now
            t0 = time.perf_counter()
            dets = detector.detect(frame)
            det_ms.append((time.perf_counter() - t0) * 1000)
            gray = frame[:, :, 0]
            found = [(d, make_obs(gray, d, seq, now)) for d in dets]
            found = [(d, o) for d, o in found if o is not None]
            items = []
            for d, _ in found:
                x1, y1, x2, y2 = (float(v) for v in d.bbox_xyxy)
                items.append(Observation(((x1 + x2) / 2, (y1 + y2) / 2), max(x2 - x1, y2 - y1)))
            matched = tracker.match(seq, items)
            for track in tracker.update(seq, items):
                submit(track)
            for i, (_, o) in enumerate(found):
                track = matched.get(i)
                if track is None:
                    track = next((t for t in tracker.active if t.first_frame == seq and t.center == items[i].center), None)
                if track is not None and len(store[track.track_id]) < MAX_OBS:
                    store[track.track_id].append(o)
            collect()
    except KeyboardInterrupt:
        print("\ndừng thu hình", flush=True)
    finally:
        source.close()
    for track in tracker.finish():
        submit(track)
    print(f"\nĐã thu xong: detect trung vị {np.median(det_ms) if det_ms else 0:.0f} ms/frame, "
          f"{len(det_ms)} frame xử lý. Đang chờ {len(pending)} lượt trong hàng đợi...", flush=True)
    try:
        collect(block=True)
    except KeyboardInterrupt:
        print("bỏ phần còn lại trong hàng đợi", flush=True)
    jsonl.close()
    for p in pools.values():
        p.shutdown(wait=False, cancel_futures=True)
    summarize(rows, names, codes, a.true_passes, os.path.join(out, "summary.txt"))
    print("Kết quả:", out, flush=True)


if __name__ == "__main__":
    main()
