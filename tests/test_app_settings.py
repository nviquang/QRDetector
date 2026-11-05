"""AppSettings — đọc/ghi JSON cấu hình, không cần Qt/camera.

Chạy (từ gốc repo):  python -m unittest tests.test_app_settings
"""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from demo_ui.app_settings import AppSettings  # noqa: E402


class AppSettingsTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "config" / "app_settings.json"

    def test_missing_file_gives_defaults_silently(self):
        self.assertEqual(AppSettings.load(self.path), AppSettings())

    def test_round_trip_creates_directory(self):
        settings = AppSettings(camera_serial="SN1", exposure_ms=8.5, analog_gain=20, decode_enabled=False,
                               band_enabled=True, band_x_enabled=True, band_x=32, band_w=64)
        settings.save(self.path)
        self.assertEqual(AppSettings.load(self.path), settings)

    def test_corrupt_file_warns_and_gives_defaults(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text("{hỏng", encoding="utf-8")
        with self.assertLogs("solution.settings", level="WARNING"):
            self.assertEqual(AppSettings.load(self.path), AppSettings())

    def test_invalid_field_falls_back_only_for_that_field(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text(json.dumps({"analog_gain": -1, "exposure_ms": 5.0, "draw_quad": "x",
                                         "band_w": 1, "unknown": 1}), encoding="utf-8")
        with self.assertLogs("solution.settings", level="WARNING"):
            settings = AppSettings.load(self.path)
        self.assertEqual(settings.exposure_ms, 5.0)
        self.assertEqual(settings.analog_gain, AppSettings().analog_gain)
        self.assertEqual(settings.draw_quad, AppSettings().draw_quad)
        self.assertEqual(settings.band_w, AppSettings().band_w)

    def test_old_file_keeps_y_band_and_ignores_removed_fields(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text(json.dumps({"camera_serial": "SN1", "param_slot": 2, "speed_mm_s": 100.0,
                                         "record_fps": 60, "band_enabled": True, "band_y": 640}),
                             encoding="utf-8")
        settings = AppSettings.load(self.path)
        self.assertEqual((settings.camera_serial, settings.band_enabled, settings.band_y), ("SN1", True, 640))
        self.assertFalse(hasattr(settings, "param_slot"))

    def test_defaults_give_a_bright_enough_image(self):
        self.assertEqual((AppSettings().exposure_ms, AppSettings().analog_gain), (12.9, 40))

    def test_decode_every_n_defaults_to_5_and_round_trips(self):
        self.assertEqual(AppSettings().decode_every_n, 5)
        AppSettings(decode_every_n=12).save(self.path)
        self.assertEqual(AppSettings.load(self.path).decode_every_n, 12)

    def test_invalid_decode_every_n_falls_back_to_default(self):
        self.path.parent.mkdir(parents=True)
        for bad in (0, 1001, 2.5, True, "5"):
            self.path.write_text(json.dumps({"decode_every_n": bad}), encoding="utf-8")
            with self.assertLogs("solution.settings", level="WARNING"):
                self.assertEqual(AppSettings.load(self.path).decode_every_n, 5)

    def test_use_gpu_defaults_on_and_round_trips(self):
        self.assertTrue(AppSettings().use_gpu)
        AppSettings(use_gpu=False).save(self.path)
        self.assertFalse(AppSettings.load(self.path).use_gpu)

    def test_invalid_use_gpu_falls_back_to_default(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text(json.dumps({"use_gpu": "no"}), encoding="utf-8")
        with self.assertLogs("solution.settings", level="WARNING"):
            self.assertTrue(AppSettings.load(self.path).use_gpu)


if __name__ == "__main__":
    unittest.main()
