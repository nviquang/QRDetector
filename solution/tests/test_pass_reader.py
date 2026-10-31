"""PassReader — detect, ghép lượt, bỏ cascade QR đã đọc chắc, overlay. Pipeline giả, không cần YOLO.

Chạy (từ solution/):  python -m unittest tests.test_pass_reader
"""
from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from qr.improved_pipeline import Decoded  # noqa: E402
from qr.pass_reader import Overlay, PassReader  # noqa: E402
from qr.tracker import PassTracker  # noqa: E402
from tests.qr_fixtures import detection_at  # noqa: E402

IMG = np.zeros((768, 2448, 3), np.uint8)
CORNERS = np.array([[1, 1], [9, 1], [9, 9], [1, 9]], np.float32)


class FakePipeline:
    """detect(): trả lần lượt từng phần tử ``frames``; decode_detection(): trả lần lượt ``answers``
    (str → Decoded với CORNERS, None → không đọc được; hết danh sách thì lặp phần tử cuối)."""

    def __init__(self, frames, answers):
        self.frames = list(frames)
        self.answers = list(answers)
        self.decode_calls = 0
        self.warmed = False

    def warmup(self):
        self.warmed = True

    def detect(self, image_bgr):
        return self.frames.pop(0)

    def decode_detection(self, image_bgr, det):
        self.decode_calls += 1
        text = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        return Decoded(text, CORNERS) if text else None


def moving(n, y=300, start=100, step=45):
    """n frame, mỗi frame một QR chạy ``step`` px/frame theo x."""
    return [[detection_at(start + step * i, y)] for i in range(n)]


class PassReaderTests(unittest.TestCase):
    def test_confirmed_track_skips_cascade_and_reuses_text(self):
        pipe = FakePipeline(moving(3), ["A"])
        reader = PassReader(pipe)
        results = [reader.process(IMG, i) for i in range(3)]
        self.assertEqual(pipe.decode_calls, 2)
        self.assertEqual((results[2].skipped, results[2].texts, results[2].results), (1, ["A"], ["A"]))

    def test_recheck_every_n_skips(self):
        pipe = FakePipeline(moving(8), ["A"])
        reader = PassReader(pipe, recheck_every=5)
        for i in range(8):
            reader.process(IMG, i)
        self.assertEqual(pipe.decode_calls, 3)   # frame 0, 1 đọc; 2–6 bỏ qua; 7 đọc kiểm tra

    def test_recheck_detects_changed_content(self):
        pipe = FakePipeline(moving(9), ["A", "A", "B"])
        reader = PassReader(pipe, recheck_every=5)
        for i in range(9):
            reader.process(IMG, i)
        self.assertEqual(pipe.decode_calls, 4)   # 0, 1, 7 (ra B → mâu thuẫn), 8 không còn bỏ qua
        (track,) = reader.flush()
        self.assertTrue(track.conflicting)

    def test_conflicting_reads_never_skip(self):
        pipe = FakePipeline(moving(5), ["A", "B", "A", "A", "A"])
        reader = PassReader(pipe)
        for i in range(5):
            reader.process(IMG, i)
        self.assertEqual(pipe.decode_calls, 5)

    def test_unreadable_qr_is_never_skipped(self):
        pipe = FakePipeline(moving(4), [None])
        reader = PassReader(pipe)
        for i in range(4):
            self.assertEqual(reader.process(IMG, i).results, [])
        self.assertEqual(pipe.decode_calls, 4)
        (track,) = reader.flush()
        self.assertIsNone(track.text)

    def test_new_qr_beside_confirmed_one_is_still_decoded(self):
        frames = moving(3) + [[detection_at(100 + 45 * 3, 300), detection_at(100, 600)]]
        pipe = FakePipeline(frames, ["A", "A", "B"])
        reader = PassReader(pipe)
        for i in range(3):
            reader.process(IMG, i)
        result = reader.process(IMG, 3)
        self.assertEqual(pipe.decode_calls, 3)
        self.assertEqual(result.texts, ["A", "B"])
        self.assertEqual(result.skipped, 1)

    def test_backwards_frame_index_closes_open_passes(self):
        pipe = FakePipeline([[detection_at(100, 300)]] * 3, ["A"])
        reader = PassReader(pipe)
        reader.process(IMG, 100)
        reader.process(IMG, 101)
        result = reader.process(IMG, 5)          # camera mở lại → seq bắt đầu lại
        self.assertEqual([t.text for t in result.finished], ["A"])
        self.assertEqual(result.skipped, 0)
        self.assertEqual(pipe.decode_calls, 3)

    def test_shape_change_closes_open_passes(self):
        pipe = FakePipeline([[detection_at(100, 300)]] * 3, ["A"])
        reader = PassReader(pipe)
        reader.process(IMG, 1)
        reader.process(IMG, 2)
        result = reader.process(np.zeros((2048, 2448, 3), np.uint8), 3)
        self.assertEqual(len(result.finished), 1)
        self.assertEqual(result.skipped, 0)

    def test_gap_finishes_pass_and_logs_it(self):
        pipe = FakePipeline([[detection_at(100, 300)], [detection_at(100, 300)], []], ["A"])
        reader = PassReader(pipe, PassTracker(max_gap=5))
        reader.process(IMG, 0)
        reader.process(IMG, 1)
        with self.assertLogs("solution.qr", "INFO") as logs:
            result = reader.process(IMG, 20)
        self.assertEqual([t.text for t in result.finished], ["A"])
        self.assertIn("pass_finished", logs.output[0])
        self.assertIn("text=A", logs.output[0])

    def test_flush_returns_open_passes_and_timings_are_reported(self):
        pipe = FakePipeline(moving(1), ["A"])
        reader = PassReader(pipe)
        result = reader.process(IMG, 0)
        self.assertGreaterEqual(result.detect_ms, 0.0)
        self.assertGreaterEqual(result.cascade_ms, 0.0)
        self.assertEqual([t.text for t in reader.flush()], ["A"])
        self.assertEqual(reader.flush(), [])

    def test_warmup_is_forwarded_to_pipeline(self):
        pipe = FakePipeline([], ["A"])
        PassReader(pipe).warmup()
        self.assertTrue(pipe.warmed)

    def test_real_decode_spacing_keeps_one_pass(self):
        # 30 cm/s ≈ 14 px/seq; decode ~0.6 s ở 50 fps → 30 seq giữa hai lần → 420 px > cổng 400 px cũ
        pipe = FakePipeline(moving(8, step=14 * 30), ["A"])
        reader = PassReader(pipe)
        results = [reader.process(IMG, 30 * i) for i in range(8)]
        self.assertEqual(len(reader.flush()), 1)
        self.assertGreater(results[2].skipped, 0)
        self.assertEqual(results[2].overlays[0].velocity, (14.0, 0.0))

    # ── overlay ──

    def test_overlay_uses_decoder_corners_when_read(self):
        pipe = FakePipeline(moving(1), ["A"])
        (ov,) = PassReader(pipe).process(IMG, 7).overlays
        np.testing.assert_array_equal(ov.quad_xy, CORNERS)
        self.assertEqual((ov.ok, ov.seq, ov.shape, ov.velocity), (True, 7, (768, 2448), (0.0, 0.0)))

    def test_overlay_of_unread_or_skipped_qr_uses_mask_rectangle(self):
        pipe = FakePipeline(moving(3), ["A", "A"])
        reader = PassReader(pipe)
        reader.process(IMG, 0)
        reader.process(IMG, 1)
        (ov,) = reader.process(IMG, 2).overlays         # bỏ cascade → không có góc decoder
        self.assertTrue(ov.ok)
        self.assertEqual(ov.quad_xy.shape, (4, 2))
        self.assertAlmostEqual(float(ov.quad_xy[:, 0].mean()), 100 + 45 * 2, delta=1.0)
        self.assertEqual(ov.velocity, (45.0, 0.0))

    def test_overlay_at_shifts_by_velocity_and_expires(self):
        ov = Overlay(CORNERS.copy(), True, (5.0, -1.0), seq=10, shape=(768, 2448))
        np.testing.assert_allclose(ov.at(14, (768, 2448), max_age=100), CORNERS + [20.0, -4.0])
        self.assertIsNone(ov.at(14, (2048, 2448), max_age=100))   # khác kích thước frame
        self.assertIsNone(ov.at(200, (768, 2448), max_age=100))   # quá cũ
        self.assertIsNone(ov.at(5, (768, 2448), max_age=100))     # seq lùi (camera mở lại)


if __name__ == "__main__":
    unittest.main()
