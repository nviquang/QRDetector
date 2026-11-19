"""Lọc chống đọc sai: nội dung dãy số#dãy số, chỉ nhận QR V2-M, mã phải nằm trong vùng đang đọc.

Chạy (từ gốc repo):  python -m unittest tests.test_content_filter
"""
from pathlib import Path
import sys
import unittest
from unittest import mock

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from qr import multiframe  # noqa: E402
from qr.content_filter import CODE_PATTERN, EXPECTED_SYMBOL, accept_text, inside  # noqa: E402
from qr.decoder import read_zxing_gray  # noqa: E402
from qr.multiframe import PassDecoder  # noqa: E402
from qr.tracker import Track  # noqa: E402
from tests.qr_fixtures import qr_image  # noqa: E402

FIELD_CODE = "000000585545#000000001612"   # 25 ký tự: vừa V2-M khi encoder mã hóa cả chuỗi ở chế độ byte


def track():
    return Track(1, 0, 0, (0.0, 0.0), 75.0, observations=2)


def frame_with(code_img, at=(200, 100), shape=(500, 800)):
    frame = np.full((shape[0], shape[1], 3), 255, np.uint8)
    x, y = at
    h, w = code_img.shape
    frame[y:y + h, x:x + w] = code_img[..., None]
    return frame, np.array([x, y, x + w, y + h], np.float32)


class AcceptTextTests(unittest.TestCase):
    def test_number_hash_number_of_any_length(self):
        for text in ("1#2", "000000585545#000000585545", FIELD_CODE):
            self.assertTrue(accept_text(text), text)

    def test_rejects_other_shapes(self):
        for text in ("", None, "1234", "#12", "12#", "12#34#5", "a1#2", "12 #34", "12#34\n", "１２#34"):
            self.assertFalse(accept_text(text), repr(text))

    def test_none_pattern_accepts_any_non_empty_text(self):
        self.assertTrue(accept_text("anything", None))
        self.assertFalse(accept_text("", None))


class SymbolTests(unittest.TestCase):
    def test_v2m_is_accepted(self):
        gray = qr_image(FIELD_CODE, 4, version=2, level="M")
        self.assertEqual(read_zxing_gray(gray, symbol=EXPECTED_SYMBOL)[0], FIELD_CODE)

    def test_other_version_or_level_is_rejected(self):
        for version, level in ((1, "L"), (2, "L"), (2, "Q"), (3, "M")):
            gray = qr_image("12#34", 4, version=version, level=level)
            self.assertEqual(read_zxing_gray(gray)[0], "12#34")                    # đọc được khi không lọc
            self.assertIsNone(read_zxing_gray(gray, symbol=EXPECTED_SYMBOL), (version, level))


class InsideTests(unittest.TestCase):
    def test_center_inside_or_within_margin(self):
        bbox = [100, 100, 200, 200]

        def square(cx, cy):
            return np.array([[cx - 5, cy - 5], [cx + 5, cy - 5], [cx + 5, cy + 5], [cx - 5, cy + 5]])

        self.assertTrue(inside(square(150, 150), bbox))
        self.assertTrue(inside(square(210, 150), bbox))       # lệch 10 px < 15% của 100 px
        self.assertFalse(inside(square(230, 150), bbox))
        self.assertFalse(inside(square(150, 60), bbox))


class PassDecoderFilterTests(unittest.TestCase):
    def test_v2m_field_code_is_read(self):
        frame, bbox = frame_with(qr_image(FIELD_CODE, 4, version=2, level="M"))
        hit = PassDecoder(CODE_PATTERN, symbol=EXPECTED_SYMBOL).read(frame, bbox, None, track(), [])
        self.assertEqual(hit.text, FIELD_CODE)

    def test_v1_code_is_not_a_vote_even_with_valid_content(self):
        frame, bbox = frame_with(qr_image("12#34", 4, version=1, level="L"))
        with mock.patch.object(multiframe, "read_wechat_gray", return_value=None):
            hit = PassDecoder(CODE_PATTERN, symbol=EXPECTED_SYMBOL).read(frame, bbox, None, None, [])
        self.assertIsNone(hit)

    def test_code_outside_bbox_is_rejected_and_logged(self):
        frame, bbox = frame_with(qr_image(FIELD_CODE, 4, version=2, level="M"))
        far = np.array([[0, 0], [10, 0], [10, 10], [0, 10]], np.float32) + 2000   # tem bên cạnh
        with mock.patch.object(multiframe, "read_zxing_gray", return_value=(FIELD_CODE, far)), \
                mock.patch.object(multiframe, "read_wechat_gray", return_value=None), \
                self.assertLogs("solution.qr", "WARNING") as logs:
            self.assertIsNone(PassDecoder(CODE_PATTERN).read(frame, bbox, None, None, []))
        self.assertIn("ngoài vùng", "\n".join(logs.output))


if __name__ == "__main__":
    unittest.main()
