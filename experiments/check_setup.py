"""Kiểm tra setup trước khi quay video chuẩn: đặt tem QR đứng yên trong vùng đọc rồi chạy

python experiments/check_setup.py [--config experiments/benchmark_basler.json] [--frames 30]

In ra px/ô, mm/px, độ sáng tem, % cháy sáng, tỉ lệ đọc và vệt mờ dự kiến theo tốc độ băng, kèm ĐẠT/CHƯA ĐẠT
theo ngưỡng của video chuẩn (experiments/benchmark_standard.md). Không ghi gì ra đĩa trừ khi có --save.
"""
import argparse
import json
import os
import sys
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
sys.stdout.reconfigure(encoding="utf-8")

import torch  # noqa: F401,E402  (torch trước PyQt5/cv2 để tránh WinError 1114)
import cv2  # noqa: E402
import numpy as np  # noqa: E402

from camera.basler_manager import BaslerCameraManager  # noqa: E402
from camera.conveyor import RunSettings  # noqa: E402
from qr.improved_pipeline import ImprovePipeline  # noqa: E402
from qr.preprocessor import roi_bounds  # noqa: E402

parser = argparse.ArgumentParser()
parser.add_argument("--config", default=os.path.join(_ROOT, "experiments", "benchmark_basler.json"))
parser.add_argument("--frames", type=int, default=30)
parser.add_argument("--save", default=None, help="thư mục lưu frame cuối (PNG) để xem lại")
args = parser.parse_args()
cfg = json.load(open(args.config, encoding="utf-8"))
setup = cfg.get("setup", {})
qr_mm = float(setup.get("qr_mm", 36))
modules = 17 + 4 * int(setup.get("qr_version", 1))
speed = float(setup.get("conveyor_mm_s", 100))

mgr = BaslerCameraManager()
mgr.list_cameras()
if not mgr.open(0):
    sys.exit("không mở được camera (app hoặc pylon Viewer đang giữ?)")
frames = []
try:
    band_y = (cfg["band_y"], cfg["band_h"]) if cfg["band_enabled"] else None
    band_x = (cfg["band_x"], cfg["band_w"]) if cfg["band_x_enabled"] else None
    applied = mgr.apply_run_settings(RunSettings(exposure_us=cfg["exposure_ms"] * 1000.0,
                                                 analog_gain=cfg["analog_gain"], band_x=band_x, band_y=band_y))
    print("áp dụng", applied)
    time.sleep(0.5)
    last, t0 = -1, time.monotonic()
    while len(frames) < args.frames and time.monotonic() - t0 < 30:
        frame, seq = mgr.latest_frame()
        if frame is not None and seq != last:
            frames.append(frame.copy())
            last = seq
        time.sleep(0.01)
finally:
    mgr.close()
if not frames:
    sys.exit("không nhận được frame")

pipe = ImprovePipeline(multi_frame=False)
sides, centers, texts, tag_p95, tag_p5, sat, n_det = [], [], {}, [], [], [], 0
for img in frames:
    for det in pipe.detect(img):
        n_det += 1
        x1, y1, x2, y2 = roi_bounds(img.shape, det.bbox_xyxy, 0.25)
        roi = img[y1:y2, x1:x2, 0]
        tag_p95.append(np.percentile(roi, 95))
        tag_p5.append(np.percentile(roi, 5))
        sat.append(float((roi >= 250).mean() * 100))
        hit = pipe.decode_detection(img, det)
        if hit:
            texts[hit.text] = texts.get(hit.text, 0) + 1
            c = hit.corners
            sides.append(np.mean([np.linalg.norm(c[i] - c[(i + 1) % 4]) for i in range(4)]))
            centers.append(np.mean(c, axis=0))
full = frames[-1][:, :, 0]
if args.save:
    os.makedirs(args.save, exist_ok=True)
    cv2.imwrite(os.path.join(args.save, "check_last.png"), full)


def verdict(ok):
    return "ĐẠT" if ok else "CHƯA ĐẠT"


print(f"\nframe {len(frames)}, kích thước {full.shape[1]}x{full.shape[0]}, detection {n_det}")
print(f"cháy sáng toàn khung: {(full >= 250).mean() * 100:.2f}%  {verdict((full >= 250).mean() < 0.01)} (< 1%)")
if not n_det:
    sys.exit("không thấy QR nào: kiểm tra tem có trong vùng đọc, nét, đủ sáng")
p95, p5 = float(np.median(tag_p95)), float(np.median(tag_p5))
print(f"tem: nền trắng p95 = {p95:.0f}  {verdict(170 <= p95 <= 225)} (170–225); "
      f"ô đen p5 = {p5:.0f}  {verdict(p5 <= 70)} (≤ 70); tương phản {p95 - p5:.0f}  {verdict(p95 - p5 >= 110)} (≥ 110)")
print(f"cháy sáng trong tem: {np.median(sat):.2f}%  {verdict(np.median(sat) < 0.5)} (< 0,5%)")
print(f"đọc được {len(sides)}/{n_det} detection, nội dung: {texts or '-'}")
if sides:
    side = float(np.median(sides))
    ppm = side / modules
    mm_px = qr_mm / side
    blur_px = speed * cfg["exposure_ms"] / 1000 / mm_px
    print(f"QR rộng {side:.1f} px → {ppm:.2f} px/ô  {verdict(2.3 <= ppm <= 2.8)} (mục tiêu 2,5 ± 0,25); "
          f"{mm_px:.3f} mm/px (QR {qr_mm:g} mm)")
    print(f"vệt mờ dự kiến ở {speed:g} mm/s, exposure {cfg['exposure_ms']:g} ms: {blur_px:.2f} px = "
          f"{blur_px / ppm:.2f} ô  {verdict(blur_px / ppm <= 0.25)} (≤ 0,25 ô)")
    # vị trí tem so với tâm cảm biến (tâm quang học xấp xỉ), dùng để ghi belt_x_mm cho từng đoạn quay
    sensor_w = 2856
    off_x = cfg["band_x"] if cfg["band_x_enabled"] else 0
    cx = float(np.median([c[0] for c in centers])) + off_x
    print(f"tâm tem ở x = {cx:.0f} px trên cảm biến → lệch {(cx - sensor_w / 2) * mm_px:+.0f} mm so với trục camera "
          f"(theo chiều 1,6 m; trái âm, phải dương)")
else:
    print("chưa đọc được QR nào nên không đo được px/ô: chỉnh nét, ánh sáng, hoặc đặt tem gần tâm hơn rồi chạy lại")
