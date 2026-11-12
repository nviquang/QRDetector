"""Gõ mã vào ô đang chọn có ở mọi app: app test camera (main.py), demo (main_demo.py), hai camera (main_dual.py).

Bản Basler (main_basler.py) được kiểm trong tests/test_demo_conveyor.py (KeyboardSwitchTests).
Chạy (từ gốc repo):  python -m unittest tests.test_keyboard_apps
"""
import json
from pathlib import Path
import tempfile
import types
import unittest
import unittest.mock

from tests import test_camera_diagnostics as fake  # noqa: E402  (dựng fake mvsdk, nạp QApplication)
from tests import test_demo_conveyor as demo  # noqa: E402
from tests import test_dual_app as dual  # noqa: E402
from tests.test_keyboard_output import FakeBackend  # noqa: E402
from demo_ui.app_settings import AppSettings, DualSettings  # noqa: E402
from ui.keyboard_output import KeyboardTyper  # noqa: E402


def make_typer():
    backend = FakeBackend()
    return backend, KeyboardTyper(backend=backend, own_pid=1, enter_delay_s=0, autostart=False)


def track(text, track_id=1):
    return types.SimpleNamespace(text=text, track_id=track_id, observations=3, conflicting=False)


class TestAppKeyboardTests(unittest.TestCase):
    """main.py: ô tích trong panel Kết quả QR, mặc định tắt, không lưu."""

    @classmethod
    def setUpClass(cls):
        cls.app = fake.QApplication.instance() or fake.QApplication([])

    def make(self, with_typer=True):
        self.backend, self.typer = make_typer()
        window = fake.window_module.MainWindow(keyboard_typer=self.typer if with_typer else None)
        window.display_timer.stop()
        window.fps_timer.stop()
        window.worker.stop()
        self.addCleanup(window.close)
        return window

    def test_without_typer_has_no_switch(self):
        window = self.make(with_typer=False)
        self.assertIsNone(window.cbx_keyboard)
        window.on_reads_done([track("A")])
        self.assertEqual(self.backend.events, [])

    def test_off_by_default_then_types_after_switching_on(self):
        window = self.make()
        self.assertFalse(window.cbx_keyboard.isChecked())
        window.on_reads_done([track("A")])
        self.typer.drain()
        self.assertEqual(self.backend.events, [])
        window.cbx_keyboard.setChecked(True)
        window.on_reads_done([track("B")])
        self.typer.drain()
        self.assertEqual(self.backend.events, [("text", "B"), ("enter",)])
        self.assertIn("B", window.ui.status_bar.text())

    def test_closing_stops_typer(self):
        window = self.make()
        window.cbx_keyboard.setChecked(True)
        window.close()
        self.assertFalse(self.typer.submit("A"))


class BaseWorkerReadsTests(unittest.TestCase):
    """DecodeWorker của ui/ phát ``reads`` cho lượt vừa đọc chắc, để app test camera biết khi nào gõ."""

    def test_first_reads_are_emitted(self):
        worker = fake.window_module.DecodeWorker(unittest.mock.Mock())
        worker.stop()
        got = []
        worker.reads.connect(got.append)
        first = [track("A")]
        worker._reader = unittest.mock.Mock()
        worker._reader.process.return_value = types.SimpleNamespace(
            results=["A"], overlays=[], detect_ms=1.0, cascade_ms=1.0, skipped=0, first_reads=first, finished=[])
        worker._process(object(), 1)
        self.assertEqual(got, [first])
        worker._reader.process.return_value.first_reads = []
        worker._process(object(), 2)
        self.assertEqual(len(got), 1)


class DemoKeyboardTests(unittest.TestCase):
    """main_demo.py: cấu hình MindVision (AppSettings) cũng lưu được lựa chọn."""

    @classmethod
    def setUpClass(cls):
        cls.app = fake.QApplication.instance() or fake.QApplication([])

    def test_app_settings_keep_keyboard_choice(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "app_settings.json"
        path.write_text(json.dumps({"keyboard_output_enabled": True}), encoding="utf-8")
        backend, typer = make_typer()
        window = demo.window_module.MainWindow(settings_path=path, uploader=unittest.mock.Mock(),
                                               settings_cls=AppSettings, keyboard_typer=typer)
        window.display_timer.stop()
        window.fps_timer.stop()
        window.worker.stop()
        self.addCleanup(window.close)
        self.assertTrue(window.cbx_keyboard.isChecked())
        with unittest.mock.patch.object(window.stats, "on_reads", return_value=[]):
            window.on_reads_done([track("A")])
        typer.drain()
        self.assertEqual(backend.events, [("text", "A"), ("enter",)])
        window.cbx_keyboard.setChecked(False)
        window._save_settings()
        self.assertFalse(json.loads(path.read_text(encoding="utf-8"))["keyboard_output_enabled"])
        self.assertFalse(AppSettings().keyboard_output_enabled)


class DualKeyboardTests(unittest.TestCase):
    """main_dual.py: một ô dùng chung hai camera, lưu ở bản ghi ``a``; cùng mã ở A và B chỉ gõ một lần."""

    @classmethod
    def setUpClass(cls):
        cls.app = fake.QApplication.instance() or fake.QApplication([])

    def make(self, with_typer=True, path=None):
        self.backend, self.typer = make_typer()
        self.a, self.b = dual.FakeManager("A1", 1), dual.FakeManager("B1", 2)
        self.window = dual.window_module.DualWindow(
            settings_path=path, uploader=dual.FakeUploader(), cameras=(self.a, self.b), pipeline=dual.FakePipeline(),
            keyboard_typer=self.typer if with_typer else None)
        self.addCleanup(self.shutdown)
        return self.window

    def shutdown(self):
        self.window.close()
        dual.wait_for(lambda: not self.window._camera_busy(), self.app)
        self.window.close()
        self.app.processEvents()

    def read(self, cam, text):
        self.window.on_reads_done(cam, [track(text, track_id=cam + 1)])
        self.typer.drain()

    def test_without_typer_has_no_switch(self):
        window = self.make(with_typer=False)
        self.assertIsNone(window.cbx_keyboard)
        window.on_reads_done(0, [track("A")])

    def test_same_code_from_both_cameras_typed_once(self):
        window = self.make()
        self.assertFalse(window.cbx_keyboard.isChecked())
        self.read(0, "A")
        self.assertEqual(self.backend.events, [])
        window.cbx_keyboard.setChecked(True)
        self.read(0, "A")
        self.read(1, "A")
        self.read(1, "B")
        self.assertEqual(self.backend.events, [("text", "A"), ("enter",), ("text", "B"), ("enter",)])
        self.assertIn("B", window.workspace.lbl_keyboard.text())

    def test_choice_saved_in_common_record(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "dual_settings.json"
        window = self.make(path=path)
        window.cbx_keyboard.setChecked(True)
        window._save_settings()
        self.assertTrue(DualSettings.load(path).a.keyboard_output_enabled)

    def test_closing_stops_typer(self):
        window = self.make()
        window.cbx_keyboard.setChecked(True)
        self.shutdown()
        self.assertFalse(self.typer.submit("A"))


if __name__ == "__main__":
    unittest.main()
