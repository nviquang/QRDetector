"""Uncompressed MVSDK recording, owned exclusively by the capture thread.

Status reads never take the acquisition lock. Native ownership survives errors
until CameraStopRecord confirms finalization; callers must respect native_open.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
import json
import logging
from pathlib import Path
import shutil
import threading
import time
import uuid

from .color_diagnostics import ColorDiagnostics

logger = logging.getLogger("solution.camera.recording")
ACTIVE_STATES = frozenset(("STARTING", "RECORDING", "STOPPING"))


@dataclass(frozen=True)
class RecordingOptions:
    directory: Path
    fps: int = 60
    color_diagnostics: bool = False


@dataclass(frozen=True)
class RecordingStatus:
    state: str = "IDLE"
    error: str = ""
    warning: str = "Chưa kiểm chứng đủ frame trên phần cứng."
    current_path: str = ""
    segment: int = 0  # Compatibility: 0 before initialization, 1 for the session file.
    elapsed: float = 0.0
    pushed_frames: int = 0
    native_open: bool = False
    capture_fps: float | None = None
    capture_count: int = 0
    lost_delta: int | None = None
    fps: int = 60
    color_diagnostic_status: str = ""

    @property
    def busy(self) -> bool:
        return self.state in ACTIVE_STATES or self.native_open


class NativeRecorder:
    """All methods except status/publish run on the capture owner thread."""

    def __init__(self, sdk, *, clock=time.monotonic, disk_free=None):
        self.sdk = sdk
        self._clock = clock
        self._disk_free = disk_free or (lambda path: shutil.disk_usage(path).free)
        self._lock = threading.Lock()
        self._status = RecordingStatus()
        self._options = None
        self._directory = None
        self._geometry = None
        self._started_at = 0.0
        self._last_disk_at = 0.0
        self._last_stamp = None
        self._frame_bytes = 0
        self._diagnostics = None
        self._diagnostic_context = None

    def status(self) -> RecordingStatus:
        with self._lock:
            status = self._status
        diagnostics = self._diagnostics
        if diagnostics is not None:
            return replace(status, color_diagnostic_status=diagnostics.status_text())
        return status

    def publish(self, **fields):
        with self._lock:
            self._status = replace(self._status, **fields)

    @staticmethod
    def _check(operation, ret):
        if ret != 0:
            raise RuntimeError(f"{operation}: 0x{int(ret) & 0xFFFFFFFF:08X}")

    @staticmethod
    def _shape(info):
        return int(info.iWidth), int(info.iHeight), int(info.uiMediaType)

    def start(self, handle, options: RecordingOptions, info):
        if self.status().native_open:
            return
        if self._diagnostics is not None:
            self._diagnostics.finish()
        self._diagnostics = None
        self._diagnostic_context = None
        with self._lock:
            self._status = RecordingStatus(state="STARTING", fps=options.fps)
        try:
            if type(options.fps) is not int or not 1 <= options.fps <= 1000:
                raise ValueError("FPS video phải là số nguyên 1–1000.")
            directory = Path(options.directory).expanduser().resolve()
            str(directory).encode("gbk").decode("gbk")
            width, height, media = self._shape(info)
            if (width <= 0 or height <= 0 or media not in
                    (self.sdk.CAMERA_MEDIA_TYPE_RGB8, self.sdk.CAMERA_MEDIA_TYPE_MONO8)):
                raise ValueError("Kích thước hoặc media type camera không hợp lệ.")
            # Budget RGB24 even if this DLL expands MONO8 internally.
            self._frame_bytes = ((width * 3 + 3) // 4 * 4) * height + 32
            self._options = options
            self._geometry = (width, height, media)
            directory.mkdir(parents=True, exist_ok=True)
            self._ensure_space(directory)
            session = datetime.now().strftime("%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:12]
            self._directory = directory / session
            self._directory.mkdir(exist_ok=False)
            self._started_at = self._clock()
            self._last_disk_at = self._started_at
            self._last_stamp = None
            self._open_file(handle)
            if options.color_diagnostics:
                try:
                    self._diagnostics = ColorDiagnostics(self._directory / "color_diagnostics")
                except Exception as exc:
                    self.publish(color_diagnostic_status="Không bật được chẩn đoán màu: " + str(exc))
                    logger.warning("color_diagnostic_init_failed: %s", exc)
        except Exception as exc:
            self._fail(handle, exc)

    def _ensure_space(self, directory):
        if self._disk_free(directory) < max(256 * 1024 ** 2, 2 * self._frame_bytes):
            raise OSError("Không đủ dung lượng trống để ghi video an toàn.")

    def _open_file(self, handle):
        path = self._directory / "video.avi"
        if path.exists():
            raise FileExistsError(f"Không ghi đè file: {path}")
        self._ensure_space(self._directory)
        self.publish(current_path=str(path))
        self._check("CameraInitRecord", self.sdk.CameraInitRecord(
            handle, 0, str(path), False, 100, self._options.fps))
        self.publish(state="RECORDING", native_open=True, segment=1)
        logger.info("record_start path=%s fps=%d shape=%s format=0", path,
                    self._options.fps, self._geometry)

    def _color_context(self, handle):
        if self._diagnostic_context is None:
            context = {}
            for key, function in (
                    ("sdk_version", "CameraSdkGetVersionString"),
                    ("isp_output", "CameraGetIspOutFormat"),
                    ("wb_mode", "CameraGetWbMode"),
                    ("rgb_gain", "CameraGetGain"),
                    ("gamma", "CameraGetGamma"),
                    ("saturation", "CameraGetSaturation"),
                    ("exposure_us", "CameraGetExposureTime"),
                    ("auto_exposure", "CameraGetAeState")):
                try:
                    getter = getattr(self.sdk, function)
                    value = getter() if key == "sdk_version" else getter(handle)
                    if self.sdk.GetLastError() != 0:
                        raise RuntimeError("SDK getter failed")
                    # Reject unserializable SDK objects instead of inventing values.
                    json.dumps(value, allow_nan=False)
                    context[key] = value
                except Exception:
                    context[key] = None
            self._diagnostic_context = context
        return dict(self._diagnostic_context)

    def push(self, handle, pointer, info):
        status = self.status()
        if status.state != "RECORDING":
            return
        try:
            if self._shape(info) != self._geometry:
                raise ValueError("Kích thước/media type thay đổi trong phiên ghi.")
            stamp = int(info.uiTimeStamp)
            delta = 0 if self._last_stamp is None else (stamp - self._last_stamp) & 0xFFFFFFFF
            if delta >= 0x80000000:
                raise ValueError("Timestamp camera bị reset hoặc đi lùi.")
            sample = None
            if self._diagnostics is not None:
                try:
                    width, height, media = self._geometry
                    interpretation = "MONO8" if media == self.sdk.CAMERA_MEDIA_TYPE_MONO8 else "RGB8"
                    size = width * height * (1 if interpretation == "MONO8" else 3)
                    sample = self._diagnostics.before(
                        pointer, size, info, interpretation, status.pushed_frames + 1,
                        self._color_context(handle))
                except Exception as exc:
                    self._diagnostics.report_error(exc)
            succeeded = False
            try:
                self._check("CameraPushFrame", self.sdk.CameraPushFrame(handle, pointer, info))
                succeeded = True
            finally:
                if sample is not None:
                    try:
                        self._diagnostics.after(sample, pointer, size, info, succeeded)
                    except Exception as exc:
                        self._diagnostics.report_error(exc)
            self._last_stamp = stamp
            self.publish(pushed_frames=status.pushed_frames + 1,
                         elapsed=max(0.0, self._clock() - self._started_at))
            self.maintain(handle)
        except Exception as exc:
            self._fail(handle, exc)

    def maintain(self, handle):
        if self.status().state != "RECORDING":
            return
        now = self._clock()
        self.publish(elapsed=max(0.0, now - self._started_at))
        if now - self._last_disk_at >= 1.0:
            self._last_disk_at = now
            try:
                self._ensure_space(self._directory)
            except Exception as exc:
                self._fail(handle, exc)

    def _finalize(self, handle) -> bool:
        if not self.status().native_open:
            return True
        self.publish(state="STOPPING")
        try:
            self._check("CameraStopRecord", self.sdk.CameraStopRecord(handle))
        except Exception as exc:
            self.publish(state="ERROR", error=self._error_text(exc))
            logger.exception("record_finalize_failed path=%s", self.status().current_path)
            return False
        self.publish(native_open=False)
        logger.info("record_finalized path=%s pushed=%d", self.status().current_path,
                    self.status().pushed_frames)
        return True

    def stop(self, handle):
        if self._diagnostics is not None:
            self._diagnostics.finish()
        status = self.status()
        if not status.native_open:
            if status.state in ACTIVE_STATES:
                self.publish(state="ERROR" if status.error else "COMPLETED")
            return
        if self._finalize(handle):
            self.publish(state="ERROR" if self.status().error else "COMPLETED")

    @staticmethod
    def _error_text(exc):
        if isinstance(exc, UnicodeError):
            return "Đường dẫn không biểu diễn được bằng GBK. Chọn thư mục ASCII/GBK."
        return str(exc) or type(exc).__name__

    def _fail(self, handle, exc):
        if self._diagnostics is not None:
            self._diagnostics.finish()
        message = self._error_text(exc)
        self.publish(state="ERROR", error=message)
        logger.warning("record_error path=%s error=%s", self.status().current_path, message)
        if self.status().native_open:
            if self._finalize(handle):
                self.publish(state="ERROR", error=message)
