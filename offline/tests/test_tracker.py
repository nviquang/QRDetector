"""Unit test PassTracker và chỉ số ROI của eval_videos — không cần model/video.

Chạy:  python -m unittest offline/tests/test_tracker.py
"""

import os
import sys
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from qr.tracker import Observation, PassTracker  # noqa: E402


def _run(tracker, frames):
    done = []
    for idx, obs in frames:
        done += tracker.update(idx, obs)
    return done + tracker.finish()


class PassTrackerTests(unittest.TestCase):
    def test_one_qr_crossing_is_one_pass(self):
        # QR 60px chạy 45 px/frame theo x, decode được ở 2 frame
        frames = [(i, [Observation((100 + 45 * i, 500), 60, "A" if i in (5, 9) else None)]) for i in range(40)]
        passes = _run(PassTracker(), frames)
        self.assertEqual(len(passes), 1)
        self.assertEqual(passes[0].text, "A")
        self.assertEqual(passes[0].observations, 40)

    def test_two_labels_side_by_side_stay_separate(self):
        frames = [(i, [Observation((100 + 45 * i, 500), 60, "A"),
                       Observation((100 + 45 * i, 700), 60, "B")]) for i in range(20)]
        passes = sorted(_run(PassTracker(), frames), key=lambda t: t.track_id)
        self.assertEqual([p.text for p in passes], ["A", "B"])
        self.assertFalse(any(p.conflicting for p in passes))

    def test_gap_longer_than_max_gap_splits_passes(self):
        frames = [(i, [Observation((500, 500), 60)]) for i in range(5)]
        frames += [(i, [Observation((500, 500), 60)]) for i in range(20, 25)]
        self.assertEqual(len(_run(PassTracker(max_gap=5), frames)), 2)

    def test_short_dropout_is_bridged_by_velocity(self):
        frames = [(i, [Observation((100 + 45 * i, 500), 60)]) for i in range(10)]
        frames += [(i, []) for i in range(10, 13)]                       # mất detect 3 frame
        frames += [(i, [Observation((100 + 45 * i, 500), 60)]) for i in range(13, 20)]
        self.assertEqual(len(_run(PassTracker(max_gap=5), frames)), 1)

    def test_conflicting_reads_flagged_and_majority_wins(self):
        frames = [(i, [Observation((100 + 10 * i, 500), 60, t)]) for i, t in enumerate("AABA")]
        (track,) = _run(PassTracker(), frames)
        self.assertEqual(track.text, "A")
        self.assertTrue(track.conflicting)


class RoiMetricTests(unittest.TestCase):
    def test_horizontal_motion_blur_raises_blur_ratio(self):
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from eval_videos import roi_metrics
        rng = np.random.default_rng(0)
        img = (rng.integers(0, 2, (21, 21)) * 200 + 30).astype(np.uint8)
        img = cv2.resize(img, (63, 63), interpolation=cv2.INTER_NEAREST)
        sharp = roi_metrics(img)
        blurred = roi_metrics(cv2.blur(img, (7, 1)))
        self.assertLess(abs(sharp["blur_ratio"] - 1.0), 0.3)
        self.assertGreater(blurred["blur_ratio"], 1.5)
        self.assertLess(blurred["sharpness"], sharp["sharpness"])


if __name__ == "__main__":
    unittest.main()
