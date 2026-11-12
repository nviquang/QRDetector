"""Chấm một phương pháp: python experiments/bench/run.py --method <file.py>:<Class> [--conds ...] [--ks ...] [--seeds N]
[--jobs N] [--clips gan,xa] [--out kq.json] [--kwargs '{"a":1}']

Mặc định chạy trên tập phát triển. Điều kiện thử:
  goc    ảnh thật               nho80  thu nhỏ ×0,8 (≈2,05 px/ô)     nho65  thu nhỏ ×0,65 (≈1,65 px/ô)
  mo     thêm vệt mờ 4 px theo hướng chạy (≈1,6 ô)                  nhieu  tối đi ×0,6 và nhiễu σ=5
k = số frame của lượt được phép dùng (CPU chỉ xử lý được vài frame mỗi lượt).
"""
import argparse
import collections
import concurrent.futures as cf
import glob
import importlib.util
import json
import os
import pickle
import sys
import time
import zlib

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
from api import Ctx, Obs  # noqa: E402

CONDS = ("goc", "nho80", "nho65", "mo", "nhieu")
SCALES = {"nho80": 0.8, "nho65": 0.65}
FPS, EXPOSURE_MS = 25.0, 3.0
_method = None


def load_class(spec):
    path, cls = spec.rsplit(":", 1)
    path = os.path.abspath(path)
    sys.path.insert(0, os.path.dirname(path))
    m = importlib.util.spec_from_file_location("bench_method_" + str(zlib.crc32(path.encode())), path)
    mod = importlib.util.module_from_spec(m)
    sys.modules[m.name] = mod
    m.loader.exec_module(mod)
    return getattr(mod, cls)


def _init(spec, kwargs):
    global _method
    cv2.setNumThreads(1)
    os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
    sys.path.insert(0, ROOT)
    import torch  # noqa: F401  (nạp trước các thư viện khác trên Windows)
    torch.set_num_threads(1)
    _method = load_class(spec)(**kwargs)


def read_obs(obs, ctx):
    """Gọi phương pháp đã nạp bởi ``_init`` trên một lượt; dùng cho chạy trên luồng camera (experiments/live_methods.py)."""
    t0 = time.perf_counter()
    text = _method.read_pass(obs, ctx)
    return text, (time.perf_counter() - t0) * 1000


def motion_kernel(length, vx, vy):
    size = (int(np.ceil(length)) * 2 + 3) | 1
    k = np.zeros((size * 8, size * 8), np.float32)
    n = np.hypot(vx, vy) or 1.0
    dx, dy = vx / n, vy / n
    c = size * 4
    for s in np.linspace(-length / 2 * 8, length / 2 * 8, int(length * 16) + 1):
        k[int(round(c + dy * s)), int(round(c + dx * s))] = 1
    k = cv2.resize(k, (size, size), interpolation=cv2.INTER_AREA)
    return k / k.sum()


def apply_cond(o, cond, vel, rng):
    g, s = o["crop"], SCALES.get(cond, 1.0)
    if s != 1.0:
        g = cv2.resize(g, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    if cond == "mo":
        g = cv2.filter2D(g, -1, motion_kernel(4.0, vel[0], vel[1]), borderType=cv2.BORDER_REPLICATE)
    if cond == "nhieu":
        g = np.clip(g.astype(np.float32) * 0.6 + rng.normal(0, 5, g.shape), 0, 255).astype(np.uint8)
    return Obs(gray=np.ascontiguousarray(g), bbox=o["bbox"] * s, quad=o["quad"] * s,
               polygon=None if o["polygon"] is None else o["polygon"] * s, conf=o["conf"], origin=o["origin"] * s,
               frame=o["frame"], t=o["t"])


def job(args):
    path, cond, k, seed = args
    tr = pickle.load(open(path, "rb"))
    rng = np.random.default_rng(zlib.crc32(f"{tr['id']}|{cond}|{k}|{seed}".encode()))
    n = len(tr["obs"])
    idx = sorted(rng.choice(n, size=min(k, n), replace=False).tolist()) if k > 0 else list(range(n))
    s = SCALES.get(cond, 1.0)
    vel = tuple(float(v) * s for v in tr["velocity"])
    obs = [apply_cond(tr["obs"][i], cond, tr["velocity"], rng) for i in idx]
    speed = float(np.hypot(*vel))
    blur = speed * FPS * EXPOSURE_MS / 1000.0 + (4.0 if cond == "mo" else 0.0)
    ctx = Ctx(velocity=vel, fps=FPS, exposure_ms=EXPOSURE_MS, blur_px=blur)
    t0 = time.perf_counter()
    try:
        text = _method.read_pass(obs, ctx)
    except Exception as e:  # lỗi phương pháp tính là không đọc được nhưng phải được báo
        return dict(id=tr["id"], clip=tr["clip"], cond=cond, k=k, seed=seed, text=None, ok=False, wrong=False,
                    ms=(time.perf_counter() - t0) * 1000, error=repr(e))
    ms = (time.perf_counter() - t0) * 1000
    return dict(id=tr["id"], clip=tr["clip"], cond=cond, k=k, seed=seed, text=text, ok=text == tr["code"],
                wrong=bool(text) and text != tr["code"], ms=ms, error=None)


def rate(rs):
    return 100.0 * sum(r["ok"] for r in rs) / max(len(rs), 1)


def summarize(res, conds, ks, name):
    print(f"\n=== {name}: {len({r['id'] for r in res})} lượt, {len(res)} lần chấm")
    print("Tỉ lệ đọc đúng theo lượt (%) [số lần báo sai]")
    print("cond    " + "".join(f"k={k:<9}" for k in ks))
    for c in conds:
        cells = []
        for k in ks:
            rs = [r for r in res if r["cond"] == c and r["k"] == k]
            cells.append(f"{rate(rs):5.1f} [{sum(r['wrong'] for r in rs)}]".ljust(11))
        print(f"{c:<8}" + "".join(cells))
    clips = sorted({r["clip"] for r in res})
    print("Theo đoạn (mọi k, cond): " + ", ".join(f"{c}={rate([r for r in res if r['clip'] == c]):.1f}" for c in clips))
    ms = [r["ms"] for r in res]
    print(f"ĐIỂM TỔNG = {rate(res):.2f}%   báo sai {sum(r['wrong'] for r in res)}/{len(res)}   "
          f"lỗi code {sum(1 for r in res if r['error'])}   ms/lượt trung vị {np.median(ms):.0f}, p95 {np.percentile(ms, 95):.0f}")
    errs = collections.Counter(r["error"] for r in res if r["error"])
    if errs:
        print("Lỗi:", errs.most_common(3))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--method", required=True)
    ap.add_argument("--kwargs", default="{}")
    ap.add_argument("--tracks", default=os.environ.get("QR_BENCH_TRACKS",
                                                       os.path.join(ROOT, "experiments", "out", "bench", "tracks_dev")))
    ap.add_argument("--conds", default=",".join(CONDS))
    ap.add_argument("--ks", default="1,3,5")
    ap.add_argument("--seeds", type=int, default=2)
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--clips", default="")
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    paths = sorted(glob.glob(os.path.join(a.tracks, "*.pkl")))
    if a.clips:
        paths = [p for p in paths if os.path.basename(p).split("_")[0] in a.clips.split(",")]
    conds, ks = a.conds.split(","), [int(x) for x in a.ks.split(",")]
    todo = [(p, c, k, s) for p in paths for c in conds for k in ks for s in range(a.seeds)]
    res = []
    t0 = time.time()
    with cf.ProcessPoolExecutor(a.jobs, initializer=_init, initargs=(a.method, json.loads(a.kwargs))) as ex:
        for n, r in enumerate(ex.map(job, todo, chunksize=2)):
            res.append(r)
            if n % 100 == 0:
                print(f"  {n}/{len(todo)}  {time.time() - t0:.0f}s", flush=True)
    summarize(res, conds, ks, a.method)
    if a.out:
        json.dump(res, open(a.out, "w", encoding="utf-8"), ensure_ascii=False)


if __name__ == "__main__":
    main()
