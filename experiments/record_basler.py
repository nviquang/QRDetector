"""Ghi frame không nén từ Basler khi băng chạy, theo config/basler_settings.json.

python experiments/record_basler.py <tên> <số giây> [--config file.json] [--fps N] [--note "..."]
Kết quả: experiments/out/runs/<tên>/frames.bin + index.json. Phát lại bằng experiments/replay_run.py.
--config: mặc định config/basler_settings.json; video chuẩn dùng experiments/benchmark_basler.json.
--fps: khóa tốc độ khung (mặc định chạy nhanh nhất camera cho phép, có thể bỏ frame khi ghi đĩa chậm).
"""
import argparse
import json
import os
import queue
import shutil
import sys
import threading
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
sys.stdout.reconfigure(encoding="utf-8")

from camera.basler_manager import BaslerCameraManager  # noqa: E402
from camera.conveyor import RunSettings  # noqa: E402
from pypylon import pylon  # noqa: E402

parser = argparse.ArgumentParser()
parser.add_argument("name")
parser.add_argument("seconds", type=float)
parser.add_argument("--config", default=os.path.join(_ROOT, "config", "basler_settings.json"))
parser.add_argument("--fps", type=float, default=None)
parser.add_argument("--note", default="")
args = parser.parse_args()
NAME, SECONDS = args.name, args.seconds
OUT = os.path.join(_ROOT, "experiments", "out", "runs", NAME)
if os.path.exists(os.path.join(OUT, "frames.bin")):
    sys.exit(f"đã có đoạn ghi tại {OUT}, chọn tên khác")
os.makedirs(OUT, exist_ok=True)
cfg = json.load(open(args.config, encoding="utf-8"))
band_y = (cfg["band_y"], cfg["band_h"]) if cfg["band_enabled"] else None
band_x = (cfg["band_x"], cfg["band_w"]) if cfg["band_x_enabled"] else None
mgr = BaslerCameraManager()
mgr.list_cameras()
if not mgr.open(0):
    sys.exit("không mở được camera (app hoặc pylon Viewer đang giữ?)")
index, dropped = [], 0
q: queue.Queue = queue.Queue(maxsize=400)


def writer():
    with open(os.path.join(OUT, "frames.bin"), "wb") as f:
        while True:
            item = q.get()
            if item is None:
                return
            f.write(item.tobytes())


thread = threading.Thread(target=writer)
try:
    applied = mgr.apply_run_settings(RunSettings(exposure_us=cfg["exposure_ms"] * 1000.0, analog_gain=cfg["analog_gain"],
                                                 band_x=band_x, band_y=band_y))
    print("áp dụng", applied, flush=True)
    resulting_fps = None
    if args.fps:
        with mgr._sdk_lock:                       # khóa fps: phải dừng grab vì camera khóa tham số khi đang grab
            cam = mgr.handle
            cam.StopGrabbing()
            try:
                cam.AcquisitionFrameRateEnable.Value = True
                cam.AcquisitionFrameRate.Value = min(args.fps, cam.AcquisitionFrameRate.Max)
            finally:
                cam.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)
            resulting_fps = round(float(cam.ResultingFrameRate.Value), 2)
        print("fps camera", resulting_fps, flush=True)
    time.sleep(0.5)
    w, h = applied["resolution"]
    need = w * h * (args.fps or 70) * SECONDS
    free = shutil.disk_usage(OUT).free
    if need * 1.2 + 5e9 > free:
        sys.exit(f"thiếu dung lượng: cần khoảng {need / 1e9:.1f} GB, còn {free / 1e9:.1f} GB")
    thread.start()
    last, t0 = -1, time.monotonic()
    shape = None
    while time.monotonic() - t0 < SECONDS:
        frame, seq = mgr.latest_frame()
        if frame is None or seq == last:
            time.sleep(0.0005)
            continue
        last = seq
        gray = frame[:, :, 0]
        shape = shape or list(gray.shape)
        try:
            q.put_nowait(gray.copy())
            index.append([seq, round(time.monotonic() - t0, 4)])
        except queue.Full:
            dropped += 1
finally:
    mgr.close()
    if thread.is_alive():
        q.put(None)
        thread.join()
meta = dict(shape=shape, exposure_ms=cfg["exposure_ms"], gain=cfg["analog_gain"], band_y=band_y, band_x=band_x,
            fps_requested=args.fps, fps_camera=resulting_fps, config=os.path.abspath(args.config), note=args.note,
            setup=cfg.get("setup"), dropped=dropped, frames=index)
with open(os.path.join(OUT, "index.json"), "w", encoding="utf-8") as f:
    json.dump(meta, f)
span = index[-1][0] - index[0][0]
print(f"xong {len(index)} frame, bỏ do ghi chậm {dropped}, camera {span / max(index[-1][1], 1e-3):.1f} seq/s, "
      f"mất giữa chừng {span + 1 - len(index) - dropped} seq, tại {OUT}")
