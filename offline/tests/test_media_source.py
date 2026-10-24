"""Test offline cho media_source và results — không cần model QR.

Chạy (từ gốc repo):  python -m unittest discover -s offline/tests -p "test_*.py"
"""

import csv
import os
import sys
import tempfile
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # offline/
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from media_source import (  # noqa: E402
    MediaError, VideoSource, ensure_bgr, format_time, is_image, is_video,
    list_images, read_image, write_image)
from results import ResultLog  # noqa: E402


class EnsureBgrTest(unittest.TestCase):
    def test_gray_to_bgr(self):
        out = ensure_bgr(np.zeros((4, 5), np.uint8))
        self.assertEqual(out.shape, (4, 5, 3))

    def test_bgra_to_bgr(self):
        out = ensure_bgr(np.zeros((4, 5, 4), np.uint8))
        self.assertEqual(out.shape, (4, 5, 3))

    def test_non_contiguous_becomes_contiguous(self):
        out = ensure_bgr(np.zeros((8, 8, 3), np.uint8)[:, ::2])
        self.assertTrue(out.flags["C_CONTIGUOUS"])


class ImageIOTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_unicode_path_roundtrip(self):
        path = os.path.join(self.dir, "ảnh_thử.png")
        img = np.full((10, 12, 3), (10, 20, 30), np.uint8)
        write_image(path, img)
        out = read_image(path)
        np.testing.assert_array_equal(out, img)

    def test_gray_png_read_as_bgr(self):
        path = os.path.join(self.dir, "gray.png")
        write_image(path, np.zeros((6, 6), np.uint8))
        self.assertEqual(read_image(path).shape, (6, 6, 3))

    def test_invalid_image_raises(self):
        path = os.path.join(self.dir, "broken.jpg")
        with open(path, "wb") as f:
            f.write(b"not an image")
        with self.assertRaises(MediaError):
            read_image(path)

    def test_missing_image_raises(self):
        with self.assertRaises(MediaError):
            read_image(os.path.join(self.dir, "missing.png"))

    def test_list_images_filters_and_sorts(self):
        for name in ("b.PNG", "a.jpg", "c.txt", "d.mp4"):
            open(os.path.join(self.dir, name), "wb").close()
        names = [os.path.basename(p) for p in list_images(self.dir)]
        self.assertEqual(names, ["a.jpg", "b.PNG"])

    def test_extension_checks(self):
        self.assertTrue(is_image("x.BMP"))
        self.assertTrue(is_video("x.AVI"))
        self.assertFalse(is_video("x.jpg"))


class VideoSourceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.path = os.path.join(cls.tmp.name, "clip.avi")
        writer = cv2.VideoWriter(cls.path, cv2.VideoWriter_fourcc(*"MJPG"), 10.0, (32, 24))
        for i in range(12):
            writer.write(np.full((24, 32, 3), i * 20, np.uint8))
        writer.release()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_metadata_and_sequential_read(self):
        with VideoSource(self.path) as src:
            self.assertAlmostEqual(src.fps, 10.0, places=1)
            self.assertEqual(src.frame_count, 12)
            indices = []
            while (item := src.read()) is not None:
                idx, frame = item
                self.assertEqual(frame.shape, (24, 32, 3))
                indices.append(idx)
            self.assertEqual(indices, list(range(12)))

    def test_seek_and_grab(self):
        with VideoSource(self.path) as src:
            src.seek(5)
            self.assertEqual(src.read()[0], 5)
            self.assertTrue(src.grab())
            self.assertEqual(src.position, 7)
            self.assertAlmostEqual(src.timestamp(7), 0.7)

    def test_open_missing_video_raises(self):
        with self.assertRaises(MediaError):
            VideoSource(os.path.join(self.tmp.name, "nope.mp4"))


class ResultLogTest(unittest.TestCase):
    def test_dedup_and_range(self):
        log = ResultLog()
        _, new = log.add("v.mp4", "ABC", 10, 1.0)
        self.assertTrue(new)
        _, new = log.add("v.mp4", "ABC", 30, 3.0)
        self.assertFalse(new)
        log.add("v.mp4", "ABC", 5, 0.5)
        log.add("other.png", "ABC")
        self.assertEqual(len(log), 2)
        rec = next(r for r in log.records() if r.source == "v.mp4")
        self.assertEqual((rec.first_frame, rec.last_frame, rec.hits), (5, 30, 3))

    def test_export_csv(self):
        log = ResultLog()
        log.add(os.path.join("d", "ảnh.png"), "Xin chào")
        log.add("v.mp4", "X", 65, 65 / 25)
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "out.csv")
            log.export_csv(path)
            with open(path, encoding="utf-8-sig") as f:
                rows = list(csv.reader(f))
        self.assertEqual(rows[0][0], "file")
        self.assertEqual(rows[1][:2], ["ảnh.png", "Xin chào"])
        self.assertEqual(rows[2][2:4], ["65", "00:02.600"])

    def test_format_time(self):
        self.assertEqual(format_time(3725.5), "1:02:05.500")


if __name__ == "__main__":
    unittest.main()
