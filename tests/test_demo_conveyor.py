"""Panel băng chuyền và nhãn decode trong bản demo, với fake SDK; không cần camera.

Chạy (từ gốc repo):  python -m unittest tests.test_demo_conveyor
"""
import importlib
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
import unittest.mock

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests import test_camera_diagnostics as fake  # noqa: E402  (dựng fake mvsdk + import module)
from dataclasses import asdict  # noqa: E402

from demo_ui.app_settings import AppSettings, BaslerSettings  # noqa: E402
from demo_ui.scan_uploader import ScanUploader  # noqa: E402


class FrameSpeed:
    def __init__(self, name):
        self.name = name

    def GetDescription(self):
        return self.name


class SensorRange:
    iWidthMax = 2448
    iHeightMax = 2048


class ConveyorCapability(fake.Capability):
    iFrameSpeedDesc = 3
    pFrameSpeedDesc = [FrameSpeed("Low"), FrameSpeed("Normal"), FrameSpeed("High")]
    sResolutionRange = SensorRange()


class StructStub:
    pass


sdk = fake.sdk
sdk.tSdkImageResolution = StructStub
sdk.CameraSetFrameSpeed = fake._set("frame_speed", "FrameSpeed")
sdk.CameraGetFrameSpeed = fake._get("frame_speed")


def _set_resolution(camera, res, *args):
    camera.writes.append(("ImageResolution", res))
    camera.values["resolution"] = res
    sdk._last_error = 0
    return 0


def _get_resolution(camera):
    sdk._last_error = 0
    return camera.values["resolution"]


sdk.CameraSetImageResolution = _set_resolution
sdk.CameraGetImageResolution = _get_resolution


with unittest.mock.patch.dict(sys.modules, {"qr": fake.qr, "mvsdk": fake.sdk,
                                            "camera.camera_manager": fake.manager_module}):
    window_module = importlib.import_module("demo_ui.main_window")


class CameraInjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = fake.QApplication.instance() or fake.QApplication([])

    def test_window_uses_given_camera_and_settings_class(self):
        from demo_ui.app_settings import BaslerSettings
        camera = unittest.mock.Mock(handle=None, camera_list=[])
        camera.latest_frame.return_value = (None, 0)
        camera.list_cameras.return_value = []
        window = window_module.MainWindow(camera=camera, settings_cls=BaslerSettings)
        self.addCleanup(window.close)
        self.assertIs(window.mgr, camera)
        self.assertIs(window.controller._mgr, camera)
        self.assertEqual(window.spin_gain.value(), BaslerSettings().analog_gain)
        self.assertEqual(window.spin_band_w.value(), BaslerSettings().band_w)
        camera.init_sdk.assert_called_once()


class ConveyorUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = fake.QApplication.instance() or fake.QApplication([])

    def setUp(self):
        self.window = window_module.MainWindow()
        self.window.display_timer.stop()
        self.window.fps_timer.stop()
        self.window.worker.stop()
        self.cam = fake.FakeCamera()
        self.cam.values.update(frame_speed=1, resolution=None)
        mgr = self.window.mgr
        mgr._cam = mgr.handle = self.cam
        mgr.capability = ConveyorCapability()
        mgr.f_exp_line_time = 1.0

    def tearDown(self):
        self.window.mgr._cam = self.window.mgr.handle = None
        self.window.close()

    def res(self):
        r = self.cam.values["resolution"]
        return (r.iHOffsetFOV, r.iVOffsetFOV, r.iWidthFOV, r.iHeightFOV)

    def test_apply_sets_exposure_gain_and_turns_ae_off(self):
        self.window.spin_exposure.setValue(8.0)
        self.window.spin_gain.setValue(12)
        self.window.on_conveyor_apply()
        self.assertAlmostEqual(self.cam.values["exposure"], 8000.0, places=1)
        self.assertEqual(self.cam.values["analog_gain"], 12)
        self.assertIs(self.cam.values["ae"], False)
        self.assertEqual(self.cam.values["frame_speed"], 2)
        self.assertIn("gain 12", self.window.ui.status_bar.text())

    def test_gain_and_exposure_clamped_to_camera_limits(self):
        self.window.spin_gain.setValue(40)           # fake camera: tối đa 24
        self.window.spin_exposure.setValue(0.01)     # 10 µs = tối thiểu của fake camera
        self.window.mgr.capability.sExposeDesc.uiExposeTimeMin = 20
        self.addCleanup(setattr, self.window.mgr.capability.sExposeDesc, "uiExposeTimeMin", 10)
        self.window.on_conveyor_apply()
        self.assertEqual(self.cam.values["analog_gain"], 24)
        self.assertEqual(self.cam.values["exposure"], 20.0)

    def test_full_frame_without_bands_keeps_resolution(self):
        self.window.on_conveyor_apply()
        self.assertFalse(any(w[0] == "ImageResolution" for w in self.cam.writes))

    def test_y_band_only(self):
        self.window.cbx_conveyor_band.setChecked(True)
        self.window.spin_band_y.setValue(640)
        self.window.spin_band_h.setValue(768)
        self.window.on_conveyor_apply()
        self.assertEqual(self.res(), (0, 640, 2448, 768))

    def test_x_band_only(self):
        self.window.cbx_band_x.setChecked(True)
        self.window.spin_band_x.setValue(320)
        self.window.spin_band_w.setValue(1600)
        self.window.on_conveyor_apply()
        self.assertEqual(self.res(), (320, 0, 1600, 2048))

    def test_both_bands_aligned_to_sensor(self):
        self.window.cbx_conveyor_band.setChecked(True)
        self.window.spin_band_y.setValue(650)        # căn xuống bội 16
        self.window.spin_band_h.setValue(768)
        self.window.cbx_band_x.setChecked(True)
        self.window.spin_band_x.setValue(330)
        self.window.spin_band_w.setValue(1600)
        self.window.on_conveyor_apply()
        self.assertEqual(self.res(), (320, 640, 1600, 768))

    def test_turning_bands_off_returns_to_full_frame(self):
        self.window.mgr.get_resolution = lambda: (2448, 2048)   # preset giả không có iWidth/iHeight
        self.window.cbx_band_x.setChecked(True)
        self.window.on_conveyor_apply()
        self.window.cbx_band_x.setChecked(False)
        self.window.on_conveyor_apply()
        self.assertIsNone(self.window.mgr.sensor_band)
        self.assertIsInstance(self.cam.values["resolution"], fake.Resolution)

    def test_apply_error_stays_visible_after_fps_refresh(self):
        self.cam.fail_writes = True
        self.window.on_conveyor_apply()
        self.cam.fail_writes = False
        self.window.on_fps_show()
        self.assertIn("LỖI", self.window.ui.status_bar.text())
        self.window.on_conveyor_apply()
        self.window.on_fps_show()
        self.assertNotIn("LỖI", self.window.ui.status_bar.text())

    def test_label_reports_exposure_and_gain(self):
        self.cam.values.update(exposure=12_900.0, analog_gain=40)
        self.window.on_fps_show()
        self.assertIn("Exposure 12.90 ms", self.window.lbl_conveyor.text())
        self.assertIn("gain 40", self.window.lbl_conveyor.text())


class DecodeStatsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = fake.QApplication.instance() or fake.QApplication([])

    def setUp(self):
        self.window = window_module.MainWindow()
        self.window.display_timer.stop()
        self.window.fps_timer.stop()
        self.window.worker.stop()

    def tearDown(self):
        self.window.close()

    def test_processing_footer_follows_device_fallback(self):
        self.window.pipeline.device = "cuda:0"
        self.window.on_decode_stats({"detect_ms": 50.0, "cascade_ms": 5.0, "skipped": 0})
        self.assertIn("GPU", self.window.workspace.lbl_processing.text())
        self.window.pipeline.device = "cpu"          # CUDA lỗi → detector tự chuyển CPU
        self.window.on_decode_stats({"detect_ms": 500.0, "cascade_ms": 5.0, "skipped": 0})
        self.assertIn("CPU", self.window.workspace.lbl_processing.text())

    def test_display_tick_submits_frame_with_seq(self):
        frame = np.zeros((48, 64, 3), np.uint8)
        self.window._decoding = True
        with unittest.mock.patch.object(self.window.mgr, "latest_frame", return_value=(frame, 10)), \
                unittest.mock.patch.object(self.window.worker, "submit", return_value=True) as submit:
            self.window.on_display_tick()
        submit.assert_called_once_with(frame, 10)

    def _tick_at_seq(self, seq):
        frame = np.zeros((48, 64, 3), np.uint8)
        with unittest.mock.patch.object(self.window.mgr, "latest_frame", return_value=(frame, seq)),                 unittest.mock.patch.object(self.window.worker, "submit", return_value=True) as submit:
            self.window.on_display_tick()
        return submit

    def test_spin_n_decides_frames_between_decodes(self):
        self.window._decoding = True
        self.window.spin_n.setValue(8)
        self._tick_at_seq(7).assert_not_called()
        self._tick_at_seq(8).assert_called_once()
        self._tick_at_seq(15).assert_not_called()
        self._tick_at_seq(16).assert_called_once()

    def test_spin_n_change_applies_while_running(self):
        self.window._decoding = True
        self.window.spin_n.setValue(20)
        self._tick_at_seq(10).assert_not_called()
        self.window.spin_n.setValue(10)
        self._tick_at_seq(11).assert_called_once()

    def test_decode_switch_stops_submitting_and_clears_quads(self):
        frame = np.zeros((48, 64, 3), np.uint8)
        self.window._decoding = True
        self.window._overlays = ["cũ"]
        self.window.cbx_decode.setChecked(False)
        self.assertEqual(self.window._overlays, [])
        with unittest.mock.patch.object(self.window.mgr, "latest_frame", return_value=(frame, 10)), \
                unittest.mock.patch.object(self.window.worker, "submit", return_value=True) as submit:
            self.window.on_display_tick()
        submit.assert_not_called()


class DecodeEveryNSettingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = fake.QApplication.instance() or fake.QApplication([])

    def make(self, **saved):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "settings.json"
        self.path.write_text(json.dumps(saved), encoding="utf-8")
        window = window_module.MainWindow(settings_path=self.path, uploader=unittest.mock.Mock())
        window.display_timer.stop()
        window.fps_timer.stop()
        window.worker.stop()
        self.addCleanup(window.close)
        return window

    def test_saved_value_is_shown_and_change_is_saved(self):
        window = self.make(decode_every_n=9)
        self.assertEqual(window.spin_n.value(), 9)
        window.spin_n.setValue(3)
        self.assertTrue(window._settings_timer.isActive())
        window._save_settings()
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8"))["decode_every_n"], 3)


class UploadSwitchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = fake.QApplication.instance() or fake.QApplication([])

    def make(self, **saved):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "settings.json"
        self.path.write_text(json.dumps(saved), encoding="utf-8")
        self.sent = []
        self.uploader = ScanUploader(send=self.sent.append, base_url="https://example.test",
                                     autostart=False)
        window = window_module.MainWindow(settings_path=self.path, uploader=self.uploader)
        window.display_timer.stop()
        window.fps_timer.stop()
        window.worker.stop()
        self.addCleanup(window.close)
        return window

    def read(self, window, text):
        with unittest.mock.patch.object(window.stats, "on_reads", return_value=[]):
            window.on_reads_done([types.SimpleNamespace(text=text)])
        self.uploader.drain()

    def test_on_by_default_sends_read_code(self):
        window = self.make()
        self.assertTrue(window.cbx_upload.isChecked())
        self.read(window, "A")
        self.assertEqual(self.sent, ["https://example.test/A"])

    def test_saved_off_shows_unchecked_and_sends_nothing(self):
        window = self.make(upload_enabled=False)
        self.assertFalse(window.cbx_upload.isChecked())
        self.read(window, "A")
        self.assertEqual(self.sent, [])

    def test_toggle_applies_immediately_and_is_saved(self):
        window = self.make()
        window.cbx_upload.setChecked(False)
        self.assertTrue(window._settings_timer.isActive())
        self.read(window, "A")
        self.assertEqual(self.sent, [])
        window._save_settings()
        self.assertFalse(json.loads(self.path.read_text(encoding="utf-8"))["upload_enabled"])
        window.cbx_upload.setChecked(True)
        self.read(window, "B")
        self.assertEqual(self.sent, ["https://example.test/B"])

    def test_saved_off_can_be_turned_on_without_restart(self):
        with unittest.mock.patch.object(window_module, "ScanUploader") as uploader_cls:
            window = window_module.MainWindow(settings_path=self._saved_off())
            window.display_timer.stop()
            window.fps_timer.stop()
            window.worker.stop()
            self.addCleanup(window.close)
        uploader_cls.assert_called_once()
        uploader_cls.return_value.set_enabled.assert_called_with(False)
        window.cbx_upload.setChecked(True)
        uploader_cls.return_value.set_enabled.assert_called_with(True)

    def _saved_off(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "settings.json"
        path.write_text(json.dumps({"upload_enabled": False}), encoding="utf-8")
        return path


class GpuSwitchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = fake.QApplication.instance() or fake.QApplication([])

    def make(self, gpu_available=True, **saved):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "settings.json"
        self.path.write_text(json.dumps(saved), encoding="utf-8")
        self.pipeline_cls = unittest.mock.Mock()
        self.pipeline_cls.return_value.gpu_available = gpu_available
        with unittest.mock.patch.object(window_module, "ImprovePipeline", self.pipeline_cls):
            window = window_module.MainWindow(settings_path=self.path, uploader=unittest.mock.Mock())
        window.display_timer.stop()
        window.fps_timer.stop()
        window.worker.stop()
        self.addCleanup(window.close)
        return window

    def test_saved_choice_decides_startup_device(self):
        self.assertTrue(self.make().cbx_gpu.isChecked())
        self.pipeline_cls.assert_called_once_with(device="auto")
        self.assertFalse(self.make(use_gpu=False).cbx_gpu.isChecked())
        self.pipeline_cls.assert_called_once_with(device="cpu")

    def test_toggle_switches_device_and_is_saved(self):
        window = self.make()
        window.cbx_gpu.setChecked(False)
        window.pipeline.set_device.assert_called_once_with("cpu")
        window._save_settings()
        self.assertFalse(json.loads(self.path.read_text(encoding="utf-8"))["use_gpu"])
        window.cbx_gpu.setChecked(True)
        window.pipeline.set_device.assert_called_with("auto")

    def test_without_cuda_switch_is_disabled_and_saved_choice_kept(self):
        window = self.make(gpu_available=False)
        self.assertFalse(window.cbx_gpu.isEnabled())
        self.assertFalse(window.cbx_gpu.isChecked())
        window.pipeline.set_device.assert_not_called()
        window._save_settings()
        self.assertTrue(json.loads(self.path.read_text(encoding="utf-8"))["use_gpu"])


class BaseWorkerReadsTests(unittest.TestCase):
    """DecodeWorker của ui/ phát ``reads`` cho lượt vừa đọc chắc."""

    def test_first_reads_are_emitted(self):
        worker = fake.window_module.DecodeWorker(unittest.mock.Mock())
        worker.stop()
        got = []
        worker.reads.connect(got.append)
        first = [types.SimpleNamespace(text="A", track_id=1, observations=3, conflicting=False)]
        worker._reader = unittest.mock.Mock()
        worker._reader.process.return_value = types.SimpleNamespace(
            results=["A"], overlays=[], detect_ms=1.0, cascade_ms=1.0, skipped=0, first_reads=first, finished=[])
        worker._process(object(), 1)
        self.assertEqual(got, [first])
        worker._reader.process.return_value.first_reads = []
        worker._process(object(), 2)
        self.assertEqual(len(got), 1)


class LegacySettingsTests(unittest.TestCase):
    def test_old_keyboard_and_url_fields_are_ignored(self):
        s = AppSettings.from_dict({"keyboard_output_enabled": True,
                                   "upload_base_url": "https://old.example", "decode_every_n": 7})
        self.assertEqual(s.decode_every_n, 7)
        self.assertNotIn("keyboard_output_enabled", asdict(s))


if __name__ == "__main__":
    unittest.main()
