"""Worker chạy ImprovePipeline ngoài UI thread.

- DecodeWorker: decode 1 frame tại một thời điểm (xem/phát video, xem ảnh).
  submit(replace=False) bỏ frame khi đang bận (giống app camera);
  submit(replace=True) thay frame đang chờ bằng frame mới nhất (chuyển ảnh liên tục).
- ScanWorker: quét toàn bộ video (mỗi N frame) hoặc toàn bộ danh sách ảnh.
Cả hai dùng chung một ImprovePipeline qua SharedPipeline (khoá) — model không chạy song song.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

import numpy as np
from PyQt5.QtCore import QObject, pyqtSignal

from media_source import MediaError, VideoSource, read_image


@dataclass(frozen=True)
class FrameMeta:
    request_id: int
    source: str
    frame_index: int | None = None   # None với ảnh tĩnh
    time_s: float | None = None


class SharedPipeline:
    def __init__(self, pipeline):
        self._pipeline = pipeline
        self._lock = threading.Lock()

    def scan(self, image_bgr: np.ndarray):
        with self._lock:
            return self._pipeline.scan(image_bgr)


class DecodeWorker(QObject):
    done = pyqtSignal(object, list, list)   # (FrameMeta, results, detections)
    failed = pyqtSignal(object, str)

    def __init__(self, pipeline: SharedPipeline, parent=None):
        super().__init__(parent)
        self._pipeline = pipeline
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._pending: tuple[np.ndarray, FrameMeta] | None = None
        self._busy = False
        self._stop = False
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def submit(self, frame: np.ndarray, meta: FrameMeta, replace: bool = False) -> bool:
        with self._lock:
            if not replace and (self._busy or self._pending is not None):
                return False   # đang bận → bỏ qua frame này
            self._pending = (frame, meta)
        self._wake.set()
        return True

    @property
    def busy(self) -> bool:
        with self._lock:
            return self._busy or self._pending is not None

    def stop(self):
        self._stop = True
        self._wake.set()
        self._thread.join(timeout=5)

    def _loop(self):
        while not self._stop:
            self._wake.wait(0.1)
            with self._lock:
                self._wake.clear()
                job, self._pending = self._pending, None
                self._busy = job is not None
            if job is None:
                continue
            frame, meta = job
            try:
                results, detections = self._pipeline.scan(frame)
                self.done.emit(meta, results, detections)
            except Exception as e:  # decode lỗi → bỏ frame này, chạy tiếp
                self.failed.emit(meta, str(e))
            finally:
                with self._lock:
                    self._busy = False


class ScanWorker(QObject):
    progress = pyqtSignal(int, int)                    # (đã xử lý, tổng — 0 nếu không biết)
    hit = pyqtSignal(object, list, list)               # (FrameMeta, results, detections) khi có QR
    preview = pyqtSignal(object, object, list, bool)   # (FrameMeta, frame, detections, ok) ~3 lần/giây
    item_failed = pyqtSignal(str, str)                 # (nguồn, lỗi) — bỏ qua, chạy tiếp
    finished = pyqtSignal(int, bool, str)              # (số frame đã decode, bị huỷ, lỗi nghiêm trọng)

    PREVIEW_INTERVAL_S = 0.3

    def __init__(self, pipeline: SharedPipeline, parent=None):
        super().__init__(parent)
        self._pipeline = pipeline
        self._cancel = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def cancel(self):
        self._cancel.set()

    def wait(self, timeout: float = 5.0):
        if self._thread is not None:
            self._thread.join(timeout)

    def scan_video(self, path: str, step: int, request_id: int) -> None:
        self._start(self._run_video, path, max(1, step), request_id)

    def scan_images(self, paths: list[str], request_id: int) -> None:
        self._start(self._run_images, list(paths), request_id)

    # ── private ───────────────────────────────────────────────────────────────

    def _start(self, target, *args):
        if self.running:
            raise RuntimeError("Đang quét — huỷ trước khi quét mới")
        self._cancel.clear()
        self._last_preview = 0.0
        self._thread = threading.Thread(target=target, args=args, daemon=True)
        self._thread.start()

    def _process(self, frame: np.ndarray, meta: FrameMeta) -> None:
        results, detections = self._pipeline.scan(frame)
        if results:
            self.hit.emit(meta, results, detections)
        now = time.monotonic()
        if results or now - self._last_preview >= self.PREVIEW_INTERVAL_S:
            self._last_preview = now
            self.preview.emit(meta, frame, detections, bool(results))

    def _run_video(self, path: str, step: int, request_id: int):
        processed = 0
        try:
            with VideoSource(path) as src:
                total = (src.frame_count + step - 1) // step if src.frame_count else 0
                while not self._cancel.is_set():
                    if src.position % step:
                        if not src.grab():
                            break
                        continue
                    item = src.read()
                    if item is None:
                        break
                    idx, frame = item
                    self._process(frame, FrameMeta(request_id, path, idx, src.timestamp(idx)))
                    processed += 1
                    self.progress.emit(processed, total)
        except Exception as e:
            self.finished.emit(processed, self._cancel.is_set(), str(e))
            return
        self.finished.emit(processed, self._cancel.is_set(), "")

    def _run_images(self, paths: list[str], request_id: int):
        processed = 0
        for i, path in enumerate(paths, 1):
            if self._cancel.is_set():
                break
            try:
                frame = read_image(path)
                self._process(frame, FrameMeta(request_id, path))
                processed += 1
            except MediaError as e:
                self.item_failed.emit(path, str(e))
            except Exception as e:
                self.item_failed.emit(path, f"Lỗi decode: {e}")
            self.progress.emit(i, len(paths))
        self.finished.emit(processed, self._cancel.is_set(), "")
