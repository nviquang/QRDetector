"""PassTracker — gom detection qua các frame thành lượt QR. Không cần model/camera.

Chạy (từ solution/):  python -m unittest tests.test_tracker
"""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from qr.tracker import Observation, PassTracker  # noqa: E402


def _run(tracker, frames):
    done = []
    for idx, obs in frames:
        done += tracker.update(idx, obs)
    return done + tracker.finish()


class PassTrackerTests(unittest.TestCase):
    def test_one_qr_crossing_is_one_pass(self):
        frames = [(i, [Observation((100 + 45 * i, 500), 60, "A" if i in (5, 9) else None)])
                  for i in range(40)]
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
        frames += [(i, []) for i in range(10, 13)]
        frames += [(i, [Observation((100 + 45 * i, 500), 60)]) for i in range(13, 20)]
        self.assertEqual(len(_run(PassTracker(max_gap=5), frames)), 1)

    def test_conflicting_reads_flagged_and_majority_wins(self):
        frames = [(i, [Observation((100 + 10 * i, 500), 60, t)]) for i, t in enumerate("AABA")]
        (track,) = _run(PassTracker(), frames)
        self.assertEqual(track.text, "A")
        self.assertTrue(track.conflicting)

    # ── mới trong solution ──

    def test_match_does_not_mutate_tracks(self):
        tracker = PassTracker()
        tracker.update(0, [Observation((100, 500), 60, "A")])
        matched = tracker.match(1, [Observation((130, 500), 60)])
        self.assertEqual(list(matched), [0])
        self.assertEqual(matched[0].observations, 1)
        self.assertEqual(matched[0].last_frame, 0)
        self.assertEqual(matched[0].center, (100, 500))

    def test_match_ignores_stale_tracks(self):
        tracker = PassTracker(max_gap=5)
        tracker.update(0, [Observation((100, 500), 60, "A")])
        self.assertEqual(tracker.match(10, [Observation((100, 500), 60)]), {})

    def test_match_pairs_same_as_update(self):
        tracker = PassTracker()
        tracker.update(0, [Observation((100, 200), 60, "A"), Observation((100, 600), 60, "B")])
        obs = [Observation((140, 600), 60), Observation((140, 200), 60)]
        matched = {i: t.track_id for i, t in tracker.match(1, obs).items()}
        tracker.update(1, obs)
        self.assertEqual(matched, {0: 1, 1: 0})
        self.assertEqual(sorted(t.observations for t in tracker.finish()), [2, 2])

    def test_votes_is_count_of_majority_text(self):
        tracker = PassTracker()
        for i, t in enumerate(["A", None, "A", "B"]):
            tracker.update(i, [Observation((100 + 10 * i, 500), 60, t)])
        (track,) = tracker.finish()
        self.assertEqual((track.text, track.votes), ("A", 2))
        self.assertEqual(PassTracker()._start(0, Observation((0, 0), 60)).votes, 0)


if __name__ == "__main__":
    unittest.main()
