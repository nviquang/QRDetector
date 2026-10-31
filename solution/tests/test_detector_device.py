"""Chọn thiết bị cho detector + kiểm tra GPU thật (bỏ qua nếu máy không có CUDA).

Chạy (từ solution/):  python -m unittest tests.test_detector_device
"""
import glob
from pathlib import Path
import sys
import unittest

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import torch  # noqa: E402
from qr.detector import Detection, QRDetector, resolve_device  # noqa: E402

SAMPLES = sorted(glob.glob(str(ROOT.parent / "images" / "*.bmp")))[:3]


class ResolveDeviceTests(unittest.TestCase):
    def test_auto_picks_cuda_when_available(self):
        self.assertEqual(resolve_device("auto", True), "cuda:0")
        self.assertEqual(resolve_device("auto", False), "cpu")

    def test_cuda_requested_without_cuda_falls_back_to_cpu(self):
        with self.assertLogs("solution.qr", "WARNING"):
            self.assertEqual(resolve_device("cuda:0", False), "cpu")

    def test_explicit_device_is_kept(self):
        self.assertEqual(resolve_device("cpu", True), "cpu")
        self.assertEqual(resolve_device("cuda:0", True), "cuda:0")

    def test_detection_polygon_defaults_to_none(self):
        det = Detection(np.zeros(4, np.float32), np.zeros((4, 2), np.float32), 0.9)
        self.assertIsNone(det.polygon_xy)


@unittest.skipUnless(SAMPLES, "thiếu ảnh mẫu ../images/*.bmp")
class RealDetectorTests(unittest.TestCase):
    def test_detections_carry_mask_polygon(self):
        det = QRDetector(conf_th=0.3, imgsz=1280, device="cpu").detect(cv2.imread(SAMPLES[0]))[0]
        self.assertGreaterEqual(len(det.polygon_xy), 3)

    @unittest.skipUnless(torch.cuda.is_available(), "máy không có CUDA")
    def test_gpu_finds_same_qrs_as_cpu(self):
        cpu = QRDetector(conf_th=0.3, imgsz=1280, device="cpu")
        gpu = QRDetector(conf_th=0.3, imgsz=1280, device="auto")
        self.assertTrue(gpu.device.startswith("cuda"))
        gpu.warmup()
        for path in SAMPLES:
            img = cv2.imread(path)
            a, b = cpu.detect(img), gpu.detect(img)
            self.assertEqual(len(a), len(b), path)
            for da, db in zip(sorted(a, key=lambda d: d.bbox_xyxy[0]), sorted(b, key=lambda d: d.bbox_xyxy[0])):
                np.testing.assert_allclose(da.bbox_xyxy, db.bbox_xyxy, atol=3.0)


if __name__ == "__main__":
    unittest.main()
