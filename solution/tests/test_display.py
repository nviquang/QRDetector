"""Vẽ quad lên frame hiển thị: bù vận tốc, bỏ quad cũ/khác kích thước; chuyển frame → QImage.

Chạy (từ solution/):  python -m unittest tests.test_display
"""
from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from qr.pass_reader import Overlay  # noqa: E402  (torch trước PyQt5)
from tests import test_camera_diagnostics as fake  # noqa: E402  (stub mvsdk/qr + import ui)

draw_overlays = fake.window_module.draw_overlays

SQUARE = np.array([[50, 50], [90, 50], [90, 90], [50, 90]], np.float32)
GREEN, RED = (0, 255, 0), (0, 0, 255)


class DrawOverlayTests(unittest.TestCase):
    def setUp(self):
        self.frame = np.zeros((200, 300, 3), np.uint8)

    def test_quad_is_shifted_by_velocity_to_current_seq(self):
        ov = Overlay(SQUARE, True, (5.0, 0.0), seq=10, shape=(200, 300))
        vis = draw_overlays(self.frame, [ov], seq=14)
        self.assertEqual(tuple(vis[70, 70]), GREEN)       # cạnh trái mới: 50 + 5 × 4
        self.assertEqual(tuple(vis[70, 50]), (0, 0, 0))   # cạnh trái cũ không còn vẽ
        self.assertEqual(tuple(self.frame[70, 70]), (0, 0, 0))   # không vẽ đè frame gốc

    def test_unread_qr_is_red(self):
        vis = draw_overlays(self.frame, [Overlay(SQUARE, False, (0.0, 0.0), 3, (200, 300))], seq=3)
        self.assertEqual(tuple(vis[70, 50]), RED)

    def test_overlay_from_other_shape_is_not_drawn(self):
        ov = Overlay(SQUARE, True, (0.0, 0.0), seq=3, shape=(2048, 2448))
        self.assertIs(draw_overlays(self.frame, [ov], seq=3), self.frame)

    def test_stale_overlay_is_not_drawn(self):
        ov = Overlay(SQUARE, True, (0.0, 0.0), seq=3, shape=(200, 300))
        self.assertIs(draw_overlays(self.frame, [ov], seq=3 + 101, max_age=100), self.frame)


if __name__ == "__main__":
    unittest.main()
