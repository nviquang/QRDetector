"""Màn hình làm việc + cửa sổ Cấu hình trong MainWindow, với CameraManager giả; không cần camera.

Chạy (từ gốc repo):  python -m unittest tests.test_workspace_ui
"""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import Mock, patch

import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

T = types.SimpleNamespace


def device(serial):
    return T(GetSn=lambda: serial, GetFriendlyName=lambda: "Cam", GetPortType=lambda: "USB3")


def track(track_id=1, text="A", observations=5, conflicting=False):
    return T(track_id=track_id, text=text, observations=observations, conflicting=conflicting)


class WorkspaceUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        manager = types.ModuleType("camera.camera_manager")
        cls.factory = Mock()
        manager.CameraManager = cls.factory
        qr = types.ModuleType("qr")
        qr.ImprovePipeline = Mock()
        qr.PassReader = Mock()
        qr.PassReader.return_value.flush.return_value = []
        qr.PassReader.return_value.decode_every.side_effect = lambda n: n
        spec = importlib.util.spec_from_file_location(
            "demo_ui._workspace_test_window", ROOT / "demo_ui" / "main_window.py")
        cls.module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"camera.camera_manager": manager, "qr": qr}):
            spec.loader.exec_module(cls.module)
        from PyQt5.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])
        cls.RunState = cls.module.RunState   # lấy từ module vừa nạp — patch.dict đã bỏ ui.run_controller

    def make_mgr(self):
        mgr = Mock()
        mgr.handle = None
        mgr.running = False
        mgr.latest_frame.return_value = (None, 0)
        mgr.list_cameras.return_value = [device("SN1")]
        mgr.camera_list = mgr.list_cameras.return_value
        mgr.frame_statistic.return_value = (0, 0)
        mgr.apply_run_settings.return_value = {"ok": True, "exposure_us": 12_900.0, "analog_gain": 40,
                                               "resolution": (2448, 2048)}
        mgr.get_exposure_time.return_value = 1000.0
        mgr.get_analog_gain.return_value = 40

        def open_camera(index):
            mgr.handle = 7
            return True
        mgr.open.side_effect = open_camera

        def close_camera():
            mgr.handle = None
        mgr.close.side_effect = close_camera
        return mgr

    def setUp(self):
        self.mgr = self.make_mgr()
        self.factory.return_value = self.mgr
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.settings_path = Path(tmp.name) / "app_settings.json"
        self.window = self.module.MainWindow(settings_path=self.settings_path)
        self.window.worker._reader.take_late_reads.return_value = []
        self.window.display_timer.stop()
        self.window.fps_timer.stop()
        self.window.close_timer.stop()

    def tearDown(self):
        self.mgr.handle = None
        self.window._camera_close_thread = None
        self.window._allow_close = True
        self.window.close()
        self.window.worker.stop()
        self.app.processEvents()

    def pump_until(self, predicate):
        deadline = time.monotonic() + 3
        while not predicate() and time.monotonic() < deadline:
            self.app.processEvents()
            self.window.on_close_tick()
            time.sleep(0.005)
        self.assertTrue(predicate())

    def start_running(self):
        self.window.on_primary_clicked()
        self.pump_until(lambda: self.window.controller.state is self.RunState.RUNNING)

    def test_config_widgets_live_in_settings_window_not_workspace(self):
        window = self.window
        self.assertIs(window.centralWidget(), window.workspace)
        for widget in (window.ui.frame_camera_list, window.qr_group, window.ui.status_bar):
            self.assertTrue(window.settings_window.isAncestorOf(widget))
            self.assertFalse(window.workspace.isAncestorOf(widget))
        self.assertTrue(window.workspace.isAncestorOf(window.ui.label_image))

    def test_settings_have_only_connection_and_conveyor_tabs(self):
        tabs = self.window.settings_window.tabs
        self.assertEqual([tabs.tabText(i) for i in range(tabs.count())], ["Kết nối camera", "Băng chuyền"])
        for removed in ("cbx_conveyor_speed", "spin_mm_per_px", "spin_max_blur", "record_group"):
            self.assertFalse(hasattr(self.window, removed), removed)

    def test_window_is_resizable_and_settings_hidden_at_start(self):
        self.assertGreater(self.window.maximumWidth(), 4000)
        self.assertEqual(self.window.minimumWidth(), 1280)
        self.assertFalse(self.window.settings_window.isVisible())
        self.assertFalse(self.window.settings_window.isModal())

    def test_menu_opens_requested_tab(self):
        self.window.settings_window.open_tab(1)
        self.assertEqual(self.window.settings_window.tabs.currentIndex(), 1)
        self.assertTrue(self.window.settings_window.isVisible())
        self.window.settings_window.hide()

    def test_primary_button_runs_start_sequence_and_enables_decode(self):
        self.window.spin_gain.setValue(30)
        self.start_running()
        self.assertTrue(self.window._decoding)
        self.mgr.open.assert_called_once_with(0)
        self.assertEqual(self.mgr.apply_run_settings.call_args.args[0].analog_gain, 30)
        self.mgr.load_param.assert_not_called()
        self.assertEqual(self.window.settings.camera_serial, "SN1")
        self.assertFalse(self.window.ui.btn_camera_open.isEnabled())
        self.assertFalse(self.window.ui.btn_camera_close.isEnabled())
        self.assertIn("DỪNG", self.window.workspace.btn_primary.text())
        self.assertTrue(self.window.workspace.video.overlay.isHidden())

    def test_display_tick_only_submits_while_running(self):
        frame = np.zeros((48, 64, 3), np.uint8)
        self.mgr.latest_frame.return_value = (frame, 10)
        with patch.object(self.window.worker, "submit", return_value=True) as submit:
            self.window.on_display_tick()
            submit.assert_not_called()
            self.window._decoding = True
            self.mgr.latest_frame.return_value = (frame, 11)
            self.window.on_display_tick()
            submit.assert_called_once_with(frame, 11)

    def test_display_tick_uses_interval_from_worker(self):
        frame = np.zeros((48, 64, 3), np.uint8)
        self.window._decoding = True
        self.window._last_seq = self.window._last_decode_seq = 10
        self.mgr.latest_frame.return_value = (frame, 12)
        with patch.object(self.window.worker, "submit", return_value=True) as submit:
            self.window.on_display_tick()
            submit.assert_not_called()      # mặc định 5 frame một lần
            self.window._last_seq = 10
            with patch.object(self.window.worker, "decode_every", return_value=2):
                self.window.on_display_tick()
            submit.assert_called_once_with(frame, 12)

    def test_configured_camera_passes_exposure_to_worker(self):
        self.window.spin_exposure.setValue(7.5)
        with patch.object(self.window.worker, "set_exposure_ms") as set_exposure:
            self.window._on_camera_configured()
        set_exposure.assert_called_once_with(7.5)

    def test_start_error_is_shown_in_video_area_with_recovery_buttons(self):
        self.mgr.list_cameras.return_value = []
        self.window.on_primary_clicked()
        self.pump_until(lambda: self.window.controller.state is self.RunState.ERROR)
        video = self.window.workspace.video
        self.assertIn("Không tìm thấy camera", video.message.text())
        self.assertFalse(video.btn_retry.isHidden())
        self.assertFalse(video.btn_settings.isHidden())
        self.assertIn("BẮT ĐẦU", self.window.workspace.btn_primary.text())

    def test_stop_keeps_numbers_and_closes_camera(self):
        self.start_running()
        self.window.on_reads_done([track(1, "A")])
        self.window.on_passes_done([track(1, "A")])
        self.window.on_primary_clicked()
        self.pump_until(lambda: self.window.controller.state is self.RunState.IDLE)
        self.mgr.close.assert_called()
        self.assertFalse(self.window._decoding)
        self.assertEqual(self.window.workspace.kpi_read.text(), "1")
        self.assertEqual(self.window.workspace.lbl_latest_code.text(), "A")
        self.assertEqual(self.window.workspace.table.rowCount(), 1)
        self.assertIn("BẮT ĐẦU", self.window.workspace.btn_primary.text())

    def test_stop_counts_passes_still_open(self):
        self.start_running()
        self.window.worker._reader.flush.return_value = [track(1, "A")]
        self.window.on_stop()
        self.pump_until(lambda: self.window.stats.read_count == 1)
        self.window.worker._reader.flush.return_value = []

    def test_read_row_appears_immediately_then_gets_final_state(self):
        workspace = self.window.workspace
        self.window.on_reads_done([track(1, "000000585546")])
        self.assertEqual(workspace.lbl_latest_code.text(), "000000585546")
        self.assertEqual(workspace.kpi_read.text(), "0")
        self.assertEqual(workspace.kpi_rate.text(), "—")
        self.assertEqual((workspace.table.item(0, 1).text(), workspace.table.item(0, 2).text()),
                         ("000000585546", "…"))
        self.window.on_passes_done([track(1, "000000585546")])
        self.assertEqual(workspace.table.rowCount(), 1)
        self.assertEqual(workspace.table.item(0, 2).text(), "✓")
        self.assertEqual(workspace.kpi_read.text(), "1")
        self.assertEqual(workspace.kpi_rate.text(), "100,0%")

    def test_failed_and_conflicting_rows_and_noise(self):
        workspace = self.window.workspace
        self.window.on_passes_done([track(1, None), track(2, "B", conflicting=True),
                                    track(3, None, observations=1)])
        self.assertEqual(workspace.table.rowCount(), 2)
        self.assertEqual(workspace.table.item(1, 1).text(), "không đọc được")
        self.assertEqual(workspace.table.item(0, 2).text(), "⚠")
        self.assertEqual(workspace.kpi_rate.text(), "50,0%")
        self.assertEqual(self.window.stats.noise_count, 1)

    def test_table_is_capped_and_old_rows_forgotten(self):
        workspace = self.window.workspace
        for track_id in range(205):
            self.window.on_reads_done([track(track_id, str(track_id))])
        self.assertEqual(workspace.table.rowCount(), 200)
        self.assertEqual(workspace.table.item(0, 1).text(), "204")
        self.assertEqual(workspace.table.item(199, 1).text(), "5")
        self.assertEqual(len(workspace._items), 200)

    def test_latest_meta_shows_clock_and_age(self):
        clock = self.module.time
        with patch.object(self.window.stats, "_clock", return_value="16:02:11"), \
                patch.object(self.window.stats, "_monotonic", return_value=100.0), \
                patch.object(clock, "monotonic", return_value=112.0):
            self.window.on_reads_done([track(1, "A")])
        self.assertEqual(self.window.workspace.lbl_latest_meta.text(), "16:02:11 · 12 giây trước")

    def test_reset_requires_confirmation_and_clears_after_flush(self):
        workspace = self.window.workspace
        self.window.on_passes_done([track(1, "A")])
        with patch.object(self.window, "_confirm_reset", return_value=False):
            self.window.on_reset()
        self.app.processEvents()
        self.assertEqual(workspace.table.rowCount(), 1)
        with patch.object(self.window, "_confirm_reset", return_value=True):
            self.window.on_reset()
        self.pump_until(lambda: workspace.table.rowCount() == 0)
        self.assertEqual(workspace.kpi_read.text(), "0")
        self.assertEqual(workspace.kpi_rate.text(), "—")
        self.assertEqual(workspace.lbl_latest_code.text(), "—")
        self.assertEqual(self.window.stats.finished_count, 0)

    def test_results_before_reset_flush_do_not_survive_it(self):
        self.window.on_flushed("reset", [track(9, "cũ")])
        self.assertEqual(self.window.stats.read_count, 0)
        self.assertEqual(self.window.workspace.table.rowCount(), 0)

    def test_signal_lost_overlay_only_when_running_without_frames(self):
        self.start_running()
        video = self.window.workspace.video
        self.window.on_fps_show()
        self.assertTrue(video.overlay.isHidden())
        self.window._last_frame_at = time.monotonic() - 10
        self.window.on_fps_show()
        self.assertFalse(video.overlay.isHidden())
        self.assertIn("Mất tín hiệu", video.message.text())
        self.window._last_frame_at = time.monotonic()
        self.window.on_fps_show()
        self.assertTrue(video.overlay.isHidden())

    def test_sdk_not_touched_by_gui_while_connecting(self):
        self.window.controller._state = self.RunState.CONNECTING
        self.mgr.handle = 7
        self.window.on_fps_show()
        self.mgr.frame_statistic.assert_not_called()
        self.mgr.get_exposure_time.assert_not_called()
        self.window.controller._state = self.RunState.IDLE

    def test_manual_open_enters_tuning_without_decode(self):
        self.window.on_camera_list_flush()
        self.window.on_camera_open()
        self.assertEqual(self.window.controller.state, self.RunState.TUNING)
        self.assertFalse(self.window._decoding)
        self.assertEqual(self.window.workspace.lbl_state.text(), "CHỈNH CAMERA")
        self.mgr.apply_run_settings.assert_called_once()   # xem trước đúng exposure/gain sẽ dùng khi chạy
        self.window.on_primary_clicked()
        self.pump_until(lambda: self.window.controller.state is self.RunState.RUNNING)
        self.mgr.open.assert_called_once()

    def test_apply_button_only_enabled_while_camera_open_and_idle(self):
        self.window.on_close_tick()
        self.assertFalse(self.window.btn_conveyor_apply.isEnabled())
        self.mgr.handle = 7
        self.window.on_close_tick()
        self.assertTrue(self.window.btn_conveyor_apply.isEnabled())
        self.window.controller._state = self.RunState.CONNECTING
        self.window.on_close_tick()
        self.assertFalse(self.window.btn_conveyor_apply.isEnabled())
        self.window.controller._state = self.RunState.IDLE

    def test_decode_switch_off_closes_open_passes_and_warns(self):
        self.start_running()
        self.window.worker._reader.flush.return_value = [track(1, "A")]
        self.window.cbx_decode.setChecked(False)
        self.pump_until(lambda: self.window.stats.read_count == 1)
        self.window.worker._reader.flush.return_value = []
        self.assertIn("Decode tắt", self.window.workspace.lbl_processing.text())
        self.window.cbx_decode.setChecked(True)
        self.assertNotIn("Decode tắt", self.window.workspace.lbl_processing.text())

    def test_close_failure_shows_error_and_retry_closes_again(self):
        self.start_running()
        self.mgr.close.side_effect = lambda: None      # handle vẫn còn
        self.window.on_stop()
        self.pump_until(lambda: self.window.controller.state is self.RunState.ERROR)
        self.assertIn("Chưa đóng được", self.window.workspace.video.message.text())

        def close_ok():
            self.mgr.handle = None
        self.mgr.close.side_effect = close_ok
        self.window.on_start()
        self.pump_until(lambda: self.window.controller.state is self.RunState.IDLE)

    def test_closing_while_running_stops_first(self):
        self.start_running()
        self.window._allow_close = False
        self.window.close()
        self.assertFalse(self.window._decoding)
        self.pump_until(lambda: self.window._allow_close)
        self.mgr.close.assert_called()
        self.assertEqual(self.window.controller.state, self.RunState.IDLE)

    def test_settings_loaded_into_widgets_and_saved_on_change(self):
        self.settings_path.write_text(json.dumps(
            {"exposure_ms": 8.5, "analog_gain": 20, "camera_serial": "SN1", "draw_quad": False,
             "decode_enabled": False, "band_x_enabled": True, "band_x": 320, "band_w": 1600}), encoding="utf-8")
        window = self.module.MainWindow(settings_path=self.settings_path)
        window.display_timer.stop()
        window.fps_timer.stop()
        window.close_timer.stop()
        self.addCleanup(window.worker.stop)
        self.addCleanup(window.close)
        self.assertEqual((window.spin_exposure.value(), window.spin_gain.value()), (8.5, 20))
        self.assertFalse(window.cbx_quad.isChecked())
        self.assertFalse(window.cbx_decode.isChecked())
        self.assertTrue(window.cbx_band_x.isChecked())
        self.assertEqual((window.spin_band_x.value(), window.spin_band_w.value()), (320, 1600))
        settings = window.run_settings()
        self.assertEqual((settings.exposure_us, settings.analog_gain, settings.band_x, settings.band_y),
                         (8500.0, 20, (320, 1600), None))
        window.spin_gain.setValue(33)
        self.assertTrue(window._settings_timer.isActive())
        window._save_settings()
        saved = json.loads(self.settings_path.read_text(encoding="utf-8"))
        self.assertEqual((saved["analog_gain"], saved["camera_serial"], saved["band_w"]), (33, "SN1", 1600))


if __name__ == "__main__":
    unittest.main()
