"""Cửa sổ chính app hai camera: MindVision (A) và Basler (B) cùng đọc QR, kết quả gộp một danh sách.

Mỗi camera có RunController và luồng đóng bất đồng bộ riêng, nên một camera lỗi không kéo camera kia
dừng. Trạng thái chung chỉ để hiển thị và điều khiển nút chính, suy ra từ trạng thái hai camera.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import cv2
import numpy as np

# torch (qua qr/) PHẢI load TRƯỚC PyQt5: nếu import PyQt5 trước, torch
# fail WinError 1114 (c10.dll) do xung đột DLL trong môi trường Windows.
from camera.basler_manager import BaslerCameraManager
from camera.camera_manager import CameraManager
from camera.conveyor import RunSettings
from qr import ImprovePipeline

from PyQt5.QtCore import QTimer, pyqtSignal
from PyQt5.QtGui import QKeySequence, QPixmap
from PyQt5.QtWidgets import (QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QGroupBox, QHBoxLayout,
                             QLabel, QMainWindow, QMenu, QMessageBox, QPushButton, QShortcut,
                             QSpinBox, QTabWidget, QVBoxLayout, QWidget)

from ui.main_window import draw_overlays, frame_to_qimage

from .app_settings import AppSettings, DualSettings
from .dual_worker import DualDecodeWorker
from .dual_workspace import DualWorkspace
from .merged_stats import MergedStats
from .run_controller import RunController, RunState, StartRequest
from .scan_uploader import ScanUploader
from .session_stats import age_text
from .settings_window import _page

SIGNAL_LOST_S = 3.0
SETTINGS_SAVE_DELAY_MS = 500
FLUSH_STOP, FLUSH_RESET = "stop", "reset"
TITLES = ("CAMERA A · MINDVISION", "CAMERA B · BASLER")
TAB_TITLES = ("Camera A · MindVision", "Camera B · Basler", "Chung")


def _device_for(use_gpu: bool) -> str:
    return "auto" if use_gpu else "cpu"


def overall_state(states: list[RunState]) -> RunState:
    """Trạng thái hiển thị chung: còn camera đang chạy thì vẫn là chạy dù camera kia lỗi."""
    for state in (RunState.STOPPING, RunState.CONNECTING, RunState.RUNNING, RunState.ERROR):
        if state in states:
            return state
    return RunState.IDLE


class CameraPanel(QGroupBox):
    """Cấu hình một camera; chỉ giữ widget, không gọi SDK."""

    def __init__(self, title: str, gain_suffix: str, parent=None):
        super().__init__(title, parent)
        layout = QVBoxLayout(self)

        row = QHBoxLayout()
        self.cbx_camera = QComboBox()
        self.cbx_camera.setMinimumWidth(320)
        self.btn_refresh = QPushButton("⟳")
        self.btn_refresh.setToolTip("Quét lại danh sách camera")
        row.addWidget(QLabel("Camera:"))
        row.addWidget(self.cbx_camera)
        row.addWidget(self.btn_refresh)
        row.addStretch(1)
        layout.addLayout(row)

        row = QHBoxLayout()
        self.spin_n = QSpinBox()
        self.spin_n.setRange(1, 1000)
        self.spin_n.setToolTip("Cứ N frame camera thì gửi 1 frame đi đọc mã; bộ đọc đang bận thì chờ frame sau.")
        self.spin_exposure = QDoubleSpinBox()
        self.spin_exposure.setRange(0.01, 2000.0)
        self.spin_exposure.setDecimals(2)
        self.spin_exposure.setSingleStep(0.5)
        self.spin_gain = QSpinBox()
        self.spin_gain.setRange(0, 1000)
        self.spin_gain.setSuffix(gain_suffix)
        self.spin_gain.setToolTip("Giá trị vượt giới hạn camera sẽ bị kẹp.")
        row.addWidget(QLabel("N (frame / lần decode):"))
        row.addWidget(self.spin_n)
        row.addWidget(QLabel("Exposure (ms):"))
        row.addWidget(self.spin_exposure)
        row.addWidget(QLabel("Gain:"))
        row.addWidget(self.spin_gain)
        row.addStretch(1)
        layout.addLayout(row)

        self.cbx_band_y, self.spin_band_y, self.spin_band_h = self._band_row(layout, "Chỉ đọc dải y:", "cao:")
        self.cbx_band_x, self.spin_band_x, self.spin_band_w = self._band_row(layout, "Chỉ đọc dải x:", "rộng:")

        row = QHBoxLayout()
        self.btn_apply = QPushButton("Áp dụng")
        self.btn_apply.setEnabled(False)
        row.addWidget(self.btn_apply)
        row.addStretch(1)
        layout.addLayout(row)
        self.lbl_status = QLabel("Exposure — | gain — | sáng — | cháy —")
        self.lbl_status.setWordWrap(True)
        layout.addWidget(self.lbl_status)

    @staticmethod
    def _band_row(layout, title: str, size_title: str):
        row = QHBoxLayout()
        enabled = QCheckBox(title)
        start = QSpinBox()
        start.setRange(0, 4096)
        start.setSingleStep(16)
        size = QSpinBox()
        size.setRange(16, 4096)
        size.setSingleStep(16)
        row.addWidget(enabled)
        row.addWidget(start)
        row.addWidget(QLabel(size_title))
        row.addWidget(size)
        row.addStretch(1)
        layout.addLayout(row)
        return enabled, start, size

    def change_signals(self) -> tuple:
        return (self.spin_n.valueChanged, self.spin_exposure.valueChanged, self.spin_gain.valueChanged,
                self.cbx_band_y.toggled, self.spin_band_y.valueChanged, self.spin_band_h.valueChanged,
                self.cbx_band_x.toggled, self.spin_band_x.valueChanged, self.spin_band_w.valueChanged)

    def load(self, s: AppSettings):
        self.spin_n.setValue(s.decode_every_n)
        self.spin_exposure.setValue(s.exposure_ms)
        self.spin_gain.setValue(s.analog_gain)
        self.cbx_band_y.setChecked(s.band_enabled)
        self.spin_band_y.setValue(s.band_y)
        self.spin_band_h.setValue(s.band_h)
        self.cbx_band_x.setChecked(s.band_x_enabled)
        self.spin_band_x.setValue(s.band_x)
        self.spin_band_w.setValue(s.band_w)

    def collect(self, s: AppSettings):
        s.decode_every_n = self.spin_n.value()
        s.exposure_ms = self.spin_exposure.value()
        s.analog_gain = self.spin_gain.value()
        s.band_enabled = self.cbx_band_y.isChecked()
        s.band_y = self.spin_band_y.value()
        s.band_h = self.spin_band_h.value()
        s.band_x_enabled = self.cbx_band_x.isChecked()
        s.band_x = self.spin_band_x.value()
        s.band_w = self.spin_band_w.value()

    def run_settings(self) -> RunSettings:
        band_x = (self.spin_band_x.value(), self.spin_band_w.value()) if self.cbx_band_x.isChecked() else None
        band_y = (self.spin_band_y.value(), self.spin_band_h.value()) if self.cbx_band_y.isChecked() else None
        return RunSettings(exposure_us=self.spin_exposure.value() * 1000.0,
                           analog_gain=self.spin_gain.value(), band_x=band_x, band_y=band_y)


class _Channel:
    """Mọi thứ thuộc về một camera trong cửa sổ."""

    def __init__(self, index: int, mgr, settings: AppSettings, panel: CameraPanel, controller: RunController):
        self.index = index
        self.mgr = mgr
        self.settings = settings
        self.panel = panel
        self.controller = controller
        self.devices: list = []
        self.video = None
        self.decoding = False
        self.overlays: list = []
        self.last_seq = -1
        self.last_decode_seq = 0
        self.last_frame: np.ndarray | None = None
        self.last_frame_at = 0.0
        self.last_capture: int | None = None
        self.last_ms: float | None = None
        self.close_thread: threading.Thread | None = None
        self.close_error = ""

    def reset_counters(self):
        self.last_seq = -1
        self.last_decode_seq = 0
        self.last_capture = None
        self.last_ms = None
        self.overlays = []


class DualWindow(QMainWindow):
    upload_status = pyqtSignal(object)      # UploadStatus từ thread gửi → GUI thread
    keyboard_status = pyqtSignal(object)    # KeyStatus từ thread gõ → GUI thread

    def __init__(self, settings_path: Path | None = None, uploader: ScanUploader | None = None,
                 cameras: tuple | None = None, pipeline=None, keyboard_typer=None):
        """settings_path: file JSON; None = không đọc/ghi file và không tạo uploader (dùng trong test).

        cameras: (camera A, camera B), mặc định MindVision và Basler; pipeline: test truyền bản giả.
        keyboard_typer: có thì hiện ô gõ mã vào ô đang chọn (dùng chung hai camera); None = không có.
        """
        super().__init__()
        self._settings_path = settings_path
        self.settings = DualSettings.load(settings_path) if settings_path else DualSettings()
        common = self.settings.a      # phần dùng chung lưu ở bản ghi camera A
        if uploader is None and settings_path:
            uploader = ScanUploader(base_url=common.upload_base_url, on_status=self.upload_status.emit)
        self.uploader = uploader
        self.keyboard_typer = keyboard_typer
        if keyboard_typer is not None:
            keyboard_typer.on_status = self.keyboard_status.emit
        self.pipeline = pipeline if pipeline is not None else ImprovePipeline(device=_device_for(common.use_gpu))
        self.worker = DualDecodeWorker(self.pipeline)
        self.stats = MergedStats()
        self._stats_running = False
        self.decode_count = 0
        self._apply_error = ""
        self._closing_app = False
        self._allow_close = False

        managers = cameras if cameras is not None else (CameraManager(), BaslerCameraManager())
        panels = (CameraPanel(TAB_TITLES[0], "", self), CameraPanel(TAB_TITLES[1], " dB", self))
        records = (self.settings.a, self.settings.b)
        self.channels = [_Channel(i, managers[i], records[i], panels[i], RunController(managers[i], self.worker, self))
                         for i in range(2)]

        self._setup_common_panel()
        self._setup_shell()
        self._bind_settings()
        self._connect_signals()

        for ch in self.channels:
            ch.mgr.init_sdk()
        self.display_timer = QTimer(self)
        self.display_timer.timeout.connect(self.on_display_tick)
        self.display_timer.start(33)
        self.fps_timer = QTimer(self)
        self.fps_timer.timeout.connect(self.on_fps_show)
        self.fps_timer.start(1000)
        self.close_timer = QTimer(self)
        self.close_timer.timeout.connect(self.on_close_tick)
        self.close_timer.start(100)
        QTimer.singleShot(100, self.refresh_all_cameras)

    # ── Dựng giao diện ────────────────────────────────────────────────────────

    def _setup_common_panel(self):
        self.common_group = QGroupBox("Dùng chung hai camera")
        layout = QVBoxLayout(self.common_group)
        self.cbx_decode = QCheckBox("Bật decode")
        self.cbx_quad = QCheckBox("Vẽ quad")
        self.cbx_gpu = QCheckBox("Dùng GPU")
        self.cbx_gpu.setToolTip("Chỉ tăng tốc bước phát hiện QR; bước đọc mã vẫn chạy CPU.")
        self.cbx_upload = QCheckBox("Gửi mã lên server")
        self.cbx_upload.setToolTip("Mã trùng trong 30 giây chỉ gửi một lần. Tắt thì mã đọc được không gửi đi.")
        for widget in (self.cbx_decode, self.cbx_quad, self.cbx_gpu, self.cbx_upload):
            layout.addWidget(widget)
        self.cbx_keyboard = None
        if self.keyboard_typer is not None:
            self.cbx_keyboard = QCheckBox("Gõ mã vào ô đang chọn")
            self.cbx_keyboard.setToolTip("Đọc được mã ở camera nào cũng gõ vào ô đang có con trỏ ở ứng dụng khác "
                                         "rồi nhấn Enter. Mã trùng trong 30 giây chỉ gõ một lần.")
            layout.addWidget(self.cbx_keyboard)
        self.lbl_common = QLabel("")
        self.lbl_common.setWordWrap(True)
        layout.addWidget(self.lbl_common)

    def _setup_shell(self):
        self.settings_window = QDialog(self)
        self.settings_window.setWindowTitle("Cấu hình")
        self.tabs = QTabWidget(self.settings_window)
        for ch in self.channels:
            self.tabs.addTab(_page(ch.panel), TAB_TITLES[ch.index])
        self.tabs.addTab(_page(self.common_group), TAB_TITLES[2])
        layout = QVBoxLayout(self.settings_window)
        layout.addWidget(self.tabs)
        self.settings_window.resize(760, 420)

        menu = QMenu(self)
        for index, title in enumerate(TAB_TITLES):
            menu.addAction(title + "…", lambda _=False, i=index: self.open_settings(i))
        menu.addSeparator()
        menu.addAction("Thoát", self.close)
        self.workspace = DualWorkspace(TITLES, menu, self)
        self.setCentralWidget(self.workspace)
        for ch in self.channels:
            ch.video = self.workspace.videos[ch.index]
        self.setWindowTitle("QR Conveyor Reader — Hai camera")
        self.setMinimumSize(1280, 720)
        self.resize(1440, 900)
        QShortcut(QKeySequence("Ctrl+,"), self, activated=lambda: self.open_settings(0))
        QShortcut(QKeySequence("F11"), self, activated=self.on_toggle_fullscreen)
        QShortcut(QKeySequence("Esc"), self, activated=self.showNormal)

    def open_settings(self, index: int):
        self.tabs.setCurrentIndex(index)
        self.settings_window.show()
        self.settings_window.raise_()
        self.settings_window.activateWindow()

    def on_toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def _bind_settings(self):
        common = self.settings.a
        gpu_available = bool(self.pipeline.gpu_available)
        self.cbx_decode.setChecked(common.decode_enabled)
        self.cbx_quad.setChecked(common.draw_quad)
        self.cbx_gpu.setChecked(common.use_gpu and gpu_available)
        self.cbx_gpu.setEnabled(gpu_available)
        self.cbx_upload.setChecked(common.upload_enabled)
        self.on_upload_toggled(common.upload_enabled)
        if self.cbx_keyboard is not None:
            self.cbx_keyboard.setChecked(common.keyboard_output_enabled)
            self.keyboard_typer.set_enabled(common.keyboard_output_enabled)
        for ch in self.channels:
            ch.panel.load(ch.settings)
        self._settings_timer = QTimer(self)
        self._settings_timer.setSingleShot(True)
        self._settings_timer.setInterval(SETTINGS_SAVE_DELAY_MS)
        self._settings_timer.timeout.connect(self._save_settings)
        signals = [self.cbx_decode.toggled, self.cbx_quad.toggled, self.cbx_gpu.toggled, self.cbx_upload.toggled]
        if self.cbx_keyboard is not None:
            signals.append(self.cbx_keyboard.toggled)
        for ch in self.channels:
            signals += ch.panel.change_signals()
        for signal in signals:
            signal.connect(lambda *_: self._settings_timer.start())

    def _connect_signals(self):
        self.worker.done.connect(self.on_decode_done)
        self.worker.failed.connect(self.on_decode_failed)
        self.worker.stats.connect(self.on_decode_stats)
        self.worker.reads.connect(self.on_reads_done)
        self.worker.passes.connect(self.on_passes_done)
        self.worker.flushed.connect(self.on_flushed)
        self.upload_status.connect(self.on_upload_status)
        self.keyboard_status.connect(self.on_keyboard_status)
        if self.cbx_keyboard is not None:
            self.cbx_keyboard.toggled.connect(self.keyboard_typer.set_enabled)
        self.cbx_decode.toggled.connect(self.on_decode_toggled)
        self.cbx_gpu.toggled.connect(lambda checked: self.pipeline.set_device(_device_for(checked)))
        self.cbx_upload.toggled.connect(self.on_upload_toggled)
        self.workspace.primary_clicked.connect(self.on_primary_clicked)
        self.workspace.reset_clicked.connect(self.on_reset)
        for ch in self.channels:
            bind = lambda method, c=ch: (lambda *args: method(c, *args))    # noqa: E731
            ch.controller.state_changed.connect(bind(self._on_channel_state))
            ch.controller.camera_chosen.connect(bind(self._remember_camera))
            ch.controller.configured.connect(bind(self._on_channel_configured))
            ch.controller.cancelled.connect(bind(self._close_channel))
            ch.video.retry_clicked.connect(bind(self._start_channel))
            ch.video.settings_clicked.connect(lambda _=False, i=ch.index: self.open_settings(i))
            ch.panel.btn_apply.clicked.connect(bind(lambda c, *_: self.on_apply(c)))
            ch.panel.btn_refresh.clicked.connect(bind(lambda c, *_: self.refresh_cameras(c)))
            ch.panel.cbx_camera.activated.connect(bind(self._on_camera_selected))

    # ── Cấu hình ──────────────────────────────────────────────────────────────

    def _collect_settings(self):
        common = self.settings.a
        common.decode_enabled = self.cbx_decode.isChecked()
        common.draw_quad = self.cbx_quad.isChecked()
        if self.cbx_gpu.isEnabled():     # máy không có CUDA: giữ lựa chọn đã lưu
            common.use_gpu = self.cbx_gpu.isChecked()
        common.upload_enabled = self.cbx_upload.isChecked()
        if self.cbx_keyboard is not None:
            common.keyboard_output_enabled = self.cbx_keyboard.isChecked()
        for ch in self.channels:
            ch.panel.collect(ch.settings)

    def _save_settings(self):
        self._collect_settings()
        if self._settings_path:
            self.settings.save(self._settings_path)

    def _remember_camera(self, ch: _Channel, serial: str):
        ch.settings.camera_serial = serial
        self._settings_timer.start()

    def _on_camera_selected(self, ch: _Channel, index: int):
        if 0 <= index < len(ch.devices):
            self._remember_camera(ch, ch.devices[index].GetSn())

    def refresh_all_cameras(self):
        for ch in self.channels:
            self.refresh_cameras(ch)

    def refresh_cameras(self, ch: _Channel):
        if ch.mgr.handle is not None or ch.controller.state is not RunState.IDLE:
            return
        ch.devices = list(ch.mgr.list_cameras())
        self._fill_camera_list(ch)

    def _fill_camera_list(self, ch: _Channel):
        combo = ch.panel.cbx_camera
        combo.clear()
        for index, device in enumerate(ch.devices):
            combo.addItem("{} {}".format(device.GetFriendlyName(), device.GetPortType()))
            if device.GetSn() == ch.settings.camera_serial:
                combo.setCurrentIndex(index)

    def on_apply(self, ch: _Channel):
        panel = ch.panel
        applied = ch.mgr.apply_run_settings(panel.run_settings())
        if applied is None:
            panel.lbl_status.setText("Không áp dụng được (camera chưa mở hoặc đang đóng).")
            return
        self.worker.set_exposure_ms(ch.index, applied["exposure_us"] / 1000)
        prefix = "" if applied["ok"] else "[MỘT SỐ THAM SỐ LỖI — xem log] "
        panel.lbl_status.setText("{}Đã áp dụng: exposure {:.2f} ms, gain {}, khung {}".format(
            prefix, applied["exposure_us"] / 1000, applied["analog_gain"], applied["resolution"]))

    def on_decode_toggled(self, checked: bool):
        if not checked:
            for ch in self.channels:
                ch.overlays = []
            if any(ch.decoding for ch in self.channels):
                self.worker.request_flush(FLUSH_STOP)   # chốt các lượt đang mở, khỏi treo ở "…"
            self.workspace.set_processing_warning("Decode tắt")
        else:
            self.workspace.set_processing_idle()

    def on_upload_toggled(self, checked: bool):
        if self.uploader is not None:
            self.uploader.set_enabled(checked)

    # ── Bắt đầu / Dừng / Reset ────────────────────────────────────────────────

    @property
    def state(self) -> RunState:
        return overall_state([ch.controller.state for ch in self.channels])

    def on_primary_clicked(self):
        if self.state in (RunState.CONNECTING, RunState.RUNNING):
            self.on_stop()
        else:
            self.on_start()

    def on_start(self):
        self._save_settings()
        for ch in self.channels:
            self._start_channel(ch)

    def _start_channel(self, ch: _Channel):
        if ch.close_thread is not None:
            return                       # đang đóng camera — bấm lại sau khi đóng xong
        if ch.controller.close_failed:
            self._stop_channel(ch)       # lần đóng trước chưa xong → thử đóng lại trước
            return
        ch.panel.collect(ch.settings)
        ch.reset_counters()
        ch.controller.start(StartRequest(ch.settings.camera_serial, ch.panel.run_settings()))

    def on_stop(self):
        if any(ch.decoding for ch in self.channels):
            self.worker.request_flush(FLUSH_STOP)
        for ch in self.channels:
            self._stop_channel(ch)

    def _stop_channel(self, ch: _Channel):
        ch.decoding = False
        ch.overlays = []
        state = ch.controller.state
        if state is RunState.CONNECTING:
            ch.controller.cancel()       # xong bước đang chạy → signal cancelled → đóng camera
        elif state in (RunState.RUNNING, RunState.ERROR):
            ch.controller.begin_stop()
            self._close_channel(ch)

    def on_reset(self):
        if self._confirm_reset():
            self.worker.request_flush(FLUSH_RESET)

    def _confirm_reset(self) -> bool:
        return QMessageBox.question(self, "Reset phiên", "Đưa toàn bộ số liệu và danh sách mã về 0?",
                                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes

    def on_flushed(self, purpose: str, flushed: list):
        if purpose != FLUSH_RESET:
            for cam, tracks in flushed:
                self.on_passes_done(cam, tracks)
            return
        self.stats.reset()               # lượt còn mở thuộc phiên cũ — bỏ
        self.decode_count = 0
        self.workspace.clear_results()
        self.workspace.set_camera_rates([None, None])
        if self._stats_running:
            self.stats.begin_run()

    def _on_channel_state(self, ch: _Channel, state: RunState, message: str):
        ch.decoding = state is RunState.RUNNING
        if ch.decoding:
            ch.last_frame_at = time.monotonic()
        self.workspace.set_camera_state(ch.index, state, message)
        self.workspace.set_state(self.state, message)
        running = any(c.decoding for c in self.channels)
        if running != self._stats_running:
            self._stats_running = running
            if running:
                self.stats.begin_run()
            else:
                self.stats.end_run()
        self._sync_controls(ch)
        self._refresh_results()

    def _on_channel_configured(self, ch: _Channel):
        self.worker.set_exposure_ms(ch.index, ch.panel.spin_exposure.value())
        ch.devices = list(ch.mgr.camera_list)
        self._fill_camera_list(ch)

    def _sync_controls(self, ch: _Channel):
        idle = ch.controller.state is RunState.IDLE and ch.close_thread is None
        ch.panel.cbx_camera.setEnabled(idle)
        ch.panel.btn_refresh.setEnabled(idle)

    def _refresh_results(self):
        at = self.stats.latest_at
        meta = "" if at is None else "{} · {}".format(self.stats.latest_clock, age_text(time.monotonic() - at))
        self.workspace.set_latest(self.stats.latest_text, meta)
        self.workspace.set_kpis(self.stats.read_count, None, self.stats.per_minute())
        self.workspace.set_camera_rates([self.stats.camera_rate(ch.index) for ch in self.channels])
        self.workspace.set_elapsed(self.stats.elapsed())

    # ── Đóng camera bất đồng bộ ───────────────────────────────────────────────

    def _close_channel(self, ch: _Channel, *_):
        if ch.close_thread is not None:
            return
        ch.close_error = ""

        def close_camera():
            try:
                ch.mgr.close()
            except Exception as exc:
                ch.close_error = str(exc)

        ch.close_thread = threading.Thread(target=close_camera, daemon=True)
        ch.close_thread.start()
        self.on_close_tick()

    def on_close_tick(self):
        for ch in self.channels:
            connecting = ch.controller.state is RunState.CONNECTING
            ch.panel.btn_apply.setEnabled(ch.close_thread is None and not connecting and ch.mgr.handle is not None)
            thread = ch.close_thread
            if thread is None or thread.is_alive():
                continue
            ch.close_thread = None
            if ch.mgr.handle is not None or ch.close_error:
                self._closing_app = False
                ch.controller.on_close_failed("Chưa đóng được camera. " + ch.close_error)
                continue
            ch.overlays = []
            ch.controller.on_camera_closed()
        if self._closing_app and not self._camera_busy():
            self._allow_close = True
            self.close()

    def _camera_busy(self) -> bool:
        return any(ch.mgr.handle is not None or ch.close_thread is not None
                   or ch.controller.state in (RunState.CONNECTING, RunState.STOPPING)
                   for ch in self.channels)

    def closeEvent(self, event):
        if not self._allow_close and self._camera_busy():
            event.ignore()
            self._closing_app = True
            self.on_stop()
            return
        self.display_timer.stop()
        self.fps_timer.stop()
        self.close_timer.stop()
        self._settings_timer.stop()
        self._save_settings()
        self.worker.stop()
        if self.uploader is not None:
            self.uploader.stop()
        if self.keyboard_typer is not None:
            self.keyboard_typer.stop()
        self.settings_window.close()
        event.accept()

    # ── Hiển thị frame + schedule decode ──────────────────────────────────────

    def on_display_tick(self):
        for ch in self.channels:
            self._show_channel(ch)

    def _show_channel(self, ch: _Channel):
        frame, seq = ch.mgr.latest_frame()
        if frame is None or seq == ch.last_seq:
            return
        if (ch.decoding and self.cbx_decode.isChecked()
                and seq - ch.last_decode_seq >= self.worker.decode_every(ch.index, ch.panel.spin_n.value())):
            if self.worker.submit(ch.index, frame, seq):
                ch.last_decode_seq = seq
        ch.last_seq = seq
        ch.last_frame = frame
        ch.last_frame_at = time.monotonic()

        label = ch.video.video_label
        label_w, label_h = label.width(), label.height()
        vis = frame
        if self.cbx_quad.isChecked() and ch.overlays:
            # nét dày theo tỷ lệ thu nhỏ để còn thấy sau khi resize về khung hiển thị
            thickness = max(2, 2 * frame.shape[1] // max(1, label_w))
            vis = draw_overlays(frame, ch.overlays, seq, thickness=thickness)
        label.setPixmap(QPixmap.fromImage(frame_to_qimage(vis, label_w, label_h)))

    def on_fps_show(self):
        self._refresh_results()
        fps: list[int | None] = []
        now = time.monotonic()
        for ch in self.channels:
            if not ch.decoding or ch.close_thread is not None:   # thread nền đang dùng SDK: không gọi getter
                fps.append(None)
                continue
            self.workspace.set_camera_lost(ch.index, now - ch.last_frame_at > SIGNAL_LOST_S)
            capture, _ = ch.mgr.frame_statistic()
            fps.append(0 if ch.last_capture is None else max(0, capture - ch.last_capture))
            ch.last_capture = capture
            if self.settings_window.isVisible():
                self._update_status(ch)
        if any(value is not None for value in fps):
            self.workspace.set_camera_fps_pair(fps)
        self.lbl_common.setText("Decode: {} lần".format(self.decode_count))

    def _update_status(self, ch: _Channel):
        text = "Exposure {:.2f} ms | gain {}".format(ch.mgr.get_exposure_time() / 1000, ch.mgr.get_analog_gain())
        if ch.last_frame is not None:
            gray = cv2.cvtColor(ch.last_frame[::4, ::4], cv2.COLOR_BGR2GRAY)
            text += " | sáng TB {:.0f} | cháy {:.2f}%".format(float(gray.mean()), float((gray >= 250).mean() * 100))
        ch.panel.lbl_status.setText(text)

    # ── Decode callbacks ──────────────────────────────────────────────────────

    def on_decode_done(self, cam: int, results, overlays):
        self.decode_count += 1
        ch = self.channels[cam]
        ch.overlays = overlays if ch.decoding and self.cbx_decode.isChecked() else []

    def on_reads_done(self, cam: int, tracks):
        if self.uploader is not None:
            for track in tracks:
                self.uploader.submit(track.text)    # uploader tự bỏ mã trùng trong 30 giây
        if self.keyboard_typer is not None:
            for track in tracks:
                self.keyboard_typer.submit(track.text)   # cùng mã ở A và B chỉ gõ một lần trong 30 giây
        for row in self.stats.on_reads(cam, tracks):
            self.workspace.upsert_row(row)
        self.workspace.flash_latest()
        self._refresh_results()

    def on_decode_stats(self, cam: int, stats):
        self.channels[cam].last_ms = stats["detect_ms"] + stats["cascade_ms"]
        if self.cbx_decode.isChecked():      # kết quả về muộn không được đè nhãn "Decode tắt"
            device = "GPU" if str(self.pipeline.device).startswith("cuda") else "CPU"
            self.workspace.set_processing_pair(device, [ch.last_ms for ch in self.channels])

    def on_passes_done(self, cam: int, tracks):
        for row in self.stats.on_passes(cam, tracks):
            self.workspace.upsert_row(row)
        self._refresh_results()

    def on_keyboard_status(self, status):
        self.workspace.set_keyboard_status(status.message, status.ok)

    def on_upload_status(self, status):
        if status.last_ok is False:
            self.lbl_common.setText("Gửi mã {} lên server lỗi ({} mã chờ)".format(status.last_text, status.pending))

    def on_decode_failed(self, cam: int, msg: str):
        self.channels[cam].panel.lbl_status.setText("Decode lỗi: {}".format(msg[:100]))
        self.workspace.set_processing_warning("Decode lỗi")
