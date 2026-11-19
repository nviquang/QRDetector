"""Bộ đọc nền B (grid_sr) và C (preproc_sweep) chuẩn V2-M, trên lượt tổng hợp ở ~2,2 px/ô.

Chậm (vài giây mỗi ca): chạy riêng bằng  python -m unittest tests.test_solvers_v2m
"""
from pathlib import Path
import sys
import time
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from qr.pass_fallback import _load_solver  # noqa: E402
from tests.v2m_synth import blank_pass, make_pass  # noqa: E402

CODE = "000000585545#000000001612"


def solver(name):
    return _load_solver({"B": "grid_sr/grid_sr.py:GridSR", "C": "preproc_sweep/preproc_sweep.py:PreprocSweep"}[name])


class ChaseBudgetTests(unittest.TestCase):
    def setUp(self):
        sys.modules.pop("qr_active_solver", None)
        self.gs = sys.modules[type(solver("B")).__module__]

    def test_random_word_gives_no_candidate_within_budget(self):
        rng = np.random.default_rng(0)
        found = 0
        for _ in range(30):
            word = [int(v) for v in rng.integers(0, 256, 44)]
            found += len(self.gs.chase_block(word, rng.random(44), 16))
        self.assertEqual(found, 0)

    def test_correctable_word_is_found(self):
        qrspec = sys.modules["qrspec"]
        data = list(range(28))
        cw = data + qrspec.rs_encode(data, 16)
        bad = list(cw)
        for i in (3, 10, 20):
            bad[i] ^= 0x5A
        rel = np.ones(44)
        cands = self.gs.chase_block(bad, rel, 16)
        self.assertIn(tuple(cw), cands)


class SolverTests(unittest.TestCase):
    def test_b_reads_blurred_v2m_that_plain_decoding_misses(self):
        obs, ctx = make_pass(ppm=2.2, sigma=(1.4, 1.4), seed=1, angle=34)   # từng frame không đọc được (đo)
        self.assertEqual(solver("B").read_pass(obs, ctx), CODE)

    def test_blank_pass_is_rejected(self):
        for name, limit in (("B", 10.0), ("C", 30.0)):     # đo trên Ryzen 5 5500U: B ~4,5 s, C ~13 s
            obs, ctx = blank_pass()
            t = time.time()
            self.assertIsNone(solver(name).read_pass(obs, ctx), name)
            self.assertLess(time.time() - t, limit, name)

    def test_v1_symbol_is_not_reported(self):
        obs, ctx = make_pass(text="12#34", version=1, level="L", ppm=2.2, sigma=(0.7, 0.7))
        for name in "BC":
            self.assertIsNone(solver(name).read_pass(obs, ctx), name)

    def test_neighbour_label_alone_is_not_reported(self):
        # tem đang đọc bị mờ hẳn (không đọc được), tem bên cạnh nét lọt một phần vào crop
        obs, ctx = make_pass(text="000000585545#000000009999", ppm=2.2, sigma=(3.0, 3.0), seed=1,
                             neighbor=(CODE, (95.0, 0.0)))
        for name in "BC":
            self.assertNotEqual(solver(name).read_pass(obs, ctx), CODE, name)


if __name__ == "__main__":
    unittest.main()
