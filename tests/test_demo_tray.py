"""Chạy nền ở khay hệ thống của bản demo (TrayController + nút Chạy nền); không cần camera.

Chạy (từ gốc repo):  python -m unittest tests.test_demo_tray
"""
from pathlib import Path
import sys
import unittest
import unittest.mock

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests import test_camera_diagnostics as fake  # noqa: E402
from tests.test_demo_conveyor import window_module  # noqa: E402  (MainWindow với fake SDK)
from PyQt5.QtWidgets import QDialog, QMainWindow, QSystemTrayIcon  # noqa: E402
from demo_ui.run_controller import RunState  # noqa: E402
from demo_ui.tray import TrayController  # noqa: E402


class FakeWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("QR test")
        self.settings_window = QDialog(self)
        self.on_primary_clicked = unittest.mock.Mock()


def _camera(frame=None):
    camera = unittest.mock.Mock(handle=None, camera_list=[])
    camera.latest_frame.return_value = (frame, 10 if frame is not None else 0)
    camera.list_cameras.return_value = []
    return camera


class TrayControllerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = fake.QApplication.instance() or fake.QApplication([])

    def setUp(self):
        self.window = FakeWindow()
        self.tray = TrayController(self.window)
        self.messages = unittest.mock.patch.object(self.tray.icon, "showMessage").start()
        self.addCleanup(unittest.mock.patch.stopall)
        self.addCleanup(self.tray.hide)
        self.addCleanup(self.window.close)

    def test_hide_window_hides_both_windows_and_shows_icon(self):
        self.window.show()
        self.window.settings_window.show()
        self.tray.hide_window()
        self.assertFalse(self.window.isVisible())
        self.assertFalse(self.window.settings_window.isVisible())
        self.assertTrue(self.tray.background)
        self.assertTrue(self.tray.icon.isVisible())
        self.assertEqual(self.messages.call_count, 1)

    def test_hint_only_shown_once(self):
        self.window.show()
        self.tray.hide_window()
        self.tray.restore()
        self.tray.hide_window()
        self.assertEqual(self.messages.call_count, 1)

    def test_restore_shows_window_and_hides_icon(self):
        self.window.show()
        self.tray.hide_window()
        self.tray.restore()
        self.assertTrue(self.window.isVisible())
        self.assertFalse(self.tray.icon.isVisible())
        self.assertFalse(self.tray.background)

    def test_restore_keeps_fullscreen(self):
        self.window.show()
        with unittest.mock.patch.object(self.window, "isFullScreen", return_value=True), \
                unittest.mock.patch.object(self.window, "showFullScreen") as full:
            self.tray.hide_window()
            self.tray.restore()
        full.assert_called_once()

    def test_click_on_icon_restores(self):
        self.window.show()
        self.tray.hide_window()
        self.tray._on_activated(QSystemTrayIcon.Trigger)
        self.assertTrue(self.window.isVisible())

    def test_primary_action_follows_state(self):
        self.assertEqual(self.tray.act_primary.text(), "Bắt đầu")
        self.tray.set_state(RunState.RUNNING)
        self.assertEqual(self.tray.act_primary.text(), "Dừng")
        self.tray.set_state(RunState.STOPPING)
        self.assertFalse(self.tray.act_primary.isEnabled())
        self.tray.set_state(RunState.IDLE)
        self.assertTrue(self.tray.act_primary.isEnabled())
        self.tray.act_primary.trigger()
        self.window.on_primary_clicked.assert_called_once()

    def test_tooltip_has_title_state_and_count(self):
        self.tray.set_state(RunState.RUNNING)
        self.tray.set_read_count(123)
        tooltip = self.tray.icon.toolTip()
        self.assertIn("QR test", tooltip)
        self.assertIn("Đang chạy", tooltip)
        self.assertIn("123", tooltip)
        self.assertLessEqual(len(tooltip), 127)

    def test_error_and_signal_lost_notify_only_in_background(self):
        self.tray.set_state(RunState.RUNNING)
        self.tray.set_signal_lost(True)
        self.tray.set_state(RunState.ERROR, "mất camera")
        self.messages.assert_not_called()           # cửa sổ đang hiện: không báo khay
        self.window.show()
        self.tray.hide_window()
        self.messages.reset_mock()
        self.tray.set_state(RunState.RUNNING)
        self.tray.set_signal_lost(True)
        self.tray.set_signal_lost(True)             # cùng sự kiện: báo một lần
        self.tray.set_state(RunState.ERROR, "mất camera")
        self.assertEqual(self.messages.call_count, 2)
        self.assertEqual(self.messages.call_args[0][1], "mất camera")

    def test_quit_closes_window(self):
        with unittest.mock.patch.object(self.window, "close") as close:
            self.tray.act_quit.trigger()
        close.assert_called_once()


class MainWindowTrayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = fake.QApplication.instance() or fake.QApplication([])

    def _window(self, tray, frame=None):
        window = window_module.MainWindow(camera=_camera(frame), tray=tray)
        self.addCleanup(window.close)
        return window

    def test_no_tray_hides_button(self):
        window = self._window(False)
        self.assertIsNone(window.tray)
        self.assertTrue(window.workspace.btn_background.isHidden())

    def test_tray_unavailable_falls_back_to_no_button(self):
        with unittest.mock.patch.object(window_module.TrayController, "available", return_value=False):
            window = self._window(True)
        self.assertIsNone(window.tray)
        self.assertTrue(window.workspace.btn_background.isHidden())

    def test_button_hides_to_tray(self):
        tray = unittest.mock.Mock()
        window = self._window(tray)
        self.assertFalse(window.workspace.btn_background.isHidden())
        window.workspace.btn_background.click()
        tray.hide_window.assert_called_once()

    def test_state_and_count_forwarded_to_tray(self):
        tray = unittest.mock.Mock()
        window = self._window(tray)
        window._on_run_state(window_module.RunState.ERROR, "lỗi")
        tray.set_state.assert_called_with(window_module.RunState.ERROR, "lỗi")
        tray.set_read_count.assert_called()

    def test_hidden_window_still_decodes_but_skips_drawing(self):
        frame = np.zeros((64, 64, 3), np.uint8)
        window = self._window(unittest.mock.Mock(), frame)
        window._decoding = True
        window.cbx_decode.setChecked(True)
        with unittest.mock.patch.object(window.worker, "submit", return_value=True) as submit, \
                unittest.mock.patch.object(window.ui.label_image, "setPixmap") as draw:
            window.on_display_tick()                 # chưa show(): như đang chạy nền
            submit.assert_called_once()
            draw.assert_not_called()
            window.show()
            window.on_display_tick()
            draw.assert_called_once()

    def test_close_hides_tray_icon(self):
        tray = unittest.mock.Mock()
        window = self._window(tray)
        window.close()
        tray.hide.assert_called_once()


if __name__ == "__main__":
    unittest.main()
