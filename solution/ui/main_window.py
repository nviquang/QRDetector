"""MainWindow của solution — port từ Demo/python/Advanced/MainWindow.py.

Khác demo gốc:
- Logic SDK chuyển vào CameraManager (camera/camera_manager.py), UI chỉ bind signal.
- Frame lấy từ mgr.latest_frame() (BGR np.ndarray) thay vì CaptureThread/Qt.
- Thêm panel Kết quả QR: decode mỗi N frame trên thread riêng qua PassReader (theo lượt, GPU nếu có),
  busy → bỏ qua frame (không xếp hàng); vẽ quad + hiển thị text QR.
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
from camera.conveyor import SPEEDS_MM_S, ConveyorSettings, blur_px
from camera.recording import RecordingOptions
from qr import ImprovePipeline, PassReader

from PyQt5.QtCore import QObject, QSignalBlocker, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog,
                             QGroupBox, QHBoxLayout, QLabel, QLineEdit,
                             QListWidget, QMainWindow, QMessageBox, QPushButton,
                             QSpinBox, QVBoxLayout)

from . import main_window_ui as MainWindowUI


def frame_to_qimage(frame_bgr: np.ndarray, max_w: int, max_h: int) -> QImage:
    """Thu nhỏ bằng OpenCV (INTER_AREA) về khung hiển thị TRƯỚC khi đổi màu — GUI thread không
    phải xử lý ảnh 5MP ở 30 Hz (tranh CPU với cascade). Không phóng to; khung 0 → giữ nguyên."""
    h, w = frame_bgr.shape[:2]
    if max_w > 0 and max_h > 0:
        scale = min(max_w / w, max_h / h)
        if scale < 1.0:
            frame_bgr = cv2.resize(frame_bgr, (max(1, int(w * scale)), max(1, int(h * scale))),
                                   interpolation=cv2.INTER_AREA)
    rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    h, w = rgb.shape[:2]
    return QImage(rgb.data, w, h, rgb.strides[0], QImage.Format_RGB888).copy()


QUAD_MAX_AGE_SEQ = 100   # quad cũ hơn ~2 s (50 fps) thì thôi vẽ — tránh khung "ma" khi QR đã đi qua


def draw_overlays(frame_bgr: np.ndarray, overlays, seq: int,
                  max_age: int = QUAD_MAX_AGE_SEQ, thickness: int = 2) -> np.ndarray:
    """Vẽ quad lên BẢN SAO frame (trả nguyên frame nếu không có gì để vẽ).

    Kết quả decode đến từ frame cũ hơn frame đang hiển thị (decode mất hàng trăm ms trong khi băng
    chạy ~700 px/s) → dịch quad theo vận tốc lượt tới ``seq``; bỏ quad của frame khác kích thước
    (đổi ROI) hoặc quá cũ. Xanh = đã có nội dung, đỏ = chưa đọc được.
    """
    shape = frame_bgr.shape[:2]
    quads = [(o.at(seq, shape, max_age), o.ok) for o in overlays]
    quads = [(q, ok) for q, ok in quads if q is not None]
    if not quads:
        return frame_bgr
    vis = frame_bgr.copy()
    for quad, ok in quads:
        pts = np.round(quad).astype(np.int32).reshape((-1, 1, 2))
        cv2.polylines(vis, [pts], isClosed=True, color=(0, 255, 0) if ok else (0, 0, 255),
                      thickness=thickness)
    return vis


# ── Decode worker ─────────────────────────────────────────────────────────────

class DecodeWorker(QObject):
    """Thread riêng gọi PassReader.process(). submit() fail khi đang bận."""

    done = pyqtSignal(list, list)   # (results, overlays)
    stats = pyqtSignal(dict)        # detect_ms, cascade_ms, skipped
    passes = pyqtSignal(list)       # list[Track] — lượt QR vừa kết thúc
    failed = pyqtSignal(str)

    def __init__(self, pipeline: ImprovePipeline, parent=None):
        super().__init__(parent)
        self._reader = PassReader(pipeline)
        self._lock = threading.Lock()
        self._pending: tuple[np.ndarray, int] | None = None
        self._busy = False
        self._stop = False
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def submit(self, frame: np.ndarray, seq: int) -> bool:
        with self._lock:
            if self._busy or self._pending is not None:
                return False   # đang bận → bỏ qua frame này
            self._pending = (frame, seq)
            return True

    @property
    def busy(self) -> bool:
        with self._lock:
            return self._busy or self._pending is not None

    def stop(self):
        self._stop = True
        self._thread.join(timeout=5)
        if self._thread.is_alive():
            return              # còn đang warm-up/decode dở → không đụng tracker từ thread khác
        finished = self._reader.flush()
        if finished:
            self.passes.emit(finished)

    def _loop(self):
        try:
            self._reader.warmup()   # lần detect đầu trên GPU mất vài giây — làm ở đây, không chặn UI
        except Exception as e:
            self.failed.emit("Warm-up lỗi: {}".format(e))
        while not self._stop:
            with self._lock:
                job, self._pending = self._pending, None
                self._busy = job is not None
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
        if r.finished:
            self.passes.emit(r.finished)


# ── Main window ───────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()

        # Thành viên
        self.mgr = CameraManager()
        self.pipeline = ImprovePipeline()
        self.worker = DecodeWorker(self.pipeline)
        self.worker.done.connect(self.on_decode_done)
        self.worker.failed.connect(self.on_decode_failed)
        self.worker.stats.connect(self.on_decode_stats)
        self.worker.passes.connect(self.on_passes_done)

        self.cameraList = []
        self.ui_initing = 0
        self.read_fps = 0
        self.display_fps = 0
        self.decode_count = 0
        self._device_label = "GPU" if str(self.pipeline.device).startswith("cuda") else "CPU"
        self._passes_total = 0
        self._passes_read = 0
        self._passes_conflict = 0
        self._last_seq = -1
        self._last_decode_seq = 0
        self._overlays = []
        self._last_frame: np.ndarray | None = None
        self._latest_qr = ""
        self._latest_qr_hits = 0       # số lần đọc liên tiếp (về 0 khi decode trượt) — chọn màu quad
        self._latest_qr_count = 0      # tổng số lần đọc mã hiện tại — hiển thị (xN)
        self._latest_qr_at: float | None = None
        self._latest_qr_clock = ""

        # Load UI
        self.ui = MainWindowUI.Ui_MainWindow()
        self.ui.setupUi(self)
        self.ui.frame_area.setEnabled(False)
        self._setup_qr_panel()
        self._closing_app = False
        self._allow_close = False
        self._camera_close_thread = None
        self._camera_close_error = ""
        self._camera_close_at = 0.0
        self._record_controls_saved = None
        self._setup_recording_panel()

        # SDK init + khung timer
        self.mgr.init_sdk()
        self.display_timer = QTimer()
        self.display_timer.timeout.connect(self.on_display_tick)
        self.display_timer.start(33)   # ~30fps hiển thị
        self.fps_timer = QTimer()
        self.fps_timer.timeout.connect(self.on_fps_show)
        self.fps_timer.start(1000)

        # Slot: Camera
        self.ui.btn_camera_list_flush.clicked.connect(self.on_camera_list_flush)
        self.ui.btn_camera_open.clicked.connect(self.on_camera_open)
        self.ui.btn_camera_close.clicked.connect(self.on_camera_close)
        #   Resolution
        self.ui.cbx_ROI.currentIndexChanged.connect(self.on_ROI_changed)
        #   Trigger
        self.ui.btngrp_trigger_mode.buttonClicked.connect(self.on_trigger_mode)
        self.ui.btn_trigger_once.clicked.connect(lambda: self.mgr.soft_trigger())
        self.ui.btngrp_flashlight_mode.buttonClicked.connect(self.on_flashlight_mode)
        self.ui.btngrp_flashlight_polarity_mode.buttonClicked.connect(self.on_flashlight_polarity_mode)
        #   Exposure
        self.ui.btngrp_exposure_mode.buttonClicked.connect(self.on_exposure_mode)
        self.ui.ae_auto_hSlider.valueChanged.connect(self.ui.ae_auto_spinBox.setValue)
        self.ui.ae_auto_spinBox.valueChanged.connect(self.ui.ae_auto_hSlider.setValue)
        self.ui.ae_auto_hSlider.valueChanged.connect(lambda v: self.mgr.set_ae_target(v))
        self.ui.ae_flicker.clicked.connect(self.on_ae_flicker)
        self.ui.btngrp_ae_flicker_HZ.buttonClicked.connect(self.on_ae_flicker_hz)
        self.ui.ae_manual_gain_hSlider.valueChanged.connect(self.ui.ae_manual_gain_spinbox.setValue)
        self.ui.ae_manual_gain_spinbox.valueChanged.connect(self.ui.ae_manual_gain_hSlider.setValue)
        self.ui.ae_manual_gain_hSlider.valueChanged.connect(lambda v: self.mgr.set_analog_gain(v))
        self.ui.ae_manual_time_hSlider.valueChanged.connect(self.on_ae_manual_time_hslider)
        self.ui.ae_manual_time_ledit.returnPressed.connect(self.on_ae_manual_time_ledit)
        #   ISP
        self.ui.checkBox_isp_h.clicked.connect(lambda c: self.mgr.set_mirror(0, c))
        self.ui.checkBox_isp_v.clicked.connect(lambda c: self.mgr.set_mirror(1, c))
        self.ui.isp_Sharpness_hSlider.valueChanged.connect(self.ui.isp_Sharpness_spinbox.setValue)
        self.ui.isp_Sharpness_spinbox.valueChanged.connect(self.ui.isp_Sharpness_hSlider.setValue)
        self.ui.isp_Sharpness_hSlider.valueChanged.connect(lambda v: self.mgr.set_sharpness(v))
        #   Parameter group
        self.ui.btn_param_save.clicked.connect(self.on_btn_param_save)
        self.ui.btn_param_load.clicked.connect(self.on_btn_param_load)
        self.ui.btn_param_default.clicked.connect(self.on_btn_param_default)
        #   LUT
        self.ui.lut_gamma_hSlider.valueChanged.connect(self.ui.lut_gamma_spinbox.setValue)
        self.ui.lut_gamma_spinbox.valueChanged.connect(self.ui.lut_gamma_hSlider.setValue)
        self.ui.lut_gamma_hSlider.valueChanged.connect(lambda v: self.mgr.set_gamma(v / 100.0))
        self.ui.lut_contrast_hSlider.valueChanged.connect(self.ui.lut_contrast_spinbox.setValue)
        self.ui.lut_contrast_spinbox.valueChanged.connect(self.ui.lut_contrast_hSlider.setValue)
        self.ui.lut_contrast_hSlider.valueChanged.connect(lambda v: self.mgr.set_contrast(v))
        #   Color
        self.ui.btn_white_blance.clicked.connect(self.on_white_blance)
        self.ui.gain_red_hSlider.valueChanged.connect(self.ui.gain_red_spinbox.setValue)
        self.ui.gain_red_spinbox.valueChanged.connect(self.ui.gain_red_hSlider.setValue)
        self.ui.gain_red_hSlider.valueChanged.connect(lambda v: self.on_gain_set("red", v))
        self.ui.gain_green_hSlider.valueChanged.connect(self.ui.gain_green_spinbox.setValue)
        self.ui.gain_green_spinbox.valueChanged.connect(self.ui.gain_green_hSlider.setValue)
        self.ui.gain_green_hSlider.valueChanged.connect(lambda v: self.on_gain_set("green", v))
        self.ui.gain_blue_hSlider.valueChanged.connect(self.ui.gain_blue_spinbox.setValue)
        self.ui.gain_blue_spinbox.valueChanged.connect(self.ui.gain_blue_hSlider.setValue)
        self.ui.gain_blue_hSlider.valueChanged.connect(lambda v: self.on_gain_set("blue", v))
        self.ui.isp_saturation_hSlider.valueChanged.connect(self.ui.isp_saturation_spinbox.setValue)
        self.ui.isp_saturation_spinbox.valueChanged.connect(self.ui.isp_saturation_hSlider.setValue)
        self.ui.isp_saturation_hSlider.valueChanged.connect(lambda v: self.mgr.set_saturation(v))
        #   Snap
        self.ui.btn_snap.clicked.connect(self.on_snap)
        #   Special effects
        self.ui.checkBox_mono_mode.clicked.connect(lambda c: self.mgr.set_monochrome(c))
        self.ui.checkBox_film_mode.clicked.connect(lambda c: self.mgr.set_inverse(c))
        self.ui.btn_modify_name2.clicked.connect(
            lambda: self.mgr.set_friendly_name(self.ui.led_device_name2.text()))

        # Load camera list
        QTimer.singleShot(100, self.on_camera_list_flush)

    # ── QR panel (thêm vào UI form cố định của Advanced) ──────────────────────

    def _setup_qr_panel(self):
        self.setMinimumSize(1440, 930)
        self.setMaximumSize(1440, 930)
        self.resize(1440, 930)

        self.qr_group = QGroupBox("Kết quả QR", self.ui.centralWidget)
        self.qr_group.setGeometry(830, 655, 591, 270)

        layout = QVBoxLayout(self.qr_group)

        row = QVBoxLayout()
        row1 = QHBoxLayout()
        lbl_n = QLabel("N (frame / lần decode):", self.qr_group)
        self.spin_n = QSpinBox(self.qr_group)
        self.spin_n.setRange(1, 1000)
        self.spin_n.setValue(5)
        self.cbx_decode = QCheckBox("Bật decode", self.qr_group)
        self.cbx_quad = QCheckBox("Vẽ quad", self.qr_group)
        self.cbx_quad.setChecked(True)
        row1.addWidget(lbl_n)
        row1.addWidget(self.spin_n)
        row1.addWidget(self.cbx_decode)
        row1.addWidget(self.cbx_quad)
        row1.addStretch(1)
        row.addLayout(row1)

        row2 = QHBoxLayout()
        self.lbl_latest = QLabel("QR mới nhất: —", self.qr_group)
        self.lbl_latest.setStyleSheet("font-weight: bold;")
        row2.addWidget(self.lbl_latest, 1)
        row.addLayout(row2)

        row3 = QHBoxLayout()
        self.lbl_stat = QLabel("Decode: 0 lần", self.qr_group)
        self.lbl_passes = QLabel("Lượt QR: 0/0 đọc được · mâu thuẫn 0", self.qr_group)
        row3.addWidget(self.lbl_stat)
        row3.addStretch(1)
        row3.addWidget(self.lbl_passes)
        row.addLayout(row3)
        layout.addLayout(row)
        self._setup_conveyor_rows(layout)

        self.lst_history = QListWidget(self.qr_group)
        layout.addWidget(self.lst_history)

    def _setup_conveyor_rows(self, layout):
        """Chế độ băng chuyền: tắt AE, exposure theo tốc độ băng, FPS cao, tùy chọn chỉ đọc dải băng."""
        row = QHBoxLayout()
        row.addWidget(QLabel("Băng:"))
        self.cbx_conveyor_speed = QComboBox()
        for speed in SPEEDS_MM_S:
            self.cbx_conveyor_speed.addItem("{:.0f} cm/s".format(speed / 10), speed)
        self.cbx_conveyor_speed.setCurrentIndex(len(SPEEDS_MM_S) - 1)
        row.addWidget(self.cbx_conveyor_speed)
        row.addWidget(QLabel("mm/px:"))
        self.spin_mm_per_px = QDoubleSpinBox()
        self.spin_mm_per_px.setRange(0.05, 3.0)
        self.spin_mm_per_px.setDecimals(3)
        self.spin_mm_per_px.setSingleStep(0.01)
        self.spin_mm_per_px.setValue(0.43)
        self.spin_mm_per_px.setToolTip("Đo bằng thước đặt trên băng: chiều dài (mm) ÷ số pixel.")
        row.addWidget(self.spin_mm_per_px)
        row.addWidget(QLabel("Mờ ≤ px:"))
        self.spin_max_blur = QDoubleSpinBox()
        self.spin_max_blur.setRange(0.25, 5.0)
        self.spin_max_blur.setSingleStep(0.25)
        self.spin_max_blur.setValue(1.0)
        row.addWidget(self.spin_max_blur)
        row.addStretch(1)
        layout.addLayout(row)

        row = QHBoxLayout()
        self.cbx_conveyor_band = QCheckBox("Chỉ đọc dải y:")
        self.cbx_conveyor_band.setToolTip("ROI sensor: chỉ đọc các dòng chứa băng → FPS cao hơn.")
        self.spin_band_y = QSpinBox()
        self.spin_band_y.setRange(0, 4096)
        self.spin_band_y.setSingleStep(16)
        self.spin_band_y.setValue(640)
        self.spin_band_h = QSpinBox()
        self.spin_band_h.setRange(16, 4096)
        self.spin_band_h.setSingleStep(16)
        self.spin_band_h.setValue(768)
        self.btn_conveyor_apply = QPushButton("Áp dụng chế độ băng chuyền")
        self.btn_conveyor_apply.clicked.connect(self.on_conveyor_apply)
        row.addWidget(self.cbx_conveyor_band)
        row.addWidget(self.spin_band_y)
        row.addWidget(QLabel("cao:"))
        row.addWidget(self.spin_band_h)
        row.addWidget(self.btn_conveyor_apply)
        row.addStretch(1)
        layout.addLayout(row)

        self.lbl_conveyor = QLabel("Exposure — | mờ ước tính — | sáng — | cháy —")
        layout.addWidget(self.lbl_conveyor)

    def conveyor_settings(self) -> ConveyorSettings:
        band = ((self.spin_band_y.value(), self.spin_band_h.value())
                if self.cbx_conveyor_band.isChecked() else None)
        return ConveyorSettings(speed_mm_s=float(self.cbx_conveyor_speed.currentData()),
                                mm_per_px=self.spin_mm_per_px.value(),
                                max_blur_px=self.spin_max_blur.value(), band=band)

    def on_conveyor_apply(self):
        if not self.mgr.handle:
            self.ui.status_bar.setText("Chưa mở camera.")
            return
        applied = self.mgr.apply_conveyor_mode(self.conveyor_settings())
        if applied is None:
            self.ui.status_bar.setText("Không áp dụng được (camera đang quay hoặc đang đóng).")
            return
        self.ui_init_param()
        names = self.mgr.frame_speed_names()
        speed = applied["frame_speed"]
        speed_text = names[speed] if speed is not None and 0 <= speed < len(names) else speed
        self.ui.status_bar.setText(
            "{}Băng chuyền: AE tắt, exposure {:.2f} ms (mục tiêu {:.2f}), frame speed {}, khung {}".format(
                "" if applied["ok"] else "[MỘT SỐ THAM SỐ LỖI — xem log] ",
                applied["exposure_us"] / 1000, applied["exposure_target_us"] / 1000,
                speed_text, applied["resolution"]))

    def _update_conveyor_label(self, sdk_busy: bool = False):
        # Khi đang quay/đóng không gọi getter SDK từ GUI thread — dùng giá trị đọc lần trước.
        if not sdk_busy:
            self._exposure_cache = (self.mgr.get_exposure_time(), self.mgr.get_ae_state())
            if self._exposure_cache[1]:
                self._sync_ae_widgets(self._exposure_cache[0])
        exposure_us, auto = getattr(self, "_exposure_cache", (0.0, None))
        speed = float(self.cbx_conveyor_speed.currentData())
        text = "Exposure {:.2f} ms ({}) | mờ ước tính {:.1f} px @ {:.0f} cm/s".format(
            exposure_us / 1000, "AE" if auto else "cố định",
            blur_px(speed, self.spin_mm_per_px.value(), exposure_us), speed / 10)
        if self._last_frame is not None:
            gray = cv2.cvtColor(self._last_frame[::4, ::4], cv2.COLOR_BGR2GRAY)
            text += " | sáng TB {:.0f} | cháy {:.2f}%".format(
                float(gray.mean()), float((gray >= 250).mean() * 100))
        self.lbl_conveyor.setText(text)

    def _sync_ae_widgets(self, exposure_us: float):
        """Khi AE bật: hiện exposure/gain camera đang tự chọn lên ô Manual (chỉ đọc, không ghi lại SDK)."""
        widgets = (self.ui.ae_manual_time_hSlider, self.ui.ae_manual_time_ledit,
                   self.ui.ae_manual_gain_hSlider, self.ui.ae_manual_gain_spinbox)
        blockers = [QSignalBlocker(widget) for widget in widgets]
        try:
            line_time = self.mgr.f_exp_line_time or 1.0
            self.ui.ae_manual_time_hSlider.setValue(int(exposure_us / line_time))
            self.ui.ae_manual_time_ledit.setText(str(round(exposure_us / 1000, 3)))
            gain = self.mgr.get_analog_gain()
            self.ui.ae_manual_gain_hSlider.setValue(gain)
            self.ui.ae_manual_gain_spinbox.setValue(gain)
        finally:
            del blockers

    # ── Ghi video: UI chỉ gửi yêu cầu, capture thread sở hữu recorder ──────────

    def _setup_recording_panel(self):
        self.record_group = QGroupBox("Quay dữ liệu — AVI không nén", self.ui.centralWidget)
        self.record_group.setGeometry(10, 685, 800, 240)
        layout = QVBoxLayout(self.record_group)
        row = QHBoxLayout()
        self.edit_record_directory = QLineEdit(str(
            Path(__file__).resolve().parents[1] / "recordings"))
        self.btn_record_browse = QPushButton("Thư mục lưu…")
        self.btn_record_browse.clicked.connect(self.on_record_browse)
        row.addWidget(self.edit_record_directory, 1)
        row.addWidget(self.btn_record_browse)
        layout.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(QLabel("FPS video:"))
        self.spin_record_fps = QSpinBox()
        self.spin_record_fps.setRange(1, 1000)
        self.spin_record_fps.setValue(60)
        self.spin_record_fps.setToolTip(
            "Không phải FPS camera. Chọn ít nhất 1,25 × FPS acquisition/trigger tối đa.")
        row.addWidget(self.spin_record_fps)
        self.cbx_record_color_diagnostics = QCheckBox("Lưu mẫu đối chiếu màu")
        self.cbx_record_color_diagnostics.setToolTip(
            "Tối đa 3 mẫu PNG/bytes trước và sau SDK ghi, trong thư mục color_diagnostics cạnh video. "
            "Không tự bù màu; có thêm chi phí copy và lưu ảnh khi bật.")
        self.btn_record_start = QPushButton("Bắt đầu quay")
        self.btn_record_stop = QPushButton("Dừng quay / Thử đóng lại")
        self.btn_record_start.clicked.connect(self.on_record_start)
        self.btn_record_stop.clicked.connect(self.mgr.stop_recording)
        self.btn_record_start.setEnabled(False)
        self.btn_record_stop.setEnabled(False)
        row.addWidget(self.btn_record_start)
        row.addWidget(self.btn_record_stop)
        self.btn_record_trigger = QPushButton("Soft trigger")
        self.btn_record_trigger.clicked.connect(self.mgr.soft_trigger)
        self.btn_record_trigger.setEnabled(False)
        row.addWidget(self.btn_record_trigger)
        row.addStretch()
        layout.addLayout(row)
        note = QLabel("Giữ độ phân giải nguồn, không overlay QR. Mỗi phiên ghi một file AVI, không tự chia đoạn.\n"
                      "FPS video phải cao hơn tốc độ camera/trigger tối đa; AVI >4 GiB và đủ frame cần kiểm chứng thực tế.")
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addWidget(self.cbx_record_color_diagnostics)
        self.lbl_record_status = QLabel("IDLE")
        self.lbl_record_status.setWordWrap(True)
        self.lbl_record_path = QLabel("—")
        self.lbl_record_path.setWordWrap(True)
        self.lbl_record_path.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.lbl_record_status)
        layout.addWidget(self.lbl_record_path)
        self.recording_timer = QTimer(self)
        self.recording_timer.timeout.connect(self.on_recording_tick)
        self.recording_timer.start(100)

    def on_record_browse(self):
        directory = QFileDialog.getExistingDirectory(
            self, "Thư mục lưu video", self.edit_record_directory.text())
        if directory:
            self.edit_record_directory.setText(directory)

    def on_record_start(self):
        try:
            directory = Path(self.edit_record_directory.text()).expanduser().resolve()
        except (OSError, RuntimeError, ValueError) as exc:
            self.lbl_record_status.setText("Thư mục lưu không hợp lệ: " + str(exc))
            return
        options = RecordingOptions(
            directory, fps=self.spin_record_fps.value(),
            color_diagnostics=self.cbx_record_color_diagnostics.isChecked())
        if not self.mgr.start_recording(options):
            self.lbl_record_status.setText(
                "Không nhận yêu cầu quay. Kiểm tra camera, frame và FPS video > FPS capture.")
        else:
            self.on_recording_tick()

    def on_recording_tick(self):
        status = self.mgr.recording_status()
        closing = self._camera_close_thread is not None
        locked = status.busy or closing
        if locked and self._record_controls_saved is None:
            self._record_controls_saved = self.ui.frame_area.isEnabled()
            self._record_soft_trigger_enabled = self.ui.btn_trigger_once.isEnabled()
            self.ui.frame_area.setEnabled(False)
        elif not locked and self._record_controls_saved is not None:
            self.ui.frame_area.setEnabled(self._record_controls_saved and self.mgr.handle is not None)
            self._record_controls_saved = None
        frame, _ = self.mgr.latest_frame()
        self.btn_record_start.setEnabled(
            not locked and self.mgr.running and frame is not None and not self._closing_app)
        self.btn_record_stop.setEnabled(status.busy and not closing)
        self.btn_record_trigger.setEnabled(
            status.state in ("STARTING", "RECORDING") and not closing
            and getattr(self, "_record_soft_trigger_enabled", False))
        self.edit_record_directory.setEnabled(not locked)
        self.btn_record_browse.setEnabled(not locked)
        self.spin_record_fps.setEnabled(not locked)
        self.cbx_record_color_diagnostics.setEnabled(not locked)
        self.btn_conveyor_apply.setEnabled(not locked and self.mgr.handle is not None)
        lost ="không xác định" if status.lost_delta is None else str(status.lost_delta)
        text = (f"{status.state} | {status.elapsed:.1f}s | "
                f"gửi ghi: {status.pushed_frames} frame | camera lost: {lost}")
        if status.error:
            text += "\nLỗi: " + status.error
        elif status.warning:
            text += "\n" + status.warning
        if status.color_diagnostic_status:
            text += "\n" + status.color_diagnostic_status
        self.lbl_record_status.setText(text)
        self.lbl_record_path.setText(status.current_path or "—")
        if closing:
            thread = self._camera_close_thread
            if thread.is_alive():
                if time.monotonic() - self._camera_close_at > 5:
                    self.lbl_record_status.setText(text + "\nĐang chờ SDK đóng; chưa xác nhận lưu file.")
                return
            self._camera_close_thread = None
            status = self.mgr.recording_status()
            if self.mgr.handle is not None or status.native_open or self._camera_close_error:
                self._closing_app = False
                self.ui.btn_camera_close.setEnabled(True)
                self.ui.status_bar.setText("Chưa đóng được camera/recorder. " + self._camera_close_error)
                return
            self._finish_camera_close()
            if self._closing_app:
                self._allow_close = True
                self.close()

    # ── Window close ──────────────────────────────────────────────────────────

    def closeEvent(self, event):
        if not self._allow_close and (self.mgr.handle is not None or self._camera_close_thread):
            event.ignore()
            self._closing_app = True
            self.on_camera_close()
            return
        self.display_timer.stop()
        self.fps_timer.stop()
        self.recording_timer.stop()
        self.worker.stop()
        event.accept()

    # ── Camera list / open / close ────────────────────────────────────────────

    def on_camera_list_flush(self):
        self.ui.btn_camera_list_flush.setEnabled(False)
        self.ui.cbx_camera_list.clear()
        self.cameraList = self.mgr.list_cameras()
        if len(self.cameraList) == 0:
            self.ui.status_bar.setText("Không tìm thấy camera nào!")
        for cam in self.cameraList:
            self.ui.cbx_camera_list.addItem("{} {}".format(cam.GetFriendlyName(), cam.GetPortType()))
        self.ui.btn_camera_list_flush.setEnabled(True)

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
        self.ui.frame_area.setEnabled(True)
        self.ui_init_param()
        self._last_seq = -1
        self._last_decode_seq = 0
        self.ui.status_bar.setText("Camera đã mở.")

    def on_camera_close(self):
        if self._camera_close_thread is not None:
            return
        self.ui.btn_camera_open.setEnabled(False)
        self.ui.btn_camera_close.setEnabled(False)
        self._camera_close_error = ""
        self._camera_close_at = time.monotonic()

        def close_camera():
            try:
                self.mgr.close()
            except Exception as exc:
                self._camera_close_error = str(exc)

        self._camera_close_thread = threading.Thread(target=close_camera, daemon=True)
        self._camera_close_thread.start()
        self.on_recording_tick()

    def _finish_camera_close(self):
        self.ui.cbx_camera_list.setEnabled(True)
        self.ui.btn_camera_list_flush.setEnabled(True)
        self.ui.btn_camera_open.setEnabled(True)
        self.ui.btn_camera_close.setEnabled(False)
        self.ui.frame_area.setEnabled(False)
        self._overlays = []
        self.ui.status_bar.setText("")

    # ── Init UI param từ camera ───────────────────────────────────────────────

    def ui_init_param(self):
        """Read camera state into widgets without writing values back to the SDK."""
        cap = self.mgr.capability
        if not cap:
            return
        widgets = (
            self.ui.cbx_ROI,
            self.ui.ae_auto_hSlider, self.ui.ae_auto_spinBox,
            self.ui.ae_manual_gain_hSlider, self.ui.ae_manual_gain_spinbox,
            self.ui.ae_manual_time_hSlider, self.ui.ae_manual_time_ledit,
            self.ui.isp_Sharpness_hSlider, self.ui.isp_Sharpness_spinbox,
            self.ui.lut_gamma_hSlider, self.ui.lut_gamma_spinbox,
            self.ui.lut_contrast_hSlider, self.ui.lut_contrast_spinbox,
            self.ui.gain_red_hSlider, self.ui.gain_red_spinbox,
            self.ui.gain_green_hSlider, self.ui.gain_green_spinbox,
            self.ui.gain_blue_hSlider, self.ui.gain_blue_spinbox,
            self.ui.isp_saturation_hSlider, self.ui.isp_saturation_spinbox,
        )
        blockers = [QSignalBlocker(widget) for widget in widgets]
        self.ui_initing = 1
        try:
            self.ui.cbx_ROI.clear()
            for i in range(cap.iImageSizeDesc):
                self.ui.cbx_ROI.addItem(cap.pImageSizeDesc[i].GetDescription())

            # These buttons describe the defaults applied by CameraManager.open().
            self.ui.radio_always.setChecked(True)
            self.ui.radio_trigger_software.setChecked(False)
            self.ui.radio_trigger_hardware.setChecked(False)
            self.ui.btn_trigger_once.setEnabled(False)
            self.ui.frame_flashlight.setEnabled(False)
            self.ui.flashlight_auto.setChecked(True)
            self.ui.flashlight_l.setChecked(True)
            auto_exposure = self.mgr.get_ae_state() is True
            self.ui.exposure_mode_auto.setChecked(auto_exposure)
            self.ui.exposure_mode_manual.setChecked(not auto_exposure)
            self.ui.frame_exposure_auto.setEnabled(auto_exposure)
            self.ui.frame_exposure_manual.setEnabled(not auto_exposure)

            target = self.mgr.get_ae_target()
            target_supported = target is not None and cap.sExposeDesc.uiTargetMax > 0
            for widget in (self.ui.ae_auto_hSlider, self.ui.ae_auto_spinBox):
                widget.setEnabled(target_supported)
                if target_supported:
                    widget.setMinimum(cap.sExposeDesc.uiTargetMin)
                    widget.setMaximum(cap.sExposeDesc.uiTargetMax)
                    widget.setValue(target)
            self.ui.ae_flicker.setChecked(False)
            self.ui.radio_50HZ.setEnabled(False)
            self.ui.radio_60HZ.setEnabled(False)

            gain = self.mgr.get_analog_gain()
            for widget in (self.ui.ae_manual_gain_hSlider,
                           self.ui.ae_manual_gain_spinbox):
                widget.setMinimum(cap.sExposeDesc.uiAnalogGainMin)
                widget.setMaximum(cap.sExposeDesc.uiAnalogGainMax)
                widget.setValue(gain)

            ae_curr_time = self.mgr.get_exposure_time()
            line_time = self.mgr.f_exp_line_time or 1.0
            self.ui.ae_manual_time_hSlider.setMinimum(cap.sExposeDesc.uiExposeTimeMin)
            self.ui.ae_manual_time_hSlider.setMaximum(cap.sExposeDesc.uiExposeTimeMax)
            self.ui.ae_manual_time_hSlider.setValue(int(ae_curr_time / line_time))
            self.ui.ae_manual_time_ledit.setText(str(ae_curr_time / 1000))

            self.ui.checkBox_isp_h.setChecked(False)
            self.ui.checkBox_isp_v.setChecked(False)
            sharpness = self.mgr.get_sharpness()
            for widget in (self.ui.isp_Sharpness_hSlider,
                           self.ui.isp_Sharpness_spinbox):
                widget.setMinimum(cap.sSharpnessRange.iMin)
                widget.setMaximum(cap.sSharpnessRange.iMax)
                widget.setValue(sharpness)

            gamma = int(round(self.mgr.get_gamma() * 100))
            for widget in (self.ui.lut_gamma_hSlider, self.ui.lut_gamma_spinbox):
                widget.setMinimum(cap.sGammaRange.iMin)
                widget.setMaximum(cap.sGammaRange.iMax)
                widget.setValue(gamma)
            contrast = self.mgr.get_contrast()
            for widget in (self.ui.lut_contrast_hSlider,
                           self.ui.lut_contrast_spinbox):
                widget.setMinimum(cap.sContrastRange.iMin)
                widget.setMaximum(cap.sContrastRange.iMax)
                widget.setValue(contrast)

            if cap.sIspCapacity.bMonoSensor != 0:
                self.ui.frame_R2_wb.setEnabled(False)
            else:
                self.ui.frame_R2_wb.setEnabled(True)
                self.ui.radio_isp_auto.setChecked(True)
                for slider, spinbox, value in zip(
                        (self.ui.gain_red_hSlider, self.ui.gain_green_hSlider,
                         self.ui.gain_blue_hSlider),
                        (self.ui.gain_red_spinbox, self.ui.gain_green_spinbox,
                         self.ui.gain_blue_spinbox), self.mgr.get_gain()):
                    slider.setValue(value)
                    spinbox.setValue(value)
                saturation = self.mgr.get_saturation()
                self.ui.isp_saturation_hSlider.setValue(saturation)
                self.ui.isp_saturation_spinbox.setValue(saturation)

            self.ui.led_device_name2.setText(self.mgr.get_friendly_name())
            self.ui.led_device_serial_no.setText(self.mgr.read_serial_number(0))
        finally:
            self.ui_initing = 0
            del blockers

    # ── Hiển thị frame + schedule decode ──────────────────────────────────────

    def on_display_tick(self):
        frame, seq = self.mgr.latest_frame()
        if frame is None:
            return

        # Đếm frame theo seq — mỗi N frame capture được → submit decode 1 lần
        if (self.cbx_decode.isChecked()
                and seq > self._last_seq
                and seq - self._last_decode_seq >= self.spin_n.value()):
            if self.worker.submit(frame, seq):
                self._last_decode_seq = seq

        if seq != self._last_seq:
            self._last_seq = seq
            self.display_fps += 1
            self._last_frame = frame

        label_w, label_h = self.ui.label_image.width(), self.ui.label_image.height()
        vis = frame
        if self.cbx_quad.isChecked() and self._overlays:
            # nét dày theo tỷ lệ thu nhỏ để còn thấy sau khi resize về khung hiển thị
            thickness = max(2, 2 * frame.shape[1] // max(1, label_w))
            vis = draw_overlays(frame, self._overlays, seq, thickness=thickness)

        self.ui.label_image.setPixmap(QPixmap.fromImage(frame_to_qimage(vis, label_w, label_h)))

    def on_fps_show(self):
        self._render_latest_qr()   # cập nhật "… s trước"
        if self.mgr.handle:
            status = self.mgr.recording_status()
            if status.busy or self._camera_close_thread is not None:
                capture = status.capture_count
            else:
                capture, _ = self.mgr.frame_statistic()
            self.ui.status_bar.setText(
                "Capture fps: {}   Display fps: {}   Decode: {} lần".format(
                    capture - self.read_fps, self.display_fps, self.decode_count))
            self.read_fps = capture
            self.display_fps = 0
            self._update_conveyor_label(
                sdk_busy=status.busy or self._camera_close_thread is not None)

    # ── Decode callbacks ──────────────────────────────────────────────────────

    def on_decode_done(self, results, overlays):
        self.decode_count += 1
        self._overlays = overlays
        self.lbl_stat.setText("Decode: {} lần".format(self.decode_count))

        if not results:
            self._latest_qr_hits = 0
            return

        text = " | ".join(results)
        clock = time.strftime("%H:%M:%S")
        if text == self._latest_qr:
            self._latest_qr_hits += 1
            self._latest_qr_count += 1
        else:
            self._latest_qr = text
            self._latest_qr_hits = 1
            self._latest_qr_count = 1
            self.lst_history.insertItem(0, "{}  {}".format(clock, text))
            while self.lst_history.count() > 50:
                self.lst_history.takeItem(self.lst_history.count() - 1)
        self._latest_qr_at = time.monotonic()
        self._latest_qr_clock = clock
        self._render_latest_qr()

    def _render_latest_qr(self):
        """Hiện mã đọc gần nhất kèm giờ đọc và đã bao lâu — tránh nhầm kết quả cũ là mới."""
        if not self._latest_qr or self._latest_qr_at is None:
            self.lbl_latest.setText("QR mới nhất: —")
            return
        age = time.monotonic() - self._latest_qr_at
        if age < 1:
            age_text = "vừa xong"
        elif age < 60:
            age_text = "{:.0f} s trước".format(age)
        else:
            age_text = "{:.0f} phút trước".format(age // 60)
        count = " (x{})".format(self._latest_qr_count) if self._latest_qr_count > 1 else ""
        self.lbl_latest.setText("QR mới nhất: {}{} — {} ({})".format(
            self._latest_qr[:60], count, self._latest_qr_clock, age_text))

    def on_decode_stats(self, stats):
        skipped = " · bỏ qua {}".format(stats["skipped"]) if stats["skipped"] else ""
        self.lbl_stat.setText("Decode: {} lần · {} · detect {:.0f} ms · cascade {:.0f} ms{}".format(
            self.decode_count, self._device_label, stats["detect_ms"], stats["cascade_ms"], skipped))

    def on_passes_done(self, tracks):
        """Đếm lượt QR đi qua (một QR chạy qua khung = một lượt) — read rate thật trên băng."""
        self._passes_total += len(tracks)
        self._passes_read += sum(1 for t in tracks if t.text)
        self._passes_conflict += sum(1 for t in tracks if t.conflicting)
        self.lbl_passes.setText("Lượt QR: {}/{} đọc được · mâu thuẫn {}".format(
            self._passes_read, self._passes_total, self._passes_conflict))

    def on_decode_failed(self, msg):
        self.ui.status_bar.setText("Decode lỗi: {}".format(msg[:100]))

    # ── Các slot param (giữ logic của demo Advanced, gọi qua CameraManager) ───

    def on_ROI_changed(self, index):
        if self.ui_initing == 0 and self.mgr.handle:
            self.mgr.set_roi(index)

    def on_trigger_mode(self, btn):
        self.ui.btn_trigger_once.setEnabled(False)
        self.ui.frame_flashlight.setEnabled(False)
        if btn.text() == "Continuous":
            self.mgr.set_trigger_mode(0)
        elif btn.text() == "Soft trigger":
            self.mgr.set_trigger_mode(1)
            self.ui.btn_trigger_once.setEnabled(True)
        elif btn.text() == "Hard trigger":
            self.mgr.set_trigger_mode(2)
            self.ui.frame_flashlight.setEnabled(True)

    def on_flashlight_mode(self, btn):
        self.ui.frame_flashlight_polarity.setEnabled(False)
        if btn.text() == "Auto":
            self.mgr.set_strobe_mode(0)
        elif btn.text() == "Manual":
            self.mgr.set_strobe_mode(1)
            self.ui.frame_flashlight_polarity.setEnabled(True)

    def on_flashlight_polarity_mode(self, btn):
        if btn.text() == "High":
            self.mgr.set_strobe_polarity(0)
        elif btn.text() == "Low":
            self.mgr.set_strobe_polarity(1)

    def on_exposure_mode(self, btn):
        self.ui.frame_exposure_auto.setEnabled(False)
        self.ui.frame_exposure_manual.setEnabled(False)
        if btn.text() == "Auto":
            self.mgr.set_ae_state(True)
            self.ui.frame_exposure_auto.setEnabled(True)
        elif btn.text() == "Manual":
            self.mgr.set_ae_state(False)
            self.ui.frame_exposure_manual.setEnabled(True)
            ae_curr_time = self.mgr.get_exposure_time()
            self.ui.ae_manual_time_hSlider.setValue(int(ae_curr_time / (self.mgr.f_exp_line_time or 1.0)))
            self.ui.ae_manual_time_ledit.setText(str(ae_curr_time / 1000))

    def on_ae_flicker(self, checked):
        self.mgr.set_anti_flick(checked)
        self.ui.radio_50HZ.setEnabled(checked)
        self.ui.radio_60HZ.setEnabled(checked)

    def on_ae_flicker_hz(self, btn):
        if btn.text() == "50HZ":
            self.mgr.set_light_frequency(0)
        elif btn.text() == "60HZ":
            self.mgr.set_light_frequency(1)

    def on_ae_manual_time_hslider(self, value):
        if self.ui_initing:
            return
        if self.mgr.handle:
            line_time = self.mgr.f_exp_line_time or 1.0
            self.mgr.set_exposure_time(value * line_time)
            self.ui.ae_manual_time_ledit.setText(str(value * line_time / 1000))

    def on_ae_manual_time_ledit(self):
        if self.ui_initing:
            return
        if self.mgr.handle:
            fvalue = float(self.ui.ae_manual_time_ledit.text())
            line_time = self.mgr.f_exp_line_time or 1.0
            self.ui.ae_manual_time_hSlider.setValue(int(fvalue * 1000 / line_time))

    def on_btn_param_save(self):
        self.mgr.save_param(self._selected_param_slot())

    def on_btn_param_load(self):
        self.mgr.load_param(self._selected_param_slot())
        self.ui_init_param()

    def on_btn_param_default(self):
        self.mgr.reset_param()
        self.ui_init_param()

    def _selected_param_slot(self) -> int:
        if self.ui.radio_param_a.isChecked():
            return 0
        if self.ui.radio_param_b.isChecked():
            return 1
        if self.ui.radio_param_c.isChecked():
            return 2
        if self.ui.radio_param_d.isChecked():
            return 3
        return 0

    def on_white_blance(self):
        self.mgr.set_once_wb()
        v_red, v_green, v_blue = self.mgr.get_gain()
        self.ui.gain_red_hSlider.setValue(v_red)
        self.ui.gain_green_hSlider.setValue(v_green)
        self.ui.gain_blue_hSlider.setValue(v_blue)

    def on_gain_set(self, color, value):
        v_red, v_green, v_blue = self.mgr.get_gain()
        if color == "red":
            v_red = value
        elif color == "green":
            v_green = value
        elif color == "blue":
            v_blue = value
        self.mgr.set_gain(v_red, v_green, v_blue)

    def on_snap(self):
        if self._last_frame is None:
            self.ui.status_bar.setText("Chưa có frame để chụp.")
            return
        if self.ui.radio_jpg.isChecked():
            path = "./output.jpg"
        elif self.ui.radio_bmp.isChecked():
            path = "./output.bmp"
        else:
            path = "./output.png"
        cv2.imwrite(path, self._last_frame)
        self.ui.status_bar.setText("Đã lưu {}".format(path))
