"""Đối soát theo danh sách mã: dựng QR đúng quy cách (zxing đọc lại được), phân biệt mã liền số, các cổng từ chối."""
import unittest

import cv2
import numpy as np
import zxingcpp

from qr.candidate_match import Gates, LEVEL_M, codewords, encode_segments, match, read_format, render

CODE = "123456789012#000000000123"


def neighbor(text: str, step: int) -> str:
    head, tail = text.split("#")
    return "{}#{:012d}".format(head, (int(tail) + step) % 10 ** 12)


def to_image(dark: np.ndarray, scale: int = 10, quiet: int = 4) -> np.ndarray:
    img = np.where(dark, 0, 255).astype(np.uint8)
    img = cv2.copyMakeBorder(img, quiet, quiet, quiet, quiet, cv2.BORDER_CONSTANT, value=255)
    return cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_NEAREST)


def clean_probs(dark: np.ndarray) -> np.ndarray:
    return np.where(dark, 0.95, 0.05)


class EncodeTests(unittest.TestCase):
    def test_spec_content_fills_version1_m_exactly(self):
        data = encode_segments(CODE, 16)
        self.assertEqual(len(data), 16)
        self.assertNotIn(0xEC, data[-1:])           # 128 bit vừa khít: không có byte đệm
        self.assertIsNone(encode_segments(CODE + "0", 16))

    def test_zxing_reads_rendered_symbol_for_every_mask(self):
        for mask in range(8):
            dark = render(CODE, mask=mask)
            self.assertEqual(dark.shape, (21, 21))
            hits = zxingcpp.read_barcodes(to_image(dark), formats=zxingcpp.BarcodeFormat.QRCode)
            self.assertEqual([h.text for h in hits], [CODE], "mask {}".format(mask))

    def test_neighbor_codes_differ_in_at_least_11_codewords(self):
        a = codewords(CODE)
        for step in (1, 2, 10):
            b = codewords(neighbor(CODE, step))
            self.assertGreaterEqual(sum(x != y for x, y in zip(a, b)), 11)

    def test_format_recovers_level_and_mask(self):
        for mask in (0, 5):
            self.assertEqual(read_format(clean_probs(render(CODE, mask=mask)))[:2], (LEVEL_M, mask))


class MatchTests(unittest.TestCase):
    def setUp(self):
        self.mask = 3
        self.probs = clean_probs(render(CODE, mask=self.mask))
        self.candidates = [neighbor(CODE, s) for s in range(-10, 11)]   # gồm cả CODE (s = 0)

    def test_clean_symbol_picks_true_code_over_neighbors(self):
        result = match(self.probs, self.candidates)
        self.assertEqual((result.text, result.reason, result.mask), (CODE, "ok", self.mask))
        self.assertGreater(result.margin, Gates().min_margin)

    def test_code_missing_from_list_is_rejected_not_forced(self):
        result = match(self.probs, [c for c in self.candidates if c != CODE])
        self.assertIsNone(result.text)
        self.assertEqual(result.reason, "mismatch")

    def test_small_glare_area_still_matches(self):
        probs = self.probs.copy()
        probs[15:21, 15:21] = np.nan                # góc dưới phải bị chói
        self.assertEqual(match(probs, self.candidates).text, CODE)

    def test_glare_hiding_too_many_bytes_is_rejected_even_if_code_missing(self):
        probs = self.probs.copy()
        probs[:, :13] = np.nan                      # che hơn nửa trái: phần lớn byte sửa lỗi
        probs[:9, :9] = self.probs[:9, :9]          # vẫn đọc được format
        others = [c for c in self.candidates if c != CODE]
        self.assertEqual(match(probs, self.candidates).reason, "bytes")
        self.assertIsNone(match(probs, others).text)

    def test_no_evidence_is_rejected(self):
        probs = np.full((21, 21), 0.5)
        probs[:9, :9] = self.probs[:9, :9]           # chỉ đọc được vùng format quanh góc trên trái
        self.assertEqual(match(probs, self.candidates).reason, "evidence")

    def test_symbol_printed_with_other_level_is_rejected(self):
        probs = clean_probs(render(CODE, level=1, mask=self.mask))   # in nhầm mức L
        self.assertEqual(match(probs, self.candidates).reason, "format")


if __name__ == "__main__":
    unittest.main()
