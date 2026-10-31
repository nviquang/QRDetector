"""API pipeline: inject detector, decode_detection trả Decoded (text + 4 góc), quad hiển thị.
Không cần YOLO.

Chạy (từ solution/):  python -m unittest tests.test_pipeline_api
"""
from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from qr import Decoded, ImprovePipeline  # noqa: E402
from qr.corrector import display_quad  # noqa: E402
from qr.decoder import read_wechat_gray, read_zxing_gray  # noqa: E402
from qr.detector import Detection  # noqa: E402
from qr.improved_pipeline import _warp_zxing_step  # noqa: E402
from qr.preprocessor import UPSCALE_PAD_PER_SCALE, upscale_gray  # noqa: E402
from tests.qr_fixtures import frame_with_qrs, qr_image, symbol_corners  # noqa: E402


class FakeDetector:
    def __init__(self, detections):
        self.detections = detections
        self.calls = 0

    def detect(self, image_bgr):
        self.calls += 1
        return list(self.detections)


def assert_corners(test, got, expected, tol=2.0):
    """Mỗi góc kỳ vọng có một góc trả về cách ≤ tol px (không ràng buộc thứ tự bắt đầu)."""
    for e in expected:
        test.assertLessEqual(float(np.min(np.linalg.norm(got - e, axis=1))), tol, (got, expected))


class DecoderCornerTests(unittest.TestCase):
    def setUp(self):
        self.gray = np.full((300, 300), 255, np.uint8)
        q = qr_image("000000585545")
        self.gray[50:50 + q.shape[0], 60:60 + q.shape[1]] = q
        self.expected = symbol_corners(60, 50)

    def test_zxing_returns_symbol_corners(self):
        text, corners = read_zxing_gray(self.gray)
        self.assertEqual(text, "000000585545")
        assert_corners(self, corners, self.expected)

    def test_wechat_returns_symbol_corners(self):
        text, corners = read_wechat_gray(self.gray)
        self.assertEqual(text, "000000585545")
        assert_corners(self, corners, self.expected)

    def test_upscale_pad_constant_matches_upscale_gray(self):
        up = upscale_gray(self.gray, 3)
        self.assertEqual(up.shape[0], 300 * 3 + 2 * UPSCALE_PAD_PER_SCALE * 3)


class PipelineApiTests(unittest.TestCase):
    def test_scan_uses_injected_detector(self):
        frame, dets = frame_with_qrs([("000000585545", (100, 100))])
        detector = FakeDetector(dets)
        results, found = ImprovePipeline(detector=detector).scan(frame)
        self.assertEqual(results, ["000000585545"])
        self.assertEqual(found, dets)
        self.assertEqual(detector.calls, 1)

    def test_decode_detection_maps_corners_back_to_frame(self):
        frame, (det,) = frame_with_qrs([("000000585545", (130, 90))])
        hit = ImprovePipeline(detector=FakeDetector([])).decode_detection(frame, det)
        self.assertIsInstance(hit, Decoded)
        self.assertEqual(hit.text, "000000585545")
        assert_corners(self, hit.corners, symbol_corners(130, 90))

    def test_warp_step_maps_corners_back_through_homography(self):
        frame, (det,) = frame_with_qrs([("000000585545", (200, 150))])
        hit = _warp_zxing_step(frame, det, None, np.zeros(2, np.float32))
        self.assertEqual(hit.text, "000000585545")
        assert_corners(self, hit.corners, symbol_corners(200, 150), tol=3.0)

    def test_decode_detection_reads_only_its_own_qr(self):
        frame, (_, second) = frame_with_qrs([("000000000001", (50, 50)),
                                             ("000000000002", (500, 300))])
        hit = ImprovePipeline(detector=FakeDetector([])).decode_detection(frame, second)
        self.assertEqual(hit.text, "000000000002")

    def test_decode_detection_on_blank_area_returns_none(self):
        frame = np.full((400, 400, 3), 255, np.uint8)
        quad = np.array([[100, 100], [160, 100], [160, 160], [100, 160]], np.float32)
        det = Detection(np.array([100, 100, 160, 160], np.float32), quad, 0.9)
        self.assertIsNone(ImprovePipeline(detector=FakeDetector([])).decode_detection(frame, det))


class DisplayQuadTests(unittest.TestCase):
    def test_display_quad_prefers_decoder_corners(self):
        corners = np.array([[1, 2], [3, 2], [3, 4], [1, 4]], np.float32)
        det = Detection(np.zeros(4, np.float32), np.zeros((4, 2), np.float32), 0.9)
        np.testing.assert_array_equal(display_quad(det, corners), corners)

    def test_display_quad_from_jagged_polygon_is_rectangle(self):
        # polygon răng cưa + một điểm lồi (kiểu ngón tay) — padded quad của qrdet thành hình diều
        poly = np.array([[100, 100], [160, 98], [162, 160], [130, 175], [99, 161]], np.float32)
        det = Detection(np.array([99, 98, 162, 175], np.float32), np.zeros((4, 2), np.float32), 0.9,
                        polygon_xy=poly)
        quad = display_quad(det)
        self.assertEqual(quad.shape, (4, 2))
        for i in range(4):          # mọi góc vuông
            a, b, c = quad[i - 1], quad[i], quad[(i + 1) % 4]
            cos = float(np.dot(a - b, c - b) / (np.linalg.norm(a - b) * np.linalg.norm(c - b)))
            self.assertLess(abs(cos), 1e-3)

    def test_display_quad_without_polygon_uses_bbox(self):
        det = Detection(np.array([10, 20, 70, 90], np.float32), np.zeros((4, 2), np.float32), 0.9)
        np.testing.assert_array_equal(display_quad(det),
                                      np.array([[10, 20], [70, 20], [70, 90], [10, 90]], np.float32))


if __name__ == "__main__":
    unittest.main()
