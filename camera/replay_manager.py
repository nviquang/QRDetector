"""Nguồn phát lại: thư mục frame TIFF (``data/field/raw/<rec_id>/frame_NNNN.tiff``) đóng vai camera cho ``demo_ui``.

Chỉ có phần API ``CameraManager`` mà bản demo gọi (như ``basler_manager.BaslerCameraManager``). Mỗi lần ghi là một
"camera": ``GetSn()`` = tên thư mục. Frame được phát theo thời gian thật: mốc thời gian lấy từ mtime từng file (hard
link giữ mtime lúc pylon ghi), chia cho hệ số ``speed``; mtime hỏng thì dùng ``write_fps`` của ``meta.json``. Một
thread đọc trước vào hàng đợi, một thread phát đúng mốc; đọc file chậm hơn nhịp thì phát trễ chứ không nhảy frame.
``open`` chỉ hiện frame đầu; đồng hồ phát chạy từ ``start_playback()`` — ``demo_ui.replay_end.ReplayEndWatcher``
gọi khi app vào RUNNING (warm-up GPU mất vài giây, lần ghi ngắn sẽ hết trước khi decode). Hết frame thì
``finished`` = True và giữ frame cuối. ``seq`` = số thứ tự frame + 1 để khớp ``frames.csv``.
"""

from __future__ import annotations

import json
import logging
import os
import queue
import re
import threading
import time
from pathlib import Path

import cv2
import numpy as np

from camera.conveyor import RunSettings

logger = logging.getLogger("solution.camera")

DEFAULT_FPS = 25.0
PREFETCH = 8                 # số frame đọc trước
LAG_LOG_INTERVAL_S = 5.0
MAX_GAP_S = 5.0              # khoảng giữa hai mtime lớn hơn thế này → coi mtime hỏng
_FRAME_RE = re.compile(r"frame_(\d+)\.tiff?$", re.IGNORECASE)


class ReplayDevice:
    """Một lần ghi, trình bày theo các hàm ``demo_ui`` đọc từ thiết bị camera."""

    def __init__(self, folder: Path):
        self.folder = Path(folder)
        self.frames = sorted((int(m.group(1)), self.folder / name) for name in os.listdir(self.folder)
                             if (m := _FRAME_RE.match(name)))
        try:
            self.meta = json.loads((self.folder / "meta.json").read_text(encoding="utf-8"))
            if not isinstance(self.meta, dict):
                self.meta = {}
        except (OSError, ValueError):
            self.meta = {}

    def GetSn(self) -> str:
        return self.folder.name

    def GetFriendlyName(self) -> str:
        scene = self.meta.get("scene")
        parts = [self.folder.name] + ([scene] if scene else []) + [f"{len(self.frames)} frame"]
        return " · ".join(parts)

    def GetPortType(self) -> str:
        return "File"


class ReplayCameraManager:
    def __init__(self, root: str | Path = "data/field/raw", speed: float = 1.0):
        self.root = Path(root)
        self.speed = max(float(speed), 1e-3)
        self.camera_list: list[ReplayDevice] = []
        self.handle: ReplayDevice | None = None
        self.finished = False
        self._lock = threading.Lock()
        self._frame: np.ndarray | None = None
        self._seq = 0
        self._played = 0
        self._crop: tuple[int, int, int, int] | None = None   # x, w, y, h
        self._preview: tuple[int, np.ndarray] | None = None   # (idx, ảnh xám) frame đầu khi chưa phát
        self._exposure_us = 0.0
        self._gain = 0
        self._stop = threading.Event()
        self._go = threading.Event()
        self._threads: list[threading.Thread] = []

    # ── Danh sách / mở / đóng ─────────────────────────────────────────────────

    def init_sdk(self) -> bool:
        return True

    def list_cameras(self) -> list[ReplayDevice]:
        devices = []
        if self.root.is_dir():
            for entry in sorted(self.root.iterdir()):
                if entry.is_dir():
                    device = ReplayDevice(entry)
                    if device.frames:
                        devices.append(device)
        self.camera_list = devices
        logger.info("Replay enumeration root=%s count=%d", self.root, len(devices))
        return devices

    @property
    def current_id(self) -> str | None:
        return None if self.handle is None else self.handle.GetSn()

    def open(self, index: int) -> bool:
        if index < 0 or index >= len(self.camera_list):
            logger.error("Replay index out of range index=%d count=%d", index, len(self.camera_list))
            return False
        self.close()
        device = self.camera_list[index]
        times = self._timestamps(device)
        first = cv2.imread(str(device.frames[0][1]), cv2.IMREAD_GRAYSCALE)
        if first is None:
            logger.error("Replay cannot read %s", device.frames[0][1])
            return False
        self._size = (first.shape[1], first.shape[0])
        self._crop = None
        self.finished = False
        with self._lock:
            self._frame, self._seq, self._played, self._preview = None, 0, 0, None
        self.handle = device
        self._stop.clear()
        self._go.clear()
        frames: queue.Queue = queue.Queue(PREFETCH)
        self._threads = [threading.Thread(target=self._read_loop, args=(device, frames), daemon=True),
                         threading.Thread(target=self._play_loop, args=(device, times, frames), daemon=True)]
        for t in self._threads:
            t.start()
        logger.info("Replay opened rec=%s frames=%d duration=%.1fs speed=%.2f",
                    device.GetSn(), len(device.frames), times[-1], self.speed)
        return True

    def start_playback(self) -> bool:
        """Bắt đầu đồng hồ phát (gọi nhiều lần không sao); False nếu chưa mở."""
        if self.handle is None:
            return False
        if not self._go.is_set():
            logger.info("Replay playback started rec=%s", self.handle.GetSn())
            self._go.set()
        return True

    @property
    def playing(self) -> bool:
        return self._go.is_set()

    def close(self):
        self._stop.set()
        for t in self._threads:
            t.join(timeout=2.0)
        self._threads = []
        was_open = self.handle is not None
        self.handle = None
        self.finished = False
        with self._lock:
            self._frame, self._seq, self._played, self._preview = None, 0, 0, None
        if was_open:
            logger.info("Replay closed")

    # ── Nhịp phát ─────────────────────────────────────────────────────────────

    def _timestamps(self, device: ReplayDevice) -> list[float]:
        """Mốc thời gian (giây, frame đầu = 0) theo mtime; hỏng thì theo write_fps của meta, rồi 25 fps."""
        mtimes = [os.stat(p).st_mtime for _, p in device.frames]
        gaps = np.diff(mtimes)
        if len(mtimes) > 1 and np.all(gaps > 0) and np.all(gaps < MAX_GAP_S):
            return [t - mtimes[0] for t in mtimes]
        fps = device.meta.get("write_fps")
        fps = float(fps) if isinstance(fps, (int, float)) and fps > 0 else DEFAULT_FPS
        if len(mtimes) > 1:
            logger.warning("Replay mtimes unusable rec=%s — dùng %.2f fps", device.GetSn(), fps)
        return [i / fps for i in range(len(mtimes))]

    def _read_loop(self, device: ReplayDevice, out: queue.Queue):
        for idx, path in device.frames:
            if self._stop.is_set():
                return
            gray = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
            if gray is None:
                logger.error("Replay cannot read %s — bỏ qua", path)
            while not self._stop.is_set():
                try:
                    out.put((idx, gray), timeout=0.1)
                    break
                except queue.Full:
                    continue
        while not self._stop.is_set():
            try:
                out.put(None, timeout=0.1)
                return
            except queue.Full:
                continue

    def _play_loop(self, device: ReplayDevice, times: list[float], frames: queue.Queue):
        start = None
        last_lag_log = 0.0
        k = 0
        while not self._stop.is_set():
            try:
                item = frames.get(timeout=0.1)
            except queue.Empty:
                continue
            if item is None:
                self.finished = True
                logger.info("Replay finished rec=%s played=%d", device.GetSn(), self._played)
                return
            idx, gray = item
            if start is None:
                if gray is not None:          # xem trước frame đầu trong lúc chờ (chưa tính là đã phát)
                    with self._lock:
                        self._preview = (idx, gray)
                    self._show_preview()
                while not self._go.wait(0.05):
                    if self._stop.is_set():
                        return
                with self._lock:
                    self._preview = None
                start = time.monotonic()
            due = start + times[k] / self.speed
            k += 1
            wait = due - time.monotonic()
            if wait > 0:
                if self._stop.wait(wait):
                    return
            elif -wait > 0.2 and time.monotonic() - last_lag_log > LAG_LOG_INTERVAL_S:
                last_lag_log = time.monotonic()
                logger.warning("Replay lagging rec=%s idx=%d late=%.2fs (đọc file chậm hơn nhịp)",
                               device.GetSn(), idx, -wait)
            if gray is None:
                continue
            frame = np.ascontiguousarray(cv2.cvtColor(self._apply_crop(gray), cv2.COLOR_GRAY2BGR))
            with self._lock:
                self._frame, self._seq = frame, idx + 1
                self._played += 1

    def _show_preview(self):
        """Vẽ lại frame xem trước theo vùng đọc hiện tại (Mở ở tab Kết nối để chỉnh vùng đọc)."""
        with self._lock:
            preview = self._preview
        if preview is None:
            return
        idx, gray = preview
        frame = np.ascontiguousarray(cv2.cvtColor(self._apply_crop(gray), cv2.COLOR_GRAY2BGR))
        with self._lock:
            if self._preview is preview:
                self._frame, self._seq = frame, idx + 1

    def _apply_crop(self, gray: np.ndarray) -> np.ndarray:
        crop = self._crop
        if crop is None:
            return gray
        x, w, y, h = crop
        return gray[y:y + h, x:x + w]

    # ── Frame ─────────────────────────────────────────────────────────────────

    def latest_frame(self) -> tuple[np.ndarray | None, int]:
        with self._lock:
            return self._frame, self._seq

    def frame_statistic(self) -> tuple[int, int]:
        """(số frame đã phát, 0) — phát lại không có frame bị thay thế ở nguồn."""
        with self._lock:
            return self._played, 0

    # ── Tham số ───────────────────────────────────────────────────────────────

    def set_trigger_mode(self, mode: int) -> bool:
        return True

    def get_exposure_time(self) -> float:
        return self._exposure_us

    def get_analog_gain(self):
        return self._gain

    def get_resolution(self) -> tuple[int, int] | None:
        if self.handle is None:
            return None
        if self._crop is None:
            return self._size
        return self._crop[1], self._crop[3]

    def apply_run_settings(self, settings: RunSettings) -> dict | None:
        """Không có phần cứng: exposure lấy theo meta.json (nếu đã điền) hoặc theo yêu cầu — dùng để tính vệt mờ;
        vùng đọc cắt từ frame, kẹp trong ảnh, áp dụng từ frame kế tiếp."""
        device = self.handle
        if device is None:
            return None
        known = device.meta.get("exposure_ms")
        self._exposure_us = float(known) * 1000 if isinstance(known, (int, float)) and known > 0 \
            else float(settings.exposure_us)
        self._gain = settings.analog_gain
        width, height = self._size
        x, w = settings.band_x or (0, width)
        y, h = settings.band_y or (0, height)
        x, y = min(max(0, int(x)), width - 1), min(max(0, int(y)), height - 1)
        w, h = max(1, min(int(w), width - x)), max(1, min(int(h), height - y))
        self._crop = None if (x, w, y, h) == (0, width, 0, height) else (x, w, y, h)
        self._show_preview()
        applied = dict(ok=True, exposure_us=self._exposure_us, analog_gain=self._gain,
                       resolution=self.get_resolution())
        logger.info("run_settings requested=%r applied=%r", settings, applied)
        return applied
