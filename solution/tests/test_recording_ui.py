"""Runtime recording controls use cached state, never blocking the Qt loop."""
import importlib.util
import os
from pathlib import Path
import sys
import threading
import types
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from camera.recording import RecordingStatus


class RecordingUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        manager = types.ModuleType("camera.camera_manager")
        cls.factory = Mock()
        manager.CameraManager = cls.factory
        qr = types.ModuleType("qr")
        qr.ImprovePipeline = Mock()
        spec = importlib.util.spec_from_file_location(
            "ui._recording_test_window", ROOT / "ui" / "main_window.py")
        cls.module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"camera.camera_manager": manager, "qr": qr}):
            spec.loader.exec_module(cls.module)
        from PyQt5.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.mgr = Mock()
        self.mgr.handle = None
        self.mgr.running = False
        self.mgr.latest_frame.return_value = (None, 0)
        self.mgr.list_cameras.return_value = []
        self.mgr.recording_status.return_value = RecordingStatus()
        self.factory.return_value = self.mgr
        self.window = self.module.MainWindow()
        self.window.display_timer.stop()
        self.window.fps_timer.stop()
        self.window.recording_timer.stop()
        self.window.worker.stop()

    def tearDown(self):
        self.mgr.handle = None
        self.mgr.recording_status.return_value = RecordingStatus()
        self.window._closing_app = False
        self.window._camera_close_thread = None
        self.window._allow_close = True
        self.window.close()
        self.app.processEvents()

    def test_start_disabled_without_frame_and_enabled_with_live_camera(self):
        self.window.on_recording_tick()
        self.assertFalse(self.window.btn_record_start.isEnabled())
        self.mgr.running = True
        self.mgr.handle = 7
        self.mgr.latest_frame.return_value = (object(), 1)
        self.window.on_recording_tick()
        self.assertTrue(self.window.btn_record_start.isEnabled())

    def test_start_submits_absolute_directory_and_selected_fps(self):
        self.window.spin_record_fps.setValue(90)
        self.window.on_record_start()
        options = self.mgr.start_recording.call_args.args[0]
        self.assertTrue(options.directory.is_absolute())
        self.assertEqual(options.fps, 90)

    def test_color_diagnostics_are_opt_in_and_locked_during_recording(self):
        self.window.on_record_start()
        self.assertFalse(self.mgr.start_recording.call_args.args[0].color_diagnostics)
        self.window.cbx_record_color_diagnostics.setChecked(True)
        self.window.on_record_start()
        self.assertTrue(self.mgr.start_recording.call_args.args[0].color_diagnostics)
        self.mgr.recording_status.return_value = RecordingStatus(state="RECORDING", native_open=True)
        self.window.on_recording_tick()
        self.assertFalse(self.window.cbx_record_color_diagnostics.isEnabled())

    def test_single_file_status_and_panel_copy(self):
        from PyQt5.QtWidgets import QLabel
        path = "D:/QRData/session/video.avi"
        self.mgr.recording_status.return_value = RecordingStatus(
            state="RECORDING", native_open=True, current_path=path,
            elapsed=120, pushed_frames=2, segment=1)
        self.window.on_recording_tick()
        text = self.window.lbl_record_status.text()
        self.assertIn("RECORDING", text)
        self.assertIn("120.0s", text)
        self.assertIn("2 frame", text)
        self.assertNotIn("đoạn", text)
        self.assertEqual(self.window.lbl_record_path.text(), path)
        labels = "\n".join(label.text() for label in
                           self.window.record_group.findChildren(QLabel))
        self.assertIn("một file AVI", labels)
        self.assertNotIn("chia đoạn dự kiến 1 GiB", labels)

    def test_invalid_user_path_is_reported_without_crashing_gui(self):
        self.window.edit_record_directory.setText("~no_such_recording_user_921")
        with patch.object(self.module.Path, "expanduser", side_effect=RuntimeError("unknown user")):
            self.window.on_record_start()
        self.assertIn("unknown user", self.window.lbl_record_status.text())
        self.mgr.start_recording.assert_not_called()

    def test_close_completion_rechecks_status_after_worker_exit(self):
        self.mgr.handle = None
        self.mgr.recording_status.side_effect = [
            RecordingStatus(state="STOPPING", native_open=True),
            RecordingStatus(state="COMPLETED")]
        self.window.ui.btn_camera_open.setEnabled(False)
        thread = Mock()
        thread.is_alive.return_value = False
        self.window._camera_close_thread = thread
        self.window.on_recording_tick()
        self.assertTrue(self.window.ui.btn_camera_open.isEnabled())

    def test_cancel_folder_selection_keeps_destination(self):
        before = self.window.edit_record_directory.text()
        with patch.object(self.module.QFileDialog, "getExistingDirectory", return_value=""):
            self.window.on_record_browse()
        self.assertEqual(self.window.edit_record_directory.text(), before)

    def test_recording_state_locks_configuration_and_restores_prior_enable_state(self):
        self.mgr.handle = 7
        self.mgr.running = True
        self.window.ui.frame_area.setEnabled(True)
        self.window.ui.cbx_ROI.setEnabled(False)
        self.mgr.recording_status.return_value = RecordingStatus(state="RECORDING", native_open=True)
        self.window.on_recording_tick()
        self.assertFalse(self.window.ui.frame_area.isEnabled())
        self.assertFalse(self.window.edit_record_directory.isEnabled())
        self.assertTrue(self.window.btn_record_stop.isEnabled())
        self.mgr.recording_status.return_value = RecordingStatus(state="COMPLETED")
        self.window.on_recording_tick()
        self.assertTrue(self.window.ui.frame_area.isEnabled())
        self.assertFalse(self.window.ui.cbx_ROI.isEnabled())

    def test_soft_trigger_remains_available_as_async_control_when_recording(self):
        self.mgr.handle = 7
        self.window.ui.frame_area.setEnabled(True)
        self.window.ui.btn_trigger_once.setEnabled(True)
        self.mgr.recording_status.return_value = RecordingStatus(state="RECORDING", native_open=True)
        self.window.on_recording_tick()
        self.assertTrue(self.window.btn_record_trigger.isEnabled())
        self.window.btn_record_trigger.click()
        self.mgr.soft_trigger.assert_called_once()

    def test_soft_trigger_available_while_waiting_for_first_recording_frame(self):
        self.mgr.handle = 7
        self.window.ui.frame_area.setEnabled(True)
        self.window.ui.btn_trigger_once.setEnabled(True)
        self.mgr.recording_status.return_value = RecordingStatus(state="STARTING")
        self.window.on_recording_tick()
        self.assertTrue(self.window.btn_record_trigger.isEnabled())

    def test_fps_timer_uses_cached_counters_while_recording(self):
        self.mgr.handle = 7
        self.mgr.recording_status.return_value = RecordingStatus(
            state="RECORDING", native_open=True, capture_count=12, capture_fps=20)
        self.window.on_fps_show()
        self.mgr.frame_statistic.assert_not_called()

    def test_error_is_persistent_outside_status_bar(self):
        self.mgr.recording_status.return_value = RecordingStatus(state="ERROR", error="disk failed")
        self.window.on_recording_tick()
        self.window.on_fps_show()
        self.assertIn("disk failed", self.window.lbl_record_status.text())

    def test_camera_close_is_nonblocking_and_does_not_claim_success_early(self):
        entered, release = threading.Event(), threading.Event()
        def close():
            entered.set()
            release.wait(5)
            self.mgr.handle = None
        self.mgr.close.side_effect = close
        self.mgr.handle = 7
        self.mgr.running = True
        self.mgr.recording_status.return_value = RecordingStatus(state="RECORDING", native_open=True)
        self.window.on_camera_close()
        self.assertTrue(entered.wait(1))
        self.addCleanup(release.set)
        self.assertFalse(self.window.ui.btn_camera_open.isEnabled())
        self.window.on_recording_tick()
        self.assertIsNotNone(self.window._camera_close_thread)
        release.set()
        self.window._camera_close_thread.join(2)
        self.mgr.recording_status.return_value = RecordingStatus(state="COMPLETED")
        self.window.on_recording_tick()
        self.assertIsNone(self.window._camera_close_thread)
        self.assertTrue(self.window.ui.btn_camera_open.isEnabled())


if __name__ == "__main__":
    unittest.main()
