"""PassReader giữ lượt chưa đọc được cho bộ đọc nền, báo một lần khi có kết quả; ranh giới tiến trình dùng bộ giải giả."""
import os
import tempfile
import time
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
        self.stages = {}

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
        self.stages.pop(key, None)
        self.revision += 1

    revision = 0

    def stage(self, key):
        return self.stages.get(key)

    def start(self, key, stage, since=50.0):
        self.stages[key] = (stage, since)
        self.revision += 1


class ScriptedFallback(FakeFallback):
    """Mỗi lần ``wait`` chạy một bước kịch bản (bộ giải đổi giai đoạn / trả kết quả); ``pending`` như PassFallback."""

    def __init__(self, script):
        super().__init__()
        self.script = list(script)

    @property
    def pending(self):
        return len(self.pending_keys)

    def wait(self, timeout):
        if self.script:
            self.script.pop(0)(self)
        done = self.poll()
        for key, *_ in done:
            self.pending_keys.discard(key)
        return done


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
        result = h.run_pass()
        self.assertEqual(len(result.finished), 1)
        self.assertIsNone(result.fallback)

    def test_status_reports_queue_then_stages_only_when_changed(self):
        fallback = FakeFallback()
        h = Harness(fallback)
        h.run_pass()
        closing = h.run_pass()
        self.assertEqual([(s.stage, s.position) for s in closing.fallback], [("queued", 1), ("queued", 2)])
        held_ids = [s.track_id for s in closing.fallback]
        self.assertIsNone(h.step([]).fallback)            # không đổi: không báo lại
        fallback.start(0, "B")
        (b, q) = h.step([]).fallback
        self.assertEqual((b.track_id, b.stage, b.since, b.position), (held_ids[0], "B", 50.0, 0))
        self.assertEqual((q.stage, q.position), ("queued", 1))
        fallback.start(0, "C")
        self.assertEqual(h.step([]).fallback[0].stage, "C")
        fallback.finish(0, None)
        result = h.step([])
        self.assertEqual([s.track_id for s in result.fallback], held_ids[1:])
        self.assertEqual(len(result.finished), 1)

    def test_flush_resets_status_baseline(self):
        fallback = FakeFallback()
        h = Harness(fallback)
        self.assertEqual(len(h.run_pass().fallback), 1)
        h.reader.flush()
        self.assertIsNone(h.step([]).fallback)            # người gọi flush tự xóa trạng thái
        self.assertEqual(h.reader.fallback_status(), [])

    def test_flush_reports_stage_changes_while_waiting(self):
        """Chốt lượt lúc Dừng/hết dữ liệu: bộ giải sang C trong lúc flush chờ thì vẫn phải báo, không đứng ở B."""
        fallback = ScriptedFallback([lambda f: f.start(0, "C"), lambda f: f.finish(0, None)])
        h = Harness(fallback)
        h.run_pass()
        fallback.start(0, "B")
        h.step([])
        seen = []
        tracks = h.reader.flush(on_fallback=seen.append)
        self.assertEqual([[s.stage for s in st] for st in seen], [["C"], []])
        self.assertEqual(len(tracks), 1)
        self.assertEqual(fallback.discarded, 1)

    def test_flush_without_callback_still_waits_for_answer(self):
        fallback = ScriptedFallback([lambda f: f.start(0, "C"), lambda f: f.finish(0, "LATE")])
        h = Harness(fallback)
        h.run_pass()
        self.assertEqual([t.text for t in h.reader.flush()], ["LATE"])

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


PROGRESS_SOURCE = """
import time


class Staged:
    def read_pass(self, obs, ctx, progress=None):
        progress("B")
        time.sleep(0.3)
        progress("C")
        time.sleep(0.5)
        return "ok"
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

    def test_solver_progress_reaches_parent(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "progress_solver.py")
            with open(path, "w", encoding="utf-8") as f:
                f.write(PROGRESS_SOURCE)
            fallback = PassFallback(path + ":Staged")
            try:
                crop = np.zeros((10, 10), np.uint8)
                obs = PassObs(crop, np.zeros(4), np.zeros((4, 2)), None, 0.9, np.zeros(2), 1, 0.0)
                key = fallback.submit([obs], PassCtx((0.0, 1.0), 25.0, 3.0, 0.5))
                seen = []
                done = []
                deadline = time.monotonic() + 120.0
                while not done and time.monotonic() < deadline:
                    done = fallback.poll()
                    stage = fallback.stage(key)
                    if stage and (not seen or seen[-1] != stage[0]):
                        seen.append(stage[0])
                    time.sleep(0.01)
                self.assertEqual(done[0][1], "ok")
                self.assertEqual(seen[-1:], ["C"])           # B có thể qua nhanh giữa hai lần poll
                self.assertIsNone(fallback.stage(key))
            finally:
                fallback.close()

    def test_backlog_limit(self):
        fallback = PassFallback.__new__(PassFallback)
        fallback._failed, fallback._pending, fallback._next_key = False, set(range(MAX_BACKLOG)), MAX_BACKLOG
        self.assertIsNone(fallback.submit([], None))


if __name__ == "__main__":
    unittest.main()
