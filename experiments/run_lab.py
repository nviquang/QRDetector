"""Chạy thử nghiệm theo đồng hồ ảo: job chiếm bao nhiêu ms thì camera trôi đi bấy nhiêu frame.

  python experiments/run_lab.py calibrate
  python experiments/run_lab.py run --set dev --configs base,H0,H1 --out out/singles.jsonl
  python experiments/run_lab.py real --configs base,best
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import torch  # noqa: E402,F401  (nạp trước các thư viện khác trên Windows)
import cv2  # noqa: E402
import numpy as np  # noqa: E402
import logging  # noqa: E402

cv2.setNumThreads(int(os.environ.get("LAB_CV_THREADS", "2")))

from lab_reader import BASE, CODE_RE, LabConfig, LabReader, replace  # noqa: E402
from scenes import SemiScene, SimParams, SimScene, VideoScene  # noqa: E402

RESEARCH = os.environ.get("QR_RESEARCH_DATA", "C:/Users/nviquang/Documents/AISTDR/QRDetector-research/data")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")

# Cấu hình từng hướng: sẽ được ghép trong CONFIGS bên dưới
SINGLES = dict(
    base=dict(),
    H0=dict(fix_tracker=True),
    H1=dict(validate=True),
    H1v1=dict(validate=True, min_votes=1),
    H2=dict(gate=True),
    H3=dict(binarizers=True),
    H4=dict(fast_roi=True),
    H5=dict(best_frame=True),
    H5cheap=dict(expensive=False, stack_wechat=False),
    H6k3=dict(stack=3),
    H6k5=dict(stack=5),
    H7=dict(deblur=True),
    H7k005=dict(deblur=True, deblur_k=0.005),
    H8=dict(refine=True),
    H9=dict(modules=True),
    H5e3=dict(best_frame=True, best_period=3),
    NoW=dict(expensive=False, stack_wechat=False),   # bỏ hẳn WeChat
    SW=dict(expensive=False, stack_wechat=True),     # WeChat chỉ trên ảnh xếp chồng
    H7k05=dict(deblur=True, deblur_k=0.05),
    M16=dict(stack_max=16),
    Y200=dict(yolo_every_ms=200.0),
    Y800=dict(yolo_every_ms=800.0),
    PROD1=dict(),    # không phải LabReader: chạy qr.PassReader thật, xem ProductReader. Báo mã sau 1 phiếu
    PROD2=dict(),    # như PROD1, báo mã sau 2 phiếu
)


def config(name: str) -> LabConfig:
    """Tên ghép bằng dấu +, ví dụ ``H4+H6k3+H9``."""
    fields: dict = {}
    for part in name.split("+"):
        fields.update(SINGLES[part])
    return replace(BASE, name=name, **fields)


# Điều kiện bán thực: chọn theo lượt quét trên ảnh camera (sweep_semi.py), từ dễ đến gần giới hạn
SEMI_SCENES = {
    "A_v10_mo1_sang": dict(speed_mm_s=100, exposure_ms=4.3, contrast=(10, 120), noise=3.0),
    "B_v10_mo3_sang": dict(speed_mm_s=100, exposure_ms=12.9, contrast=(10, 120), noise=3.0),
    "C_v10_mo3_vua_nhieu": dict(speed_mm_s=100, exposure_ms=12.9, contrast=(10, 75), noise=7.0),
    "D_v10_mo1_toi": dict(speed_mm_s=100, exposure_ms=4.3, contrast=(8, 47), noise=3.0),
    "E_v20_mo3_toi": dict(speed_mm_s=200, exposure_ms=6.45, contrast=(8, 47), noise=3.0),
    "F_v30_mo3_rat_toi": dict(speed_mm_s=300, exposure_ms=4.3, contrast=(8, 33), noise=3.0),
    "G_v20_mo1_rat_toi": dict(speed_mm_s=200, exposure_ms=2.15, contrast=(8, 33), noise=3.0),
    "H_v20_mo6_sang": dict(speed_mm_s=200, exposure_ms=12.9, contrast=(10, 120), noise=3.0),
}

# Điều kiện mô phỏng: 0,43 mm/px, QR 25 mm (2,77 px/ô), dải 2448×768, 50 fps
SCENES = {
    # Băng chậm, exposure mặc định của bản demo: vệt mờ ~3 px (~1 ô)
    "v10_e12.9": dict(speed_mm_s=100, exposure_ms=12.9, contrast=(8, 47), noise=8.0),
    # Exposure rút theo tốc độ để giữ vệt mờ ~3 px, ảnh tối đi tương ứng
    "v20_e6.45": dict(speed_mm_s=200, exposure_ms=6.45, contrast=(5, 33), noise=6.0),
    "v30_e4.3": dict(speed_mm_s=300, exposure_ms=4.3, contrast=(4, 28), noise=5.0),
    # Giữ exposure mặc định khi băng nhanh: đủ sáng nhưng mờ ~6 px
    # Đối chứng: đủ sáng, bản hiện tại đã đọc tốt — không được tụt
    "ctl_bright": dict(speed_mm_s=100, exposure_ms=12.9, contrast=(10, 120), noise=3.0),
    # Thử độ bền: nhiễu tương quan (xếp chồng khó hơn nhiễu trắng) và tốc độ dao động ±15%
    "rob_corr": dict(speed_mm_s=200, exposure_ms=6.45, contrast=(5, 33), noise=6.0, noise_blur=0.7),
    "rob_jit": dict(speed_mm_s=150, exposure_ms=12.9, contrast=(10, 75), noise=7.0, speed_jitter=0.15),
    "v15_e12.9": dict(speed_mm_s=150, exposure_ms=12.9, contrast=(10, 75), noise=7.0),
    "v20_e12.9": dict(speed_mm_s=200, exposure_ms=12.9, contrast=(10, 75), noise=7.0),
}


def make_scene(name: str, seed: int, detector, n_passes: int = 40) -> SimScene:
    scene = SimScene(SimParams(name=name, seed=seed, n_passes=n_passes, **SCENES[name]), detector)
    return scene


class _ScenePipeline:
    """Pipeline cho qr.PassReader: detect lấy từ cache của scene, cùng kết quả với LabReader."""

    multi_frame = True
    code_pattern = None
    roi_margin = 0.25

    def __init__(self, scene):
        self.scene = scene
        self.idx = 0
        self.detected = False

    def detect(self, image_bgr):
        self.detected = True
        return self.scene.detect(self.idx)


class ProductReader:
    """Bọc qr.PassReader bằng giao diện LabReader, đồng hồ ảo theo frame."""

    def __init__(self, cfg: LabConfig, scene):
        from qr.pass_reader import PassReader
        self.cfg, self.scene = cfg, scene
        self.pipe = _ScenePipeline(scene)
        self.now = 0.0
        votes = 2 if cfg.name == "PROD2" else 1
        self.reader = PassReader(self.pipe, clock=lambda: self.now, min_votes=votes, announce_votes=votes)
        self.reader.set_exposure_ms(scene.exposure_ms)
        self.emitted, self.all_finished = [], []
        self.jobs = dict(yolo=0, fast=0)
        self.total_ms = 0.0
        self.attempts = self.gated = self.skipped = 0
        self.step_hits, self.step_ms = {}, {}

    def next_gap_frames(self, idx: int, base_n: int) -> int:
        return self.reader.decode_every(base_n)

    def process(self, frame, idx: int, now_s: float) -> float:
        self.pipe.idx, self.pipe.detected, self.now = idx, False, now_s
        r = self.reader.process(frame, idx)
        ms = r.cascade_ms + (self.scene.detect_ms if self.pipe.detected else 0.0)
        self.jobs["yolo" if self.pipe.detected else "fast"] += 1
        self.total_ms += ms
        self.skipped += r.skipped
        self.all_finished += r.finished
        self.emitted += [(t.text, idx, float(t.center[0]), float(t.center[1]), t.track_id) for t in r.first_reads]
        return ms

    def finish(self):
        self.all_finished += self.reader.flush()


def simulate(cfg: LabConfig, scene, memo: dict, base_n: int) -> dict:
    reader = ProductReader(cfg, scene) if cfg.name.startswith("PROD") else LabReader(cfg, scene, memo)
    t = 0.0
    last_idx = -1
    t0 = time.perf_counter()
    while True:
        gap = reader.next_gap_frames(last_idx, base_n)
        # Frame sớm nhất có sẵn sau thời điểm t, theo nhịp gap
        idx = int(np.ceil(t * scene.fps / gap - 1e-9)) * gap
        idx = max(idx, last_idx + 1)
        if idx >= scene.n_frames:
            break
        ms = reader.process(scene.frame(idx), idx, idx / scene.fps)
        last_idx = idx
        t = idx / scene.fps + ms / 1000.0
    reader.finish()
    scene.save()
    return score(reader, scene, base_n, time.perf_counter() - t0)


def score(reader, scene, base_n: int, wall: float) -> dict:
    cfg = reader.cfg
    n = len(scene.passes)
    if scene.kind == "semi":
        read = 0
        lags = []
        for p in scene.passes:
            hits = [e[1] for e in reader.emitted if e[0] == p.text and p.first <= e[1] <= p.last + 110]
            if hits:
                read += 1
                lags.append((hits[0] - p.first) / scene.fps)
        wrong = [e[0] for e in reader.emitted if e[0] not in scene.codes]
    elif scene.kind == "sim":
        emitted_texts = {e[0] for e in reader.emitted}
        read = sum(p.text in emitted_texts for p in scene.passes)
        wrong = [e[0] for e in reader.emitted if e[0] not in scene.codes]
        lags = []
        first = {}
        for e in reader.emitted:
            first.setdefault(e[0], e[1])
        for p in scene.passes:
            if p.text in first:
                lags.append((first[p.text] - p.first) / scene.fps)
    else:
        read_set = set()
        wrong = []
        for text, idx, cx, cy, _ in reader.emitted:
            if (scene.codes and text not in scene.codes) or not CODE_RE.match(text):
                wrong.append(text)
                continue
            best, best_d = None, 1e9
            for i, p in enumerate(scene.passes):
                if idx < p.first - 3 or idx > p.last + 3:
                    continue
                j = int(np.argmin(np.abs(p.x[:, 0] - idx)))
                d = float(np.hypot(p.x[j, 1] - cx, p.x[j, 2] - cy))
                if d < best_d:
                    best, best_d = i, d
            if best is not None:
                read_set.add(best)
        read = len(read_set)
        lags = []
    jobs = reader.jobs["yolo"] + reader.jobs["fast"]
    return dict(
        config=cfg.name, scene=scene.key, passes=n, read=read,
        rate=round(read / max(n, 1), 4), wrong=len(wrong), wrong_texts=sorted(set(wrong))[:5],
        emitted=len(reader.emitted), emitted_texts=sorted({e[0] for e in reader.emitted})[:12],
        tracks=len(reader.all_finished),
        conflicts=sum(t.conflicting for t in reader.all_finished),
        attempts_per_pass=round(reader.attempts / max(n, 1), 2),
        yolo_jobs=reader.jobs["yolo"], fast_jobs=reader.jobs["fast"],
        ms_per_job=round(reader.total_ms / max(jobs, 1), 1),
        detect_ms=round(scene.detect_ms, 1),
        step_hits=reader.step_hits,
        step_ms={k: round(v) for k, v in reader.step_ms.items()},
        gated=reader.gated, skipped=reader.skipped,
        lag_s=round(float(np.median(lags)), 3) if lags else None,
        wall_s=round(wall, 1),
    )


def load_detector():
    logging.disable(logging.INFO)
    from qr.detector import QRDetector
    det = QRDetector(conf_th=0.3, imgsz=1280, device="auto")
    return det


def cmd_run(args):
    detector = load_detector()
    names = args.scenes.split(",") if args.scenes else list(SCENES)
    configs = [config(c) for c in args.configs.split(",")]
    out_path = args.out
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    done = set()
    if os.path.exists(out_path):
        with open(out_path, encoding="utf-8") as f:
            for line in f:
                row = json.loads(line)
                done.add((row["config"], row["scene"]))
    for name in names:
        for seed in args.seeds:
            scene = make_scene(name, seed, detector, args.passes)
            memo: dict = {}
            for cfg in configs:
                if (cfg.name, scene.key) in done:
                    continue
                row = simulate(cfg, scene, memo, base_n=5)
                row["group"] = name
                row["seed"] = seed
                with open(out_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
                print(f"{name:10} s{seed} {cfg.name:24} {row['read']:3}/{row['passes']:<3} wrong={row['wrong']} "
                      f"att/pass={row['attempts_per_pass']:<6} ms/job={row['ms_per_job']:<6} "
                      f"lag={row['lag_s']} wall={row['wall_s']}s", flush=True)


def real_scenes(detector) -> list[VideoScene]:
    paths = sorted(glob.glob(RESEARCH + "/video/*.mp4") + glob.glob(RESEARCH + "/videos/*.avi"))
    return [VideoScene(p, detector) for p in paths]


def cmd_real(args):
    detector = load_detector()
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    configs = [config(c) for c in args.configs.split(",")]
    done = set()
    if os.path.exists(args.out):
        with open(args.out, encoding="utf-8") as f:
            for line in f:
                row = json.loads(line)
                done.add((row["config"], row["scene"]))
    codes = set(args.codes.split(",")) if args.codes else set()
    for scene in real_scenes(detector):
        scene.build_oracle()
        scene.codes = codes
        memo: dict = {}
        for cfg in configs:
            if (cfg.name, scene.key) in done:
                continue
            row = simulate(cfg, scene, memo, base_n=1)
            row["group"] = "real"
            with open(args.out, "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            print(f"{scene.key[-18:]:18} {cfg.name:24} {row['read']:3}/{row['passes']:<3} wrong={row['wrong']} "
                  f"{row['wrong_texts']} att/pass={row['attempts_per_pass']:<6} ms/job={row['ms_per_job']:<6} "
                  f"wall={row['wall_s']}s", flush=True)


def cmd_semi(args):
    detector = load_detector()
    from qr.improved_pipeline import ImprovePipeline
    pipe = ImprovePipeline(detector=detector)

    def clean_read(image, det):
        hit = pipe.decode_detection(image, det)
        return hit.text if hit else None

    paths = sorted(glob.glob(RESEARCH + "/images/*.bmp"))
    configs = [config(c) for c in args.configs.split(",")]
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    done = set()
    if os.path.exists(args.out):
        with open(args.out, encoding="utf-8") as f:
            done = {(r["config"], r["scene"]) for r in map(json.loads, f)}
    for name in args.scenes.split(","):
        for seed in args.seeds:
            cond = SEMI_SCENES[name]
            scene = SemiScene(name, paths, detector, seed, args.repeats, clean_read, **cond)
            print(name, "ảnh dùng được", len(scene.items), "lượt", len(scene.passes), "mã", sorted(scene.codes), flush=True)
            memo: dict = {}
            for cfg in configs:
                if (cfg.name, scene.key) in done:
                    continue
                row = simulate(cfg, scene, memo, base_n=5)
                row["group"] = name
                row["seed"] = seed
                with open(args.out, "a", encoding="utf-8") as f:
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
                print(f"{name:10} s{seed} {cfg.name:24} {row['read']:3}/{row['passes']:<3} wrong={row['wrong']} "
                      f"att/pass={row['attempts_per_pass']:<6} ms/job={row['ms_per_job']:<6} lag={row['lag_s']} "
                      f"wall={row['wall_s']}s", flush=True)


def cmd_calibrate(args):
    detector = load_detector()
    os.makedirs(OUT, exist_ok=True)
    for name in (args.scenes.split(",") if args.scenes else SCENES):
        scene = make_scene(name, 99, detector, 12)
        cv2.imwrite(os.path.join(OUT, f"sample_{name}.png"),
                    scene.frame(scene.passes[0].first + (scene.passes[0].last - scene.passes[0].first) // 2))
        row = simulate(config("base"), scene, {}, base_n=5)
        print(name, "blur", round(scene.p.blur_px, 1), "px/frame", round(scene.p.speed_px_frame, 2),
              f"read {row['read']}/{row['passes']}", "wrong", row["wrong"], "tracks", row["tracks"],
              "att/pass", row["attempts_per_pass"], "ms/job", row["ms_per_job"], "det", row["detect_ms"],
              "hits", row["step_hits"], "wall", row["wall_s"], flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("calibrate")
    c.add_argument("--scenes", default="")
    r = sub.add_parser("run")
    r.add_argument("--configs", required=True)
    r.add_argument("--scenes", default="")
    r.add_argument("--seeds", type=int, nargs="+", default=[1])
    r.add_argument("--passes", type=int, default=40)
    r.add_argument("--out", required=True)
    v = sub.add_parser("real")
    v.add_argument("--configs", required=True)
    v.add_argument("--codes", default="")
    v.add_argument("--out", required=True)
    b = sub.add_parser("semi")
    b.add_argument("--configs", required=True)
    b.add_argument("--scenes", required=True)
    b.add_argument("--seeds", type=int, nargs="+", default=[1])
    b.add_argument("--repeats", type=int, default=3)
    b.add_argument("--out", required=True)
    a = p.parse_args()
    dict(calibrate=cmd_calibrate, run=cmd_run, real=cmd_real, semi=cmd_semi)[a.cmd](a)
