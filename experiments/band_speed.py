"""Đo camera và detect khi chỉ đọc dải băng: python experiments/band_speed.py <y> <h>. Không đổi config."""
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

Y, H = int(sys.argv[1]), int(sys.argv[2])
det = QRDetector(conf_th=0.3, imgsz=1280, device="auto")
mgr = BaslerCameraManager()
mgr.list_cameras()
if not mgr.open(0):
    sys.exit("không mở được camera")
try:
    for name, band in (("toàn khung", None), ("dải băng", (Y, H))):
        applied = mgr.apply_run_settings(RunSettings(exposure_us=6000.0, analog_gain=12, band_y=band))
        time.sleep(0.6)
        frames, seqs, last, t0 = [], [], -1, time.monotonic()
        while time.monotonic() - t0 < 3.0:
            frame, seq = mgr.latest_frame()
            if seq != last and frame is not None:
                seqs.append((seq, time.monotonic()))
                last = seq
                if len(frames) < 12:
                    frames.append(frame)
            time.sleep(0.0005)
        rate = (seqs[-1][0] - seqs[0][0]) / (seqs[-1][1] - seqs[0][1])
        f = np.ascontiguousarray(frames[-1])
        det.detect(f)
        ms, n = [], 0
        for g in frames[:12]:
            t = time.perf_counter()
            n = len(det.detect(np.ascontiguousarray(g)))
            ms.append((time.perf_counter() - t) * 1000)
        print(f"{name}: khung thật {f.shape[1]}x{f.shape[0]}, {rate:.1f} fps, detect {np.median(ms):.0f} ms, {n} QR, ok={applied['ok']}", flush=True)
finally:
    mgr.close()
