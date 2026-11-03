"""Chọn thiết bị cho detector + kiểm tra GPU thật (bỏ qua nếu máy không có CUDA).

Chạy (từ gốc repo):  python -m unittest tests.test_detector_device
"""
import glob
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import torch  # noqa: E402
from qr.detector import Detection, QRDetector, resolve_device  # noqa: E402
from qr.improved_pipeline import ImprovePipeline  # noqa: E402

SAMPLES_DIR = os.environ.get("QR_SAMPLES_DIR", ROOT.parent / "QRDetector-research" / "data" / "images")
SAMPLES = sorted(glob.glob(os.path.join(SAMPLES_DIR, "*.bmp")))[:3]


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


class SetDeviceTests(unittest.TestCase):
    def make(self, half=False):
        with patch("qr.detector._QRDetector"), patch("torch.cuda.is_available", return_value=False):
            return QRDetector(device="cpu", half=half)

    def test_switches_both_ways_and_restores_half(self):
        det = self.make(half=True)
        with patch("torch.cuda.is_available", return_value=True), \
                patch("torch.cuda.get_device_name", return_value="GTX"):
            det.set_device("auto")
        self.assertEqual((det.device, det._half), ("cuda:0", True))
        det.set_device("cpu")
        self.assertEqual((det.device, det._half), ("cpu", False))

    def test_without_cuda_stays_on_cpu(self):
        det = self.make()
        with patch("torch.cuda.is_available", return_value=False):
            det.set_device("auto")
            self.assertFalse(det.gpu_available)
        self.assertEqual(det.device, "cpu")

    def test_broken_driver_stays_on_cpu(self):
        det = self.make()
        with patch("torch.cuda.is_available", return_value=True), \
                patch("torch.cuda.get_device_name", side_effect=RuntimeError("driver")), \
                self.assertLogs("solution.qr", "WARNING"):
            det.set_device("cuda:0")
        self.assertEqual(det.device, "cpu")

    def test_pipeline_forwards_to_detector(self):
        fake_detector = Mock(gpu_available=True)
        pipeline = ImprovePipeline(detector=fake_detector)
        pipeline.set_device("cpu")
        fake_detector.set_device.assert_called_once_with("cpu")
        self.assertTrue(pipeline.gpu_available)


@unittest.skipUnless(SAMPLES, "thiếu ảnh mẫu *.bmp trong QR_SAMPLES_DIR")
class RealDetectorTests(unittest.TestCase):
    def test_detections_carry_mask_polygon(self):
        det = QRDetector(conf_th=0.3, imgsz=1280, device="cpu").detect(cv2.imread(SAMPLES[0]))[0]
        self.assertGreaterEqual(len(det.polygon_xy), 3)

    def test_cuda_runtime_error_falls_back_to_cpu(self):
        det = QRDetector(conf_th=0.3, imgsz=1280, device="cpu")
        det._device = "cuda:0"               # giả lập đang chạy GPU thì CUDA hỏng (OOM / driver)
        original = det._detector.model.predict

        def predict(**kwargs):
            if str(kwargs["device"]).startswith("cuda"):
                raise RuntimeError("CUDA error: out of memory")
            return original(**kwargs)

        det._detector.model.predict = predict
        with self.assertLogs("solution.qr", "WARNING"):
            found = det.detect(cv2.imread(SAMPLES[0]))
        self.assertEqual(det.device, "cpu")
        self.assertGreaterEqual(len(found), 1)

    @unittest.skipUnless(torch.cuda.is_available(), "máy không có CUDA")
    def test_switching_at_runtime_moves_the_model(self):
        det = QRDetector(conf_th=0.3, imgsz=1280, device="cuda:0")
        img = cv2.imread(SAMPLES[0])
        expected = len(det.detect(img))
        for device, kind in (("cpu", "cpu"), ("auto", "cuda")):
            det.set_device(device)
            self.assertEqual(len(det.detect(img)), expected)
            self.assertEqual(det._detector.model.predictor.device.type, kind)

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
