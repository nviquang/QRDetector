"""Chạy nền: ẩn cửa sổ xuống khay hệ thống, camera và decode vẫn chạy; bấm icon để mở lại."""

from __future__ import annotations

from PyQt5.QtCore import QObject, QRectF, Qt
from PyQt5.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PyQt5.QtWidgets import QAction, QMenu, QSystemTrayIcon

from . import theme
from .run_controller import RunState
from .workspace import STATE_TEXT

TOOLTIP_MAX = 127        # Windows cắt tooltip khay ở 127 ký tự
MESSAGE_MS = 4000

STATE_COLOR = {RunState.IDLE: theme.MUTED, RunState.TUNING: theme.BLUE,
               RunState.CONNECTING: theme.AMBER, RunState.RUNNING: theme.GREEN,
               RunState.STOPPING: theme.AMBER, RunState.ERROR: theme.RED}


def make_icon(color: str) -> QIcon:
    """Ô vuông bo góc màu trạng thái, bên trong là ba ô định vị của QR."""
    size = 32
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(color))
    painter.drawRoundedRect(QRectF(0, 0, size, size), 6, 6)
    for x, y in ((5, 5), (19, 5), (5, 19)):
        painter.setBrush(QColor("white"))
        painter.drawRect(x, y, 8, 8)
        painter.setBrush(QColor(color))
        painter.drawRect(x + 2, y + 2, 4, 4)
    painter.setBrush(QColor("white"))
    painter.drawRect(20, 20, 3, 3)
    painter.drawRect(24, 24, 3, 3)
    painter.end()
    return QIcon(pixmap)


class TrayController(QObject):
    """Icon khay của MainWindow demo. Icon chỉ hiện khi cửa sổ đang chạy nền.

    window cần có: settings_window, on_primary_clicked(), close(), các hàm show/hide của QMainWindow.
    """

    def __init__(self, window, parent=None):
        super().__init__(parent or window)
        self._window = window
        self._state = RunState.IDLE
        self._read_count = 0
        self._was_fullscreen = False
        self._was_maximized = False
        self._hinted = False
        self._signal_lost = False
        self._icons: dict[str, QIcon] = {}
        self.background = False

        self.menu = QMenu()
        self.act_open = QAction("Mở cửa sổ", self.menu)
        font = QFont(self.act_open.font())
        font.setBold(True)
        self.act_open.setFont(font)
        self.act_open.triggered.connect(self.restore)
        self.act_primary = QAction("Bắt đầu", self.menu)
        self.act_primary.triggered.connect(window.on_primary_clicked)
        self.act_quit = QAction("Thoát", self.menu)
        self.act_quit.triggered.connect(self.quit)
        self.menu.addAction(self.act_open)
        self.menu.addAction(self.act_primary)
        self.menu.addSeparator()
        self.menu.addAction(self.act_quit)

        self.icon = QSystemTrayIcon(self)
        self.icon.setContextMenu(self.menu)
        self.icon.activated.connect(self._on_activated)
        self.icon.messageClicked.connect(self.restore)
        self._render()

    @staticmethod
    def available() -> bool:
        return QSystemTrayIcon.isSystemTrayAvailable()

    # ── Ẩn / hiện ────────────────────────────────────────────────────────────

    def hide_window(self):
        window = self._window
        self._was_fullscreen = window.isFullScreen()
        self._was_maximized = window.isMaximized()
        window.settings_window.hide()
        window.hide()
        self.background = True
        self._render()
        self.icon.show()
        if not self._hinted:
            self._hinted = True
            self.icon.showMessage("Đang chạy nền", "Vẫn tiếp tục đọc mã. Bấm icon ở khay hệ thống để mở lại.",
                                  QSystemTrayIcon.Information, MESSAGE_MS)

    def restore(self):
        window = self._window
        self.background = False
        self.icon.hide()
        if self._was_fullscreen:
            window.showFullScreen()
        elif self._was_maximized:
            window.showMaximized()
        else:
            window.showNormal()
        window.raise_()
        window.activateWindow()

    def quit(self):
        """Thoát qua closeEvent của cửa sổ (đóng camera bất đồng bộ như nút X)."""
        self._window.close()

    def hide(self):
        self.background = False
        self.icon.hide()

    def _on_activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.restore()

    # ── Trạng thái ───────────────────────────────────────────────────────────

    def set_state(self, state: RunState, message: str = ""):
        changed = state is not self._state
        self._state = state
        if state is not RunState.RUNNING:
            self._signal_lost = False
        self._render()
        if changed and state is RunState.ERROR and self.background:
            self.icon.showMessage("Lỗi camera", message or "Mở cửa sổ để xem chi tiết.",
                                  QSystemTrayIcon.Warning, MESSAGE_MS)

    def set_read_count(self, count: int):
        if count != self._read_count:
            self._read_count = count
            self._render_tooltip()

    def set_signal_lost(self, lost: bool):
        if lost == self._signal_lost:
            return
        self._signal_lost = lost
        self._render_tooltip()
        if lost and self.background:
            self.icon.showMessage("Mất tín hiệu camera", "Không nhận được frame mới từ camera.",
                                  QSystemTrayIcon.Warning, MESSAGE_MS)

    def _render(self):
        color = STATE_COLOR.get(self._state, theme.MUTED)
        if color not in self._icons:
            self._icons[color] = make_icon(color)
        self.icon.setIcon(self._icons[color])
        running = self._state in (RunState.CONNECTING, RunState.RUNNING)
        self.act_primary.setText("Dừng" if running else "Bắt đầu")
        self.act_primary.setEnabled(self._state is not RunState.STOPPING)
        self._render_tooltip()

    def _render_tooltip(self):
        text = STATE_TEXT.get(self._state, "").capitalize()
        if self._signal_lost:
            text += " · mất tín hiệu"
        text += " · đã đọc {}".format(self._read_count)
        title = self._window.windowTitle() or "QR Conveyor Reader"
        tooltip = "{}\n{}".format(title, text)
        self.icon.setToolTip(tooltip[:TOOLTIP_MAX])
