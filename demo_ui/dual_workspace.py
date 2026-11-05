"""Màn hình làm việc hai camera: hai khung video, trạng thái riêng từng khung, danh sách mã đã gộp."""

from __future__ import annotations

from PyQt5.QtWidgets import QLabel, QMenu, QVBoxLayout, QWidget

from .merged_stats import MergedRow
from .run_controller import RunState
from .workspace import VideoPanel, Workspace, _label


class DualWorkspace(Workspace):
    def __init__(self, titles: tuple[str, str], menu: QMenu, parent=None):
        self._titles = titles
        self._camera_states = [(RunState.IDLE, "") for _ in titles]
        self._camera_lost = [False for _ in titles]
        super().__init__(QLabel(), menu, parent)

    def _build_video_area(self) -> QWidget:
        self.videos = [self.video, VideoPanel(QLabel(), self)]
        area = QWidget(self)
        column = QVBoxLayout(area)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(6)
        for title, video in zip(self._titles, self.videos):
            column.addWidget(_label(title, "cardTitle"))
            column.addWidget(video, 1)
        return area

    def set_camera_state(self, cam: int, state: RunState, message: str = ""):
        self._camera_states[cam] = (state, message)
        self._camera_lost[cam] = False
        if state is not RunState.RUNNING:
            self.videos[cam].video_label.clear()
        self._render_overlay()

    def set_camera_lost(self, cam: int, lost: bool):
        if lost != self._camera_lost[cam]:
            self._camera_lost[cam] = lost
            self._render_overlay()

    def _render_overlay(self):
        for video, (state, message), lost in zip(self.videos, self._camera_states, self._camera_lost):
            if lost:
                video.show_message("Mất tín hiệu camera\nBấm Dừng rồi Bắt đầu lại.", error=False)
            elif state is RunState.IDLE:
                video.show_message("Sẵn sàng\nBấm Bắt đầu để chạy.")
            elif state in (RunState.CONNECTING, RunState.STOPPING):
                video.show_message(message)
            elif state is RunState.ERROR:
                video.show_message(message, error=True)
            else:
                video.hide_message()

    def set_camera_fps_pair(self, values: list[int | None]):
        """Mỗi camera một số; None = camera đó không chạy."""
        parts = ["{} ● {} fps".format(name, "—" if fps is None else fps)
                 for name, fps in zip("AB", values)]
        self.lbl_camera.setText("   ".join(parts))
        running = [fps for fps in values if fps is not None]
        self._set_level(self.lbl_camera, "" if not running else "ok" if all(running) else "bad")

    def set_processing_pair(self, device: str, values: list[float | None]):
        parts = ["{} {}".format(name, "—" if ms is None else "{:.0f} ms".format(ms))
                 for name, ms in zip("AB", values)]
        self.lbl_processing.setText("{} ● {}".format(device, " · ".join(parts)))
        self._set_level(self.lbl_processing, "ok" if device == "GPU" else "warn")

    def set_camera_rates(self, rates: list[float | None]):
        parts = ["{} {}".format(name, "—" if rate is None else "{:.0f}%".format(rate * 100))
                 for name, rate in zip("AB", rates)]
        self.kpi_rate.setText(" · ".join(parts))
        self.kpi_rate.setStyleSheet("font-size: 16px;")

    def upsert_row(self, row: MergedRow):
        super().upsert_row(row)
        index = self._items[row.track_id].row()
        self.table.item(index, 0).setText("{}  {}".format(row.clock, row.camera_text))
