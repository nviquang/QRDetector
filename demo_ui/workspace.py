"""Màn hình làm việc: chỉ hiển thị dữ liệu MainWindow đưa vào, không gọi SDK/pipeline."""

from __future__ import annotations

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (QAbstractItemView, QFrame, QHBoxLayout, QHeaderView, QLabel, QMenu,
                             QPushButton, QSizePolicy, QTableWidget, QTableWidgetItem, QToolButton,
                             QVBoxLayout, QWidget)

from . import theme
from .run_controller import RunState
from .session_stats import PassRow, RowState

MAX_ROWS = 200
FLASH_MS = 300

STATE_TEXT = {RunState.IDLE: "SẴN SÀNG", RunState.TUNING: "CHỈNH CAMERA",
              RunState.CONNECTING: "ĐANG KẾT NỐI", RunState.RUNNING: "ĐANG CHẠY",
              RunState.STOPPING: "ĐANG DỪNG", RunState.ERROR: "LỖI"}

ROW_MARK = {RowState.READING: ("…", theme.MUTED), RowState.OK: ("✓", theme.GREEN),
            RowState.CONFLICT: ("⚠", theme.AMBER), RowState.FAILED: ("✗", theme.RED)}


def _label(text: str, name: str, parent=None) -> QLabel:
    label = QLabel(text, parent)
    label.setObjectName(name)
    return label


def _repolish(widget):
    widget.style().unpolish(widget)
    widget.style().polish(widget)


def format_elapsed(seconds: float) -> str:
    seconds = int(seconds)
    return "{:02d}:{:02d}:{:02d}".format(seconds // 3600, seconds // 60 % 60, seconds % 60)


class VideoPanel(QFrame):
    """Khung video kèm lớp phủ thông báo (trạng thái, lỗi, mất tín hiệu)."""

    retry_clicked = pyqtSignal()
    settings_clicked = pyqtSignal()

    def __init__(self, video_label: QLabel, parent=None):
        super().__init__(parent)
        self.setObjectName("videoPanel")
        self.video_label = video_label
        video_label.setFrameShape(QFrame.NoFrame)
        video_label.setAlignment(Qt.AlignCenter)
        # Ignored: pixmap lớn không được đẩy layout giãn ra
        video_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(video_label)

        self.overlay = QFrame(self)
        self.overlay.setObjectName("videoOverlay")
        self.message = _label("", "overlayMessage", self.overlay)
        self.message.setAlignment(Qt.AlignCenter)
        self.message.setWordWrap(True)
        self.btn_retry = QPushButton("Thử lại", self.overlay)
        self.btn_settings = QPushButton("Mở Cấu hình", self.overlay)
        for button in (self.btn_retry, self.btn_settings):
            button.setObjectName("overlayButton")
        self.btn_retry.clicked.connect(self.retry_clicked)
        self.btn_settings.clicked.connect(self.settings_clicked)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(self.btn_retry)
        buttons.addWidget(self.btn_settings)
        buttons.addStretch(1)
        overlay_layout = QVBoxLayout(self.overlay)
        overlay_layout.setContentsMargins(40, 0, 40, 0)
        overlay_layout.addStretch(1)
        overlay_layout.addWidget(self.message)
        overlay_layout.addSpacing(16)
        overlay_layout.addLayout(buttons)
        overlay_layout.addStretch(1)

    def resizeEvent(self, event):
        self.overlay.setGeometry(self.rect())
        super().resizeEvent(event)

    def show_message(self, text: str, error: bool = False):
        self.message.setText(text)
        self.message.setProperty("error", error)
        _repolish(self.message)
        self.btn_retry.setVisible(error)
        self.btn_settings.setVisible(error)
        self.overlay.show()
        self.overlay.raise_()

    def hide_message(self):
        self.overlay.hide()


class Workspace(QWidget):
    primary_clicked = pyqtSignal()
    reset_clicked = pyqtSignal()

    def __init__(self, video_label: QLabel, menu: QMenu, parent=None):
        super().__init__(parent)
        self.setObjectName("workspace")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.video = VideoPanel(video_label, self)
        self._items: dict[int, QTableWidgetItem] = {}   # track_id → ô mã (ô tự biết dòng hiện tại)
        self._state = RunState.IDLE
        self._state_message = ""
        self._signal_lost = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._build_header(menu))
        body = QHBoxLayout()
        body.setContentsMargins(12, 12, 12, 12)
        body.setSpacing(12)
        body.addWidget(self._build_video_area(), 65)
        body.addLayout(self._build_results(), 35)
        layout.addLayout(body, 1)
        layout.addWidget(self._build_footer())

        self._flash_timer = QTimer(self)
        self._flash_timer.setSingleShot(True)
        self._flash_timer.timeout.connect(self._end_flash)   # method, không lambda: PyQt tự ngắt khi widget bị hủy
        self.set_state(RunState.IDLE)
        self.set_latest(None, "")
        self.set_kpis(0, None, None)

    # ── Dựng giao diện ────────────────────────────────────────────────────────

    def _build_video_area(self) -> QWidget:
        return self.video

    def _build_header(self, menu: QMenu) -> QFrame:
        bar = QFrame(self)
        bar.setObjectName("headerBar")
        row = QHBoxLayout(bar)
        row.setContentsMargins(16, 8, 16, 8)
        row.setSpacing(12)
        row.addWidget(_label("▣  QR Conveyor Reader", "appTitle"))
        row.addSpacing(24)
        self.lbl_state = _label("", "stateText")
        self.lbl_elapsed = _label("", "elapsedText")
        row.addWidget(self.lbl_state)
        row.addWidget(self.lbl_elapsed)
        row.addStretch(1)
        self.btn_reset = QPushButton("Reset phiên", bar)
        self.btn_reset.setObjectName("headerButton")
        self.btn_reset.clicked.connect(self.reset_clicked)
        self.btn_menu = QToolButton(bar)
        self.btn_menu.setObjectName("headerButton")
        self.btn_menu.setText("⚙  Cấu hình")
        self.btn_menu.setPopupMode(QToolButton.InstantPopup)
        self.btn_menu.setMenu(menu)
        row.addWidget(self.btn_reset)
        row.addWidget(self.btn_menu)
        return bar

    def _build_results(self) -> QVBoxLayout:
        column = QVBoxLayout()
        column.setSpacing(12)

        self.latest_card = QFrame(self)
        self.latest_card.setObjectName("latestCard")
        latest = QVBoxLayout(self.latest_card)
        latest.setContentsMargins(16, 12, 16, 12)
        latest.addWidget(_label("MÃ VỪA ĐỌC", "cardTitle"))
        self.lbl_latest_code = _label("", "latestCode")
        self.lbl_latest_code.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.lbl_latest_code.setMinimumHeight(52)
        latest.addWidget(self.lbl_latest_code)
        self.lbl_latest_meta = _label("", "latestMeta")
        latest.addWidget(self.lbl_latest_meta)
        column.addWidget(self.latest_card)

        kpis = QHBoxLayout()
        kpis.setSpacing(12)
        self.kpi_read = self._kpi(kpis, "ĐÃ ĐỌC")
        self.kpi_rate = self._kpi(kpis, "TỈ LỆ ĐỌC")
        self.kpi_speed = self._kpi(kpis, "MÃ / PHÚT")
        column.addLayout(kpis)

        card = QFrame(self)
        card.setObjectName("card")
        table_layout = QVBoxLayout(card)
        table_layout.setContentsMargins(16, 12, 8, 8)
        table_layout.addWidget(_label("MÃ ĐÃ ĐỌC", "cardTitle"))
        self.table = QTableWidget(0, 3, card)
        self.table.setObjectName("passTable")
        self.table.horizontalHeader().hide()
        self.table.verticalHeader().hide()
        self.table.setShowGrid(False)
        self.table.setFocusPolicy(Qt.NoFocus)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setTextElideMode(Qt.ElideRight)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        table_layout.addWidget(self.table)
        column.addWidget(card, 1)
        return column

    def _kpi(self, row: QHBoxLayout, title: str) -> QLabel:
        card = QFrame(self)
        card.setObjectName("card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.addWidget(_label(title, "cardTitle"))
        value = _label("", "kpiValue")
        layout.addWidget(value)
        row.addWidget(card, 1)
        return value

    def _build_footer(self) -> QFrame:
        bar = QFrame(self)
        bar.setObjectName("footerBar")
        row = QHBoxLayout(bar)
        row.setContentsMargins(16, 10, 16, 10)
        row.setSpacing(28)
        self.btn_primary = QPushButton("", bar)
        self.btn_primary.setObjectName("primaryButton")
        self.btn_primary.clicked.connect(self.primary_clicked)
        row.addWidget(self.btn_primary)
        row.addStretch(1)
        self.lbl_camera = _label("Camera —", "footerItem")
        self.lbl_processing = _label("Xử lý —", "footerItem")
        self.lbl_keyboard = _label("", "footerItem")
        self.lbl_keyboard.hide()
        row.addWidget(self.lbl_keyboard)
        row.addWidget(self.lbl_camera)
        row.addWidget(self.lbl_processing)
        return bar

    # ── Cập nhật dữ liệu ──────────────────────────────────────────────────────

    def set_state(self, state: RunState, message: str = ""):
        self._state, self._state_message = state, message
        self.lbl_state.setText(STATE_TEXT[state])
        self.lbl_state.setStyleSheet("color: {};".format(theme.STATE_COLORS[state.value]))
        running = state in (RunState.CONNECTING, RunState.RUNNING)
        self.btn_primary.setText("■  DỪNG" if running else "▶  BẮT ĐẦU")
        self.btn_primary.setProperty("running", running)
        _repolish(self.btn_primary)
        self.btn_primary.setEnabled(state is not RunState.STOPPING)
        if state in (RunState.IDLE, RunState.CONNECTING, RunState.STOPPING):
            self.video.video_label.clear()
        if state not in (RunState.RUNNING, RunState.TUNING):
            self.set_camera_fps(None)
        self._signal_lost = False
        self._render_overlay()

    def _render_overlay(self):
        if self._signal_lost:
            self.video.show_message("Mất tín hiệu camera\nBấm Dừng rồi Bắt đầu lại.", error=False)
        elif self._state is RunState.IDLE:
            self.video.show_message("Sẵn sàng\nBấm Bắt đầu để chạy.")
        elif self._state in (RunState.CONNECTING, RunState.STOPPING):
            self.video.show_message(self._state_message)
        elif self._state is RunState.ERROR:
            self.video.show_message(self._state_message, error=True)
        else:
            self.video.hide_message()

    def set_signal_lost(self, lost: bool):
        if lost != self._signal_lost:
            self._signal_lost = lost
            self._render_overlay()

    def set_elapsed(self, seconds: float):
        self.lbl_elapsed.setText(format_elapsed(seconds))

    def set_latest(self, text: str | None, meta: str):
        if text is None:
            self._show_code("—")
            self.lbl_latest_meta.setText("Chưa đọc được mã nào")
            return
        self._show_code(text)
        self.lbl_latest_meta.setText(meta)

    def _show_code(self, text: str):
        if text == self.lbl_latest_code.toolTip() or (text == "—" and self.lbl_latest_code.text() == "—"):
            return      # gọi mỗi giây: không đặt lại stylesheet khi mã không đổi
        # QR có thể chứa chuỗi dài (URL): thu nhỏ chữ rồi cắt, tooltip giữ nội dung đầy đủ
        size = 32 if len(text) <= 16 else 22 if len(text) <= 28 else 15
        self.lbl_latest_code.setStyleSheet("font-size: {}px;".format(size))
        self.lbl_latest_code.setText(text if len(text) <= 60 else text[:59] + "…")
        self.lbl_latest_code.setToolTip(text if text != "—" else "")

    def flash_latest(self):
        self._set_flash(True)
        self._flash_timer.start(FLASH_MS)

    def _end_flash(self):
        self._set_flash(False)

    def _set_flash(self, on: bool):
        self.latest_card.setProperty("flash", on)
        _repolish(self.latest_card)

    def set_kpis(self, read_count: int, read_rate: float | None, per_minute: float | None):
        self.kpi_read.setText(str(read_count))
        self.kpi_rate.setText("—" if read_rate is None else "{:.1f}%".format(read_rate * 100).replace(".", ","))
        self.kpi_speed.setText("—" if per_minute is None else "{:.0f}".format(per_minute))

    def set_camera_fps(self, fps: int | None):
        self.lbl_camera.setText("Camera —" if fps is None else "Camera ● {} fps".format(fps))
        self._set_level(self.lbl_camera, "" if fps is None else "ok" if fps > 0 else "bad")

    def set_processing(self, device: str, total_ms: float):
        self.lbl_processing.setText("{} ● {:.0f} ms".format(device, total_ms))
        self._set_level(self.lbl_processing, "ok" if device == "GPU" else "warn")

    def set_processing_idle(self):
        self.lbl_processing.setText("Xử lý —")
        self._set_level(self.lbl_processing, "")

    def set_processing_warning(self, text: str):
        self.lbl_processing.setText(text)
        self._set_level(self.lbl_processing, "warn")

    def set_keyboard_status(self, message: str, ok: bool):
        self.lbl_keyboard.setText(message if len(message) <= 48 else message[:47] + "…")
        self.lbl_keyboard.setToolTip(message)
        self.lbl_keyboard.show()
        self._set_level(self.lbl_keyboard, "ok" if ok else "warn")

    @staticmethod
    def _set_level(label: QLabel, level: str):
        if label.property("level") != level:
            label.setProperty("level", level)
            _repolish(label)

    def upsert_row(self, row: PassRow):
        item = self._items.get(row.track_id)
        if item is None:
            self.table.insertRow(0)
            item = QTableWidgetItem()
            self._items[row.track_id] = item
            self.table.setItem(0, 0, QTableWidgetItem(row.clock))
            self.table.setItem(0, 1, item)
            self.table.setItem(0, 2, QTableWidgetItem())
            self.table.item(0, 0).setForeground(QColor(theme.MUTED))
            item.setData(Qt.UserRole, row.track_id)
            while self.table.rowCount() > MAX_ROWS:
                last = self.table.rowCount() - 1
                self._items.pop(self.table.item(last, 1).data(Qt.UserRole), None)
                self.table.removeRow(last)
        index = item.row()
        mark, color = ROW_MARK[row.state]
        failed = row.state is RowState.FAILED
        item.setText("không đọc được" if failed else row.text or "")
        item.setToolTip(row.text or "")
        item.setForeground(QColor(theme.RED if failed else theme.TEXT))
        cell = self.table.item(index, 2)
        cell.setText(mark)
        cell.setForeground(QColor(color))

    def clear_results(self):
        self.table.setRowCount(0)
        self._items.clear()
        self.set_latest(None, "")
        self.set_kpis(0, None, None)
        self.set_elapsed(0.0)
