"""Đọc QR nhiều frame: xếp chồng, khử mờ, lọc định dạng. Ảnh QR tổng hợp, không cần camera hay YOLO.

Chạy (từ gốc repo):  python -m unittest tests.test_multiframe
"""
from pathlib import Path
import sys
import unittest
from unittest import mock

import cv2
import numpy as np
import zxingcpp

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from qr import multiframe  # noqa: E402
from qr.content_filter import CODE_PATTERN  # noqa: E402
from qr.decoder import read_zxing_gray  # noqa: E402
from qr.improved_pipeline import ImprovePipeline  # noqa: E402
from qr.multiframe import PassDecoder, stack_rois, wiener_motion  # noqa: E402
from qr.tracker import Track  # noqa: E402
from tests.qr_fixtures import frame_with_qrs, qr_image, symbol_corners  # noqa: E402

CODE = "000000585545"
PATTERN = r"^\d{12}$"


def small_qr(text=CODE, scale=3, margin=20):
    """QR xám ~3 px/ô có nền trắng quanh, giống ROI thật."""
    return cv2.copyMakeBorder(qr_image(text, scale), margin, margin, margin, margin,
                              cv2.BORDER_CONSTANT, value=255)


def dim_noisy(gray, rng, lo=8, hi=25, noise=10.0):
    img = lo + np.float32(gray) * ((hi - lo) / 255.0)
    return np.clip(img + rng.normal(0, noise, img.shape), 0, 255).astype(np.uint8)


def noisy_frame(rng, shape=(400, 600), at=(250, 150), lo=8, hi=25, noise=10.0):
    """Frame BGR tối, nhiễu; trả (frame, bbox QR)."""
    code = qr_image(CODE, 3)
    gray = np.full(shape, 255, np.uint8)
    x, y = at
    gray[y:y + code.shape[0], x:x + code.shape[1]] = code
    frame = dim_noisy(gray, rng, lo, hi, noise)
    bbox = np.array([x, y, x + code.shape[1], y + code.shape[0]], np.float32)
    return cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR), bbox


def track(track_id=1, velocity=(0.0, 0.0)):
    return Track(track_id, 0, 0, (0.0, 0.0), 75.0, velocity=velocity, observations=2)


class DefaultPipelineTests(unittest.TestCase):
    def test_pipeline_filters_field_format_and_accepts_every_version_by_default(self):
        pipeline = ImprovePipeline(detector=object())
        self.assertEqual(pipeline.code_pattern, CODE_PATTERN)
        self.assertIsNone(pipeline.expected_symbol)


class StackRoisTests(unittest.TestCase):
    def test_stacking_recovers_qr_unreadable_in_any_single_frame(self):
        rng = np.random.default_rng(1)
        rois = [dim_noisy(small_qr(), rng) for _ in range(8)]
        up = lambda g: cv2.copyMakeBorder(cv2.resize(g, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC),  # noqa: E731
                                          64, 64, 64, 64, cv2.BORDER_REPLICATE)
        self.assertTrue(all(read_zxing_gray(up(r)) is None for r in rois))
        stacked = cv2.copyMakeBorder(stack_rois(rois), 64, 64, 64, 64, cv2.BORDER_REPLICATE)
        self.assertEqual(read_zxing_gray(stacked)[0], CODE)

    def test_stack_aligns_shifted_frames(self):
        rng = np.random.default_rng(2)
        base = small_qr()
        rois = []
        for dx in (-5, -3, 2, 0, 4, -2, 3, 0):
            shifted = cv2.warpAffine(base, np.float32([[1, 0, dx], [0, 1, -dx]]), base.shape[::-1],
                                     borderMode=cv2.BORDER_REPLICATE)
            rois.append(dim_noisy(shifted, rng))
        stacked = cv2.copyMakeBorder(stack_rois(rois), 64, 64, 64, 64, cv2.BORDER_REPLICATE)
        self.assertEqual(read_zxing_gray(stacked)[0], CODE)


class WienerTests(unittest.TestCase):
    def test_restores_horizontal_motion_blur(self):
        up = cv2.resize(small_qr(scale=3), None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
        length = 28
        blurred = cv2.filter2D(up, -1, np.ones((1, length), np.float32) / length, borderType=cv2.BORDER_REPLICATE)
        pad = lambda g: cv2.copyMakeBorder(g, 64, 64, 64, 64, cv2.BORDER_REPLICATE)  # noqa: E731
        self.assertIsNone(read_zxing_gray(pad(blurred)))
        self.assertEqual(read_zxing_gray(pad(wiener_motion(blurred, length, 0.0, 0.005)))[0], CODE)

    def test_output_keeps_shape_and_dtype(self):
        out = wiener_motion(np.full((64, 80), 128, np.uint8), 5.0, 0.3, 0.05)
        self.assertEqual((out.shape, out.dtype), ((64, 80), np.uint8))


class PassDecoderTests(unittest.TestCase):
    def test_clean_read_returns_corners_in_frame_coordinates(self):
        frame, (det,) = frame_with_qrs([(CODE, (200, 100))])
        hit = PassDecoder(PATTERN).read(frame, det.bbox_xyxy, det, track(), [])
        self.assertEqual(hit.text, CODE)
        expected = symbol_corners(200, 100, CODE)
        got = hit.corners[np.argsort(hit.corners.sum(axis=1))]
        np.testing.assert_allclose(got, expected[np.argsort(expected.sum(axis=1))], atol=2.0)

    def test_wrong_format_is_rejected_and_logged_once(self):
        frame, (det,) = frame_with_qrs([("5576", (200, 100))])
        decoder = PassDecoder(PATTERN)
        with self.assertLogs("solution.qr", "WARNING") as logs:
            self.assertIsNone(decoder.read(frame, det.bbox_xyxy, det, track(), []))
            self.assertIsNone(decoder.read(frame, det.bbox_xyxy, det, track(), []))
        self.assertEqual(len(logs.output), 1)
        self.assertIn("5576", logs.output[0])

    def test_other_binarizers_are_tried_after_default(self):
        frame, (det,) = frame_with_qrs([(CODE, (200, 100))])
        tried = []

        def fake(gray, binarizer=None, symbol=None):
            tried.append(binarizer)
            return (CODE, np.zeros((4, 2), np.float32)) if binarizer == zxingcpp.Binarizer.FixedThreshold else None

        with mock.patch.object(multiframe, "read_zxing_gray", fake):
            self.assertEqual(PassDecoder(PATTERN).read(frame, det.bbox_xyxy, det, track(), []).text, CODE)
        self.assertEqual(tried, [None, zxingcpp.Binarizer.GlobalHistogram, zxingcpp.Binarizer.FixedThreshold])

    def test_no_pattern_accepts_anything(self):
        frame, (det,) = frame_with_qrs([("5576", (200, 100))])
        self.assertEqual(PassDecoder(None).read(frame, det.bbox_xyxy, det, track(), []).text, "5576")

    def test_stack_reads_after_enough_failed_frames_with_frame_corners(self):
        rng = np.random.default_rng(3)
        decoder = PassDecoder(PATTERN)
        t = track()
        hits = []
        with mock.patch.object(multiframe, "read_wechat_gray", return_value=None):
            for _ in range(8):
                frame, bbox = noisy_frame(rng)
                hits.append(decoder.read(frame, bbox, None, t, []))
        self.assertIsNone(hits[0])
        hit = next(h for h in hits if h)
        self.assertEqual(hit.text, CODE)
        expected = symbol_corners(250, 150, CODE, scale=3)
        self.assertLess(abs(hit.corners.mean(axis=0) - expected.mean(axis=0)).max(), 6.0)

    def test_no_stack_without_track(self):
        rng = np.random.default_rng(3)
        decoder = PassDecoder(PATTERN)
        with mock.patch.object(multiframe, "read_wechat_gray", return_value=None) as wechat:
            for _ in range(8):
                frame, bbox = noisy_frame(rng)
                self.assertIsNone(decoder.read(frame, bbox, None, None, []))
        self.assertEqual(wechat.call_count, 8 * 3)   # chỉ WeChat từng frame, không có lần trên ảnh xếp chồng

    def test_forget_clears_collected_frames(self):
        rng = np.random.default_rng(4)
        decoder = PassDecoder(PATTERN)
        t = track()
        frame, bbox = noisy_frame(rng)
        decoder.read(frame, bbox, None, t, [])
        self.assertIn(t.track_id, decoder.states)
        decoder.forget(t.track_id)
        self.assertNotIn(t.track_id, decoder.states)

    def test_wechat_runs_on_every_frame_and_once_more_on_stack(self):
        rng = np.random.default_rng(5)
        with mock.patch.object(multiframe, "read_wechat_gray", return_value=None) as wechat, \
                mock.patch.object(multiframe, "read_zxing_gray", return_value=None):
            decoder = PassDecoder(PATTERN)
            t = track()
            for _ in range(2):      # chưa đủ ảnh để xếp chồng
                frame, bbox = noisy_frame(rng)
                decoder.read(frame, bbox, None, t, [])
            self.assertEqual(wechat.call_count, 2 * 3)
            frame, bbox = noisy_frame(rng)
            decoder.read(frame, bbox, None, t, [])
            self.assertEqual(wechat.call_count, 3 * 3 + 1)

    def test_wechat_read_stops_later_steps_and_maps_corners_to_frame(self):
        frame, (det,) = frame_with_qrs([(CODE, (200, 100))])
        decoder = PassDecoder(PATTERN)
        pad = multiframe.UPSCALE_PAD_PER_SCALE * 4
        pts = np.array([[0, 0], [400, 0], [400, 400], [0, 400]], np.float32) + pad   # tâm nằm trong bbox
        x1, y1, _, _ = multiframe.roi_bounds(frame.shape, det.bbox_xyxy, 0.25)
        with mock.patch.object(multiframe, "read_zxing_gray", return_value=None), \
                mock.patch.object(multiframe, "read_wechat_gray", return_value=(CODE, pts)) as wechat:
            hit = decoder.read(frame, det.bbox_xyxy, None, track(), [3.0])
        self.assertEqual(wechat.call_count, 1)
        self.assertEqual(hit.text, CODE)
        np.testing.assert_allclose(hit.corners[2], [x1 + 100, y1 + 100])
        self.assertNotIn(1, decoder.states)     # đọc được thì không gom ảnh

    def test_roi_touching_frame_edge_is_not_collected(self):
        rng = np.random.default_rng(6)
        decoder = PassDecoder(PATTERN)
        t = track()
        frame, _ = noisy_frame(rng)
        decoder.read(frame, np.array([0, 150, 75, 225], np.float32), None, t, [])
        self.assertEqual(len(decoder.states[t.track_id].rois), 0)


if __name__ == "__main__":
    unittest.main()
