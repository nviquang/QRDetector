"""Chụp frame liên tiếp từ Basler với cấu hình đang dùng: python experiments/capture_basler.py [số frame]"""
import json
import os
import sys
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
sys.stdout.reconfigure(encoding="utf-8")

import cv2  # noqa: E402

from camera.basler_manager import BaslerCameraManager  # noqa: E402
from camera.camera_manager import RunSettings  # noqa: E402

OUT = os.path.join(_ROOT, "experiments", "out", "basler_live")
count = int(sys.argv[1]) if len(sys.argv) > 1 else 40
with open(os.path.join(_ROOT, "config", "basler_settings.json"), encoding="utf-8") as f:
    cfg = json.load(f)
os.makedirs(OUT, exist_ok=True)
mgr = BaslerCameraManager()
print("camera", len(mgr.list_cameras()))
if not mgr.open(0):
    sys.exit("không mở được camera (app khác đang giữ?)")
try:
    applied = mgr.apply_run_settings(RunSettings(exposure_us=cfg["exposure_ms"] * 1000.0, analog_gain=cfg["analog_gain"],
                                                 band_x=None, band_y=None))
    print("applied", applied)
    time.sleep(0.5)
    frames, last, t0 = [], -1, time.monotonic()
    while len(frames) < count and time.monotonic() - t0 < 30:
        frame, seq = mgr.latest_frame()
        if frame is not None and seq != last:
            frames.append((seq, time.monotonic(), frame))
            last = seq
        time.sleep(0.002)
finally:
    mgr.close()
dt = frames[-1][1] - frames[0][1]
print("frame", len(frames), "seq/s", round((frames[-1][0] - frames[0][0]) / dt, 1))
for seq, _, frame in frames:
    cv2.imwrite(os.path.join(OUT, f"{seq:06d}.png"), frame[:, :, 0])
print("lưu tại", OUT)
