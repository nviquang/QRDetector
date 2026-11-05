"""PassReader ở chế độ nhiều frame: đoán ROI giữa các lần YOLO, cổng kích thước, nhịp decode, lọc phiếu.

Chạy (từ gốc repo):  python -m unittest tests.test_pass_reader_multiframe
"""
from pathlib import Path
import sys
import unittest
from unittest import mock

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from qr.improved_pipeline import Decoded  # noqa: E402
from qr.pass_reader import PassReader  # noqa: E402
from qr.tracker import PassTracker  # noqa: E402
from tests.qr_fixtures import detection_at  # noqa: E402

IMG = np.zeros((768, 2448, 3), np.uint8)
CORNERS = np.array([[1, 1], [9, 1], [9, 9], [1, 9]], np.float32)
CODE = "000000585545"


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


class FakePipeline:
    multi_frame = True
    code_pattern = None
    roi_margin = 0.25

    def __init__(self, frames):
        self.frames = list(frames)
        self.detect_calls = 0

    def warmup(self):
        pass

    def detect(self, image_bgr):
        self.detect_calls += 1
        return self.frames.pop(0)


class FakeDecoder:
    """Thay PassDecoder: trả lần lượt ``answers``, ghi lại các lần gọi."""

    def __init__(self, answers):
        self.answers = list(answers)
        self.calls = []
        self.forgotten = []

    def read(self, image, bbox, det, track, blur_lengths, cheap_only=False):
        self.calls.append(dict(bbox=bbox, det=det, track=track, blur=blur_lengths, cheap=cheap_only))
        text = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        return Decoded(text, CORNERS) if text else None

    def forget(self, track_id):
        self.forgotten.append(track_id)


def make_reader(frames, answers, **kw):
    clock = Clock()
    pipe = FakePipeline(frames)
    reader = PassReader(pipe, clock=clock, **kw)
    decoder = FakeDecoder(answers)
    reader._decoder = decoder
    return reader, pipe, decoder, clock


def moving(n, y=300, start=500, step=45):
    return [[detection_at(start + step * i, y)] for i in range(n)]


class FastJobTests(unittest.TestCase):
    def two_sightings(self, answers, frames=None):
        reader, pipe, decoder, clock = make_reader(frames or moving(5), answers)
        reader.process(IMG, 0)
        clock.now += 0.5
        reader.process(IMG, 1)     # 2 lần thấy → lượt có vận tốc 45 px/seq
        return reader, pipe, decoder, clock

    def test_track_read_between_yolo_runs_without_detect(self):
        reader, pipe, decoder, clock = self.two_sightings([None, None, CODE])
        clock.now += 0.1
        result = reader.process(IMG, 3)
        self.assertEqual(pipe.detect_calls, 2)
        self.assertEqual(result.detections, [])
        self.assertEqual(result.detect_ms, 0.0)
        self.assertEqual([t.text for t in result.first_reads], [CODE])
        self.assertEqual(result.results, [CODE])

    def test_fast_job_predicts_position_and_runs_cheap_only(self):
        reader, _, decoder, clock = self.two_sightings([None])
        clock.now += 0.1
        reader.process(IMG, 3)
        call = decoder.calls[-1]
        self.assertTrue(call["cheap"])
        self.assertIsNone(call["det"])
        x1, y1, x2, y2 = call["bbox"]
        # lần cuối thấy ở seq 1 tâm x=545, vận tốc 45 → seq 3 tâm 635
        self.assertAlmostEqual(float(x1 + x2) / 2, 635.0, delta=0.5)
        self.assertAlmostEqual(float(y1 + y2) / 2, 300.0, delta=0.5)

    def test_yolo_runs_again_after_interval(self):
        reader, pipe, _, clock = self.two_sightings([None])
        clock.now += 0.5
        reader.process(IMG, 3)
        self.assertEqual(pipe.detect_calls, 3)

    def test_no_fast_job_for_first_sighting(self):
        reader, pipe, _, clock = make_reader(moving(3), [None])
        reader.process(IMG, 0)
        clock.now += 0.1
        reader.process(IMG, 2)
        self.assertEqual(pipe.detect_calls, 2)

    def test_no_fast_job_once_read(self):
        reader, pipe, _, clock = self.two_sightings([None, CODE])
        clock.now += 0.1
        reader.process(IMG, 3)
        self.assertEqual(pipe.detect_calls, 3)

    def test_no_fast_job_when_predicted_outside_frame(self):
        reader, pipe, _, clock = self.two_sightings([None])
        clock.now += 0.1
        reader.process(IMG, 60)     # 545 + 59×45 > 2448
        self.assertEqual(pipe.detect_calls, 3)

    def test_fast_job_keeps_last_overlays(self):
        reader, _, _, clock = self.two_sightings([None])
        clock.now += 0.1
        result = reader.process(IMG, 3)
        self.assertEqual(len(result.overlays), 1)
        self.assertEqual(result.overlays[0].seq, 1)

    def test_decode_every_shortens_while_track_awaits_read(self):
        reader, _, _, clock = make_reader(moving(5), [None])
        self.assertEqual(reader.decode_every(5), 5)
        reader.process(IMG, 0)
        self.assertEqual(reader.decode_every(5), 5)
        clock.now += 0.5
        reader.process(IMG, 1)
        self.assertEqual(reader.decode_every(5), 2)

    def test_decode_every_returns_default_once_read(self):
        reader, _, _, clock = make_reader(moving(5), [None, CODE])
        reader.process(IMG, 0)
        clock.now += 0.5
        reader.process(IMG, 1)
        self.assertEqual(reader.decode_every(5), 5)


class GateTests(unittest.TestCase):
    def test_qr_touching_edge_skips_decoder(self):
        reader, _, decoder, _ = make_reader([[detection_at(20, 300)]], [CODE])
        result = reader.process(IMG, 0)
        self.assertEqual(decoder.calls, [])
        self.assertEqual(result.texts, [None])
        self.assertEqual(len(result.overlays), 1)

    def test_size_far_from_recent_reads_skips_decoder(self):
        frames = [[detection_at(500 + i, 300, size=60)] for i in range(3)] + [[detection_at(1500, 300, size=200)]]
        reader, _, decoder, clock = make_reader(frames, [CODE])
        for i in range(3):
            reader.process(IMG, i * 200)   # lượt mới mỗi lần → mỗi lần đọc một kích thước
            clock.now += 1.0
        before = len(decoder.calls)
        reader.process(IMG, 1000)
        self.assertEqual(len(decoder.calls), before)

    def test_elongated_detection_skips_decoder(self):
        det = detection_at(500, 300)
        det.bbox_xyxy = np.array([400, 280, 600, 320], np.float32)
        reader, _, decoder, _ = make_reader([[det]], [CODE])
        reader.process(IMG, 0)
        self.assertEqual(decoder.calls, [])


class VotesAndTrackerTests(unittest.TestCase):
    def test_one_vote_is_enough_to_skip(self):
        reader, _, decoder, clock = make_reader(moving(3), [CODE])
        reader.process(IMG, 0)
        clock.now += 0.5
        result = reader.process(IMG, 1)
        self.assertEqual((len(decoder.calls), result.skipped, result.texts), (1, 1, [CODE]))

    def test_default_tracker_is_strict(self):
        reader, *_ = make_reader([], [CODE])
        self.assertTrue(reader._tracker.strict)

    def test_explicit_tracker_is_kept(self):
        tracker = PassTracker(max_gap=5)
        reader, *_ = make_reader([], [CODE], tracker=tracker)
        self.assertIs(reader._tracker, tracker)

    def test_closed_track_is_forgotten(self):
        reader, _, decoder, clock = make_reader(moving(1) + [[]], [None])
        reader.process(IMG, 0)
        clock.now += 1.0
        reader.process(IMG, 500)
        self.assertEqual(decoder.forgotten, [0])


class BlurLengthTests(unittest.TestCase):
    def full_job(self, exposure_ms):
        frames = moving(3, step=10)
        reader, _, decoder, clock = make_reader(frames, [None])
        if exposure_ms is not None:
            reader.set_exposure_ms(exposure_ms)
        reader.process(IMG, 0)
        clock.now += 0.2       # 10 seq trong 0,2 s → 50 seq/s
        reader.process(IMG, 10)
        clock.now += 0.5
        reader.process(IMG, 11)
        return decoder.calls[-1]["blur"]

    def test_length_from_speed_and_exposure(self):
        # 1 px/seq × khoảng 50 seq/s × 60 ms ≈ 3 px, thêm một độ dài ×1,3 phòng vận tốc lệch
        np.testing.assert_allclose(self.full_job(60.0), [3.0, 3.9], atol=1.0)

    def test_short_blur_is_not_deblurred(self):
        self.assertEqual(self.full_job(1.0), [])

    def test_unknown_exposure_tries_common_lengths(self):
        self.assertEqual(self.full_job(None), [2.0, 3.0, 4.5, 6.5])

    def test_set_exposure_without_multi_frame_is_harmless(self):
        reader = PassReader(mock.Mock(spec=["warmup", "detect", "decode_detection"]))
        reader.set_exposure_ms(5.0)
        self.assertEqual(reader.decode_every(5), 5)


if __name__ == "__main__":
    unittest.main()
