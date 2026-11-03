"""SessionStats — số liệu màn hình làm việc, không cần Qt/camera.

Chạy (từ solution/):  python -m unittest tests.test_session_stats
"""
from pathlib import Path
import sys
import types
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from demo_ui.session_stats import RowState, SessionStats, age_text  # noqa: E402


def track(track_id=1, text="A", observations=5, conflicting=False):
    return types.SimpleNamespace(track_id=track_id, text=text, observations=observations,
                                 conflicting=conflicting)


class SessionStatsTests(unittest.TestCase):
    def setUp(self):
        self.now = [100.0]
        self.stats = SessionStats(monotonic=lambda: self.now[0], clock=lambda: "16:02:11")

    def test_rate_and_speed_are_empty_before_any_finished_pass(self):
        self.stats.begin_run()
        self.stats.on_reads([track()])
        self.assertIsNone(self.stats.read_rate)
        self.assertIsNone(self.stats.per_minute())
        self.assertEqual(self.stats.read_count, 0)

    def test_first_read_creates_reading_row_and_updates_latest(self):
        (row,) = self.stats.on_reads([track(7, "A")])
        self.assertEqual((row.track_id, row.text, row.clock, row.state),
                         (7, "A", "16:02:11", RowState.READING))
        self.assertEqual((self.stats.latest_text, self.stats.latest_clock), ("A", "16:02:11"))

    def test_finished_pass_updates_same_row_with_majority_text_and_counts(self):
        self.stats.on_reads([track(1, "A")])
        self.now[0] = 110.0
        (row,) = self.stats.on_passes([track(1, "B", conflicting=True)])
        self.assertEqual((row.track_id, row.text, row.state), (1, "B", RowState.CONFLICT))
        self.assertEqual(row.clock, "16:02:11")
        self.assertEqual((self.stats.read_count, self.stats.conflict_count), (1, 1))

    def test_unread_pass_with_several_detections_is_a_failed_row(self):
        (row,) = self.stats.on_passes([track(2, None, observations=4)])
        self.assertEqual((row.text, row.state), (None, RowState.FAILED))
        self.assertEqual(self.stats.read_rate, 0.0)

    def test_single_detection_without_text_is_noise_and_not_counted(self):
        self.assertEqual(self.stats.on_passes([track(3, None, observations=1)]), [])
        self.assertIsNone(self.stats.read_rate)
        self.assertEqual(self.stats.noise_count, 1)

    def test_single_detection_with_text_counts_as_read(self):
        self.stats.on_passes([track(3, "A", observations=1)])
        self.assertEqual(self.stats.read_rate, 1.0)

    def test_read_rate_ratio(self):
        self.stats.on_passes([track(1, "A"), track(2, "B"), track(3, None)])
        self.assertAlmostEqual(self.stats.read_rate, 2 / 3)

    def test_per_minute_uses_elapsed_time_until_window_is_full(self):
        self.stats.begin_run()
        self.now[0] = 130.0
        self.stats.on_passes([track(1), track(2)])
        self.assertAlmostEqual(self.stats.per_minute(), 4.0)
        self.now[0] = 180.0
        self.assertAlmostEqual(self.stats.per_minute(), 2.0)
        self.now[0] = 191.0
        self.assertEqual(self.stats.per_minute(), 0.0)

    def test_per_minute_does_not_spike_right_after_start(self):
        self.stats.begin_run()
        self.now[0] = 101.0
        self.stats.on_passes([track(1)])
        self.assertAlmostEqual(self.stats.per_minute(), 6.0)

    def test_elapsed_accumulates_over_runs(self):
        self.stats.begin_run()
        self.now[0] = 110.0
        self.stats.end_run()
        self.now[0] = 500.0
        self.assertEqual(self.stats.elapsed(), 10.0)
        self.stats.begin_run()
        self.now[0] = 505.0
        self.assertEqual(self.stats.elapsed(), 15.0)

    def test_reset_clears_everything(self):
        self.stats.begin_run()
        self.stats.on_reads([track()])
        self.stats.on_passes([track()])
        self.stats.reset()
        self.assertEqual((self.stats.read_count, self.stats.latest_text, self.stats.elapsed()),
                         (0, None, 0.0))
        self.assertIsNone(self.stats.read_rate)

    def test_age_text(self):
        self.assertEqual(age_text(0.4), "vừa xong")
        self.assertEqual(age_text(12), "12 giây trước")
        self.assertEqual(age_text(130), "2 phút trước")


if __name__ == "__main__":
    unittest.main()
