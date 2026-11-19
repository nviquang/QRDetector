"""Bản phát lại: nối nguồn phát với trạng thái chạy của demo.

- Vào RUNNING (warm-up xong, đang decode) thì ``mgr.start_playback()`` — trước đó nguồn chỉ hiện frame đầu, để lần
  ghi ngắn không hết trước khi decode và Mở ở tab Kết nối chỉ để xem/chỉnh vùng đọc.
- Nguồn hết frame thì Dừng như bấm nút (chốt lượt, đóng nguồn, giữ số liệu phiên) rồi báo "Hết dữ liệu".

Chỉ dùng API công khai của MainWindow (``controller``, ``on_stop``, ``workspace``) để không phải sửa giao diện demo.
"""

from __future__ import annotations

from PyQt5.QtCore import QObject, QTimer

from .run_controller import RunState


class ReplayEndWatcher(QObject):
    def __init__(self, window, mgr, interval_ms: int = 250):
        super().__init__()
        self._window, self._mgr = window, mgr
        self._ended: str | None = None     # tên lần ghi vừa hết, chờ báo khi đã dừng xong
        window.controller.state_changed.connect(self._on_state)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.check)
        self._timer.start(interval_ms)

    def check(self):
        if self._window.controller.state is not RunState.RUNNING:
            return
        if not self._mgr.playing:
            self._mgr.start_playback()
        elif self._ended is None and self._mgr.finished:
            self._ended = self._mgr.current_id or ""
            self._window.on_stop()

    def _on_state(self, state, _message: str = ""):
        if state is RunState.RUNNING:
            self._mgr.start_playback()
        if state is RunState.IDLE and self._ended is not None:
            name = ": " + self._ended if self._ended else ""
            self._window.workspace.video.show_message(f"Hết dữ liệu{name}\nBấm Bắt đầu để phát lại từ đầu.")
            self._ended = None
        elif state is not RunState.STOPPING and state is not RunState.IDLE:
            self._ended = None
