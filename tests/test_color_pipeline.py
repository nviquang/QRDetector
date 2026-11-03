"""Color diagnostics preserve bytes and compare pixels, without camera hardware."""
import ctypes
import importlib
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class ColorDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.module = importlib.import_module("camera.color_diagnostics")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_reference_rgb_mono_and_odd_width_pixels(self):
        rgb = bytes([255, 0, 0, 0, 255, 0, 0, 0, 255])
        image = self.module.reference_bgr(rgb, 3, 1, "RGB8")
        np.testing.assert_array_equal(image, [[[0, 0, 255], [0, 255, 0], [255, 0, 0]]])
        gray = self.module.reference_bgr(bytes([0, 127, 255]), 3, 1, "MONO8")
        np.testing.assert_array_equal(gray, [[[0, 0, 0], [127, 127, 127], [255, 255, 255]]])
        with self.assertRaises(ValueError):
            self.module.reference_bgr(rgb, 3, 1, "BAYER")
        with self.assertRaises(ValueError):
            self.module.reference_bgr(rgb + b"\0", 3, 1, "RGB8")

    def test_sample_owns_before_and_after_bytes_and_never_overwrites(self):
        directory = Path(self.tmp.name) / "diagnostics"
        sampler = self.module.ColorDiagnostics(directory, max_samples=1)
        header = types.SimpleNamespace(iWidth=1, iHeight=1, uiMediaType=3,
                                       uiTimeStamp=1000, uBytes=3, fRgain=1.25)
        buffer = (ctypes.c_ubyte * 3)(255, 0, 0)
        before = sampler.before(ctypes.addressof(buffer), 3, header, "RGB8", 1, {"sdk": "test"})
        buffer[:] = [0, 0, 255]
        header.uiTimeStamp = 1001
        sampler.after(before, ctypes.addressof(buffer), 3, header, True)
        buffer[:] = [0, 0, 0]
        self.assertIsNone(sampler.before(ctypes.addressof(buffer), 3, header, "RGB8", 2, {}))
        sampler.finish()
        self.assertTrue(sampler.wait(5))
        sample_dir = directory / "sample_0001"
        self.assertEqual((sample_dir / "before.bin").read_bytes(), bytes([255, 0, 0]))
        self.assertEqual((sample_dir / "after.bin").read_bytes(), bytes([0, 0, 255]))
        np.testing.assert_array_equal(cv2.imread(str(sample_dir / "before.png")), [[[0, 0, 255]]])
        np.testing.assert_array_equal(cv2.imread(str(sample_dir / "preview.png")), [[[0, 0, 255]]])
        np.testing.assert_array_equal(cv2.imread(str(sample_dir / "after.png")), [[[255, 0, 0]]])
        metadata = json.loads((sample_dir / "metadata.json").read_text(encoding="utf-8"))
        self.assertTrue(metadata["buffer_changed"])
        self.assertEqual(metadata["before_header"]["uiTimeStamp"], 1000)
        self.assertEqual(metadata["after_header"]["uiTimeStamp"], 1001)
        self.assertTrue(metadata["push_succeeded"])
        self.assertEqual(metadata["push_ordinal"], 1)
        self.assertEqual(metadata["context"], {"sdk": "test"})
        self.assertFalse(sampler.errors)
        other = self.module.ColorDiagnostics(directory, max_samples=1)
        token = other.before(ctypes.addressof(buffer), 3, header, "RGB8", 1, {})
        other.after(token, ctypes.addressof(buffer), 3, header, True)
        other.finish()
        self.assertTrue(other.wait(5))
        self.assertTrue(other.errors)
        self.assertEqual((sample_dir / "before.bin").read_bytes(), bytes([255, 0, 0]))

    def test_memory_budget_skips_sample_without_reading_oversized_buffer(self):
        sampler = self.module.ColorDiagnostics(Path(self.tmp.name), max_bytes=2)
        header = types.SimpleNamespace(iWidth=1, iHeight=1)
        self.assertIsNone(sampler.before(0, 3, header, "RGB8", 1, {}))
        sampler.finish()
        self.assertTrue(sampler.wait(5))
        self.assertTrue(sampler.errors)

    def test_channel_metrics_do_not_hide_swap_or_neutral_yellow_cast(self):
        reference = np.array([[[0, 10, 250], [128, 128, 128]]], dtype=np.uint8)
        swapped = reference[:, :, ::-1].copy()
        metrics = self.module.compare_bgr(reference, swapped)
        self.assertEqual(metrics["max_abs_bgr"], [250, 0, 250])
        self.assertEqual(metrics["swapped_rb_max_abs_bgr"], [0, 0, 0])
        self.assertFalse(metrics["identical"])
        yellow = np.array([[[0, 10, 250], [100, 128, 128]]], dtype=np.uint8)
        metrics = self.module.compare_bgr(reference, yellow)
        self.assertEqual(metrics["max_abs_bgr"], [28, 0, 0])
        self.assertFalse(metrics["identical"])
        with self.assertRaises(ValueError):
            self.module.compare_bgr(reference, np.zeros((2, 2, 3), dtype=np.uint8))


if __name__ == "__main__":
    unittest.main()
