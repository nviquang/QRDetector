"""Quét exposure và gain trên Basler bằng SDK, lưu frame thật: python experiments/sweep_exposure.py <tên đợt>

Không đổi config; camera nhận lại cấu hình của app khi app Bắt đầu. Lưu dải quanh tem cho mọi frame và vài frame toàn khung.
"""
import json
import os
import sys
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
sys.stdout.reconfigure(encoding="utf-8")

import torch  # noqa: F401,E402
import cv2  # noqa: E402
import numpy as np  # noqa: E402

from qr.detector import QRDetector  # noqa: E402
from camera.basler_manager import BaslerCameraManager  # noqa: E402
from camera.conveyor import RunSettings  # noqa: E402

RUN = sys.argv[1] if len(sys.argv) > 1 else "f4"
OUT = os.path.join(_ROOT, "experiments", "out", "exposure_" + RUN)
EXPOSURES_MS = (1, 2, 3, 4, 6, 8, 12, 16, 23, 32)
GAINS_DB = (6, 12, 18)
FRAMES, FULL = 16, 3
os.makedirs(OUT, exist_ok=True)
det = QRDetector(conf_th=0.3, imgsz=1280, device="auto")
mgr = BaslerCameraManager()
print("camera", len(mgr.list_cameras()))
if not mgr.open(0):
    sys.exit("không mở được camera (app khác đang giữ?)")


def grab(n):
    frames, last, t0, seqs = [], -1, time.monotonic(), []
    while len(frames) < n and time.monotonic() - t0 < 15:
        frame, seq = mgr.latest_frame()
        if frame is not None and seq != last:
            frames.append(frame)
            seqs.append((seq, time.monotonic()))
            last = seq
        time.sleep(0.001)
    rate = (seqs[-1][0] - seqs[0][0]) / max(seqs[-1][1] - seqs[0][1], 1e-3)
    return frames, rate


try:
    meta = dict(runs=[])
    mgr.apply_run_settings(RunSettings(exposure_us=23000.0, analog_gain=12))
    time.sleep(0.5)
    ref = grab(1)[0][0]
    cv2.imwrite(os.path.join(OUT, "ref.png"), ref[:, :, 0])
    det.detect(ref)
    dets = det.detect(ref)
    print("QR tham chiếu", [[round(float(v)) for v in d.bbox_xyxy] for d in dets])
    if not dets:
        sys.exit("không thấy QR nào")
    xs = [float(v) for d in dets for v in d.bbox_xyxy[[0, 2]]]
    ys = [float(v) for d in dets for v in d.bbox_xyxy[[1, 3]]]
    h, w = ref.shape[:2]
    x0, x1 = max(0, int(min(xs)) - 200), min(w, int(max(xs)) + 200)
    y0, y1 = max(0, int(min(ys)) - 200), min(h, int(max(ys)) + 200)
    meta["crop"] = [x0, y0, x1, y1]
    meta["bboxes"] = [[float(v) for v in d.bbox_xyxy] for d in dets]
    for gain in GAINS_DB:
        for ms in EXPOSURES_MS:
            applied = mgr.apply_run_settings(RunSettings(exposure_us=ms * 1000.0, analog_gain=gain))
            time.sleep(0.3)
            grab(2)   # bỏ frame còn thông số cũ
            frames, rate = grab(FRAMES)
            folder = os.path.join(OUT, f"g{gain:02d}_e{ms:02d}")
            os.makedirs(folder, exist_ok=True)
            for i, f in enumerate(frames):
                cv2.imwrite(os.path.join(folder, f"c{i:02d}.png"), f[y0:y1, x0:x1, 0])
                if i < FULL:
                    cv2.imwrite(os.path.join(folder, f"f{i:02d}.png"), f[:, :, 0])
            row = dict(gain=gain, ms=ms, applied_us=applied["exposure_us"], applied_gain=applied["analog_gain"],
                       ok=applied["ok"], fps=round(rate, 1), mean=round(float(frames[0].mean()), 1))
            meta["runs"].append(row)
            print(row, flush=True)
    with open(os.path.join(OUT, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=1)
finally:
    mgr.close()
print("xong", OUT)
