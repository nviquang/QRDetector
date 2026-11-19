"""Bộ phát hiện YOLOv8n detect chạy ONNX Runtime/OpenVINO và bộ ước lượng quad từ ảnh.

Chạy (từ gốc repo):  python -m unittest tests.test_detector_onnx
"""
import importlib.util
import os
from pathlib import Path
import sys
import unittest
from unittest import mock

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from qr import improved_pipeline  # noqa: E402
from qr.detector_onnx import DEFAULT_MODEL, OnnxQRDetector, letterbox_shape, postprocess, preprocess  # noqa: E402
from qr.quad_estimate import bbox_quad, estimate_quad  # noqa: E402
from tests.qr_fixtures import qr_image  # noqa: E402

HAS_MODEL = os.path.isfile(DEFAULT_MODEL)
HAS_ORT = importlib.util.find_spec("onnxruntime") is not None
HAS_OV = importlib.util.find_spec("openvino") is not None


def rotated_qr_frame(angle_deg, module_px=2.3, shape=(1072, 2856), center=(1400.0, 500.0), bg=60):
    """Tem trắng mang QR V2-M ~57 px xoay ``angle_deg`` trên nền tối đồng đều (như kính trong buồng tối)."""
    code = qr_image("000000585545#000000001612", 8, version=2, level="M")       # 29 ô (gồm viền 2 ô) × 8 px
    scale = module_px / 8.0
    side = code.shape[0] * scale
    label = cv2.copyMakeBorder(code, 24, 24, 24, 24, cv2.BORDER_CONSTANT, value=255)
    h, w = label.shape
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle_deg, scale)
    m[:, 2] += np.array(center) - np.array([w / 2, h / 2])
    frame = cv2.warpAffine(label, m, (shape[1], shape[0]), flags=cv2.INTER_AREA, borderValue=bg)
    sym = 25 * module_px                                                    # cạnh ký hiệu không gồm viền
    return cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR), sym, side


class LetterboxTests(unittest.TestCase):
    def test_band_at_scale_06_pads_to_multiple_of_32(self):
        self.assertEqual(letterbox_shape(1072, 2856, 0.6), (643, 1714, 672, 1728))
        t = preprocess(np.zeros((1072, 2856, 3), np.uint8), 0.6)
        self.assertEqual(t.shape, (1, 3, 672, 1728))
        self.assertAlmostEqual(float(t[0, 0, 670, 1720]), 114 / 255, places=5)   # vùng đệm


class PostprocessTests(unittest.TestCase):
    def test_nms_threshold_and_mapping_to_original_coordinates(self):
        cols = [[100, 100, 30, 30, 0.9],      # giữ
                [102, 101, 30, 30, 0.8],      # trùng, bị NMS
                [400, 200, 20, 20, 0.1]]      # dưới ngưỡng
        out = np.array(cols, np.float32).T[None]
        found = postprocess(out, 0.5, 0.3, 0.3, (1000, 2000))
        self.assertEqual(len(found), 1)
        box, score = found[0]
        np.testing.assert_allclose(box, [170, 170, 230, 230])
        self.assertAlmostEqual(score, 0.9, places=5)

    def test_empty(self):
        self.assertEqual(postprocess(np.zeros((1, 5, 10), np.float32), 0.6, 0.3, 0.3, (100, 100)), [])


class QuadEstimateTests(unittest.TestCase):
    def test_rotated_qr_quad_matches_rotation_and_size(self):
        for angle in (0, 20, 45):
            frame, sym, _ = rotated_qr_frame(angle)
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            half = sym * (abs(np.cos(np.radians(angle))) + abs(np.sin(np.radians(angle)))) / 2
            bbox = [1400 - half, 500 - half, 1400 + half, 500 + half]
            quad = estimate_quad(gray, bbox)
            sides = np.linalg.norm(np.roll(quad, -1, axis=0) - quad, axis=1)
            self.assertLess(abs(sides.mean() - sym) / sym, 0.15, (angle, sides))
            edge = quad[1] - quad[0]
            got = np.degrees(np.arctan2(edge[1], edge[0])) % 90
            want = (-angle) % 90                                   # getRotationMatrix2D: góc dương = ngược chiều kim đồng hồ
            diff = min(abs(got - want), 90 - abs(got - want))
            self.assertLess(diff, 6.0, (angle, got))

    def test_flat_image_falls_back_to_bbox(self):
        bbox = [10, 10, 60, 60]
        np.testing.assert_allclose(estimate_quad(np.full((100, 100), 128, np.uint8), bbox), bbox_quad(bbox))


@unittest.skipUnless(HAS_MODEL, "chưa có qr/models/qrdet_n_detect.onnx (tools/export_qrdet_detect.py)")
class DetectorTests(unittest.TestCase):
    def check_backend(self, backend):
        det = OnnxQRDetector(backend=backend, scale=0.6)
        frame, sym, _ = rotated_qr_frame(30)
        found = det.detect(frame)
        self.assertTrue(found, backend)
        best = max(found, key=lambda d: d.confidence)
        cx, cy = (best.bbox_xyxy[:2] + best.bbox_xyxy[2:]) / 2
        self.assertLess(np.hypot(cx - 1400, cy - 500), 10, backend)
        self.assertEqual(best.quad_xy.shape, (4, 2))
        self.assertEqual(det.detect(np.full((1072, 2856, 3), 60, np.uint8)), [])

    @unittest.skipUnless(HAS_ORT, "thiếu onnxruntime")
    def test_onnxruntime(self):
        self.check_backend("onnxruntime")

    @unittest.skipUnless(HAS_OV, "thiếu openvino")
    def test_openvino(self):
        self.check_backend("openvino")

    @unittest.skipUnless(HAS_ORT, "thiếu onnxruntime")
    def test_env_selects_onnx_detector(self):
        with mock.patch.dict(os.environ, {"QR_DETECTOR": "onnx", "QR_DETECT_SCALE": "0.5"}):
            det = improved_pipeline.make_detector()
        self.assertIsInstance(det, OnnxQRDetector)
        self.assertEqual((det.scale, det.backend), (0.5, "onnxruntime"))

    def test_unknown_env_value_is_an_error(self):
        with mock.patch.dict(os.environ, {"QR_DETECTOR": "yolo11"}):
            with self.assertRaises(ValueError):
                improved_pipeline.make_detector()


if __name__ == "__main__":
    unittest.main()
