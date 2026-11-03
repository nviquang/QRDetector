"""DecodeWorker dùng PassReader: signal kết quả/thời gian/lượt, warm-up, flush khi dừng.

Chạy (từ gốc repo):  python -m unittest tests.test_decode_worker
"""
import importlib.util
import os
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch

import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# qr (torch) PHẢI import trước PyQt5 — xem CLAUDE.md
from qr.improved_pipeline import Decoded  # noqa: E402
from qr.pass_reader import PassReader  # noqa: E402
from tests.qr_fixtures import detection_at  # noqa: E402

_manager = types.ModuleType("camera.camera_manager")
_manager.CameraManager = Mock()
_qr = types.ModuleType("qr")
_qr.ImprovePipeline = Mock()
_qr.PassReader = PassReader
_spec = importlib.util.spec_from_file_location("ui._decode_worker_test", ROOT / "ui" / "main_window.py")
window_module = importlib.util.module_from_spec(_spec)
with patch.dict(sys.modules, {"camera.camera_manager": _manager, "qr": _qr}):
    _spec.loader.exec_module(window_module)

FRAME = np.zeros((768, 2448, 3), np.uint8)


class FakePipeline:
    def __init__(self, fail=False):
        self.fail = fail
        self.warmups = 0

    def warmup(self):
        self.warmups += 1

    def detect(self, image_bgr):
        if self.fail:
            raise RuntimeError("detect hỏng")
        return [detection_at(100, 300)]

    def decode_detection(self, image_bgr, det):
        return Decoded("A", det.quad_xy)


class DecodeWorkerTests(unittest.TestCase):
    def make(self, pipeline):
        worker = window_module.DecodeWorker(pipeline)
        worker.stop()                    # dừng thread nền — test gọi _process trực tiếp
        self.done, self.stats, self.passes, self.failed = [], [], [], []
        worker.done.connect(lambda r, o: self.done.append((r, o)))
        worker.stats.connect(self.stats.append)
        worker.passes.connect(self.passes.append)
        worker.failed.connect(self.failed.append)
        return worker

    def test_thread_warms_up_pipeline_first(self):
        pipe = FakePipeline()
        self.make(pipe)
        self.assertEqual(pipe.warmups, 1)

    def test_process_emits_results_overlays_and_stage_stats(self):
        worker = self.make(FakePipeline())
        worker._process(FRAME, 1)
        (results, overlays), = self.done
        self.assertEqual(results, ["A"])
        self.assertEqual([(o.ok, o.seq) for o in overlays], [(True, 1)])
        self.assertEqual(set(self.stats[0]), {"detect_ms", "cascade_ms", "skipped"})

    def test_failure_emits_failed_and_no_result(self):
        worker = self.make(FakePipeline(fail=True))
        worker._process(FRAME, 1)
        self.assertEqual(self.failed, ["detect hỏng"])
        self.assertEqual(self.done, [])

    def test_stop_flushes_open_passes_when_thread_finished(self):
        worker = self.make(FakePipeline())
        worker._process(FRAME, 1)
        worker._process(FRAME, 2)
        worker.stop()
        (tracks,) = self.passes
        self.assertEqual([t.text for t in tracks], ["A"])

    def test_stop_skips_flush_while_thread_alive(self):
        worker = self.make(FakePipeline())
        worker._process(FRAME, 1)
        worker._thread = Mock()
        worker._thread.is_alive.return_value = True
        worker.stop()
        self.assertEqual(self.passes, [])

    def test_submit_keeps_seq_with_frame(self):
        worker = self.make(FakePipeline())
        self.assertTrue(worker.submit(FRAME, 7))
        self.assertEqual(worker._pending[1], 7)
        self.assertFalse(worker.submit(FRAME, 8))     # đang có frame chờ → bỏ


if __name__ == "__main__":
    unittest.main()
