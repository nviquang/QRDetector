"""Cửa sổ chính app offline: mở ảnh / thư mục / video → ImprovePipeline → quad + text QR.

- Ảnh: chuyển ảnh bằng Trước/Sau hoặc danh sách; mỗi ảnh decode 1 lần (frame mới thay frame chờ).
- Video: Play/Pause + thanh tua; khi phát, mỗi N frame submit decode, worker bận → bỏ frame.
- Quét toàn bộ: decode tuần tự mọi ảnh, hoặc mỗi N frame của video (không theo thời gian thực).
Kết quả gom theo (file, nội dung) trong ResultLog → bảng + xuất CSV.
"""

from __future__ import annotations

import os

import cv2
import numpy as np
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import (
    QAbstractItemView, QCheckBox, QFileDialog, QGroupBox, QHBoxLayout, QHeaderView,
    QLabel, QListWidget, QMainWindow, QMessageBox, QPlainTextEdit, QProgressBar,
    QPushButton, QSlider, QSpinBox, QSplitter, QStyle, QTableWidget, QTableWidgetItem,
    QToolBar, QVBoxLayout, QWidget)

from media_source import (
    IMAGE_EXTS, VIDEO_EXTS, MediaError, VideoSource, format_time, is_image, is_video,
    list_images, read_image, write_image)
from results import ResultLog
from workers import DecodeWorker, FrameMeta, ScanWorker, SharedPipeline

COLOR_OK = (0, 255, 0)       # BGR — decode thành công
COLOR_DETECT = (0, 0, 255)   # chỉ phát hiện được QR


def draw_overlay(frame: np.ndarray, detections: list, ok: bool) -> np.ndarray:
    if not detections:
        return frame
    vis = frame.copy()
    thickness = max(2, round(max(frame.shape[:2]) / 400))
    color = COLOR_OK if ok else COLOR_DETECT
    for det in detections:
        pts = det.quad_xy.astype(np.int32).reshape((-1, 1, 2))
        cv2.polylines(vis, [pts], isClosed=True, color=color, thickness=thickness)
    return vis


def _filter(label: str, exts) -> str:
    return "{} ({})".format(label, " ".join("*" + e for e in exts))


class MainWindow(QMainWindow):
    COLS = ("File", "Nội dung QR", "Frame đầu", "Thời điểm đầu", "Số lần")

    def __init__(self, pipeline):
        super().__init__()
        self.setWindowTitle("QR Detector — Offline (ảnh / video)")
        self.resize(1400, 860)
        self.setAcceptDrops(True)

        shared = SharedPipeline(pipeline)
        self.worker = DecodeWorker(shared)
        self.worker.done.connect(self.on_decode_done)
        self.worker.failed.connect(self.on_decode_failed)
        self.scanner = ScanWorker(shared)
        self.scanner.progress.connect(self.on_scan_progress)
        self.scanner.hit.connect(self.on_scan_hit)
        self.scanner.preview.connect(self.on_scan_preview)
        self.scanner.item_failed.connect(self.on_scan_item_failed)
        self.scanner.finished.connect(self.on_scan_finished)

        self.log = ResultLog()
        self._rows: dict[tuple[str, str], int] = {}

        self._mode: str | None = None          # "image" | "video"
        self._images: list[str] = []
        self._image_idx = -1
        self._video: VideoSource | None = None
        self._request_id = 0                   # tăng mỗi khi đổi nguồn → bỏ overlay cũ
        self._frame: np.ndarray | None = None  # frame đang hiển thị (BGR, chưa vẽ)
        self._frame_meta: FrameMeta | None = None
        self._detections: list = []
        self._ok = False
        self._last_decode_index = -10**9
        self.decode_count = 0

        self._timer = QTimer(self)
        self._timer.timeout.connect(self.on_play_tick)

        self._build_ui()
        self._update_controls()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        tb = QToolBar("Chính", self)
        tb.setMovable(False)
        self.addToolBar(tb)
        self.act_open_images = tb.addAction("Mở ảnh…", self.open_images)
        self.act_open_folder = tb.addAction("Mở thư mục ảnh…", self.open_folder)
        self.act_open_video = tb.addAction("Mở video…", self.open_video)
        tb.addSeparator()
        self.act_scan = tb.addAction("Quét toàn bộ", self.start_scan)
        self.act_cancel = tb.addAction("Huỷ quét", self.scanner.cancel)
        tb.addSeparator()
        self.act_save = tb.addAction("Lưu ảnh kết quả…", self.save_annotated)
        self.act_csv = tb.addAction("Xuất CSV…", self.export_csv)
        self.act_clear = tb.addAction("Xoá kết quả", self.clear_results)

        # ── Trái: ảnh + điều khiển ──
        self.label_image = QLabel("Kéo thả ảnh / video vào đây, hoặc dùng nút Mở trên thanh công cụ")
        self.label_image.setAlignment(Qt.AlignCenter)
        self.label_image.setMinimumSize(320, 240)
        self.label_image.setStyleSheet("background:#202020; color:#bbb;")

        style = self.style()
        self.btn_prev = QPushButton(style.standardIcon(QStyle.SP_MediaSkipBackward), "")
        self.btn_play = QPushButton(style.standardIcon(QStyle.SP_MediaPlay), "")
        self.btn_next = QPushButton(style.standardIcon(QStyle.SP_MediaSkipForward), "")
        self.btn_prev.setToolTip("Ảnh trước / lùi 1 frame")
        self.btn_play.setToolTip("Phát / tạm dừng video (Space)")
        self.btn_next.setToolTip("Ảnh sau / tiến 1 frame")
        self.btn_prev.clicked.connect(lambda: self.step(-1))
        self.btn_next.clicked.connect(lambda: self.step(1))
        self.btn_play.clicked.connect(self.toggle_play)
        self.btn_play.setShortcut(Qt.Key_Space)

        self.slider = QSlider(Qt.Horizontal)
        self.slider.sliderMoved.connect(self.on_slider_moved)
        self.slider.sliderReleased.connect(lambda: self.seek(self.slider.value()))
        self.lbl_pos = QLabel("—")
        self.lbl_pos.setMinimumWidth(220)
        self.lbl_pos.setMaximumWidth(340)

        self.spin_n = QSpinBox()
        self.spin_n.setRange(1, 1000)
        self.spin_n.setValue(5)
        self.spin_n.setPrefix("Decode mỗi ")
        self.spin_n.setSuffix(" frame")
        self.cbx_decode = QCheckBox("Decode khi phát")
        self.cbx_decode.setChecked(True)
        self.cbx_quad = QCheckBox("Vẽ quad")
        self.cbx_quad.setChecked(True)
        self.cbx_quad.toggled.connect(self.render)

        row_ctl = QHBoxLayout()
        for w in (self.btn_prev, self.btn_play, self.btn_next):
            row_ctl.addWidget(w)
        row_ctl.addWidget(self.slider, 1)
        row_ctl.addWidget(self.lbl_pos)
        row_opt = QHBoxLayout()
        row_opt.addWidget(self.spin_n)
        row_opt.addWidget(self.cbx_decode)
        row_opt.addWidget(self.cbx_quad)
        row_opt.addStretch(1)

        self.progress = QProgressBar()
        self.progress.setVisible(False)

        left = QWidget()
        lv = QVBoxLayout(left)
        lv.addWidget(self.label_image, 1)
        lv.addLayout(row_ctl)
        lv.addLayout(row_opt)
        lv.addWidget(self.progress)

        # ── Phải: danh sách ảnh, QR hiện tại, bảng kết quả, log ──
        self.list_images = QListWidget()
        self.list_images.currentRowChanged.connect(self.on_image_selected)
        grp_files = QGroupBox("Danh sách ảnh")
        QVBoxLayout(grp_files).addWidget(self.list_images)
        self.grp_files = grp_files

        self.txt_current = QPlainTextEdit()
        self.txt_current.setReadOnly(True)
        self.txt_current.setMaximumHeight(110)
        grp_cur = QGroupBox("QR của frame hiện tại")
        QVBoxLayout(grp_cur).addWidget(self.txt_current)

        self.table = QTableWidget(0, len(self.COLS))
        self.table.setHorizontalHeaderLabels(self.COLS)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.cellDoubleClicked.connect(self.on_result_activated)
        self.lbl_stat = QLabel("Kết quả: 0 QR")
        grp_res = QGroupBox("Kết quả (gộp theo file + nội dung) — double-click để nhảy tới")
        gv = QVBoxLayout(grp_res)
        gv.addWidget(self.table)
        gv.addWidget(self.lbl_stat)

        self.txt_log = QPlainTextEdit()
        self.txt_log.setReadOnly(True)
        self.txt_log.setMaximumBlockCount(500)
        grp_log = QGroupBox("Nhật ký")
        QVBoxLayout(grp_log).addWidget(self.txt_log)

        right = QSplitter(Qt.Vertical)
        for w in (grp_files, grp_cur, grp_res, grp_log):
            right.addWidget(w)
        right.setSizes([160, 110, 400, 120])

        split = QSplitter(Qt.Horizontal)
        split.addWidget(left)
        split.addWidget(right)
        split.setSizes([900, 500])
        self.setCentralWidget(split)
        self.statusBar().showMessage("Sẵn sàng")

    def _update_controls(self):
        scanning = self.scanner.running
        video = self._mode == "video"
        has_media = self._mode is not None
        for act in (self.act_open_images, self.act_open_folder, self.act_open_video):
            act.setEnabled(not scanning)
        self.act_scan.setEnabled(has_media and not scanning)
        self.act_cancel.setEnabled(scanning)
        self.act_save.setEnabled(self._frame is not None)
        self.act_csv.setEnabled(len(self.log) > 0)
        self.act_clear.setEnabled(not scanning)
        nav = has_media and not scanning
        self.btn_prev.setEnabled(nav)
        self.btn_next.setEnabled(nav)
        self.btn_play.setEnabled(video and not scanning)
        self.slider.setEnabled(video and not scanning and bool(self._video and self._video.frame_count))
        self.cbx_decode.setEnabled(video)
        self.list_images.setEnabled(not scanning)
        self.grp_files.setVisible(self._mode != "video")

    def append_log(self, msg: str):
        self.txt_log.appendPlainText(msg)

    # ── Mở nguồn ──────────────────────────────────────────────────────────────

    def open_images(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Chọn ảnh", "", _filter("Ảnh", IMAGE_EXTS) + ";;Tất cả (*)")
        if paths:
            self.load_images(paths)

    def open_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Chọn thư mục ảnh")
        if not folder:
            return
        paths = list_images(folder)
        if not paths:
            QMessageBox.information(self, "Không có ảnh", f"Không tìm thấy ảnh trong:\n{folder}")
            return
        self.load_images(paths)

    def open_video(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Chọn video", "", _filter("Video", VIDEO_EXTS) + ";;Tất cả (*)")
        if path:
            self.load_video(path)

    def _close_media(self):
        self.pause()
        if self._video is not None:
            self._video.release()
            self._video = None
        self._request_id += 1
        self._frame = None
        self._frame_meta = None
        self._detections = []
        self._ok = False
        self._last_decode_index = -10**9
        self.txt_current.clear()

    def load_images(self, paths: list[str]):
        self._close_media()
        self._mode = "image"
        self._images = list(paths)
        self.list_images.blockSignals(True)
        self.list_images.clear()
        self.list_images.addItems([os.path.basename(p) for p in self._images])
        self.list_images.blockSignals(False)
        self.lbl_pos.setText(f"{len(paths)} ảnh")
        self.append_log(f"Mở {len(paths)} ảnh")
        self._update_controls()
        self.list_images.setCurrentRow(0)

    def load_video(self, path: str):
        self._close_media()
        try:
            self._video = VideoSource(path)
        except MediaError as e:
            self._mode = None
            self._update_controls()
            QMessageBox.warning(self, "Lỗi mở video", str(e))
            return
        v = self._video
        self._mode = "video"
        self._images = []
        self.list_images.clear()
        self.slider.blockSignals(True)
        self.slider.setRange(0, max(0, v.frame_count - 1))
        self.slider.setValue(0)
        self.slider.blockSignals(False)
        self.append_log(
            f"Mở video {os.path.basename(path)} — {v.width}x{v.height}, "
            f"{v.fps:.2f} fps, {v.frame_count or '?'} frame")
        self._update_controls()
        self._read_video_frame(force_decode=True)

    # ── Ảnh ───────────────────────────────────────────────────────────────────

    def on_image_selected(self, row: int):
        if self._mode != "image" or not 0 <= row < len(self._images):
            return
        self._image_idx = row
        path = self._images[row]
        self._request_id += 1
        self._detections, self._ok = [], False
        try:
            frame = read_image(path)
        except MediaError as e:
            self._frame = None
            self.label_image.setText(str(e))
            self.append_log(str(e))
            self._update_controls()
            return
        self._frame = frame
        self._frame_meta = FrameMeta(self._request_id, path)
        self.lbl_pos.setText(f"Ảnh {row + 1}/{len(self._images)} — {frame.shape[1]}x{frame.shape[0]}")
        self.txt_current.setPlainText("Đang decode…")
        self.worker.submit(frame, self._frame_meta, replace=True)
        self.render()
        self._update_controls()

    # ── Video ─────────────────────────────────────────────────────────────────

    def _read_video_frame(self, force_decode: bool = False) -> bool:
        item = self._video.read() if self._video else None
        if item is None:
            return False
        idx, frame = item
        self._frame = frame
        self._frame_meta = FrameMeta(self._request_id, self._video.path, idx, self._video.timestamp(idx))
        if self.slider.isEnabled() and not self.slider.isSliderDown():
            self.slider.blockSignals(True)
            self.slider.setValue(idx)
            self.slider.blockSignals(False)
        self._update_pos_label(idx)

        playing = self._timer.isActive()
        want = force_decode or not playing or (
            self.cbx_decode.isChecked() and idx - self._last_decode_index >= self.spin_n.value())
        if want:
            # Khi dừng/tua: luôn decode frame mới nhất; khi phát: bận thì bỏ frame
            if self.worker.submit(frame, self._frame_meta, replace=not playing):
                self._last_decode_index = idx
        self.render()
        return True

    def _update_pos_label(self, idx: int):
        v = self._video
        total = f"/{v.frame_count}" if v.frame_count else ""
        dur = f" / {format_time(v.timestamp(v.frame_count))}" if v.frame_count else ""
        self.lbl_pos.setText(f"Frame {idx + 1}{total}   {format_time(v.timestamp(idx))}{dur}")

    def toggle_play(self):
        if self._mode != "video" or self.scanner.running:
            return
        if self._timer.isActive():
            self.pause()
            return
        v = self._video
        if v.frame_count and v.position >= v.frame_count:
            v.seek(0)
        self._last_decode_index = -10**9
        self._timer.start(max(1, int(round(1000 / v.fps))))
        self.btn_play.setIcon(self.style().standardIcon(QStyle.SP_MediaPause))

    def pause(self):
        self._timer.stop()
        self.btn_play.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))

    def on_play_tick(self):
        if not self._read_video_frame():
            self.pause()
            self.append_log("Hết video")

    def on_slider_moved(self, value: int):
        if self._video:
            self._update_pos_label(value)

    def seek(self, index: int):
        if self._mode != "video" or self._video is None:
            return
        self._video.seek(index)
        self._read_video_frame(force_decode=not self._timer.isActive())

    def step(self, delta: int):
        if self._mode == "image" and self._images:
            row = (self._image_idx + delta) % len(self._images)
            self.list_images.setCurrentRow(row)
        elif self._mode == "video" and self._video is not None:
            self.pause()
            cur = self._frame_meta.frame_index if self._frame_meta else -1
            if delta == 1 and cur + 1 == self._video.position:
                self._read_video_frame(force_decode=True)   # đọc tuần tự, không cần seek
            else:
                self.seek(cur + delta)

    # ── Decode (DecodeWorker) ─────────────────────────────────────────────────

    def _record(self, meta: FrameMeta, results: list[str]):
        for text in results:
            rec, new = self.log.add(meta.source, text, meta.frame_index, meta.time_s)
            self._upsert_row(rec)
            if new:
                where = "" if meta.frame_index is None else \
                    f" @ frame {meta.frame_index} ({format_time(meta.time_s)})"
                self.append_log(f"QR mới [{os.path.basename(meta.source)}{where}]: {text}")
        self.lbl_stat.setText(f"Kết quả: {len(self.log)} QR")
        self._update_controls()

    def on_decode_done(self, meta: FrameMeta, results: list, detections: list):
        self.decode_count += 1
        self._record(meta, results)
        if meta.request_id != self._request_id:
            return   # kết quả của nguồn cũ — vẫn ghi log, không vẽ đè
        self._detections, self._ok = detections, bool(results)
        if results:
            self.txt_current.setPlainText("\n".join(f"[{i}] {t}" for i, t in enumerate(results, 1)))
        elif detections:
            self.txt_current.setPlainText(f"Phát hiện {len(detections)} QR nhưng không decode được")
        else:
            self.txt_current.setPlainText("Không phát hiện QR")
        self.statusBar().showMessage(f"Decode: {self.decode_count} lần")
        self.render()

    def on_decode_failed(self, meta: FrameMeta, err: str):
        self.append_log(f"Lỗi decode {os.path.basename(meta.source)}: {err}")

    # ── Quét toàn bộ (ScanWorker) ─────────────────────────────────────────────

    def start_scan(self):
        if self.scanner.running or self._mode is None:
            return
        self.pause()
        self._request_id += 1
        if self._mode == "video":
            step = self.spin_n.value()
            self.append_log(f"Quét toàn bộ video, mỗi {step} frame…")
            self.scanner.scan_video(self._video.path, step, self._request_id)
        else:
            self.append_log(f"Quét toàn bộ {len(self._images)} ảnh…")
            self.scanner.scan_images(self._images, self._request_id)
        self.progress.setValue(0)
        self.progress.setVisible(True)
        self._update_controls()

    def on_scan_progress(self, done: int, total: int):
        if total:
            self.progress.setRange(0, total)
            self.progress.setValue(min(done, total))
            self.progress.setFormat(f"{done}/{total} (%p%)")
        else:
            self.progress.setRange(0, 0)   # không biết tổng → thanh chạy vô hạn
        self.statusBar().showMessage(f"Đang quét: {done} frame")

    def on_scan_hit(self, meta: FrameMeta, results: list, detections: list):
        self._record(meta, results)

    def on_scan_preview(self, meta: FrameMeta, frame, detections: list, ok: bool):
        if meta.request_id != self._request_id:
            return
        self._frame, self._frame_meta = frame, meta
        self._detections, self._ok = detections, ok
        if meta.frame_index is not None:
            self._update_pos_label(meta.frame_index)
        else:
            self.lbl_pos.setText(os.path.basename(meta.source))
        self.render()

    def on_scan_item_failed(self, source: str, err: str):
        self.append_log(f"Bỏ qua {os.path.basename(source)}: {err}")

    def on_scan_finished(self, processed: int, cancelled: bool, err: str):
        self.progress.setVisible(False)
        state = "đã huỷ" if cancelled else "xong"
        self.append_log(f"Quét {state}: decode {processed} frame/ảnh, tổng {len(self.log)} QR"
                        + (f" — lỗi: {err}" if err else ""))
        self.statusBar().showMessage(f"Quét {state}")
        if err:
            QMessageBox.warning(self, "Lỗi quét", err)
        # Đồng bộ lại vị trí đọc video với frame preview cuối
        if self._mode == "video" and self._video and self._frame_meta \
                and self._frame_meta.frame_index is not None:
            self._video.seek(self._frame_meta.frame_index + 1)
            self.slider.blockSignals(True)
            self.slider.setValue(self._frame_meta.frame_index)
            self.slider.blockSignals(False)
        self._update_controls()

    # ── Hiển thị ──────────────────────────────────────────────────────────────

    def render(self):
        if self._frame is None:
            return
        vis = draw_overlay(self._frame, self._detections, self._ok) \
            if self.cbx_quad.isChecked() else self._frame
        rgb = cv2.cvtColor(vis, cv2.COLOR_BGR2RGB)
        h, w = rgb.shape[:2]
        qimg = QImage(rgb.data, w, h, rgb.strides[0], QImage.Format_RGB888).copy()
        pixmap = QPixmap.fromImage(qimg).scaled(
            self.label_image.width(), self.label_image.height(),
            Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.label_image.setPixmap(pixmap)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.render()

    # ── Bảng kết quả ──────────────────────────────────────────────────────────

    def _upsert_row(self, rec):
        key = (rec.source, rec.text)
        row = self._rows.get(key)
        if row is None:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self._rows[key] = row
        values = (
            os.path.basename(rec.source), rec.text,
            "" if rec.first_frame is None else str(rec.first_frame),
            "" if rec.first_time is None else format_time(rec.first_time),
            str(rec.hits),
        )
        for col, val in enumerate(values):
            item = QTableWidgetItem(val)
            if col == 0:
                item.setData(Qt.UserRole, (rec.source, rec.first_frame))
                item.setToolTip(rec.source)
            self.table.setItem(row, col, item)

    def on_result_activated(self, row: int, _col: int):
        if self.scanner.running:
            return
        source, frame_index = self.table.item(row, 0).data(Qt.UserRole)
        if frame_index is None:
            if self._mode == "image" and source in self._images:
                self.list_images.setCurrentRow(self._images.index(source))
            elif os.path.exists(source):
                self.load_images([source])
            return
        if self._mode != "video" or self._video is None or self._video.path != source:
            if not os.path.exists(source):
                return
            self.load_video(source)
        self.pause()
        self.seek(frame_index)

    def clear_results(self):
        self.log.clear()
        self._rows.clear()
        self.table.setRowCount(0)
        self.lbl_stat.setText("Kết quả: 0 QR")
        self._update_controls()

    # ── Xuất ──────────────────────────────────────────────────────────────────

    def save_annotated(self):
        if self._frame is None:
            return
        meta = self._frame_meta
        base = os.path.splitext(os.path.basename(meta.source))[0] if meta else "frame"
        if meta and meta.frame_index is not None:
            base += f"_f{meta.frame_index:06d}"
        path, _ = QFileDialog.getSaveFileName(
            self, "Lưu ảnh kết quả", base + "_qr.png", "PNG (*.png);;JPEG (*.jpg)")
        if not path:
            return
        try:
            write_image(path, draw_overlay(self._frame, self._detections, self._ok))
        except (MediaError, OSError) as e:
            QMessageBox.warning(self, "Lỗi lưu ảnh", str(e))
            return
        self.append_log(f"Đã lưu {path}")

    def export_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, "Xuất CSV", "qr_results.csv", "CSV (*.csv)")
        if not path:
            return
        try:
            self.log.export_csv(path)
        except OSError as e:
            QMessageBox.warning(self, "Lỗi xuất CSV", str(e))
            return
        self.append_log(f"Đã xuất {len(self.log)} dòng → {path}")

    # ── Kéo thả ───────────────────────────────────────────────────────────────

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and not self.scanner.running:
            event.acceptProposedAction()

    def dropEvent(self, event):
        paths = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        videos = [p for p in paths if is_video(p)]
        images = [p for p in paths if is_image(p)]
        for p in paths:
            if os.path.isdir(p):
                images.extend(list_images(p))
        if videos:
            self.load_video(videos[0])
        elif images:
            self.load_images(images)

    # ── Đóng ──────────────────────────────────────────────────────────────────

    def closeEvent(self, event):
        self.pause()
        self.scanner.cancel()
        self.scanner.wait()
        self.worker.stop()
        if self._video is not None:
            self._video.release()
        super().closeEvent(event)
