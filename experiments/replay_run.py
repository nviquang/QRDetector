"""Phát lại đoạn ghi của record_basler.py qua bản cũ và bản mới, đồng hồ ảo theo thời gian xử lý thật.

python experiments/replay_run.py <tên> [số lượt thật]
YOLO chỉ chạy một lần cho mỗi frame rồi nhớ lại, nên hai bản nhận cùng kết quả detect; thời gian detect lấy trung vị đo được.
"""
import collections
import json
import os
import pickle
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
from qr.pass_reader import PassReader  # noqa: E402

logging.disable(logging.INFO)
NAME = sys.argv[1]
TRUE_PASSES = int(sys.argv[2]) if len(sys.argv) > 2 else None
OUT = os.path.join(_ROOT, "experiments", "out", "runs", NAME)
meta = json.load(open(os.path.join(OUT, "index.json"), encoding="utf-8"))
h, w = meta["shape"]
raw = np.memmap(os.path.join(OUT, "frames.bin"), dtype=np.uint8, mode="r", shape=(len(meta["frames"]), h, w))
seqs = np.array([f[0] for f in meta["frames"]])
times = np.array([f[1] for f in meta["frames"]])
detector = QRDetector(conf_th=0.3, imgsz=1280, device="auto")
cache_path = os.path.join(OUT, "detections.pkl")
cache, det_ms = ({}, []) if not os.path.exists(cache_path) else pickle.load(open(cache_path, "rb"))


def bgr(i):
    return np.ascontiguousarray(cv2.cvtColor(np.array(raw[i]), cv2.COLOR_GRAY2BGR))


class Cached:
    device = "cached"
    gpu_available = True

    def __init__(self):
        self.index = 0
        self.called = False

    def warmup(self, shape=None):
        pass

    def detect(self, image):
        self.called = True
        if self.index not in cache:
            t = time.perf_counter()
            cache[self.index] = detector.detect(image)
            det_ms.append((time.perf_counter() - t) * 1000)
        return cache[self.index]


def run(multi_frame: bool, base_n: int = 5):
    source = Cached()
    pipe = ImprovePipeline(detector=source, multi_frame=multi_frame)
    now = [0.0]
    reader = PassReader(pipe, clock=lambda: now[0])
    reader.set_exposure_ms(meta["exposure_ms"])
    finished, reads, jobs, busy = [], [], 0, 0.0
    t_free, last = 0.0, -1
    fixed = float(np.median(det_ms)) if len(det_ms) >= 5 else 180.0
    while True:
        gap = reader.decode_every(base_n)
        # frame sớm nhất đã có khi worker rảnh, cách lần gửi trước ít nhất ``gap`` seq
        i = int(np.searchsorted(times, t_free))
        if last >= 0:
            i = max(i, int(np.searchsorted(seqs, seqs[last] + gap)))
        if i >= len(seqs):
            break
        source.index, source.called, now[0] = i, False, float(times[i])
        r = reader.process(bgr(i), int(seqs[i]))
        ms = r.cascade_ms + (fixed if source.called else 0.0)
        t_free = float(times[i]) + ms / 1000.0
        last, jobs, busy = i, jobs + 1, busy + ms
        finished += r.finished
        reads += [(t.text, float(times[i]), t.track_id, t.first_frame) for t in r.first_reads]
    finished += reader.flush()
    real = [t for t in finished if t.text or t.observations >= 2]
    seq_rate = (seqs[-1] - seqs[0]) / max(times[-1] - times[0], 1e-3)
    lags = [(r[1] - (r[3] - seqs[0]) / seq_rate) for r in reads]
    return dict(reads=collections.Counter(r[0] for r in reads), passes=len(real), read_passes=sum(bool(t.text) for t in real),
                conflict=sum(t.conflicting for t in real), jobs=jobs, ms_job=round(busy / max(jobs, 1)),
                lag_median=round(float(np.median(lags)), 2) if lags else None)


results = {}
for name, flag in (("cũ", False), ("mới", True)):
    results[name] = run(flag)
    pickle.dump((cache, det_ms), open(cache_path, "wb"))
    r = results[name]
    print(f"== {name}: lượt theo dõi {r['passes']}, có mã {r['read_passes']}, mâu thuẫn {r['conflict']}, {r['jobs']} job, "
          f"{r['ms_job']} ms/job, trễ trung vị {r['lag_median']} s", flush=True)
    print("   mã (lần báo):", dict(r["reads"]), flush=True)
    if TRUE_PASSES:
        print(f"   số lần báo mã / số lượt thật: {sum(r['reads'].values())}/{TRUE_PASSES}", flush=True)
print("detect trung vị", round(float(np.median(det_ms))), "ms")
