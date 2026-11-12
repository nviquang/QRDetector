"""PassReader giữ lượt chưa đọc được cho bộ đọc nền, báo một lần khi có kết quả; ranh giới tiến trình dùng bộ giải giả."""
import os
import tempfile
import unittest

import numpy as np

from qr.detector import Detection
from qr.pass_fallback import MAX_BACKLOG, PassCtx, PassFallback, PassObs
from qr.pass_reader import PassReader


def det(x, y, side=60.0):
    box = np.array([x, y, x + side, y + side], np.float32)
    quad = np.array([[x, y], [x + side, y], [x + side, y + side], [x, y + side]], np.float32)
    return Detection(box, quad, 0.9, None)


class FakePipeline:
    multi_frame = True
    code_pattern = None
    roi_margin = 0.25

    def __init__(self):
        self.next = []

    def detect(self, image):
        return self.next

    def warmup(self):
        pass


class FakeFallback:
    def __init__(self, full=False):
        self.jobs, self.results, self.full, self.discarded = [], [], full, 0
        self.pending_keys = set()

    def submit(self, obs, ctx):
        if self.full:
            return None
        key = len(self.jobs)
        self.jobs.append((obs, ctx))
        self.pending_keys.add(key)
        return key

    def poll(self):
        done, self.results = self.results, []
        return done

    def wait(self, timeout):
        return self.poll()

    def discard(self):
        self.discarded += 1

    def finish(self, key, text):
        self.results.append((key, text, 12.0, None))


class Harness:
    def __init__(self, fallback):
        self.pipe = FakePipeline()
        self.now = [0.0]
        self.reader = PassReader(self.pipe, fallback=fallback, clock=lambda: self.now[0])
        self.image = np.full((600, 800, 3), 128, np.uint8)
        self.seq = 0

    def step(self, dets):
        self.seq += 1
        self.now[0] += 1.0
        self.pipe.next = dets
        return self.reader.process(self.image, self.seq)

    def run_pass(self, frames=6):
        for i in range(frames):
            self.step([det(300.0, 100.0 + 20.0 * i)])
        self.seq += 200                # quá max_gap: lượt đóng ở frame kế tiếp
        return self.step([])


class ReaderHoldTest(unittest.TestCase):
    def test_unread_pass_is_held_until_solver_answers(self):
        fallback = FakeFallback()
        h = Harness(fallback)
        closing = h.run_pass()
        self.assertEqual(closing.finished, [])
        self.assertEqual(len(fallback.jobs), 1)
        obs, ctx = fallback.jobs[0]
        self.assertEqual(len(obs), 5)
        self.assertEqual(obs[0].gray.ndim, 2)
        self.assertAlmostEqual(ctx.velocity[1], 20.0, places=1)
        fallback.finish(0, "ABC123")
        result = h.step([])
        self.assertEqual([t.text for t in result.first_reads], ["ABC123"])
        self.assertEqual([t.text for t in result.finished], ["ABC123"])
        self.assertEqual(result.finished[0].votes, 2)
        self.assertEqual(h.step([]).first_reads, [])

    def test_solver_none_finishes_pass_unread(self):
        fallback = FakeFallback()
        h = Harness(fallback)
        h.run_pass()
        fallback.finish(0, None)
        result = h.step([])
        self.assertEqual(result.first_reads, [])
        self.assertEqual(len(result.finished), 1)
        self.assertIsNone(result.finished[0].text)

    def test_full_queue_finishes_pass_unread(self):
        h = Harness(FakeFallback(full=True))
        self.assertEqual(len(h.run_pass().finished), 1)

    def test_flush_returns_answered_and_abandons_the_rest(self):
        fallback = FakeFallback()
        h = Harness(fallback)
        h.run_pass()
        h.run_pass()
        self.assertEqual(len(fallback.jobs), 2)
        fallback.finish(1, "LATE")
        tracks = h.reader.flush()
        self.assertEqual(sorted(str(t.text) for t in tracks), ["LATE", "None"])
        self.assertEqual([t.text for t in h.reader.take_late_reads()], ["LATE"])
        self.assertEqual(fallback.discarded, 1)
        self.assertEqual(h.reader.take_late_reads(), [])

    def test_without_fallback_pass_finishes_immediately(self):
        h = Harness(None)
        self.assertEqual(len(h.run_pass().finished), 1)

    def test_short_pass_is_not_sent(self):
        fallback = FakeFallback()
        h = Harness(fallback)
        self.assertEqual(len(h.run_pass(frames=1).finished), 1)
        self.assertEqual(fallback.jobs, [])


SOLVER_SOURCE = """
class Fake:
    def read_pass(self, obs, ctx):
        if obs[0].frame == 99:
            raise ValueError("hỏng")
        return "n={}:v={}".format(len(obs), ctx.velocity[1])
"""


class ProcessBoundaryTest(unittest.TestCase):
    def test_round_trip_and_solver_error(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "fake_solver.py")
            with open(path, "w", encoding="utf-8") as f:
                f.write(SOLVER_SOURCE)
            fallback = PassFallback(path + ":Fake")
            try:
                crop = np.zeros((10, 10), np.uint8)
                obs = PassObs(crop, np.zeros(4), np.zeros((4, 2)), None, 0.9, np.zeros(2), 1, 0.0)
                ctx = PassCtx((0.0, 7.0), 25.0, 3.0, 0.5)
                good = fallback.submit([obs, obs], ctx)
                bad_obs = PassObs(crop, np.zeros(4), np.zeros((4, 2)), None, 0.9, np.zeros(2), 99, 0.0)
                bad = fallback.submit([bad_obs], ctx)
                done = {key: (text, error) for key, text, _, error in fallback.wait(120.0)}
                self.assertEqual(done[good], ("n=2:v=7.0", None))
                self.assertIsNone(done[bad][0])
                self.assertIn("hỏng", done[bad][1])
            finally:
                fallback.close()

    def test_backlog_limit(self):
        fallback = PassFallback.__new__(PassFallback)
        fallback._failed, fallback._pending, fallback._next_key = False, set(range(MAX_BACKLOG)), MAX_BACKLOG
        self.assertIsNone(fallback.submit([], None))


if __name__ == "__main__":
    unittest.main()
