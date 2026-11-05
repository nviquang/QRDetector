"""Một thread decode cho hai camera, luân phiên giữa các camera có frame chờ.

Chỉ một thread vì hai camera dùng chung một GPU và ``qr/decoder.py`` giữ detector WeChat toàn cục
không có khóa. Mỗi camera có PassReader riêng nên lượt của hai camera không lẫn nhau.
"""

from __future__ import annotations

import threading

import numpy as np

from qr.pass_reader import PassReader

from PyQt5.QtCore import QObject, pyqtSignal


class DualDecodeWorker(QObject):
    done = pyqtSignal(int, list, list)   # (camera, results, overlays)
    stats = pyqtSignal(int, dict)        # (camera, detect_ms / cascade_ms / skipped)
    reads = pyqtSignal(int, list)        # (camera, list[Track] vừa có nội dung lần đầu)
    passes = pyqtSignal(int, list)       # (camera, list[Track] vừa kết thúc)
    failed = pyqtSignal(int, str)
    flushed = pyqtSignal(str, list)      # (mục đích, list[(camera, list[Track] còn mở)])
    ready = pyqtSignal()                 # warm-up xong (kể cả lỗi)

    def __init__(self, pipeline, count: int = 2, parent=None):
        super().__init__(parent)
        self._readers = [PassReader(pipeline) for _ in range(count)]
        self._lock = threading.Lock()
        self._pending: list[tuple[np.ndarray, int] | None] = [None] * count
        self._active: int | None = None
        self._next = 0
        self._flushes: list[str] = []
        self._stop = False
        self.is_ready = False
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def submit(self, cam: int, frame: np.ndarray, seq: int) -> bool:
        """False nếu camera này đang có frame chờ hoặc đang được decode — frame đó bị bỏ qua."""
        with self._lock:
            if self._active == cam or self._pending[cam] is not None:
                return False
            self._pending[cam] = (frame, seq)
            return True

    def decode_every(self, cam: int, default_n: int) -> int:
        """Số frame nên chờ giữa hai lần gửi của camera này: ngắn hơn khi có lượt đang chờ đọc."""
        return self._readers[cam].decode_every(default_n)

    def set_exposure_ms(self, cam: int, exposure_ms: float | None):
        self._readers[cam].set_exposure_ms(exposure_ms)

    def request_flush(self, purpose: str):
        """Chốt lượt đang mở trên thread worker rồi phát ``flushed``, sau mọi kết quả trước đó."""
        if not self._thread.is_alive():
            self.flushed.emit(purpose, self._flush_all())
            return
        with self._lock:
            self._flushes.append(purpose)

    def stop(self):
        self._stop = True
        self._thread.join(timeout=5)
        if self._thread.is_alive():
            return              # còn đang warm-up/decode dở → không đụng tracker từ thread khác
        for cam, tracks in self._flush_all():
            if tracks:
                self.passes.emit(cam, tracks)

    def _flush_all(self) -> list[tuple[int, list]]:
        return [(cam, reader.flush()) for cam, reader in enumerate(self._readers)]

    def _take_job(self) -> tuple[int, np.ndarray, int] | None:
        count = len(self._pending)
        for offset in range(count):
            cam = (self._next + offset) % count
            job = self._pending[cam]
            if job is not None:
                self._pending[cam] = None
                self._next = (cam + 1) % count
                return (cam, *job)
        return None

    def _loop(self):
        try:
            self._readers[0].warmup()   # dùng chung pipeline: warm-up một lần; không chặn UI
        except Exception as e:
            self.failed.emit(0, "Warm-up lỗi: {}".format(e))
        self.is_ready = True
        self.ready.emit()
        while not self._stop:
            with self._lock:
                flushes, self._flushes = self._flushes, []
                if flushes:
                    self._pending = [None] * len(self._pending)   # frame chờ thuộc về trước lúc chốt
                job = self._take_job()
                self._active = job[0] if job is not None else None
            for purpose in flushes:
                self.flushed.emit(purpose, self._flush_all())
            if job is None:
                threading.Event().wait(0.01)
                continue
            try:
                self._process(*job)
            finally:
                with self._lock:
                    self._active = None

    def _process(self, cam: int, frame: np.ndarray, seq: int):
        try:
            r = self._readers[cam].process(frame, seq)
        except Exception as e:  # decode lỗi → bỏ frame này, chạy tiếp
            self.failed.emit(cam, str(e))
            return
        self.done.emit(cam, r.results, r.overlays)
        self.stats.emit(cam, {"detect_ms": r.detect_ms, "cascade_ms": r.cascade_ms,
                              "skipped": r.skipped})
        if r.first_reads:
            self.reads.emit(cam, r.first_reads)
        if r.finished:
            self.passes.emit(cam, r.finished)
