"""App hai camera với camera và pipeline giả; không cần phần cứng, không gọi mạng.

Chạy (từ gốc repo):  python -m unittest tests.test_dual_app
"""
from collections import Counter
import importlib
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import types
import unittest
import unittest.mock
from unittest.mock import Mock, patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests import test_camera_diagnostics as fake  # noqa: E402  (dựng fake mvsdk, nạp QApplication)
from qr.improved_pipeline import Decoded  # noqa: E402
from qr.pass_reader import PassReader  # noqa: E402
from demo_ui.app_settings import AppSettings, BaslerSettings, DualSettings  # noqa: E402
from demo_ui.merged_stats import MergedStats  # noqa: E402
from demo_ui.run_controller import RunState  # noqa: E402
from demo_ui.session_stats import RowState  # noqa: E402
from demo_ui.dual_worker import DualDecodeWorker  # noqa: E402
from demo_ui.scan_uploader import UploadStatus  # noqa: E402
from tests.qr_fixtures import detection_at  # noqa: E402

with unittest.mock.patch.dict(sys.modules, {"mvsdk": fake.sdk, "camera.camera_manager": fake.manager_module}):
    window_module = importlib.import_module("demo_ui.dual_window")

FRAME = np.zeros((64, 96, 3), np.uint8)


def track(track_id, text=None, observations=3, conflicting=False):
    return types.SimpleNamespace(track_id=track_id, text=text, observations=observations, conflicting=conflicting)


class MergedStatsTests(unittest.TestCase):
    def setUp(self):
        self.now = 100.0
        self.stats = MergedStats(monotonic=lambda: self.now, clock=lambda: "10:00:00")

    def test_same_code_from_both_cameras_is_one_row(self):
        first = self.stats.on_reads(0, [track(1, "X")])[0]
        second = self.stats.on_reads(1, [track(1, "X")])[0]
        self.assertIs(first, second)
        self.assertEqual(second.camera_text, "A+B")

    def test_same_track_id_on_two_cameras_does_not_collide(self):
        self.stats.on_reads(0, [track(1, "X")])
        self.stats.on_reads(1, [track(1, "Y")])
        rows = self.stats.on_passes(0, [track(1, "X")]) + self.stats.on_passes(1, [track(1, "Y")])
        self.assertEqual([row.text for row in rows], ["X", "Y"])
        self.assertNotEqual(rows[0].track_id, rows[1].track_id)
        self.assertEqual(self.stats.read_count, 2)

    def test_counts_merged_code_once_and_rates_per_camera(self):
        self.stats.on_reads(0, [track(1, "X")])
        self.stats.on_reads(1, [track(5, "X")])
        self.stats.on_passes(0, [track(1, "X")])
        self.stats.on_passes(1, [track(5, "X"), track(6)])
        self.assertEqual(self.stats.read_count, 1)
        self.assertEqual(self.stats.camera_rate(0), 1.0)
        self.assertEqual(self.stats.camera_rate(1), 0.5)

    def test_row_stays_reading_until_both_passes_finish(self):
        self.stats.on_reads(0, [track(1, "X")])
        row = self.stats.on_reads(1, [track(2, "X")])[0]
        self.stats.on_passes(0, [track(1, "X")])
        self.assertIs(row.state, RowState.READING)
        self.stats.on_passes(1, [track(2, "X")])
        self.assertIs(row.state, RowState.OK)

    def test_code_after_window_is_a_new_row(self):
        first = self.stats.on_reads(0, [track(1, "X")])[0]
        self.now += 31
        second = self.stats.on_reads(1, [track(2, "X")])[0]
        self.assertIsNot(first, second)

    def test_second_camera_finishing_late_keeps_reading_row(self):
        first = self.stats.on_reads(0, [track(1, "X")])[0]
        self.stats.on_passes(0, [track(1, "X")])
        self.now += 5
        self.assertIs(self.stats.on_reads(1, [track(2, "X")])[0], first)
        self.assertIs(first.state, RowState.READING)

    def test_failed_pass_is_its_own_row_and_noise_is_ignored(self):
        rows = self.stats.on_passes(1, [track(1), track(2, observations=1)])
        self.assertEqual(len(rows), 1)
        self.assertIs(rows[0].state, RowState.FAILED)
        self.assertEqual(rows[0].camera_text, "B")
        self.assertEqual(self.stats.noise_count, 1)
        self.assertEqual(self.stats.camera_rate(1), 0.0)
        self.assertIsNone(self.stats.camera_rate(0))

    def test_conflict_in_one_camera_marks_merged_row(self):
        self.stats.on_reads(0, [track(1, "X")])
        row = self.stats.on_reads(1, [track(2, "X")])[0]
        self.stats.on_passes(0, [track(1, "X", conflicting=True)])
        self.stats.on_passes(1, [track(2, "X")])
        self.assertIs(row.state, RowState.CONFLICT)

    def test_reset_clears_everything(self):
        self.stats.on_reads(0, [track(1, "X")])
        self.stats.on_passes(0, [track(1, "X")])
        self.stats.reset()
        self.assertEqual(self.stats.read_count, 0)
        self.assertIsNone(self.stats.camera_rate(0))
        self.assertIsNot(self.stats.on_reads(0, [track(1, "X")])[0].track_id, None)


class FakePipeline:
    gpu_available = False
    device = "cpu"

    def __init__(self, delay=0.0, fail=False):
        self.delay, self.fail = delay, fail
        self.warmups = 0
        self.concurrent = self.peak = 0
        self.order: list[int] = []
        self._lock = threading.Lock()

    def warmup(self):
        self.warmups += 1

    def set_device(self, device):
        self.device = device

    def detect(self, image_bgr):
        with self._lock:
            self.concurrent += 1
            self.peak = max(self.peak, self.concurrent)
        self.order.append(int(image_bgr[0, 0, 0]))
        time.sleep(self.delay)
        with self._lock:
            self.concurrent -= 1
        if self.fail:
            raise RuntimeError("detect hỏng")
        return [detection_at(10, 10)]

    def decode_detection(self, image_bgr, det):
        return Decoded("MA{}".format(int(image_bgr[0, 0, 0])), det.quad_xy)


def wait_for(condition, app=None, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if app is not None:
            app.processEvents()
        if condition():
            return True
        time.sleep(0.002)
    return False


def camera_frame(value):
    return np.full((64, 96, 3), value, np.uint8)


class WorkerTests(unittest.TestCase):
    def make(self, pipeline):
        worker = DualDecodeWorker(pipeline)
        self.addCleanup(worker.stop)
        self.done, self.failed, self.flushed = [], [], []
        from PyQt5.QtCore import Qt
        worker.done.connect(lambda cam, r, o: self.done.append((cam, r)), Qt.DirectConnection)
        worker.failed.connect(lambda cam, msg: self.failed.append((cam, msg)), Qt.DirectConnection)
        worker.flushed.connect(lambda p, f: self.flushed.append((p, f)), Qt.DirectConnection)
        return worker

    def test_warms_up_pipeline_once(self):
        pipe = FakePipeline()
        worker = self.make(pipe)
        self.assertTrue(wait_for(lambda: worker.is_ready))
        self.assertEqual(pipe.warmups, 1)

    def test_only_one_job_at_a_time_and_cameras_alternate(self):
        pipe = FakePipeline(delay=0.01)
        worker = self.make(pipe)
        seq = [0, 0]
        deadline = time.monotonic() + 0.5
        while time.monotonic() < deadline and len(pipe.order) < 12:
            for cam in (0, 1):
                if worker.submit(cam, camera_frame(cam), seq[cam] + 1):
                    seq[cam] += 1
            time.sleep(0.001)
        self.assertEqual(pipe.peak, 1)
        counts = Counter(pipe.order)
        self.assertLessEqual(abs(counts[0] - counts[1]), 2)

    def test_decode_every_and_exposure_are_per_camera(self):
        worker = self.make(FakePipeline())
        worker._readers = [Mock(), Mock()]
        worker._readers[0].decode_every.return_value = 2
        worker._readers[1].decode_every.return_value = 5
        self.assertEqual((worker.decode_every(0, 5), worker.decode_every(1, 5)), (2, 5))
        worker.set_exposure_ms(1, 3.0)
        worker._readers[1].set_exposure_ms.assert_called_once_with(3.0)
        worker._readers[0].set_exposure_ms.assert_not_called()
        worker._readers = [PassReader(FakePipeline()), PassReader(FakePipeline())]

    def test_second_frame_of_same_camera_refused_while_pending(self):
        pipe = FakePipeline(delay=0.05)
        worker = self.make(pipe)
        self.assertTrue(wait_for(lambda: worker.is_ready))
        self.assertTrue(worker.submit(0, camera_frame(0), 1))
        self.assertFalse(worker.submit(0, camera_frame(0), 2))
        self.assertTrue(worker.submit(1, camera_frame(1), 1))

    def test_each_camera_has_its_own_passes(self):
        worker = self.make(FakePipeline())
        passes = []
        from PyQt5.QtCore import Qt
        worker.reads.connect(lambda cam, tracks: passes.extend((cam, t.text) for t in tracks), Qt.DirectConnection)
        for seq in (1, 2):
            for cam in (0, 1):
                self.assertTrue(wait_for(lambda: worker.submit(cam, camera_frame(cam), seq)))
        self.assertTrue(wait_for(lambda: len(passes) == 2))
        self.assertEqual(sorted(passes), [(0, "MA0"), (1, "MA1")])

    def test_decode_error_reports_camera_and_continues(self):
        pipe = FakePipeline(fail=True)
        worker = self.make(pipe)
        self.assertTrue(wait_for(lambda: worker.submit(1, camera_frame(1), 1)))
        self.assertTrue(wait_for(lambda: self.failed == [(1, "detect hỏng")]))
        pipe.fail = False
        self.assertTrue(wait_for(lambda: worker.submit(0, camera_frame(0), 1)))
        self.assertTrue(wait_for(lambda: bool(self.done)))

    def test_flush_returns_open_passes_per_camera_and_drops_pending(self):
        worker = self.make(FakePipeline())
        self.assertTrue(wait_for(lambda: worker.submit(1, camera_frame(1), 1)))
        self.assertTrue(wait_for(lambda: bool(self.done)))
        worker.request_flush("stop")
        self.assertTrue(wait_for(lambda: bool(self.flushed)))
        purpose, flushed = self.flushed[0]
        self.assertEqual(purpose, "stop")
        self.assertEqual([cam for cam, _ in flushed], [0, 1])
        self.assertEqual(flushed[0][1], [])
        self.assertEqual(len(flushed[1][1]), 1)


class FakeDevice:
    def __init__(self, serial):
        self.serial = serial

    def GetSn(self):
        return self.serial

    def GetFriendlyName(self):
        return "Cam " + self.serial

    def GetPortType(self):
        return "Test"


class FakeManager:
    def __init__(self, serial, value, fail_open=False, close_fails=False):
        self.camera_list = []
        self.handle = None
        self.serial, self.value = serial, value
        self.fail_open, self.close_fails = fail_open, close_fails
        self.seq = 0
        self.applied = []
        self.closes = 0
        self.frame = None

    def init_sdk(self):
        return True

    def list_cameras(self):
        self.camera_list = [FakeDevice(self.serial)]
        return self.camera_list

    def open(self, index):
        if self.fail_open:
            return False
        self.handle = object()
        self.frame = camera_frame(self.value)
        return True

    def close(self):
        self.closes += 1
        if not self.close_fails:
            self.handle = None
            self.frame = None

    def set_trigger_mode(self, mode):
        return True

    def apply_run_settings(self, settings):
        if self.handle is None:
            return None
        self.applied.append(settings)
        return dict(ok=True, exposure_us=settings.exposure_us, analog_gain=settings.analog_gain, resolution=(96, 64))

    def latest_frame(self):
        if self.frame is None:
            return None, self.seq
        self.seq += 1              # mỗi lần đọc coi như có frame mới
        return self.frame, self.seq

    def frame_statistic(self):
        return self.seq, 0

    def get_exposure_time(self):
        return 1000.0

    def get_analog_gain(self):
        return 1


class FakeUploader:
    def __init__(self):
        self.texts = []
        self.enabled = None

    def submit(self, text):
        self.texts.append(text)

    def set_enabled(self, enabled):
        self.enabled = enabled

    def stop(self):
        pass


class DualWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = fake.QApplication.instance() or fake.QApplication([])

    def make(self, a=None, b=None, **kwargs):
        self.a = a or FakeManager("A1", 1)
        self.b = b or FakeManager("B1", 2)
        self.uploader = FakeUploader()
        self.window = window_module.DualWindow(uploader=self.uploader, cameras=(self.a, self.b),
                                               pipeline=FakePipeline(), **kwargs)
        self.addCleanup(self.shutdown)
        return self.window

    def shutdown(self):
        for manager in (self.a, self.b):
            manager.close_fails = False
        self.window.close()
        wait_for(lambda: not self.window._camera_busy(), self.app)
        self.window.close()
        self.app.processEvents()

    def states(self):
        return [ch.controller.state for ch in self.window.channels]

    def start(self):
        self.window.on_start()
        return wait_for(lambda: all(s is not RunState.CONNECTING for s in self.states())
                        and self.window.worker.is_ready, self.app)

    def test_overall_state_priority(self):
        overall = window_module.overall_state
        self.assertIs(overall([RunState.RUNNING, RunState.ERROR]), RunState.RUNNING)
        self.assertIs(overall([RunState.CONNECTING, RunState.RUNNING]), RunState.CONNECTING)
        self.assertIs(overall([RunState.ERROR, RunState.IDLE]), RunState.ERROR)
        self.assertIs(overall([RunState.STOPPING, RunState.RUNNING]), RunState.STOPPING)
        self.assertIs(overall([RunState.IDLE, RunState.IDLE]), RunState.IDLE)

    def test_start_opens_both_with_their_own_settings(self):
        window = self.make()
        window.channels[1].panel.spin_exposure.setValue(3.0)
        self.assertTrue(self.start())
        self.assertEqual(self.states(), [RunState.RUNNING, RunState.RUNNING])
        self.assertIsNotNone(self.a.handle)
        self.assertIsNotNone(self.b.handle)
        self.assertEqual(self.b.applied[-1].exposure_us, 3000.0)
        self.assertNotEqual(self.a.applied[-1].exposure_us, 3000.0)
        self.assertEqual(window.settings.b.camera_serial, "B1")

    def test_each_camera_passes_its_exposure_to_worker(self):
        window = self.make()
        window.channels[0].panel.spin_exposure.setValue(7.0)
        window.channels[1].panel.spin_exposure.setValue(3.0)
        with patch.object(window.worker, "set_exposure_ms") as set_exposure:
            self.assertTrue(self.start())
        set_exposure.assert_any_call(0, 7.0)
        set_exposure.assert_any_call(1, 3.0)

    def test_apply_passes_applied_exposure_to_worker(self):
        window = self.make()
        self.assertTrue(self.start())
        with patch.object(window.worker, "set_exposure_ms") as set_exposure:
            window.on_apply(window.channels[1])
        self.assertEqual(set_exposure.call_args[0][0], 1)

    def test_tick_uses_interval_from_worker_for_that_camera(self):
        window = self.make()
        ch = window.channels[0]
        ch.decoding = True
        ch.panel.spin_n.setValue(5)
        ch.last_seq = ch.last_decode_seq = 10
        ch.mgr.latest_frame = Mock(return_value=(camera_frame(0), 12))
        with patch.object(window.worker, "submit", return_value=True) as submit:
            window._show_channel(ch)
            submit.assert_not_called()
            ch.last_seq = 10
            with patch.object(window.worker, "decode_every", return_value=2) as decode_every:
                window._show_channel(ch)
            decode_every.assert_called_once_with(0, 5)
            self.assertEqual(submit.call_count, 1)

    def test_frames_reach_both_videos_and_decode(self):
        window = self.make()
        self.assertTrue(self.start())
        self.assertTrue(wait_for(lambda: window.decode_count >= 2 and window.stats.latest_text is not None, self.app))
        self.assertIsNotNone(window.workspace.videos[0].video_label.pixmap())
        self.assertIsNotNone(window.workspace.videos[1].video_label.pixmap())
        self.assertTrue(wait_for(lambda: {"MA1", "MA2"} <= set(self.uploader.texts), self.app))

    def test_one_camera_failing_keeps_the_other_running(self):
        window = self.make(b=FakeManager("B1", 2, fail_open=True))
        self.assertTrue(self.start())
        self.assertEqual(self.states(), [RunState.RUNNING, RunState.ERROR])
        self.assertIs(window.state, RunState.RUNNING)
        self.assertFalse(window.workspace.videos[1].overlay.isHidden())
        self.assertIn("Không mở được", window.workspace.videos[1].message.text())
        self.assertTrue(window.workspace.videos[0].overlay.isHidden())
        self.assertTrue(wait_for(lambda: window.decode_count >= 1, self.app))

    def test_retry_starts_only_failed_camera_and_keeps_session(self):
        window = self.make(b=FakeManager("B1", 2, fail_open=True))
        self.assertTrue(self.start())
        started = window.stats._run_started
        self.b.fail_open = False
        window.channels[1].video.btn_retry.click()
        self.assertTrue(wait_for(lambda: self.states() == [RunState.RUNNING, RunState.RUNNING], self.app))
        self.assertEqual(window.stats._run_started, started)

    def test_both_failing_is_overall_error(self):
        window = self.make(a=FakeManager("A1", 1, fail_open=True), b=FakeManager("B1", 2, fail_open=True))
        self.assertTrue(self.start())
        self.assertIs(window.state, RunState.ERROR)

    def test_stop_closes_both_and_returns_idle(self):
        window = self.make()
        self.assertTrue(self.start())
        window.on_primary_clicked()
        self.assertTrue(wait_for(lambda: self.states() == [RunState.IDLE, RunState.IDLE], self.app))
        self.assertIsNone(self.a.handle)
        self.assertIsNone(self.b.handle)
        self.assertIs(window.state, RunState.IDLE)
        self.assertIsNone(window.stats._run_started)

    def test_stop_while_other_camera_in_error_clears_error(self):
        window = self.make(b=FakeManager("B1", 2, fail_open=True))
        self.assertTrue(self.start())
        window.on_stop()
        self.assertTrue(wait_for(lambda: self.states() == [RunState.IDLE, RunState.IDLE], self.app))

    def test_close_failure_is_reported_on_that_camera(self):
        window = self.make(b=FakeManager("B1", 2, close_fails=True))
        self.assertTrue(self.start())
        window.on_stop()
        self.assertTrue(wait_for(lambda: self.states() == [RunState.IDLE, RunState.ERROR], self.app))
        self.assertTrue(window.channels[1].controller.close_failed)

    def test_reset_clears_rows_and_counts(self):
        window = self.make()
        self.assertTrue(self.start())
        self.assertTrue(wait_for(lambda: window.workspace.table.rowCount() > 0, self.app))
        with unittest.mock.patch.object(window, "_confirm_reset", return_value=True):
            window.on_reset()
        self.assertTrue(wait_for(lambda: window.decode_count < 3 and window.stats.finished_count == 0, self.app))
        window.on_stop()

    def test_window_close_waits_for_cameras_then_closes(self):
        window = self.make()
        self.assertTrue(self.start())
        window.close()
        self.assertTrue(wait_for(lambda: self.a.handle is None and self.b.handle is None
                                 and window._allow_close, self.app))

    def test_row_shows_cameras(self):
        window = self.make()
        rows = window.stats.on_reads(0, [track(1, "X")])
        window.stats.on_reads(1, [track(2, "X")])
        window.workspace.upsert_row(rows[0])
        self.assertTrue(window.workspace.table.item(0, 0).text().endswith("A+B"))

    def test_upload_toggle_reaches_uploader(self):
        window = self.make()
        window.cbx_upload.setChecked(False)
        self.assertIs(self.uploader.enabled, False)

    def test_missing_env_disables_upload_switch(self):
        self.a, self.b = FakeManager("A1", 1), FakeManager("B1", 2)
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        with patch.object(window_module, "ScanUploader") as uploader_cls,                 patch.object(window_module, "load_api_config", return_value=(None, ["BASE_URL", "API_KEY"])):
            self.window = window_module.DualWindow(settings_path=Path(folder.name) / "dual.json",
                                                   cameras=(self.a, self.b), pipeline=FakePipeline())
        self.addCleanup(self.shutdown)
        uploader_cls.assert_not_called()
        self.assertIsNone(self.window.uploader)
        self.assertFalse(self.window.cbx_upload.isEnabled())
        self.assertIn("BASE_URL, API_KEY", self.window.cbx_upload.toolTip())
        self.assertIn("API_KEY", self.window.lbl_common.text())

    def test_upload_error_shows_server_message(self):
        window = self.make()
        window.on_upload_status(UploadStatus(1, 0, 1, "A", False, "Không tìm thấy tấm"))
        self.assertIn("Không tìm thấy tấm", window.lbl_common.text())


class DualSettingsTests(unittest.TestCase):
    def test_first_run_seeds_from_single_camera_files(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            AppSettings(exposure_ms=8.0).save(folder / "a.json")
            BaslerSettings(exposure_ms=4.0, decode_every_n=15).save(folder / "b.json")
            settings = DualSettings.load(folder / "dual.json", seed_a=folder / "a.json", seed_b=folder / "b.json")
        self.assertEqual(settings.a.exposure_ms, 8.0)
        self.assertEqual(settings.b.exposure_ms, 4.0)
        self.assertEqual(settings.b.decode_every_n, 15)
        self.assertIsInstance(settings.b, BaslerSettings)

    def test_round_trip_keeps_each_camera_apart(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "dual.json"
            settings = DualSettings()
            settings.a.analog_gain, settings.b.analog_gain = 40, 9
            self.assertTrue(settings.save(path))
            loaded = DualSettings.load(path)
            raw = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual((loaded.a.analog_gain, loaded.b.analog_gain), (40, 9))
        self.assertEqual(set(raw), {"a", "b"})

    def test_invalid_value_falls_back_for_that_field_only(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "dual.json"
            path.write_text(json.dumps({"a": {"analog_gain": "sai", "exposure_ms": 7.0}}), encoding="utf-8")
            loaded = DualSettings.load(path)
        self.assertEqual(loaded.a.analog_gain, AppSettings().analog_gain)
        self.assertEqual(loaded.a.exposure_ms, 7.0)
        self.assertEqual(loaded.b, BaslerSettings())

    def test_broken_file_falls_back_to_seeds(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            (folder / "dual.json").write_text("{hỏng", encoding="utf-8")
            AppSettings(exposure_ms=8.0).save(folder / "a.json")
            loaded = DualSettings.load(folder / "dual.json", seed_a=folder / "a.json", seed_b=folder / "b.json")
        self.assertEqual(loaded.a.exposure_ms, 8.0)


if __name__ == "__main__":
    unittest.main()
