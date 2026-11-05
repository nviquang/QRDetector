"""Mở camera Basler bằng pypylon, xem ảnh trực tiếp và đo fps, số frame mất, độ sáng.

Chạy (từ gốc repo). Cần `pip install pypylon` và pylon Runtime (có driver USB):
  python tools/test_basler.py --list                        # liệt kê camera rồi thoát
  python tools/test_basler.py                               # camera đầu tiên, giữ tham số đang có
  python tools/test_basler.py --auto                        # tự động exposure + gain
  python tools/test_basler.py --exposure 12900 --gain 6     # exposure (µs), gain (dB) cố định
  python tools/test_basler.py --fps 15 --roi 2840 800       # giới hạn fps, chỉ đọc dải giữa sensor
  python tools/test_basler.py --serial 12345678             # chọn camera theo số serial
  python tools/test_basler.py --seconds 30 --no-view        # đo tốc độ, không mở cửa sổ
Trong cửa sổ xem: q/Esc thoát, s lưu ảnh vào thư mục hiện tại.
"""

from __future__ import annotations

import argparse
import sys
import time

import cv2
import numpy as np
from pypylon import pylon

WINDOW = "Basler test (q: thoat, s: luu anh)"
VIEW_WIDTH = 1000
GRAB_TIMEOUT_MS = 5000


def set_param(camera, name: str, value) -> bool:
    """Đặt một tham số nếu camera có và đang cho ghi; không thì báo rồi bỏ qua."""
    param = getattr(camera, name, None)
    if param is None or not param.IsWritable():
        print("  bỏ qua {}: camera không có hoặc không cho ghi".format(name))
        return False
    param.Value = value
    return True


def read_param(camera, name: str):
    param = getattr(camera, name, None)
    return param.Value if param is not None and param.IsReadable() else None


def set_roi(camera, width: int, height: int):
    """Đọc vùng giữa sensor; kích thước kẹp theo max và căn theo bước của camera."""
    camera.OffsetX.Value = camera.OffsetX.Min
    camera.OffsetY.Value = camera.OffsetY.Min
    for size, value in ((camera.Width, width), (camera.Height, height)):
        value = min(max(value, size.Min), size.Max)
        size.Value = size.Min + (value - size.Min) // size.Inc * size.Inc
    for offset, free in ((camera.OffsetX, camera.OffsetX.Max), (camera.OffsetY, camera.OffsetY.Max)):
        offset.Value = offset.Min + (free // 2 - offset.Min) // offset.Inc * offset.Inc


def configure(camera, args):
    # Thứ tự: ROI trước, fps sau, vì fps tối đa phụ thuộc kích thước vùng đọc
    set_param(camera, "PixelFormat", "Mono8")
    if args.roi:
        set_roi(camera, *args.roi)
    if args.auto:
        set_param(camera, "ExposureAuto", "Continuous")
        set_param(camera, "GainAuto", "Continuous")
    if args.exposure is not None:
        set_param(camera, "ExposureAuto", "Off")
        set_param(camera, "ExposureTime", args.exposure)
    if args.gain is not None:
        set_param(camera, "GainAuto", "Off")
        set_param(camera, "Gain", args.gain)
    if args.fps is not None:
        set_param(camera, "AcquisitionFrameRateEnable", True)
        set_param(camera, "AcquisitionFrameRate", args.fps)


def describe(camera) -> str:
    fields = ("Width", "Height", "PixelFormat", "ExposureAuto", "ExposureTime", "GainAuto", "Gain",
              "BslResultingAcquisitionFrameRate", "BslUSBSpeedMode")
    return ", ".join("{}={}".format(name, read_param(camera, name)) for name in fields
                     if read_param(camera, name) is not None)


def annotate(frame: np.ndarray, text: str) -> np.ndarray:
    scale = VIEW_WIDTH / frame.shape[1]
    view = cv2.resize(frame, (VIEW_WIDTH, max(1, round(frame.shape[0] * scale))), interpolation=cv2.INTER_AREA)
    view = cv2.cvtColor(view, cv2.COLOR_GRAY2BGR)
    cv2.putText(view, text, (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2, cv2.LINE_AA)
    return view


def run(camera, args) -> int:
    grabbed = failed = skipped = 0
    started = window_at = time.perf_counter()
    window_grabbed = 0
    fps = 0.0
    brightness = saturated = 0.0
    if not args.no_view:
        cv2.namedWindow(WINDOW, cv2.WINDOW_AUTOSIZE)
    # Chỉ giữ ảnh mới nhất như capture thread của app; ảnh bị thay thế được đếm qua skipped
    camera.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)
    try:
        while camera.IsGrabbing():
            with camera.RetrieveResult(GRAB_TIMEOUT_MS, pylon.TimeoutHandling_ThrowException) as result:
                if not result.GrabSucceeded():
                    failed += 1
                    print("Grab lỗi 0x{:x}: {}".format(result.GetErrorCode(), result.GetErrorDescription()))
                    continue
                grabbed += 1
                window_grabbed += 1
                skipped += result.GetNumberOfSkippedImages()
                frame = result.Array.copy()

            now = time.perf_counter()
            if now - window_at >= 1.0:
                fps = window_grabbed / (now - window_at)
                window_at, window_grabbed = now, 0
                brightness = float(frame.mean())
                saturated = float(np.count_nonzero(frame >= 255)) * 100.0 / frame.size
                print("{:6.1f} fps | sáng TB {:5.1f} | cháy {:5.2f}% | nhận {} | bỏ qua {} | lỗi {}".format(
                    fps, brightness, saturated, grabbed, skipped, failed))

            if args.seconds is not None and now - started >= args.seconds:
                break
            if args.no_view:
                continue
            text = "{}x{} {:.1f} fps  sang {:.0f}  chay {:.2f}%".format(
                frame.shape[1], frame.shape[0], fps, brightness, saturated)
            cv2.imshow(WINDOW, annotate(frame, text))
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27) or cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE) < 1:
                break
            if key == ord("s"):
                path = "basler_{}.png".format(time.strftime("%Y%m%d_%H%M%S"))
                print("Đã lưu {}".format(path) if cv2.imwrite(path, frame) else "Không lưu được {}".format(path))
    finally:
        camera.StopGrabbing()
        cv2.destroyAllWindows()

    elapsed = time.perf_counter() - started
    print("Tổng: {} ảnh trong {:.1f} s ({:.1f} fps TB), bỏ qua {}, lỗi {}".format(
        grabbed, elapsed, grabbed / elapsed if elapsed else 0.0, skipped, failed))
    return 1 if failed or not grabbed else 0


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # console cp1252 không in được tiếng Việt
    parser = argparse.ArgumentParser(description="Mở và kiểm tra camera Basler")
    parser.add_argument("--list", action="store_true", help="liệt kê camera rồi thoát")
    parser.add_argument("--serial", help="số serial camera, mặc định camera đầu tiên")
    parser.add_argument("--auto", action="store_true", help="bật tự động exposure và gain")
    parser.add_argument("--exposure", type=float, help="exposure cố định (µs)")
    parser.add_argument("--gain", type=float, help="gain cố định (dB)")
    parser.add_argument("--fps", type=float, help="giới hạn tốc độ khung hình")
    parser.add_argument("--roi", type=int, nargs=2, metavar=("W", "H"), help="chỉ đọc vùng W×H ở giữa sensor")
    parser.add_argument("--seconds", type=float, help="tự thoát sau số giây này")
    parser.add_argument("--no-view", action="store_true", help="không mở cửa sổ, chỉ đo")
    args = parser.parse_args()
    if args.no_view and args.seconds is None:
        parser.error("--no-view cần đi kèm --seconds")

    factory = pylon.TlFactory.GetInstance()
    devices = factory.EnumerateDevices()
    for device in devices:
        print("{} | serial {} | {}".format(device.GetModelName(), device.GetSerialNumber(), device.GetDeviceClass()))
    if not devices:
        print("Không thấy camera Basler. Kiểm tra cáp, cổng USB 3 và driver trong pylon Runtime.")
        return 1
    if args.list:
        return 0

    device = devices[0]
    if args.serial:
        device = next((d for d in devices if d.GetSerialNumber() == args.serial), None)
        if device is None:
            print("Không có camera serial {}".format(args.serial))
            return 1

    camera = pylon.InstantCamera(factory.CreateDevice(device))
    try:
        camera.Open()
        configure(camera, args)
        print("Tham số: " + describe(camera))
        return run(camera, args)
    except pylon.GenericException as exc:
        print("Lỗi camera: {}".format(exc))
        return 1
    finally:
        camera.Close()


if __name__ == "__main__":
    sys.exit(main())
