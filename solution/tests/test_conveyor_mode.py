"""Chế độ băng chuyền: công thức exposure + CameraManager/UI với fake SDK; không cần camera.

Chạy (từ solution/):  python -m unittest tests.test_conveyor_mode
"""
from pathlib import Path
import sys
import types
import unittest
import unittest.mock

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests import test_camera_diagnostics as fake  # noqa: E402  (dựng fake mvsdk + import module)
from camera.conveyor import (ConveyorSettings, align_band, blur_px,  # noqa: E402
                             max_exposure_us, px_per_module)


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


class FormulaTests(unittest.TestCase):
    def test_exposure_limits_motion_blur(self):
        self.assertAlmostEqual(max_exposure_us(300, 0.43, 1.0), 1433.3, places=1)
        self.assertAlmostEqual(max_exposure_us(100, 0.43, 1.0), 4300.0, places=1)
        self.assertAlmostEqual(blur_px(300, 0.43, max_exposure_us(300, 0.43, 2.0)), 2.0)
        # exposure 20 ms ở 30 cm/s → vệt mờ ~14 px (giải thích video băng chạy hiện tại)
        self.assertAlmostEqual(blur_px(300, 0.43, 20_000), 13.95, places=2)

    def test_px_per_module(self):
        self.assertAlmostEqual(px_per_module(0.43), 2.77, places=2)

    def test_band_is_aligned_and_clamped(self):
        self.assertEqual(align_band(641, 770, 2048), (640, 768))
        self.assertEqual(align_band(1900, 768, 2048), (1280, 768))
        self.assertEqual(align_band(0, 5000, 2048), (0, 2048))


class ConveyorModeTests(unittest.TestCase):
    def setUp(self):
        self.mgr = fake.CameraManager()
        self.cam = fake.FakeCamera()
        self.cam.values.update(frame_speed=1, resolution=None)
        self.mgr._cam = self.mgr.handle = self.cam
        self.mgr.capability = ConveyorCapability()
        self.mgr.f_exp_line_time = 10.0

    def test_apply_turns_ae_off_and_sets_short_exposure_and_fast_frame_speed(self):
        applied = self.mgr.apply_conveyor_mode(ConveyorSettings(speed_mm_s=300, mm_per_px=0.43))
        self.assertTrue(applied["ok"])
        self.assertIs(self.cam.values["ae"], False)
        self.assertAlmostEqual(self.cam.values["exposure"], 1433.33, places=1)
        self.assertEqual(self.cam.values["frame_speed"], 2)
        labels = [w[0] for w in self.cam.writes]
        self.assertLess(labels.index("AeState"), labels.index("ExposureTime"))
        self.assertNotIn("ImageResolution", labels)

    def test_exposure_is_clamped_to_camera_minimum(self):
        # min = uiExposeTimeMin (10) × line time (10 µs) = 100 µs
        self.mgr.apply_conveyor_mode(ConveyorSettings(speed_mm_s=300, mm_per_px=0.01))
        self.assertEqual(self.cam.values["exposure"], 100.0)

    def test_band_sets_custom_full_width_roi(self):
        applied = self.mgr.apply_conveyor_mode(ConveyorSettings(band=(641, 770)))
        res = self.cam.values["resolution"]
        self.assertEqual((res.iIndex, res.iHOffsetFOV, res.iVOffsetFOV), (0xFF, 0, 640))
        self.assertEqual((res.iWidth, res.iHeight, res.iWidthFOV, res.iHeightFOV), (2448, 768, 2448, 768))
        self.assertEqual(applied["band"], (640, 768))
        self.assertEqual(applied["resolution"], (2448, 768))

    def test_refused_while_recording(self):
        self.mgr._closing = True
        self.assertIsNone(self.mgr.apply_conveyor_mode(ConveyorSettings()))
        self.assertEqual(self.cam.writes, [])


class ConveyorUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = fake.QApplication.instance() or fake.QApplication([])

    def setUp(self):
        self.window = fake.window_module.MainWindow()
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

    def test_apply_button_uses_selected_speed(self):
        self.window.cbx_conveyor_speed.setCurrentIndex(0)   # 10 cm/s
        self.window.spin_mm_per_px.setValue(0.5)
        self.window.on_conveyor_apply()
        self.assertAlmostEqual(self.cam.values["exposure"], 5000.0, places=1)
        self.assertIs(self.cam.values["ae"], False)
        self.assertIn("Băng chuyền", self.window.ui.status_bar.text())

    def test_label_reports_estimated_blur(self):
        self.cam.values.update(exposure=20_000.0, ae=True)
        self.window.spin_mm_per_px.setValue(0.43)
        self.window._update_conveyor_label()
        self.assertIn("mờ ước tính 14.0 px", self.window.lbl_conveyor.text())
        self.assertIn("AE", self.window.lbl_conveyor.text())

    def test_ae_values_shown_in_manual_widgets_without_writing_back(self):
        self.window.ui_init_param()
        self.cam.writes.clear()
        self.cam.values.update(exposure=101_470.0, ae=True, analog_gain=17)
        self.window._update_conveyor_label()
        self.assertEqual(self.window.ui.ae_manual_time_ledit.text(), "101.47")
        self.assertEqual(self.window.ui.ae_manual_time_hSlider.value(), 101_470)
        self.assertEqual(self.window.ui.ae_manual_gain_spinbox.value(), 17)
        self.assertEqual(self.window.ui.ae_manual_gain_hSlider.value(), 17)
        self.assertEqual(self.cam.writes, [])

    def test_manual_mode_and_busy_sdk_do_not_touch_widgets(self):
        self.window.ui_init_param()
        before = self.window.ui.ae_manual_time_ledit.text()
        self.cam.values.update(exposure=5_000.0, ae=False)
        self.window._update_conveyor_label()
        self.cam.values.update(exposure=7_000.0, ae=True)
        self.window._update_conveyor_label(sdk_busy=True)
        self.assertEqual(self.window.ui.ae_manual_time_ledit.text(), before)


class LatestQrLabelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = fake.QApplication.instance() or fake.QApplication([])

    def setUp(self):
        self.window = fake.window_module.MainWindow()
        self.window.display_timer.stop()
        self.window.fps_timer.stop()
        self.window.worker.stop()

    def tearDown(self):
        self.window.close()

    def test_latest_qr_shows_clock_age_and_count(self):
        clock = fake.window_module.time
        now = [100.0]
        with unittest.mock.patch.object(clock, "strftime", return_value="16:02:11"), \
                unittest.mock.patch.object(clock, "monotonic", side_effect=lambda: now[0]):
            self.window.on_decode_done(["000000585546"], [])
            self.assertIn("000000585546 — 16:02:11 (vừa xong)", self.window.lbl_latest.text())
            now[0] = 101.0
            self.window.on_decode_done(["000000585546"], [])
            now[0] = 113.0
            self.window._render_latest_qr()
        self.assertIn("(x2) — 16:02:11 (12 s trước)", self.window.lbl_latest.text())
        self.assertEqual(self.window.lst_history.count(), 1)
        self.assertEqual(self.window.lst_history.item(0).text(), "16:02:11  000000585546")

    def test_failed_decode_keeps_last_result_with_its_age(self):
        self.window.on_decode_done(["A"], [])
        self.window.on_decode_done([], [])
        self.assertIn("QR mới nhất: A — ", self.window.lbl_latest.text())
        self.assertEqual(self.window._latest_qr_hits, 0)

    def test_stats_label_shows_device_and_stage_timings(self):
        self.window.on_decode_done(["A"], [])
        self.window.on_decode_stats({"detect_ms": 61.4, "cascade_ms": 32.0, "skipped": 1})
        self.assertEqual(self.window.lbl_stat.text(),
                         "Decode: 1 lần · CPU · detect 61 ms · cascade 32 ms · bỏ qua 1")
        self.window.on_decode_stats({"detect_ms": 70.0, "cascade_ms": 5.0, "skipped": 0})
        self.assertEqual(self.window.lbl_stat.text(), "Decode: 1 lần · CPU · detect 70 ms · cascade 5 ms")

    def test_stats_label_follows_device_fallback(self):
        self.window.pipeline.device = "cuda:0"
        self.window.on_decode_stats({"detect_ms": 50.0, "cascade_ms": 5.0, "skipped": 0})
        self.assertIn(" · GPU · ", self.window.lbl_stat.text())
        self.window.pipeline.device = "cpu"          # CUDA lỗi → detector tự chuyển CPU
        self.window.on_decode_stats({"detect_ms": 500.0, "cascade_ms": 5.0, "skipped": 0})
        self.assertIn(" · CPU · ", self.window.lbl_stat.text())

    def test_pass_counter_counts_read_and_conflicting(self):
        self.assertEqual(self.window.lbl_passes.text(), "Lượt QR: 0/0 đọc được · mâu thuẫn 0")
        T = types.SimpleNamespace
        self.window.on_passes_done([T(text="A", conflicting=False), T(text=None, conflicting=False),
                                    T(text="B", conflicting=True)])
        self.assertEqual(self.window.lbl_passes.text(), "Lượt QR: 2/3 đọc được · mâu thuẫn 1")

    def test_display_tick_submits_frame_with_seq(self):
        frame = np.zeros((48, 64, 3), np.uint8)
        self.window.cbx_decode.setChecked(True)
        self.window.spin_n.setValue(1)
        with unittest.mock.patch.object(self.window.mgr, "latest_frame", return_value=(frame, 10)), \
                unittest.mock.patch.object(self.window.worker, "submit", return_value=True) as submit:
            self.window.on_display_tick()
        submit.assert_called_once_with(frame, 10)


if __name__ == "__main__":
    unittest.main()
