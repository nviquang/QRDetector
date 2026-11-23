"""MainWindow của phiên bản demo cho khách hàng — tách riêng, không thay app test camera (ui/).

Dùng lại form, helper hiển thị và DecodeWorker của ui/; khác app test camera:
- Màn hình làm việc (workspace.py), form cấu hình chuyển vào cửa sổ riêng (settings_window.py).
- Nút Bắt đầu/Dừng qua run_controller.py; cấu hình lưu giữa các lần chạy (app_settings.py).
- Mã hiện ngay khi đọc được, số liệu theo phiên (session_stats.py).
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import cv2
import numpy as np

# torch (qua qr/) PHẢI load TRƯỚC PyQt5: nếu import PyQt5 trước, torch
# fail WinError 1114 (c10.dll) do xung đột DLL trong môi trường Windows.
from camera.camera_manager import CameraManager
from camera.conveyor import RunSettings
from qr import ImprovePipeline

from PyQt5.QtCore import QTimer, pyqtSignal
from PyQt5.QtGui import QKeySequence, QPixmap
from PyQt5.QtWidgets import (QApplication, QCheckBox, QDoubleSpinBox, QGroupBox, QHBoxLayout, QLabel,
                             QMainWindow, QMenu, QMessageBox, QPushButton,
                             QShortcut, QSpinBox, QVBoxLayout)

from ui import main_window_ui as MainWindowUI
from ui.main_window import DecodeWorker as BaseDecodeWorker
from ui.main_window import draw_overlays, frame_to_qimage

from .app_settings import AppSettings
from .run_controller import RunController, RunState, StartRequest
from .scan_uploader import ScanUploader
from .session_stats import SessionStats, age_text
from .settings_window import TAB_CONNECTION, TAB_TITLES, SettingsWindow
from .tray import TrayController
from .workspace import Workspace


SIGNAL_LOST_S = 3.0      # đang chạy mà không có frame mới quá lâu → báo mất tín hiệu
SETTINGS_SAVE_DELAY_MS = 500
FLUSH_STOP, FLUSH_RESET = "stop", "reset"


def _device_for(use_gpu: bool) -> str:
    return "auto" if use_gpu else "cpu"


# ── Decode worker ─────────────────────────────────────────────────────────────

class DecodeWorker(BaseDecodeWorker):
    """Thêm báo mã ngay khi đọc được, chốt lượt theo phiên và báo warm-up xong."""

    reads = pyqtSignal(list)        # list[Track] — lượt vừa có nội dung lần đầu
    flushed = pyqtSignal(str, list) # (mục đích, list[Track] còn mở) — sau mọi kết quả trước đó
    ready = pyqtSignal()            # warm-up xong (kể cả lỗi — decode vẫn chạy được, chỉ chậm lần đầu)
    fallback = pyqtSignal(list)     # list[FallbackStatus] — lượt đang đọc nền, phát khi thay đổi

    def __init__(self, pipeline: ImprovePipeline, parent=None):
        self._flushes: list[str] = []
        self.is_ready = False
        super().__init__(pipeline, parent)     # thread bắt đầu chạy ngay trong đây

    def request_flush(self, purpose: str):
        """Chốt các lượt đang mở trên thread worker, rồi phát ``flushed``. Signal từ một thread đến
        GUI theo đúng thứ tự, nên khi GUI nhận ``flushed`` thì mọi kết quả cũ đã được xử lý xong."""
        if not self._thread.is_alive():
            self._emit_flush(purpose)
            return
        with self._lock:
            self._flushes.append(purpose)

    def _emit_flush(self, purpose: str):
        tracks = self._reader.flush(on_fallback=self.fallback.emit)   # chờ đọc nền: vẫn báo B → C
        late = self._reader.take_late_reads()   # đọc nền xong đúng lúc chốt: báo mã trước khi chốt lượt
        if late and purpose != FLUSH_RESET:
            self.reads.emit(late)
        self.fallback.emit([])                  # lượt đọc nền đã chốt hoặc bị bỏ trong flush
        self.flushed.emit(purpose, tracks)

    def _loop(self):
        try:
            self._reader.warmup()   # lần detect đầu trên GPU mất vài giây — làm ở đây, không chặn UI
        except Exception as e:
            self.failed.emit("Warm-up lỗi: {}".format(e))
        self.is_ready = True
        self.ready.emit()
        while not self._stop:
            with self._lock:
                flushes, self._flushes = self._flushes, []
                if flushes:
                    self._pending = None     # frame chờ thuộc về trước thời điểm chốt
                job, self._pending = self._pending, None
                self._busy = job is not None
            for purpose in flushes:
                self._emit_flush(purpose)
            if job is None:
                threading.Event().wait(0.02)
                continue
            try:
                self._process(*job)
            finally:
                with self._lock:
                    self._busy = False

    def _process(self, frame: np.ndarray, seq: int):
        try:
            r = self._reader.process(frame, seq)
        except Exception as e:  # decode lỗi → bỏ frame này, chạy tiếp
            self.failed.emit(str(e))
            return
        self.done.emit(r.results, r.overlays)
        self.stats.emit({"detect_ms": r.detect_ms, "cascade_ms": r.cascade_ms,
                         "skipped": r.skipped})
        if r.first_reads:
            self.reads.emit(r.first_reads)
        if r.finished:
            self.passes.emit(r.finished)
        if r.fallback is not None:              # sau passes: lượt vừa chốt đã rời danh sách đọc nền
            self.fallback.emit(r.fallback)


# ── Main window ───────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):

    upload_status = pyqtSignal(object)      # UploadStatus từ thread gửi → GUI thread

    def __init__(self, settings_path: Path | None = None, uploader: ScanUploader | None = None,
                 camera=None, settings_cls: type[AppSettings] = AppSettings,
                 tray: TrayController | bool = False):
        """settings_path: file JSON lưu cấu hình; None = không đọc/ghi file (dùng trong test).

        uploader: None + có settings_path → tạo ScanUploader thật; test truyền bản giả.
        camera: backend cùng API CameraManager mà demo dùng; None = MindVision.
        settings_cls: lớp cấu hình, quyết định giá trị mặc định theo camera.
        tray: True = nút Chạy nền + icon khay hệ thống (máy không có khay thì bỏ qua);
            False = không có (dùng trong test); test truyền bản giả có cùng API TrayController.
        """
        super().__init__()
        self._tray_option = tray
        self.tray: TrayController | None = None

        # Thành viên
        self._settings_path = settings_path
        self.settings = settings_cls.load(settings_path) if settings_path else settings_cls()
        if uploader is None and settings_path:     # luôn tạo để bật lại được khi đang chạy
            uploader = ScanUploader(base_url=self.settings.upload_base_url,
                                    on_status=self.upload_status.emit)
        self.uploader = uploader
        self.mgr = camera if camera is not None else CameraManager()
        self.pipeline = ImprovePipeline(device=_device_for(self.settings.use_gpu))
        self.worker = DecodeWorker(self.pipeline)
        self.worker.done.connect(self.on_decode_done)
        self.worker.failed.connect(self.on_decode_failed)
        self.worker.stats.connect(self.on_decode_stats)
        self.worker.reads.connect(self.on_reads_done)
        self.worker.passes.connect(self.on_passes_done)
        self.worker.flushed.connect(self.on_flushed)
        self.worker.fallback.connect(self.on_fallback_status)
        self.stats = SessionStats()
        self.controller = RunController(self.mgr, self.worker, self)
        self._decoding = False
        self._last_frame_at = 0.0

        self.cameraList = []
        self.read_fps = 0
        self.display_fps = 0
        self.decode_count = 0
        self._last_seq = -1
        self._last_decode_seq = 0
        self._overlays = []
        self._last_frame: np.ndarray | None = None
        self._apply_error = ""

        # Load UI
        self.ui = MainWindowUI.Ui_MainWindow()
        self.ui.setupUi(self)
        self._setup_qr_panel()
        self._closing_app = False
        self._allow_close = False
        self._camera_close_thread = None
        self._camera_close_error = ""
        self._setup_shell()
        self._bind_settings()

        self.upload_status.connect(self.on_upload_status)
        self.controller.state_changed.connect(self._on_run_state)
        self.controller.configured.connect(self._on_camera_configured)
        self.controller.camera_chosen.connect(self._remember_camera)
        self.controller.cancelled.connect(self.on_camera_close)
        self.workspace.primary_clicked.connect(self.on_primary_clicked)
        self.workspace.reset_clicked.connect(self.on_reset)
        self.workspace.video.retry_clicked.connect(self.on_start)
        self.workspace.video.settings_clicked.connect(lambda: self.settings_window.open_tab(TAB_CONNECTION))

        # SDK init + khung timer
        self.mgr.init_sdk()
        self.display_timer = QTimer()
        self.display_timer.timeout.connect(self.on_display_tick)
        self.display_timer.start(33)   # ~30fps hiển thị
        self.fps_timer = QTimer()
        self.fps_timer.timeout.connect(self.on_fps_show)
        self.fps_timer.start(1000)
        self.close_timer = QTimer(self)
        self.close_timer.timeout.connect(self.on_close_tick)
        self.close_timer.start(100)

        # Slot: Camera
        self.ui.btn_camera_list_flush.clicked.connect(self.on_camera_list_flush)
        self.ui.btn_camera_open.clicked.connect(self.on_camera_open)
        self.ui.btn_camera_close.clicked.connect(self.on_camera_close)

        # Load camera list
        QTimer.singleShot(100, self.on_camera_list_flush)

    # ── Màn hình làm việc + cửa sổ Cấu hình ───────────────────────────────────

    def _setup_shell(self):
        """Chuyển widget của form cũ vào cửa sổ Cấu hình và vùng video, rồi thay central widget."""
        ui = self.ui
        ui.frame_camera_list.setTitle("Camera")
        ui.btn_camera_open.setText("Mở")
        ui.btn_camera_close.setText("Đóng")
        ui.btn_camera_list_flush.setText("⟳")
        ui.btn_camera_list_flush.setToolTip("Quét lại danh sách camera")
        self.settings_window = SettingsWindow(self, ui.frame_camera_list, self.qr_group, ui.status_bar)
        if self._tray_option is True:
            self.tray = TrayController(self) if TrayController.available() else None
        elif self._tray_option:
            self.tray = self._tray_option
        menu = QMenu(self)
        for index, title in enumerate(TAB_TITLES):
            menu.addAction(title + "…", lambda _=False, i=index: self.settings_window.open_tab(i))
        menu.addSeparator()
        if self.tray is not None:
            menu.addAction("Chạy nền", self.on_background)
        menu.addAction("Thoát", self.close)
        self.workspace = Workspace(ui.label_image, menu, self)
        if self.tray is not None:
            self.workspace.set_background_available(True)
            self.workspace.background_clicked.connect(self.on_background)
            QShortcut(QKeySequence("Ctrl+H"), self, activated=self.on_background)
        self.setCentralWidget(self.workspace)     # central widget cũ không còn widget con
        self.setWindowTitle("QR Conveyor Reader")
        self.setMaximumSize(16777215, 16777215)   # setupUi khóa kích thước theo form cũ
        self.setMinimumSize(1280, 720)
        self.resize(1440, 900)
        QShortcut(QKeySequence("Ctrl+,"), self, activated=self.settings_window.open_tab)
        QShortcut(QKeySequence("F11"), self, activated=self.on_toggle_fullscreen)
        QShortcut(QKeySequence("Esc"), self, activated=self.showNormal)

    def on_background(self):
        """Ẩn xuống khay hệ thống; capture, decode, gửi server, gõ phím vẫn chạy."""
        if self.tray is not None:
            self.tray.hide_window()

    def on_toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def _bind_settings(self):
        """Đưa giá trị đã lưu lên widget, sau đó mọi thay đổi đều tự lưu (gom lại bằng timer)."""
        s = self.settings
        self.spin_n.setValue(s.decode_every_n)
        self.cbx_decode.setChecked(s.decode_enabled)
        self.cbx_quad.setChecked(s.draw_quad)
        gpu_available = bool(self.pipeline.gpu_available)
        self.cbx_gpu.setChecked(s.use_gpu and gpu_available)
        self.cbx_gpu.setEnabled(gpu_available)
        if not gpu_available:
            self.cbx_gpu.setToolTip("Không có GPU CUDA trên máy này — nhận diện chạy bằng CPU.")
        self.cbx_upload.setChecked(s.upload_enabled)
        self.on_upload_toggled(s.upload_enabled)
        self.spin_exposure.setValue(s.exposure_ms)
        self.spin_gain.setValue(s.analog_gain)
        self.cbx_conveyor_band.setChecked(s.band_enabled)
        self.spin_band_y.setValue(s.band_y)
        self.spin_band_h.setValue(s.band_h)
        self.cbx_band_x.setChecked(s.band_x_enabled)
        self.spin_band_x.setValue(s.band_x)
        self.spin_band_w.setValue(s.band_w)

        self._settings_timer = QTimer(self)
        self._settings_timer.setSingleShot(True)
        self._settings_timer.setInterval(SETTINGS_SAVE_DELAY_MS)
        self._settings_timer.timeout.connect(self._save_settings)
        for signal in (self.spin_n.valueChanged, self.cbx_upload.toggled,
                       self.cbx_decode.toggled, self.cbx_quad.toggled, self.cbx_gpu.toggled,
                       self.spin_exposure.valueChanged, self.spin_gain.valueChanged,
                       self.cbx_conveyor_band.toggled, self.spin_band_y.valueChanged, self.spin_band_h.valueChanged,
                       self.cbx_band_x.toggled, self.spin_band_x.valueChanged, self.spin_band_w.valueChanged):
            signal.connect(lambda *_: self._settings_timer.start())
        self.ui.cbx_camera_list.activated.connect(self._on_camera_selected)
        self.cbx_decode.toggled.connect(self.on_decode_toggled)
        self.cbx_gpu.toggled.connect(self.on_gpu_toggled)
        self.cbx_upload.toggled.connect(self.on_upload_toggled)

    def _collect_settings(self):
        s = self.settings
        s.decode_every_n = self.spin_n.value()
        s.decode_enabled = self.cbx_decode.isChecked()
        s.draw_quad = self.cbx_quad.isChecked()
        if self.cbx_gpu.isEnabled():     # máy không có CUDA: giữ lựa chọn đã lưu
            s.use_gpu = self.cbx_gpu.isChecked()
        s.upload_enabled = self.cbx_upload.isChecked()
        s.exposure_ms = self.spin_exposure.value()
        s.analog_gain = self.spin_gain.value()
        s.band_enabled = self.cbx_conveyor_band.isChecked()
        s.band_y = self.spin_band_y.value()
        s.band_h = self.spin_band_h.value()
        s.band_x_enabled = self.cbx_band_x.isChecked()
        s.band_x = self.spin_band_x.value()
        s.band_w = self.spin_band_w.value()

    def _save_settings(self):
        self._collect_settings()
        if self._settings_path:
            self.settings.save(self._settings_path)

    def _remember_camera(self, serial: str):
        self.settings.camera_serial = serial
        self._settings_timer.start()

    def _on_camera_selected(self, index: int):
        if 0 <= index < len(self.cameraList):
            self._remember_camera(self.cameraList[index].GetSn())

    # ── Bắt đầu / Dừng / Reset ────────────────────────────────────────────────

    def on_primary_clicked(self):
        if self.controller.state in (RunState.CONNECTING, RunState.RUNNING):
            self.on_stop()
        else:
            self.on_start()

    def on_start(self):
        if self._camera_close_thread is not None:
            return                       # đang đóng camera — bấm lại sau khi đóng xong
        if self.controller.close_failed:
            self.on_stop()               # lần đóng trước chưa xong → thử đóng lại trước
            return
        self._save_settings()
        self._last_seq = -1
        self._last_decode_seq = 0
        self.read_fps = 0
        self.controller.start(StartRequest(self.settings.camera_serial, self.run_settings()))

    def on_stop(self):
        self._decoding = False
        self._overlays = []
        if self.controller.state is RunState.CONNECTING:
            self.controller.cancel()     # xong bước đang chạy → signal cancelled → đóng camera
            return
        self.worker.request_flush(FLUSH_STOP)
        self.controller.begin_stop()
        self.on_camera_close()

    def on_reset(self):
        if self._confirm_reset():
            self.worker.request_flush(FLUSH_RESET)

    def _confirm_reset(self) -> bool:
        return QMessageBox.question(self, "Reset phiên", "Đưa toàn bộ số liệu và danh sách mã về 0?",
                                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes

    def on_flushed(self, purpose: str, tracks: list):
        if purpose != FLUSH_RESET:
            self.on_passes_done(tracks)
            return
        self.stats.reset()               # lượt còn mở thuộc phiên cũ — bỏ
        self.decode_count = 0
        self.workspace.clear_results()
        if self.controller.state is RunState.RUNNING:
            self.stats.begin_run()

    def _on_run_state(self, state: RunState, message: str):
        self.workspace.set_state(state, message)
        if self.tray is not None:
            self.tray.set_state(state, message)
        if state is RunState.RUNNING:
            self._decoding = True
            self._last_frame_at = time.monotonic()
            self.stats.begin_run()
            self._show_decode_state()
        else:
            self._decoding = False
            self.stats.end_run()
        self._sync_camera_controls()
        self._refresh_results()

    def _on_camera_configured(self):
        self.worker.set_exposure_ms(self.spin_exposure.value())
        self.cameraList = list(self.mgr.camera_list)
        self._fill_camera_list()
        self.ui.status_bar.setText("Camera đã mở.")

    def _sync_camera_controls(self):
        if self._camera_close_thread is not None:
            return
        busy = self.controller.state in (RunState.CONNECTING, RunState.RUNNING, RunState.STOPPING)
        opened = self.mgr.handle is not None
        self.ui.cbx_camera_list.setEnabled(not busy and not opened)
        self.ui.btn_camera_list_flush.setEnabled(not busy and not opened)
        self.ui.btn_camera_open.setEnabled(not busy and not opened)
        self.ui.btn_camera_close.setEnabled(not busy and opened)

    def _render_latest_qr(self):
        """Mã đọc gần nhất kèm giờ đọc và đã bao lâu — tránh nhầm kết quả cũ là mới."""
        at = self.stats.latest_at
        meta = "" if at is None else "{} · {}".format(self.stats.latest_clock, age_text(time.monotonic() - at))
        self.workspace.set_latest(self.stats.latest_text, meta)

    def _refresh_results(self):
        self._render_latest_qr()
        self.workspace.set_kpis(self.stats.read_count, self.stats.read_rate, self.stats.per_minute())
        if self.tray is not None:
            self.tray.set_read_count(self.stats.read_count)
        self.workspace.set_elapsed(self.stats.elapsed())
        self._render_fallback()

    def _render_fallback(self):
        """Dòng và nhãn chân của lượt đang đọc nền; gọi định kỳ để cập nhật số giây."""
        rows = list(self.stats.solving.values())
        for row in rows:
            self.workspace.upsert_row(row)
        self.workspace.set_fallback(rows)

    def on_fallback_status(self, statuses):
        self.stats.on_fallback(statuses)
        self._render_fallback()

    # ── Panel băng chuyền (tab trong cửa sổ Cấu hình) ─────────────────────────

    def _setup_qr_panel(self):
        self.qr_group = QGroupBox("Băng chuyền")
        layout = QVBoxLayout(self.qr_group)

        row = QHBoxLayout()
        row.addWidget(QLabel("N (frame / lần decode):"))
        self.spin_n = QSpinBox()
        self.spin_n.setRange(1, 1000)
        self.spin_n.setValue(5)
        self.spin_n.setToolTip("Cứ N frame camera thì gửi 1 frame đi đọc mã; bộ đọc đang bận thì chờ frame sau. "
                               "Có hiệu lực ngay, kể cả khi đang chạy.")
        row.addWidget(self.spin_n)
        self.cbx_decode = QCheckBox("Bật decode")
        self.cbx_decode.setChecked(True)
        self.cbx_quad = QCheckBox("Vẽ quad")
        self.cbx_quad.setChecked(True)
        self.cbx_gpu = QCheckBox("Dùng GPU")
        self.cbx_gpu.setToolTip("Chỉ tăng tốc bước phát hiện QR; bước đọc mã vẫn chạy CPU. "
                                "Lần đầu chuyển sang GPU có thể mất vài giây.")
        row.addWidget(self.cbx_decode)
        row.addWidget(self.cbx_quad)
        row.addWidget(self.cbx_gpu)
        row.addStretch(1)
        layout.addLayout(row)

        self.cbx_upload = QCheckBox("Gửi mã lên server")
        self.cbx_upload.setChecked(True)
        self.cbx_upload.setToolTip("Tắt thì mã vẫn được đọc và hiện trong danh sách nhưng không gửi đi; "
                                   "các mã đang chờ gửi bị bỏ. Có hiệu lực ngay, kể cả khi đang chạy.")
        layout.addWidget(self.cbx_upload)

        row = QHBoxLayout()
        row.addWidget(QLabel("Exposure (ms):"))
        self.spin_exposure = QDoubleSpinBox()
        self.spin_exposure.setRange(0.01, 2000.0)
        self.spin_exposure.setDecimals(2)
        self.spin_exposure.setSingleStep(0.5)
        self.spin_exposure.setValue(12.9)
        self.spin_exposure.setToolTip("Dài hơn thì ảnh sáng hơn, nhưng QR trên băng bị nhòe hơn.")
        row.addWidget(self.spin_exposure)
        row.addWidget(QLabel("Gain:"))
        self.spin_gain = QSpinBox()
        self.spin_gain.setRange(0, 1000)
        self.spin_gain.setValue(40)
        self.spin_gain.setToolTip("Cao hơn thì ảnh sáng hơn, nhưng nhiễu hơn. Giá trị vượt giới hạn camera sẽ bị kẹp.")
        row.addWidget(self.spin_gain)
        row.addStretch(1)
        layout.addLayout(row)

        self.cbx_conveyor_band, self.spin_band_y, self.spin_band_h = self._band_row(
            layout, "Chỉ đọc dải y:", "cao:", 640, 768, "Chỉ đọc các dòng chứa băng → FPS cao hơn.")
        self.cbx_band_x, self.spin_band_x, self.spin_band_w = self._band_row(
            layout, "Chỉ đọc dải x:", "rộng:", 0, 2448,
            "Băng chạy theo trục x: dải hẹp làm QR ở trong khung ít frame hơn.")

        row = QHBoxLayout()
        self.btn_conveyor_apply = QPushButton("Áp dụng")
        self.btn_conveyor_apply.setEnabled(False)
        self.btn_conveyor_apply.clicked.connect(self.on_conveyor_apply)
        row.addWidget(self.btn_conveyor_apply)
        row.addStretch(1)
        layout.addLayout(row)

        self.lbl_conveyor = QLabel("Exposure — | gain — | sáng — | cháy —")
        layout.addWidget(self.lbl_conveyor)

    def _band_row(self, layout, title: str, size_title: str, start: int, size: int, tooltip: str):
        row = QHBoxLayout()
        enabled = QCheckBox(title)
        enabled.setToolTip(tooltip)
        spin_start = QSpinBox()
        spin_start.setRange(0, 4096)
        spin_start.setSingleStep(16)
        spin_start.setValue(start)
        spin_size = QSpinBox()
        spin_size.setRange(16, 4096)
        spin_size.setSingleStep(16)
        spin_size.setValue(size)
        row.addWidget(enabled)
        row.addWidget(spin_start)
        row.addWidget(QLabel(size_title))
        row.addWidget(spin_size)
        row.addStretch(1)
        layout.addLayout(row)
        return enabled, spin_start, spin_size

    def run_settings(self) -> RunSettings:
        band_x = (self.spin_band_x.value(), self.spin_band_w.value()) if self.cbx_band_x.isChecked() else None
        band_y = ((self.spin_band_y.value(), self.spin_band_h.value())
                  if self.cbx_conveyor_band.isChecked() else None)
        return RunSettings(exposure_us=self.spin_exposure.value() * 1000.0,
                           analog_gain=self.spin_gain.value(), band_x=band_x, band_y=band_y)

    def on_conveyor_apply(self):
        if not self.mgr.handle:
            self.ui.status_bar.setText("Chưa mở camera.")
            return
        applied = self.mgr.apply_run_settings(self.run_settings())
        if applied is None:
            self.ui.status_bar.setText("Không áp dụng được (camera đang đóng).")
            return
        self.worker.set_exposure_ms(applied["exposure_us"] / 1000)
        self._apply_error = "" if applied["ok"] else "[MỘT SỐ THAM SỐ LỖI — xem log] "
        self.ui.status_bar.setText("{}Đã áp dụng: exposure {:.2f} ms, gain {}, khung {}".format(
            self._apply_error, applied["exposure_us"] / 1000, applied["analog_gain"], applied["resolution"]))

    def on_decode_toggled(self, checked: bool):
        if not checked:
            self._overlays = []
            if self._decoding:
                self.worker.request_flush(FLUSH_STOP)   # chốt các lượt đang mở, khỏi treo ở "…"
        self._show_decode_state()

    def on_gpu_toggled(self, checked: bool):
        self.pipeline.set_device(_device_for(checked))

    def on_upload_toggled(self, checked: bool):
        if self.uploader is not None:
            self.uploader.set_enabled(checked)

    def _show_decode_state(self):
        if self.cbx_decode.isChecked():
            self.workspace.set_processing_idle()
        else:
            self.workspace.set_processing_warning("Decode tắt")

    def _update_conveyor_label(self):
        text = "Exposure {:.2f} ms | gain {}".format(
            self.mgr.get_exposure_time() / 1000, self.mgr.get_analog_gain())
        if self._last_frame is not None:
            gray = cv2.cvtColor(self._last_frame[::4, ::4], cv2.COLOR_BGR2GRAY)
            text += " | sáng TB {:.0f} | cháy {:.2f}%".format(
                float(gray.mean()), float((gray >= 250).mean() * 100))
        self.lbl_conveyor.setText(text)

    # ── Đóng camera bất đồng bộ ───────────────────────────────────────────────

    def on_close_tick(self):
        thread = self._camera_close_thread
        connecting = self.controller.state is RunState.CONNECTING   # thread nền đang cấu hình camera
        self.btn_conveyor_apply.setEnabled(thread is None and not connecting and self.mgr.handle is not None)
        if thread is None or thread.is_alive():
            return
        self._camera_close_thread = None
        if self.mgr.handle is not None or self._camera_close_error:
            self._closing_app = False
            self.ui.btn_camera_close.setEnabled(True)
            message = "Chưa đóng được camera. " + self._camera_close_error
            self.ui.status_bar.setText(message)
            self.controller.on_close_failed(message)
            return
        self._finish_camera_close()
        if self._closing_app:
            self._allow_close = True
            self.close()

    # ── Window close ──────────────────────────────────────────────────────────

    def closeEvent(self, event):
        state = self.controller.state
        connecting = state in (RunState.CONNECTING, RunState.STOPPING)
        if not self._allow_close and (self.mgr.handle is not None or self._camera_close_thread or connecting):
            event.ignore()
            self._closing_app = True
            if state in (RunState.CONNECTING, RunState.RUNNING):
                self.on_stop()
            elif state is not RunState.STOPPING:
                self.on_camera_close()
            return
        self.display_timer.stop()
        self.fps_timer.stop()
        self.close_timer.stop()
        self._settings_timer.stop()
        self._save_settings()
        self.worker.stop()
        if self.uploader is not None:
            self.uploader.stop()
        self.settings_window.close()
        event.accept()
        if self.tray is not None:
            self.tray.hide()             # icon không kẹt lại ở khay
        app = QApplication.instance()
        if app is not None and not app.quitOnLastWindowClosed():
            app.quit()                   # entry tắt tự thoát để đóng cửa sổ Cấu hình lúc chạy nền không thoát app

    # ── Camera list / open / close ────────────────────────────────────────────

    def on_camera_list_flush(self):
        self.ui.btn_camera_list_flush.setEnabled(False)
        self.cameraList = self.mgr.list_cameras()
        if len(self.cameraList) == 0:
            self.ui.status_bar.setText("Không tìm thấy camera nào!")
        self._fill_camera_list()
        self.ui.btn_camera_list_flush.setEnabled(True)

    def _fill_camera_list(self):
        self.ui.cbx_camera_list.clear()
        for index, cam in enumerate(self.cameraList):
            self.ui.cbx_camera_list.addItem("{} {}".format(cam.GetFriendlyName(), cam.GetPortType()))
            if cam.GetSn() == self.settings.camera_serial:
                self.ui.cbx_camera_list.setCurrentIndex(index)

    def on_camera_open(self):
        index = self.ui.cbx_camera_list.currentIndex()
        if index < 0 or index >= len(self.cameraList):
            self.ui.status_bar.setText("Chưa chọn camera.")
            return
        if not self.mgr.open(index):
            QMessageBox.warning(self, "Lỗi", "Không mở được camera (CameraInit thất bại).")
            return
        self.ui.cbx_camera_list.setEnabled(False)
        self.ui.btn_camera_list_flush.setEnabled(False)
        self.ui.btn_camera_open.setEnabled(False)
        self.ui.btn_camera_close.setEnabled(True)
        self.on_conveyor_apply()         # xem trước đúng exposure/gain sẽ dùng khi chạy, không phải AE
        self._last_seq = -1
        self._last_decode_seq = 0
        self._remember_camera(self.cameraList[index].GetSn())
        self.controller.enter_tuning()

    def on_camera_close(self):
        if self._camera_close_thread is not None:
            return
        self.ui.btn_camera_open.setEnabled(False)
        self.ui.btn_camera_close.setEnabled(False)
        self._camera_close_error = ""

        def close_camera():
            try:
                self.mgr.close()
            except Exception as exc:
                self._camera_close_error = str(exc)

        self._camera_close_thread = threading.Thread(target=close_camera, daemon=True)
        self._camera_close_thread.start()
        self.on_close_tick()

    def _finish_camera_close(self):
        self.ui.cbx_camera_list.setEnabled(True)
        self.ui.btn_camera_list_flush.setEnabled(True)
        self.ui.btn_camera_open.setEnabled(True)
        self.ui.btn_camera_close.setEnabled(False)
        self._overlays = []
        self.ui.status_bar.setText("")
        self.controller.on_camera_closed()

    # ── Hiển thị frame + schedule decode ──────────────────────────────────────

    def on_display_tick(self):
        frame, seq = self.mgr.latest_frame()
        if frame is None:
            return

        # Đếm frame theo seq — mỗi N frame capture được → submit decode 1 lần
        if (self._decoding and self.cbx_decode.isChecked()
                and seq > self._last_seq
                and seq - self._last_decode_seq >= self.worker.decode_every(self.spin_n.value())):
            if self.worker.submit(frame, seq):
                self._last_decode_seq = seq

        if seq != self._last_seq:
            self._last_seq = seq
            self.display_fps += 1
            self._last_frame = frame
            self._last_frame_at = time.monotonic()

        if not self.isVisible():
            return                       # chạy nền: vẫn gửi decode ở trên, bỏ phần vẽ cho đỡ CPU

        label_w, label_h = self.ui.label_image.width(), self.ui.label_image.height()
        vis = frame
        if self.cbx_quad.isChecked() and self._overlays:
            # nét dày theo tỷ lệ thu nhỏ để còn thấy sau khi resize về khung hiển thị
            thickness = max(2, 2 * frame.shape[1] // max(1, label_w))
            vis = draw_overlays(frame, self._overlays, seq, thickness=thickness)

        self.ui.label_image.setPixmap(QPixmap.fromImage(frame_to_qimage(vis, label_w, label_h)))

    def on_fps_show(self):
        self._refresh_results()    # cập nhật "… giây trước", tốc độ, thời gian chạy
        state = self.controller.state
        if state is RunState.RUNNING:
            lost = time.monotonic() - self._last_frame_at > SIGNAL_LOST_S
            self.workspace.set_signal_lost(lost)
            if self.tray is not None:
                self.tray.set_signal_lost(lost)
        # Đang kết nối/đóng: thread nền đang dùng SDK, GUI không gọi getter
        if self.mgr.handle and state is not RunState.CONNECTING and self._camera_close_thread is None:
            capture, _ = self.mgr.frame_statistic()
            self.ui.status_bar.setText(
                "{}Capture fps: {}   Display fps: {}   Decode: {} lần".format(
                    self._apply_error, capture - self.read_fps, self.display_fps, self.decode_count))
            if state in (RunState.RUNNING, RunState.TUNING):
                self.workspace.set_camera_fps(max(0, capture - self.read_fps))
            self.read_fps = capture
            self.display_fps = 0
            self._update_conveyor_label()

    # ── Decode callbacks ──────────────────────────────────────────────────────

    def on_decode_done(self, results, overlays):
        self.decode_count += 1
        # kết quả về muộn sau khi đã Dừng / tắt decode
        self._overlays = overlays if self._decoding and self.cbx_decode.isChecked() else []

    def on_reads_done(self, tracks):
        if self.uploader is not None:
            for track in tracks:
                self.uploader.submit(track.text)
        for row in self.stats.on_reads(tracks):
            self.workspace.upsert_row(row)
        self.workspace.flash_latest()
        self._render_latest_qr()

    def on_decode_stats(self, stats):
        # đọc lại mỗi lần: detector tự chuyển CPU khi CUDA lỗi lúc chạy
        device = "GPU" if str(self.pipeline.device).startswith("cuda") else "CPU"
        if self.cbx_decode.isChecked():      # kết quả về muộn không được đè nhãn "Decode tắt"
            self.workspace.set_processing(device, stats["detect_ms"] + stats["cascade_ms"])

    def on_passes_done(self, tracks):
        """Đếm lượt QR đi qua (một QR chạy qua khung = một lượt) — read rate thật trên băng."""
        for row in self.stats.on_passes(tracks):
            self.workspace.upsert_row(row)
        self._refresh_results()

    def on_upload_status(self, status):
        """Chỉ báo khi có chuyện đáng chú ý: lỗi gửi (thành công là việc bình thường)."""
        if status.last_ok is False:
            self.ui.status_bar.setText("Gửi mã {} lên server lỗi ({} mã chờ)".format(
                status.last_text, status.pending))

    def on_decode_failed(self, msg):
        self.ui.status_bar.setText("Decode lỗi: {}".format(msg[:100]))
        self.workspace.set_processing_warning("Decode lỗi")
