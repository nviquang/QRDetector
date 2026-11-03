"""RunController — máy trạng thái Bắt đầu/Dừng với CameraManager giả, không cần camera.

Chạy (từ solution/):  python -m unittest tests.test_run_controller
"""
import os
from pathlib import Path
import sys
import threading
import time
import types
import unittest
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from camera.conveyor import RunSettings  # noqa: E402
from PyQt5.QtCore import QObject, pyqtSignal  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402
from demo_ui.run_controller import RunController, RunState, StartError, StartRequest, pick_camera  # noqa: E402


def device(serial):
    return types.SimpleNamespace(GetSn=lambda: serial)


class FakeWorker(QObject):
    ready = pyqtSignal()

    def __init__(self, is_ready=True):
        super().__init__()
        self.is_ready = is_ready


def make_mgr(devices=("SN1",), handle=None):
    mgr = Mock()
    mgr.handle = handle
    mgr.list_cameras.return_value = [device(s) for s in devices]

    def open_camera(index):
        mgr.handle = 7
        return True
    mgr.open.side_effect = open_camera
    mgr.apply_run_settings.return_value = {"ok": True}
    return mgr


class PickCameraTests(unittest.TestCase):
    def test_saved_serial_wins(self):
        self.assertEqual(pick_camera([device("A"), device("B")], "B"), 1)

    def test_single_camera_used_when_nothing_saved(self):
        self.assertEqual(pick_camera([device("A")], ""), 0)

    def test_no_camera(self):
        with self.assertRaisesRegex(StartError, "Không tìm thấy camera"):
            pick_camera([], "")

    def test_several_cameras_without_choice(self):
        with self.assertRaisesRegex(StartError, "chưa chọn"):
            pick_camera([device("A"), device("B")], "")

    def test_saved_camera_missing(self):
        with self.assertRaisesRegex(StartError, "ZZ"):
            pick_camera([device("A")], "ZZ")


class RunControllerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def build(self, mgr, worker=None):
        self.worker = worker or FakeWorker()
        controller = RunController(mgr, self.worker)
        self.states, self.configured, self.cancelled, self.chosen = [], [], [], []
        controller.state_changed.connect(lambda s, m: self.states.append((s, m)))
        controller.configured.connect(lambda: self.configured.append(True))
        controller.cancelled.connect(lambda: self.cancelled.append(True))
        controller.camera_chosen.connect(self.chosen.append)
        return controller

    def request(self, serial=""):
        return StartRequest(serial, RunSettings(exposure_us=12_900.0, analog_gain=40))

    def wait(self, controller, *states):
        deadline = time.monotonic() + 3
        while controller.state not in states and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.005)
        self.assertIn(controller.state, states)

    def wait_for(self, values):
        deadline = time.monotonic() + 3
        while not values and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.005)

    def test_start_never_loads_a_camera_param(self):
        # Param A lưu gain thấp: nạp ngay sau khi mở làm ảnh tối đi khoảng 3 lần và không đọc được QR.
        mgr = make_mgr()
        controller = self.build(mgr)
        controller.start(self.request())
        self.wait(controller, RunState.RUNNING)
        mgr.load_param.assert_not_called()

    def test_success_runs_steps_in_order_and_reaches_running(self):
        mgr = make_mgr()
        controller = self.build(mgr)
        self.assertTrue(controller.start(self.request()))
        self.wait(controller, RunState.RUNNING)
        names = [c[0] for c in mgr.method_calls]
        order = [names.index(n) for n in ("list_cameras", "open", "set_trigger_mode", "apply_run_settings")]
        self.assertEqual(order, sorted(order))
        mgr.set_trigger_mode.assert_called_once_with(0)
        self.assertEqual(mgr.apply_run_settings.call_args.args[0].analog_gain, 40)
        self.assertEqual(self.configured, [True])
        self.assertEqual(self.chosen, ["SN1"])

    def test_open_failure_reports_error_and_can_retry(self):
        mgr = make_mgr()
        mgr.open.side_effect = lambda i: False
        controller = self.build(mgr)
        controller.start(self.request())
        self.wait(controller, RunState.ERROR)
        self.assertIn("Không mở được camera", self.states[-1][1])
        self.assertEqual(self.configured, [])
        self.assertTrue(controller.start(self.request()))
        self.wait(controller, RunState.ERROR)

    def test_apply_failure_names_the_step(self):
        mgr = make_mgr()
        mgr.apply_run_settings.return_value = {"ok": False}
        controller = self.build(mgr)
        controller.start(self.request())
        self.wait(controller, RunState.ERROR)
        self.assertIn("cấu hình camera", self.states[-1][1])

    def test_locked_camera_reports_error(self):
        mgr = make_mgr()
        mgr.apply_run_settings.return_value = None
        controller = self.build(mgr)
        controller.start(self.request())
        self.wait(controller, RunState.ERROR)

    def test_unexpected_exception_becomes_error_state(self):
        mgr = make_mgr()
        mgr.list_cameras.side_effect = RuntimeError("sdk")
        controller = self.build(mgr)
        with self.assertLogs("solution.ui.run", level="ERROR"):
            controller.start(self.request())
            self.wait(controller, RunState.ERROR)

    def test_start_from_tuning_keeps_open_camera(self):
        mgr = make_mgr(handle=7)
        controller = self.build(mgr)
        controller.enter_tuning()
        self.assertEqual(controller.state, RunState.TUNING)
        controller.start(self.request())
        self.wait(controller, RunState.RUNNING)
        mgr.open.assert_not_called()
        mgr.list_cameras.assert_not_called()
        mgr.set_trigger_mode.assert_called_once_with(0)
        mgr.apply_run_settings.assert_called_once()

    def test_waits_for_warmup_before_running(self):
        worker = FakeWorker(is_ready=False)
        controller = self.build(make_mgr(), worker)
        controller.start(self.request())
        self.wait_for(self.configured)
        self.assertEqual(controller.state, RunState.CONNECTING)
        worker.is_ready = True
        worker.ready.emit()
        self.app.processEvents()
        self.assertEqual(controller.state, RunState.RUNNING)

    def test_cancel_during_connect_finishes_current_step_then_stops(self):
        mgr = make_mgr()
        entered, release = threading.Event(), threading.Event()

        def slow_open(index):
            entered.set()
            release.wait(3)
            mgr.handle = 7
            return True
        mgr.open.side_effect = slow_open
        controller = self.build(mgr)
        controller.start(self.request())
        self.assertTrue(entered.wait(2))
        controller.cancel()
        self.assertEqual(controller.state, RunState.STOPPING)
        release.set()
        self.wait_for(self.cancelled)
        self.assertEqual(self.cancelled, [True])
        mgr.apply_run_settings.assert_not_called()
        self.assertEqual(self.configured, [])

    def test_cancel_while_waiting_for_warmup_is_immediate(self):
        controller = self.build(make_mgr(), FakeWorker(is_ready=False))
        controller.start(self.request())
        self.wait_for(self.configured)
        controller.cancel()
        self.assertEqual(self.cancelled, [True])

    def test_stop_and_close_outcomes(self):
        controller = self.build(make_mgr(handle=7))
        controller.start(self.request())
        self.wait(controller, RunState.RUNNING)
        self.assertFalse(controller.start(self.request()))   # đang chạy thì không start lại
        controller.begin_stop()
        self.assertEqual(controller.state, RunState.STOPPING)
        controller.on_close_failed("treo")
        self.assertEqual(controller.state, RunState.ERROR)
        self.assertTrue(controller.close_failed)
        controller.begin_stop()
        controller.on_camera_closed()
        self.assertEqual(controller.state, RunState.IDLE)
        self.assertFalse(controller.close_failed)


if __name__ == "__main__":
    unittest.main()
