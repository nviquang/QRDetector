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


class BandImgszTests(unittest.TestCase):
    def predict_imgsz(self, shape, imgsz=1280):
        with patch("qr.detector._QRDetector"), patch("torch.cuda.is_available", return_value=False):
            det = QRDetector(device="cpu", imgsz=imgsz)
        det._predict(np.zeros((*shape, 3), np.uint8))
        return det._detector.model.predict.call_args.kwargs["imgsz"]

    def test_narrow_band_uses_more_resolution(self):
        self.assertEqual(self.predict_imgsz((400, 2856)), 1600)

    def test_full_frame_keeps_configured_size(self):
        self.assertEqual(self.predict_imgsz((2848, 2856)), 1280)
        self.assertEqual(self.predict_imgsz((768, 2448)), 1280)

    def test_never_lowers_configured_size(self):
        self.assertEqual(self.predict_imgsz((400, 2856), imgsz=1920), 1920)


class DegenerateMaskTests(unittest.TestCase):
    """qrdet.crop_qr cố cấp phát vài PiB khi mask của detection đầu suy biến: không được mất cả frame."""

    def make(self):
        with patch("qr.detector._QRDetector"), patch("torch.cuda.is_available", return_value=False):
            det = QRDetector(device="cpu")
        det._predict = Mock(return_value=[list(range(3))])
        return det

    @staticmethod
    def raw(i):
        quad = np.full((4, 2), float(i), np.float32)
        return dict(padded_quad_xy=quad, bbox_xyxy=np.array([i, i, i + 1, i + 1], np.float32), confidence=0.9,
                    polygon_xy=quad)

    def test_bad_detection_is_dropped_and_others_kept(self):
        def convert(results, image):
            if len(results) > 1 or results[0] == 1:
                raise MemoryError("1.28 PiB")
            return [self.raw(results[0])]

        det = self.make()
        with patch("qr.detector._yolo_v8_results_to_dict", convert), self.assertLogs("solution.qr", "WARNING"):
            found = det.detect(np.zeros((32, 32, 3), np.uint8))
        self.assertEqual([float(d.bbox_xyxy[0]) for d in found], [0.0, 2.0])

    def test_normal_frame_converts_all_at_once(self):
        calls = []

        def convert(results, image):
            calls.append(len(results))
            return [self.raw(i) for i in results]

        det = self.make()
        with patch("qr.detector._yolo_v8_results_to_dict", convert):
            self.assertEqual(len(det.detect(np.zeros((32, 32, 3), np.uint8))), 3)
        self.assertEqual(calls, [3])


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
