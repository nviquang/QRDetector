"""ReplayCameraManager: phát lại thư mục frame TIFF như một camera — không cần camera, không cần pylon.

Chạy (từ gốc repo):  python -m unittest tests.test_replay_manager
"""
from pathlib import Path
import json
import os
import sys
import tempfile
import time
import unittest

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from camera.conveyor import RunSettings  # noqa: E402
from camera.replay_manager import ReplayCameraManager  # noqa: E402

DT = 0.04   # 40 ms giữa hai frame, như dữ liệu lab 25 fps


def make_recording(root: Path, name: str, n: int, size=(48, 64), meta: dict | None = None,
                   dt: float | None = DT) -> Path:
    folder = root / name
    folder.mkdir(parents=True)
    t0 = time.time() - 1000
    for i in range(n):
        img = np.full(size, i * 10 % 256, np.uint8)
        path = folder / f"frame_{i:04d}.tiff"
        cv2.imwrite(str(path), img)
        t = t0 + (i * dt if dt is not None else 0.0)
        os.utime(path, (t, t))
    if meta is not None:
        (folder / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    return folder


def wait_until(cond, timeout=5.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.005)
    return False


class ReplayManagerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        make_recording(self.root, "b_rec_xuong_chay", 6, meta=dict(scene="xuong_chay", frames=6, write_fps=25.0))
        make_recording(self.root, "a_rec_lab_gan", 4, meta=dict(scene="lab_gan", frames=4, exposure_ms=2.5))
        (self.root / "empty_dir").mkdir()
        self.mgr = ReplayCameraManager(self.root, speed=4.0)

    def tearDown(self):
        self.mgr.close()
        self.tmp.cleanup()

    def test_lists_recordings_as_cameras(self):
        self.assertTrue(self.mgr.init_sdk())
        cams = self.mgr.list_cameras()
        self.assertEqual([c.GetSn() for c in cams], ["a_rec_lab_gan", "b_rec_xuong_chay"])
        self.assertEqual(self.mgr.camera_list, cams)
        self.assertIn("lab_gan", cams[0].GetFriendlyName())
        self.assertIn("4 frame", cams[0].GetFriendlyName())
        self.assertEqual(cams[0].GetPortType(), "File")

    def test_missing_root_gives_no_cameras(self):
        self.assertEqual(ReplayCameraManager(self.root / "nope").list_cameras(), [])

    def test_open_rejects_bad_index(self):
        self.mgr.list_cameras()
        self.assertFalse(self.mgr.open(5))
        self.assertIsNone(self.mgr.handle)

    def test_plays_all_frames_in_order_then_finishes(self):
        self.mgr.list_cameras()
        self.assertTrue(self.mgr.open(1))
        self.assertIsNotNone(self.mgr.handle)
        self.assertTrue(self.mgr.start_playback())
        seen = []

        def collect():
            frame, seq = self.mgr.latest_frame()
            if frame is not None and (not seen or seen[-1][0] != seq):
                seen.append((seq, int(frame[0, 0, 0]), frame.shape, frame.flags["C_CONTIGUOUS"]))
            return self.mgr.finished

        self.assertTrue(wait_until(collect))
        collect()
        seqs = [s[0] for s in seen]
        self.assertEqual(seqs, sorted(seqs))
        self.assertEqual(seqs[-1], 6)                 # seq = idx + 1, frame cuối idx 5
        self.assertEqual(seen[-1][1], 50)             # nội dung frame cuối
        self.assertEqual(seen[-1][2], (48, 64, 3))    # BGR 3 kênh
        self.assertTrue(all(s[3] for s in seen))
        self.assertEqual(self.mgr.frame_statistic(), (6, 0))
        self.assertIsNotNone(self.mgr.latest_frame()[0])   # giữ frame cuối

    def test_paces_by_file_mtime_and_speed(self):
        self.mgr.list_cameras()
        self.assertTrue(self.mgr.open(1))
        t = time.monotonic()
        self.mgr.start_playback()
        self.assertTrue(wait_until(lambda: self.mgr.finished))
        elapsed = time.monotonic() - t
        expected = 5 * DT / 4.0                     # 5 khoảng 40 ms ở tốc độ 4×
        self.assertGreater(elapsed, expected * 0.8)
        self.assertLess(elapsed, expected + 1.0)

    def test_bad_mtimes_fall_back_to_meta_fps(self):
        make_recording(self.root, "c_rec_copied", 5, meta=dict(scene="x", write_fps=10.0), dt=None)
        mgr = ReplayCameraManager(self.root, speed=1.0)
        try:
            mgr.list_cameras()
            np.testing.assert_allclose(mgr._timestamps(mgr.camera_list[2]), [0.0, 0.1, 0.2, 0.3, 0.4])
        finally:
            mgr.close()

    def test_open_shows_first_frame_and_waits_for_start(self):
        self.mgr.list_cameras()
        self.assertFalse(self.mgr.start_playback())          # chưa mở
        self.assertTrue(self.mgr.open(1))
        self.assertTrue(wait_until(lambda: self.mgr.latest_frame()[0] is not None))
        time.sleep(0.3)                                       # đủ phát hết nếu đồng hồ đã chạy
        frame, seq = self.mgr.latest_frame()
        self.assertEqual(seq, 1)
        self.assertEqual(int(frame[0, 0, 0]), 0)
        self.assertFalse(self.mgr.finished)
        self.assertEqual(self.mgr.frame_statistic(), (0, 0))  # xem trước không tính là đã phát
        self.mgr.start_playback()
        self.assertTrue(wait_until(lambda: self.mgr.finished))
        self.assertEqual(self.mgr.frame_statistic(), (6, 0))

    def test_close_is_idempotent_and_clears_frame(self):
        self.mgr.list_cameras()
        self.assertTrue(self.mgr.open(0))
        self.assertTrue(wait_until(lambda: self.mgr.latest_frame()[0] is not None))
        self.mgr.close()
        self.mgr.close()
        self.assertIsNone(self.mgr.handle)
        self.assertEqual(self.mgr.latest_frame(), (None, 0))
        self.assertFalse(self.mgr.finished)

    def test_reopen_restarts_from_first_frame(self):
        self.mgr.list_cameras()
        self.assertTrue(self.mgr.open(0))
        self.mgr.start_playback()
        self.assertTrue(wait_until(lambda: self.mgr.finished))
        self.assertTrue(self.mgr.open(0))
        self.assertFalse(self.mgr.finished)
        self.assertFalse(self.mgr.playing)
        self.mgr.start_playback()
        self.assertTrue(wait_until(lambda: self.mgr.finished))
        self.assertEqual(self.mgr.frame_statistic(), (4, 0))

    def test_apply_run_settings_prefers_meta_exposure(self):
        self.mgr.list_cameras()
        self.assertIsNone(self.mgr.apply_run_settings(RunSettings(exposure_us=8000, analog_gain=6)))  # chưa mở
        self.assertTrue(self.mgr.open(0))       # meta có exposure_ms=2.5
        applied = self.mgr.apply_run_settings(RunSettings(exposure_us=8000, analog_gain=6))
        self.assertTrue(applied["ok"])
        self.assertEqual(applied["exposure_us"], 2500.0)
        self.assertEqual(self.mgr.get_exposure_time(), 2500.0)
        self.assertEqual(self.mgr.get_analog_gain(), 6)
        self.assertEqual(applied["resolution"], (64, 48))

    def test_apply_run_settings_uses_requested_exposure_without_meta(self):
        self.mgr.list_cameras()
        self.assertTrue(self.mgr.open(1))       # meta không có exposure_ms
        applied = self.mgr.apply_run_settings(RunSettings(exposure_us=8000, analog_gain=6))
        self.assertEqual(applied["exposure_us"], 8000.0)
        self.assertTrue(self.mgr.set_trigger_mode(0))

    def test_band_crops_preview_and_played_frames(self):
        self.mgr.list_cameras()
        self.assertTrue(self.mgr.open(1))
        self.assertTrue(wait_until(lambda: self.mgr.latest_frame()[0] is not None))
        self.assertEqual(self.mgr.latest_frame()[0].shape, (48, 64, 3))
        applied = self.mgr.apply_run_settings(RunSettings(exposure_us=1000, analog_gain=0,
                                                          band_x=(10, 30), band_y=(40, 100)))
        self.assertEqual(applied["resolution"], (30, 8))   # y kẹp trong ảnh cao 48
        self.assertEqual(self.mgr.get_resolution(), (30, 8))
        self.assertEqual(self.mgr.latest_frame()[0].shape, (8, 30, 3))   # xem trước vẽ lại ngay
        self.mgr.start_playback()
        self.assertTrue(wait_until(lambda: self.mgr.finished))
        self.assertEqual(self.mgr.latest_frame()[0].shape, (8, 30, 3))
        self.mgr.apply_run_settings(RunSettings(exposure_us=1000, analog_gain=0))
        self.assertEqual(self.mgr.get_resolution(), (64, 48))   # bỏ vùng đọc → toàn khung


class ReplaySettingsTests(unittest.TestCase):
    def test_upload_off_by_default_and_saved_choice_kept(self):
        from demo_ui.app_settings import ReplaySettings
        self.assertFalse(ReplaySettings().upload_enabled)
        self.assertTrue(ReplaySettings.from_dict({"upload_enabled": True}).upload_enabled)


if __name__ == "__main__":
    unittest.main()
