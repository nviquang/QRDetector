"""MindVision camera manager using the vendor ``mvsdk`` binding.

The class deliberately keeps the public API consumed by ``ui/main_window.py``.
Capture is Qt-independent and publishes owned BGR numpy arrays; old frames are
replaced instead of queued.
"""

from __future__ import annotations

import ctypes
import logging
import threading
import time

import cv2
import numpy as np

import mvsdk

from .conveyor import ConveyorSettings, align_band
from .recording import NativeRecorder, RecordingOptions, RecordingStatus


MV_OK = 0
logger = logging.getLogger("solution.camera")


class _CaptureThread(threading.Thread):
    def __init__(self, mgr: "CameraManager"):
        super().__init__(daemon=True)
        self._mgr = mgr

    def run(self):
        mgr = self._mgr
        try:
            self._capture()
        finally:
            with mgr._sdk_lock:
                mgr._recorder.stop(mgr.handle)

    def _capture(self):
        mgr = self._mgr
        while mgr.running:
            raw_ptr = None
            try:
                with mgr._sdk_lock:
                    if not mgr.running or mgr.handle is None:
                        break
                    mgr._service_recording()
                    mgr._update_recording_stats()
                    mgr._recorder.maintain(mgr.handle)
                    raw_ptr, frame_head = mvsdk.CameraGetImageBuffer(mgr.handle, 1000)
                    try:
                        width = int(frame_head.iWidth)
                        height = int(frame_head.iHeight)
                        channels = 1 if mgr._mono_sensor else 3
                        byte_count = width * height * channels
                        if width <= 0 or height <= 0 or byte_count > mgr._frame_buffer_size:
                            mgr._log_sdk_error("invalid_frame", -1)
                            continue
                        ret = mvsdk.CameraImageProcess(
                            mgr.handle, raw_ptr, mgr._frame_buffer, frame_head)
                        if ret != MV_OK:
                            mgr._log_sdk_error("image_process", ret)
                            continue
                        with mgr._record_command_lock:
                            mgr._record_head = frame_head
                        # Own preview pixels before handing the processed buffer to the recorder.
                        native = (ctypes.c_ubyte * byte_count).from_address(
                            int(mgr._frame_buffer))
                        data = np.ctypeslib.as_array(native).copy()
                        mgr._service_recording(frame_head)
                        mgr._recorder.push(mgr.handle, mgr._frame_buffer, frame_head)
                    finally:
                        mvsdk.CameraReleaseImageBuffer(mgr.handle, raw_ptr)
                        raw_ptr = None

                if mgr._mono_sensor:
                    gray = data.reshape((height, width))
                    frame = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
                else:
                    rgb = data.reshape((height, width, 3))
                    frame = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
                mgr._set_frame(np.ascontiguousarray(frame))
            except mvsdk.CameraException as exc:
                if mgr.running:
                    mgr._log_sdk_error("capture", exc.error_code)
                    time.sleep(0.01)
            except Exception:
                if mgr.running:
                    logger.exception("Capture thread failed")
                    time.sleep(0.05)


class CameraManager:
    def __init__(self):
        self.handle: int | None = None
        self._cam: int | None = None  # compatibility alias for older diagnostics
        self.camera_list: list = []
        self.capability = None
        self.f_exp_line_time = 1.0

        self._sdk_inited = False
        self._running = False
        self._playing = False
        self._thread: _CaptureThread | None = None
        self._frame_buffer = None
        self._frame_buffer_size = 0
        self._mono_sensor = False

        self._frame: np.ndarray | None = None
        self._seq = 0
        self._lock = threading.Lock()
        self._sdk_lock = threading.RLock()
        self._last_diag_at = time.monotonic()
        self._last_sdk_error_at: dict[str, float] = {}
        self._recorder = NativeRecorder(mvsdk)
        self._record_command_lock = threading.RLock()
        self._record_start: RecordingOptions | None = None
        self._record_stop = False
        self._record_trigger = False
        self._record_head = None
        self._closing = False
        self._stats_at = 0.0
        self._stats_previous = None
        self._lost_baseline = None
        self._band: tuple[int, int] | None = None   # dải sensor đang đọc (chế độ băng chuyền)

    def start_recording(self, options: RecordingOptions) -> bool:
        with self._record_command_lock:
            status = self._recorder.status()
            if (not self.running or self._closing or self._record_head is None
                    or status.busy or self._record_start is not None):
                return False
            if status.capture_fps is not None and options.fps <= status.capture_fps:
                self._recorder.publish(error="FPS video phải cao hơn FPS capture đo được.")
                return False
            self._record_start = options
            self._record_stop = False
            self._recorder.publish(state="STARTING", error="", fps=options.fps)
            return True

    def stop_recording(self) -> bool:
        with self._record_command_lock:
            status = self._recorder.status()
            if not status.busy and self._record_start is None:
                return True
            self._record_start = None
            self._record_stop = True
            self._recorder.publish(state="STOPPING")
            if self._recorder.status().native_open and (
                    self._thread is None or not self._thread.is_alive()):
                # The old owner has exited. A one-shot owner handles explicit
                # finalization retry without blocking Qt or racing acquisition.
                def retry_stop():
                    with self._sdk_lock:
                        self._recorder.stop(self.handle)
                self._thread = threading.Thread(target=retry_stop, daemon=True)
                self._thread.start()
            return True

    def recording_status(self) -> RecordingStatus:
        return self._recorder.status()

    def _service_recording(self, info=None):
        with self._record_command_lock:
            stop, self._record_stop = self._record_stop, False
            options = None
            if info is not None and not stop:
                options, self._record_start = self._record_start, None
            trigger, self._record_trigger = self._record_trigger, False
        if stop:
            self._recorder.stop(self.handle)
        elif options is not None and not self._closing:
            self._lost_baseline = None
            self._stats_previous = None
            self._stats_at = 0.0
            self._recorder.start(self.handle, options, info)
        if trigger and not self._closing:
            try:
                ret = mvsdk.CameraSoftTrigger(self.handle)
                if ret != MV_OK:
                    self._recorder.publish(warning="Soft trigger lỗi: " + self._status(ret))
            except Exception as exc:
                self._recorder.publish(warning="Soft trigger lỗi: " + str(exc))

    def _update_recording_stats(self):
        now = time.monotonic()
        if now - self._stats_at < 1.0:
            return
        self._stats_at = now
        try:
            stat = mvsdk.CameraGetFrameStatistic(self.handle)
            self._raise_last_error("frame_statistic")
            capture, lost = int(stat.iCapture), int(stat.iLost)
            fps = None
            if self._stats_previous is not None:
                previous_at, previous_count = self._stats_previous
                fps = max(0.0, (capture - previous_count) / (now - previous_at))
            self._stats_previous = now, capture
            if self._lost_baseline is None:
                self._lost_baseline = lost
            fields = dict(capture_count=capture, capture_fps=fps,
                          lost_delta=max(0, lost - self._lost_baseline))
            status = self._recorder.status()
            if status.busy and fps is not None and fps >= status.fps:
                fields["warning"] = "Capture đạt/vượt FPS video: dừng và tăng FPS video."
            self._recorder.publish(**fields)
        except Exception:
            self._stats_previous = None
            self._recorder.publish(capture_fps=None, lost_delta=None)

    def _configuration_locked(self) -> bool:
        return self._closing or self._recorder.status().busy

    # ── lifecycle ──────────────────────────────────────────────────────────────

    def init_sdk(self) -> bool:
        if self._sdk_inited:
            return True
        try:
            ret = mvsdk.CameraSdkInit(0)
        except Exception:
            logger.exception("SDK initialize raised")
            return False
        if ret != MV_OK:
            logger.error("SDK initialize failed ret=%s", self._status(ret))
            return False
        self._sdk_inited = True
        logger.info("MindVision SDK initialized ret=%s", self._status(ret))
        return True

    def list_cameras(self) -> list:
        self.camera_list = []
        if not self.init_sdk():
            return self.camera_list
        try:
            devices = list(mvsdk.CameraEnumerateDevice())
            ret = mvsdk.GetLastError()
            if ret != MV_OK:
                logger.error("Camera enumeration failed ret=%s", self._status(ret))
                return self.camera_list
            self.camera_list = devices
            logger.info("Camera enumeration count=%d", len(devices))
        except Exception:
            logger.exception("Camera enumeration raised")
        return self.camera_list

    def open(self, index: int) -> bool:
        if index < 0 or index >= len(self.camera_list):
            logger.error("Camera index out of range index=%d count=%d",
                         index, len(self.camera_list))
            return False
        self.close()
        if self.handle is not None or (self._thread is not None and self._thread.is_alive()):
            logger.error("Previous camera/recorder cleanup unresolved; open refused")
            return False
        self._closing = False
        self._record_head = None
        self._recorder = NativeRecorder(mvsdk)
        self._stats_previous = None
        self._lost_baseline = None
        self._stats_at = 0.0
        try:
            handle = mvsdk.CameraInit(self.camera_list[index], -1, -1)
            self.handle = self._cam = handle
            self.capability = mvsdk.CameraGetCapability(handle)
            self._raise_last_error("get_capability")

            self._mono_sensor = bool(self.capability.sIspCapacity.bMonoSensor)
            out_format = (mvsdk.CAMERA_MEDIA_TYPE_MONO8 if self._mono_sensor
                          else mvsdk.CAMERA_MEDIA_TYPE_RGB8)
            if not self._set("IspOutFormat", out_format,
                             mvsdk.CameraSetIspOutFormat, out_format):
                raise RuntimeError("CameraSetIspOutFormat failed")

            resolution = self.capability.sResolutionRange
            max_width = max(1, int(resolution.iWidthMax))
            max_height = max(1, int(resolution.iHeightMax))
            channels = 1 if self._mono_sensor else 3
            self._frame_buffer_size = max_width * max_height * channels
            self._frame_buffer = mvsdk.CameraAlignMalloc(self._frame_buffer_size, 16)
            if not self._frame_buffer:
                raise MemoryError("CameraAlignMalloc returned NULL")

            self.f_exp_line_time = float(mvsdk.CameraGetExposureLineTime(handle)) or 1.0
            if mvsdk.GetLastError() != MV_OK:
                self.f_exp_line_time = 1.0

            self.set_trigger_mode(0)
            current_exposure = self.get_exposure_time()
            if current_exposure < 1000.0:
                self.set_ae_state(False)
                min_us = self.capability.sExposeDesc.uiExposeTimeMin * self.f_exp_line_time
                max_us = self.capability.sExposeDesc.uiExposeTimeMax * self.f_exp_line_time
                self.set_exposure_time(min(max(20_000.0, min_us), max_us))
            self.set_ae_state(True)

            ret = mvsdk.CameraPlay(handle)
            if ret != MV_OK:
                raise RuntimeError("CameraPlay failed: {}".format(self._status(ret)))
            self._playing = True
            self._running = True
            self._last_diag_at = time.monotonic()
            self._thread = _CaptureThread(self)
            self._thread.start()
            logger.info("Camera opened index=%d max_size=%dx%d", index,
                        max_width, max_height)
            self.log_parameter_snapshot("open")
            return True
        except mvsdk.CameraException as exc:
            logger.error("CameraInit failed ret=%s message=%s",
                         self._status(exc.error_code), exc.message)
        except Exception:
            logger.exception("Camera open raised index=%d", index)
        self._running = False
        self._teardown_handle()
        return False

    def close(self):
        was_open = self.handle is not None
        self._closing = True
        with self._record_command_lock:
            self._record_start = None
        self._running = False
        thread = self._thread
        if thread is not None:
            thread.join(timeout=2.0)
            if (thread.is_alive() and self.handle is not None and self._playing
                    and not self._recorder.status().busy):
                try:
                    mvsdk.CameraStop(self.handle)
                    self._playing = False
                except Exception:
                    logger.exception("CameraStop while joining failed")
                thread.join(timeout=1.5)
            if thread.is_alive():
                logger.error("Capture thread did not stop; native resources retained")
                self._thread = thread
                return
        if self._recorder.status().native_open:
            logger.error("Recording finalization unresolved; camera resources retained")
            return
        self._teardown_handle()
        if self.handle is not None or self._frame_buffer is not None:
            return
        self._record_head = None
        self._closing = False
        self._thread = None
        with self._lock:
            self._frame = None
        self.capability = None
        if was_open:
            logger.info("Camera closed")

    def _teardown_handle(self):
        handle = self.handle
        if handle is not None:
            try:
                if self._playing:
                    ret = mvsdk.CameraStop(handle)
                    if ret != MV_OK:
                        self._log_cleanup("CameraStop", ret)
                        return
                    self._playing = False
                ret = mvsdk.CameraUnInit(handle)
                if ret != MV_OK:
                    self._log_cleanup("CameraUnInit", ret)
                    return
            except Exception:
                logger.exception("Camera teardown failed; native resources retained")
                return
            self.handle = self._cam = None
        if self._frame_buffer:
            try:
                mvsdk.CameraAlignFree(self._frame_buffer)
            except Exception:
                logger.exception("CameraAlignFree raised")
                return
        self._frame_buffer = None
        self._frame_buffer_size = 0

    @property
    def running(self) -> bool:
        return self._running and self.handle is not None

    # ── frame ──────────────────────────────────────────────────────────────────

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
            sample = frame if min(frame.shape[:2]) <= 64 else frame[::8, ::8]
            gray = cv2.cvtColor(sample, cv2.COLOR_BGR2GRAY)
            logger.info(
                "frame_summary seq=%d shape=%sx%s mean=%.1f min=%d max=%d "
                "near_black_pct=%.1f", seq, frame.shape[1], frame.shape[0],
                float(gray.mean()), int(gray.min()), int(gray.max()),
                float((gray < 8).mean() * 100))

    def frame_statistic(self):
        if self.handle is not None:
            try:
                stat = mvsdk.CameraGetFrameStatistic(self.handle)
                if mvsdk.GetLastError() == MV_OK:
                    return int(stat.iCapture), int(stat.iLost)
            except Exception:
                pass
        with self._lock:
            return self._seq, 0

    # ── SDK helpers ────────────────────────────────────────────────────────────

    @staticmethod
    def _status(ret) -> str:
        return "0x{:08X}".format(int(ret) & 0xFFFFFFFF)

    def _raise_last_error(self, operation: str):
        ret = mvsdk.GetLastError()
        if ret != MV_OK:
            raise RuntimeError("{} failed: {}".format(operation, self._status(ret)))

    def _log_sdk_error(self, operation: str, ret, interval: float = 5.0):
        now = time.monotonic()
        previous = self._last_sdk_error_at.get(operation, float("-inf"))
        if now - previous >= interval:
            self._last_sdk_error_at[operation] = now
            logger.warning("SDK error operation=%s ret=%s", operation,
                           self._status(ret))

    def _log_cleanup(self, operation: str, ret):
        if ret != MV_OK:
            logger.warning("SDK cleanup failed operation=%s ret=%s",
                           operation, self._status(ret))

    def _set(self, name: str, value, func, *args) -> bool:
        with self._record_command_lock:
            if self.handle is None or self._configuration_locked():
                return False
            return self._set_unlocked(name, value, func, *args)

    def _set_unlocked(self, name: str, value, func, *args) -> bool:
        try:
            ret = func(self.handle, *args)
            if ret == MV_OK:
                logger.info("SDK set node=%s value=%r ret=%s", name, value,
                            self._status(ret))
                return True
            logger.warning("SDK set failed node=%s value=%r ret=%s", name,
                           value, self._status(ret))
        except Exception:
            logger.exception("SDK set raised node=%s value=%r", name, value)
        return False

    def _get(self, name: str, func, default, *args):
        if self.handle is None:
            return default
        try:
            value = func(self.handle, *args)
            ret = mvsdk.GetLastError()
            if ret == MV_OK:
                return value
            logger.warning("SDK get failed node=%s ret=%s", name,
                           self._status(ret))
        except Exception:
            logger.exception("SDK get raised node=%s", name)
        return default

    # ── controls ───────────────────────────────────────────────────────────────

    def set_trigger_mode(self, mode: int):
        return self._set("TriggerMode", mode, mvsdk.CameraSetTriggerMode, int(mode))

    def soft_trigger(self):
        with self._record_command_lock:
            if self._closing or not self.running:
                return False
            if self._recorder.status().busy:
                if self._record_trigger:
                    return False
                self._record_trigger = True
                return True
        return self._set("SoftTrigger", True, mvsdk.CameraSoftTrigger)

    def set_strobe_mode(self, mode: int):
        return self._set("StrobeMode", mode, mvsdk.CameraSetStrobeMode, int(mode))

    def set_strobe_polarity(self, polarity: int):
        return self._set("StrobePolarity", polarity,
                         mvsdk.CameraSetStrobePolarity, int(polarity))

    def set_ae_state(self, auto: bool):
        return self._set("AeState", auto, mvsdk.CameraSetAeState, bool(auto))

    def get_ae_state(self) -> bool | None:
        value = self._get("AeState", mvsdk.CameraGetAeState, None)
        return None if value is None else bool(value)

    def set_ae_target(self, target: int):
        return self._set("AeTarget", target, mvsdk.CameraSetAeTarget, int(target))

    def get_ae_target(self) -> int | None:
        if self.capability is not None and not self.capability.sIspCapacity.bAutoExposure:
            return None
        return self._get("AeTarget", mvsdk.CameraGetAeTarget, None)

    def set_anti_flick(self, enable: bool):
        return self._set("AntiFlick", enable, mvsdk.CameraSetAntiFlick, bool(enable))

    def set_light_frequency(self, hz: int):
        return self._set("LightFrequency", hz,
                         mvsdk.CameraSetLightFrequency, int(hz))

    def set_analog_gain(self, gain: int):
        return self._set("AnalogGain", gain,
                         mvsdk.CameraSetAnalogGain, int(gain))

    def get_analog_gain(self) -> int:
        return int(self._get("AnalogGain", mvsdk.CameraGetAnalogGain, 0))

    def set_exposure_time(self, time_us: float):
        return self._set("ExposureTime", time_us,
                         mvsdk.CameraSetExposureTime, float(time_us))

    def get_exposure_time(self) -> float:
        return float(self._get("ExposureTime", mvsdk.CameraGetExposureTime, 0.0))

    def set_mirror(self, axis: int, enable: bool):
        return self._set("Mirror", (axis, enable), mvsdk.CameraSetMirror,
                         int(axis), bool(enable))

    def set_sharpness(self, value: int):
        return self._set("Sharpness", value, mvsdk.CameraSetSharpness, int(value))

    def get_sharpness(self) -> int:
        return int(self._get("Sharpness", mvsdk.CameraGetSharpness, 0))

    def set_gamma(self, value: float):
        native = int(round(float(value) * 100))
        return self._set("Gamma", value, mvsdk.CameraSetGamma, native)

    def get_gamma(self) -> float:
        native = self._get("Gamma", mvsdk.CameraGetGamma, 0)
        return float(native) / 100.0

    def set_contrast(self, value: int):
        return self._set("Contrast", value, mvsdk.CameraSetContrast, int(value))

    def get_contrast(self) -> int:
        return int(self._get("Contrast", mvsdk.CameraGetContrast, 0))

    def set_gain(self, r: int, g: int, b: int):
        return self._set("RgbGain", (r, g, b), mvsdk.CameraSetGain,
                         int(r), int(g), int(b))

    def get_gain(self) -> tuple[int, int, int]:
        value = self._get("RgbGain", mvsdk.CameraGetGain, (0, 0, 0))
        return tuple(int(v) for v in value)

    def set_saturation(self, value: int):
        return self._set("Saturation", value,
                         mvsdk.CameraSetSaturation, int(value))

    def get_saturation(self) -> int:
        return int(self._get("Saturation", mvsdk.CameraGetSaturation, 0))

    def set_once_wb(self):
        return self._set("OnceWB", True, mvsdk.CameraSetOnceWB)

    def set_monochrome(self, enable: bool):
        return self._set("Monochrome", enable,
                         mvsdk.CameraSetMonochrome, bool(enable))

    def set_inverse(self, enable: bool):
        return self._set("Inverse", enable, mvsdk.CameraSetInverse, bool(enable))

    def set_roi(self, index: int):
        if self._configuration_locked():
            return False
        if self.handle is None or self.capability is None:
            return False
        if index < 0 or index >= int(self.capability.iImageSizeDesc):
            return False
        resolution = self.capability.pImageSizeDesc[index]
        with self._sdk_lock:
            ok = self._set("ImageResolution", index,
                           mvsdk.CameraSetImageResolution, resolution)
        if ok:
            self._band = None
        return ok

    def get_resolution(self) -> tuple[int, int] | None:
        res = self._get("ImageResolution", mvsdk.CameraGetImageResolution, None)
        return None if res is None else (int(res.iWidth), int(res.iHeight))

    def set_frame_speed(self, index: int):
        return self._set("FrameSpeed", index, mvsdk.CameraSetFrameSpeed, int(index))

    def get_frame_speed(self) -> int | None:
        return self._get("FrameSpeed", mvsdk.CameraGetFrameSpeed, None)

    def frame_speed_names(self) -> list[str]:
        if self.capability is None:
            return []
        return [self.capability.pFrameSpeedDesc[i].GetDescription()
                for i in range(int(self.capability.iFrameSpeedDesc))]

    def set_sensor_band(self, y: int, height: int) -> bool:
        """Chỉ đọc dải ngang ``height`` dòng từ ``y`` trên toàn bề rộng sensor (ROI tùy biến).

        Ít dòng hơn → mỗi frame truyền/xử lý nhanh hơn → FPS cao hơn. Offset/kích thước được căn
        bội 16; cần kiểm chứng trên camera thật nếu SDK từ chối.
        """
        if self._configuration_locked() or self.handle is None or self.capability is None:
            return False
        sensor = self.capability.sResolutionRange
        width = int(sensor.iWidthMax)
        y, height = align_band(y, height, int(sensor.iHeightMax))
        res = mvsdk.tSdkImageResolution()
        res.iIndex = 0xFF
        res.iHOffsetFOV, res.iVOffsetFOV = 0, y
        res.iWidthFOV, res.iHeightFOV = width, height
        res.iWidth, res.iHeight = width, height
        with self._sdk_lock:
            ok = self._set("ImageResolution", (0, y, width, height),
                           mvsdk.CameraSetImageResolution, res)
        if ok:
            self._band = (y, height)
        return ok

    @property
    def sensor_band(self) -> tuple[int, int] | None:
        return self._band

    def apply_conveyor_mode(self, settings: ConveyorSettings) -> dict | None:
        """Cấu hình camera cho QR chạy trên băng: tắt AE, exposure cố định giới hạn vệt mờ,
        tốc độ khung cao nhất, (tùy chọn) chỉ đọc dải băng. Trả về giá trị thực tế đã áp dụng."""
        if self.handle is None or self.capability is None or self._configuration_locked():
            return None
        expose = self.capability.sExposeDesc
        line_time = self.f_exp_line_time or 1.0
        lo = expose.uiExposeTimeMin * line_time
        hi = expose.uiExposeTimeMax * line_time
        target = settings.exposure_us
        ok = self.set_ae_state(False)
        ok = self.set_exposure_time(min(max(target, lo), hi)) and ok
        speeds = int(getattr(self.capability, "iFrameSpeedDesc", 0) or 0)
        if settings.max_frame_speed and speeds > 0:
            ok = self.set_frame_speed(speeds - 1) and ok
        if settings.band is not None:
            ok = self.set_sensor_band(*settings.band) and ok
        elif self._band is not None:
            ok = self.set_roi(0) and ok           # bỏ dải cũ → về độ phân giải preset đầu (toàn khung)
        applied = dict(ok=ok, exposure_target_us=target, exposure_us=self.get_exposure_time(),
                       ae=self.get_ae_state(), frame_speed=self.get_frame_speed(),
                       resolution=self.get_resolution(), band=self._band)
        logger.info("conveyor_mode speed_mm_s=%.0f mm_per_px=%.3f max_blur_px=%.2f applied=%r",
                    settings.speed_mm_s, settings.mm_per_px, settings.max_blur_px, applied)
        return applied

    def save_param(self, slot: int):
        return self._set("SaveParameter", slot,
                         mvsdk.CameraSaveParameter, int(slot))

    def load_param(self, slot: int):
        return self._set("LoadParameter", slot,
                         mvsdk.CameraLoadParameter, int(slot))

    def reset_param(self):
        return self._set("LoadDefaultParameter", 0xFF,
                         mvsdk.CameraLoadParameter, 0xFF)

    def set_friendly_name(self, name: str):
        return self._set("FriendlyName", name,
                         mvsdk.CameraSetFriendlyName, str(name))

    def get_friendly_name(self) -> str:
        return str(self._get("FriendlyName", mvsdk.CameraGetFriendlyName, ""))

    def read_serial_number(self, level: int = 0) -> str:
        return str(self._get("SerialNumber", mvsdk.CameraReadSN, "", int(level)))

    def log_parameter_snapshot(self, reason: str):
        logger.info(
            "parameter_snapshot reason=%s exposure_us=%.1f gain=%d "
            "ae_target=%r gamma=%.3f", reason, self.get_exposure_time(),
            self.get_analog_gain(), self.get_ae_target(), self.get_gamma())
