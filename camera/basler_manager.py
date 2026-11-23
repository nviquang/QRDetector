"""Camera Basler qua ``pypylon``, cùng API mà ``demo_ui`` dùng của ``CameraManager``.

Capture không phụ thuộc Qt: ảnh Mono8 chuyển thành BGR sở hữu độc lập, frame cũ bị thay thế.
Đổi vùng đọc phải dừng grab (camera khóa tham số truyền tải khi đang grab); ``_sdk_lock`` giữ
capture thread đứng ngoài lúc cấu hình. Getter đọc giá trị đã cache để GUI không phải chờ grab.
"""

from __future__ import annotations

import logging
import os
import threading
import time

import cv2
import numpy as np
from pypylon import pylon

from .conveyor import RunSettings, align_band

logger = logging.getLogger("solution.camera")

GRAB_TIMEOUT_MS = 1000
ERROR_LOG_INTERVAL_S = 5.0
PORT_NAMES = {"BaslerUsb": "USB", "BaslerGigE": "GigE", "BaslerCamEmu": "Emulation"}


def max_fps() -> float | None:
    """Giới hạn fps camera từ biến môi trường ``QR_MAX_FPS`` (rỗng/0 = không giới hạn). Máy yếu (Jetson Nano) cần
    giới hạn: ở ~84 fps riêng nhận ảnh và chuyển BGR đã chiếm khoảng 1,6/4 nhân, detect chậm từ 1,5 s lên ~6 s."""
    try:
        value = float(os.environ.get("QR_MAX_FPS", "") or 0)
    except ValueError:
        logger.warning("QR_MAX_FPS=%r không hợp lệ, bỏ qua", os.environ.get("QR_MAX_FPS"))
        return None
    return value if value > 0 else None


class BaslerDevice:
    """Thông tin thiết bị pylon, trình bày theo các hàm ``demo_ui`` đọc từ thiết bị MVSDK."""

    def __init__(self, info):
        self.info = info

    def GetSn(self) -> str:
        return self.info.GetSerialNumber()

    def GetFriendlyName(self) -> str:
        return "{} ({})".format(self.info.GetModelName(), self.GetSn())

    def GetPortType(self) -> str:
        device_class = self.info.GetDeviceClass()
        return PORT_NAMES.get(device_class, device_class)


class _CaptureThread(threading.Thread):
    def __init__(self, mgr: "BaslerCameraManager"):
        super().__init__(daemon=True)
        self._mgr = mgr

    def run(self):
        mgr = self._mgr
        while mgr.running:
            try:
                gray = self._grab()
                if gray is None:
                    time.sleep(0.001)
                    continue
                mgr._set_frame(np.ascontiguousarray(cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)))
            except pylon.GenericException as exc:
                if mgr.running:
                    mgr._log_error("capture", exc)
                    time.sleep(0.01)
            except Exception:
                if mgr.running:
                    logger.exception("Capture thread failed")
                    time.sleep(0.05)

    def _grab(self) -> np.ndarray | None:
        mgr = self._mgr
        with mgr._sdk_lock:
            camera = mgr.handle
            if camera is None or not mgr.running or not camera.IsGrabbing():
                return None
            result = camera.RetrieveResult(GRAB_TIMEOUT_MS, pylon.TimeoutHandling_Return)
            try:
                if not result.IsValid():       # hết thời gian chờ, không phải lỗi
                    return None
                if not result.GrabSucceeded():
                    mgr._log_error("grab", result.GetErrorDescription())
                    return None
                mgr._skipped += result.GetNumberOfSkippedImages()
                return result.Array.copy()
            finally:
                result.Release()


class BaslerCameraManager:
    def __init__(self):
        self.handle = None
        self.camera_list: list[BaslerDevice] = []
        self._running = False
        self._thread: _CaptureThread | None = None
        self._frame: np.ndarray | None = None
        self._seq = 0
        self._skipped = 0
        self._lock = threading.Lock()
        self._sdk_lock = threading.RLock()
        self._last_error_at: dict[str, float] = {}
        self._last_diag_at = time.monotonic()
        self._sensor = (0, 0)                 # (rộng, cao) lớn nhất của sensor
        self._window: tuple[int, int, int, int] | None = None   # (x, rộng, y, cao) đang đọc
        self._exposure_us = 0.0
        self._gain = 0.0

    def init_sdk(self) -> bool:
        return True                           # pypylon tự khởi tạo pylon khi import

    def list_cameras(self) -> list[BaslerDevice]:
        self.camera_list = []
        try:
            devices = pylon.TlFactory.GetInstance().EnumerateDevices()
            self.camera_list = [BaslerDevice(info) for info in devices]
            logger.info("Camera enumeration count=%d", len(self.camera_list))
        except pylon.GenericException:
            logger.exception("Camera enumeration raised")
        return self.camera_list

    # ── Mở / đóng ─────────────────────────────────────────────────────────────

    def open(self, index: int) -> bool:
        if index < 0 or index >= len(self.camera_list):
            logger.error("Camera index out of range index=%d count=%d", index, len(self.camera_list))
            return False
        self.close()
        if self.handle is not None:
            logger.error("Previous camera cleanup unresolved; open refused")
            return False
        camera = None
        try:
            factory = pylon.TlFactory.GetInstance()
            camera = pylon.InstantCamera(factory.CreateDevice(self.camera_list[index].info))
            camera.Open()
            self.handle = camera
            ok = self._set("PixelFormat", "Mono8")
            self._set("TriggerSelector", "FrameStart", required=False)
            ok = self._set("TriggerMode", "Off", required=False) and ok
            camera.OffsetX.Value = camera.OffsetX.Min
            camera.OffsetY.Value = camera.OffsetY.Min
            if not ok:
                raise RuntimeError("Camera rejected Mono8 or continuous mode")
            self._sensor = (int(camera.Width.Max), int(camera.Height.Max))
            self._window = (0, int(camera.Width.Value), 0, int(camera.Height.Value))
            self._exposure_us = float(camera.ExposureTime.Value)
            self._gain = round(float(camera.Gain.Value), 2)
            camera.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)
            self._running = True
            self._last_diag_at = time.monotonic()
            self._thread = _CaptureThread(self)
            self._thread.start()
            logger.info("Camera opened index=%d sensor=%dx%d", index, *self._sensor)
            return True
        except Exception:
            logger.exception("Camera open raised index=%d", index)
        self._running = False
        self.handle = None
        self._release(camera)
        return False

    def close(self):
        was_open = self.handle is not None
        self._running = False
        thread = self._thread
        if thread is not None:
            thread.join(timeout=GRAB_TIMEOUT_MS / 1000 * 2)
            if thread.is_alive():
                logger.error("Capture thread did not stop; camera retained")
                return
        self._thread = None
        camera, self.handle = self.handle, None
        self._release(camera)
        with self._lock:
            self._frame = None
        if was_open:
            logger.info("Camera closed")

    @staticmethod
    def _release(camera):
        if camera is None:
            return
        for operation in (camera.StopGrabbing, camera.Close, camera.DestroyDevice):
            try:
                operation()
            except Exception:                  # camera đã rút cáp: vẫn phải thử bước sau
                logger.exception("Camera teardown step failed")

    @property
    def running(self) -> bool:
        return self._running and self.handle is not None

    # ── Frame ─────────────────────────────────────────────────────────────────

    def latest_frame(self) -> tuple[np.ndarray | None, int]:
        with self._lock:
            return self._frame, self._seq

    def _set_frame(self, frame: np.ndarray):
        with self._lock:
            self._frame = frame
            self._seq += 1
            seq = self._seq
        now = time.monotonic()
        if now - self._last_diag_at >= 5.0:
            self._last_diag_at = now
            gray = frame[::8, ::8, 0]
            logger.info("frame_summary seq=%d shape=%sx%s mean=%.1f skipped=%d",
                        seq, frame.shape[1], frame.shape[0], float(gray.mean()), self._skipped)

    def frame_statistic(self) -> tuple[int, int]:
        """(số frame app nhận được, số frame bị ảnh mới hơn thay thế trước khi kịp đọc)."""
        with self._lock:
            return self._seq, self._skipped

    # ── Tham số ───────────────────────────────────────────────────────────────

    def _log_error(self, operation: str, detail):
        now = time.monotonic()
        if now - self._last_error_at.get(operation, -ERROR_LOG_INTERVAL_S) >= ERROR_LOG_INTERVAL_S:
            self._last_error_at[operation] = now
            logger.error("camera_error operation=%s detail=%s", operation, detail)

    def _set(self, name: str, value, required: bool = True) -> bool:
        """Đặt tham số, không ghi nếu đã đúng giá trị. required=False: camera không có thì bỏ qua."""
        try:
            param = getattr(self.handle, name)
        except (AttributeError, pylon.GenericException):
            param = None
        if param is None:
            logger.log(logging.ERROR if required else logging.INFO, "camera_param_missing name=%s", name)
            return not required
        try:
            if param.Value == value:
                return True
            if not param.IsWritable():
                logger.error("camera_param_readonly name=%s value=%r", name, value)
                return False
            param.Value = value
            return True
        except pylon.GenericException as exc:
            logger.error("camera_param_failed name=%s value=%r detail=%s", name, value, exc)
            return False

    def _set_clamped(self, name: str, value: float) -> bool:
        param = getattr(self.handle, name)
        return self._set(name, min(max(float(value), param.Min), param.Max))

    def set_trigger_mode(self, mode: int) -> bool:
        """Bản demo chỉ chạy liên tục (0), đã đặt khi mở camera; chưa hỗ trợ trigger."""
        return mode == 0

    def get_exposure_time(self) -> float:
        return self._exposure_us

    def get_analog_gain(self) -> float:
        return self._gain

    def get_resolution(self) -> tuple[int, int] | None:
        return None if self._window is None else (self._window[1], self._window[3])

    def _target_window(self, settings: RunSettings) -> tuple[int, int, int, int]:
        """Vùng cần đọc; None theo một trục = toàn trục đó (không căn bội 16 để giữ đủ sensor)."""
        sensor_w, sensor_h = self._sensor
        x, width = align_band(*settings.band_x, sensor_w) if settings.band_x else (0, sensor_w)
        y, height = align_band(*settings.band_y, sensor_h) if settings.band_y else (0, sensor_h)
        return x, width, y, height

    def _apply_window(self, window: tuple[int, int, int, int]) -> bool:
        camera = self.handle
        x, width, y, height = window
        # Offset về đầu trước: Width/Height tối đa phụ thuộc offset hiện tại
        ok = self._set("OffsetX", camera.OffsetX.Min) and self._set("OffsetY", camera.OffsetY.Min)
        ok = ok and self._set("Width", self._snap(camera.Width, width))
        ok = ok and self._set("Height", self._snap(camera.Height, height))
        ok = ok and self._set("OffsetX", self._snap(camera.OffsetX, x))
        ok = ok and self._set("OffsetY", self._snap(camera.OffsetY, y))
        self._window = (int(camera.OffsetX.Value), int(camera.Width.Value),
                        int(camera.OffsetY.Value), int(camera.Height.Value))
        return ok

    @staticmethod
    def _snap(param, value: int) -> int:
        return int(value - (value - param.Min) % param.Inc)

    def apply_run_settings(self, settings: RunSettings) -> dict | None:
        """Tắt tự động, exposure (µs) + gain (dB) cố định kẹp theo camera, fps cao nhất (hoặc ``QR_MAX_FPS``),
        vùng đọc."""
        with self._sdk_lock:
            camera = self.handle
            if camera is None or not self._running:
                return None
            ok = self._set("ExposureAuto", "Off", required=False)
            ok = self._set("GainAuto", "Off", required=False) and ok
            fps_limit = None
            try:
                ok = self._set_clamped("ExposureTime", settings.exposure_us) and ok
                ok = self._set_clamped("Gain", settings.analog_gain) and ok
                target = self._target_window(settings)
                fps_limit = max_fps()
                restart = (target != self._window
                           or bool(camera.AcquisitionFrameRateEnable.Value) != (fps_limit is not None))
                if restart:
                    camera.StopGrabbing()
                try:
                    ok = self._set("AcquisitionFrameRateEnable", fps_limit is not None) and ok
                    if fps_limit is not None:
                        ok = self._set_clamped("AcquisitionFrameRate", fps_limit) and ok
                    if target != self._window:
                        ok = self._apply_window(target) and ok
                finally:
                    if restart:
                        camera.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)
                self._exposure_us = float(camera.ExposureTime.Value)
                self._gain = round(float(camera.Gain.Value), 2)
            except pylon.GenericException as exc:
                logger.error("apply_run_settings failed detail=%s", exc)
                ok = False
            applied = dict(ok=ok, exposure_us=self._exposure_us, analog_gain=self._gain,
                           resolution=self.get_resolution(), max_fps=fps_limit if ok else None)
        logger.info("run_settings requested=%r applied=%r", settings, applied)
        return applied
