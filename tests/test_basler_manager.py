"""BaslerCameraManager với pylon giả — không cần camera, không cần driver.

Chạy (từ gốc repo):  python -m unittest tests.test_basler_manager
"""
from pathlib import Path
import os
import sys
import tempfile
import threading
import time
import types
import unittest
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from camera import basler_manager  # noqa: E402
from camera.conveyor import RunSettings  # noqa: E402
from demo_ui.app_settings import AppSettings, BaslerSettings  # noqa: E402


class FakeParam:
    def __init__(self, value, lo=None, hi=None, inc=1, writable=True):
        self._value, self.Min, self.Max, self.Inc = value, lo, hi, inc
        self._writable = writable
        self.locked_by = None

    def IsWritable(self):
        return self._writable

    def IsReadable(self):
        return True

    @property
    def Value(self):
        return self._value

    @Value.setter
    def Value(self, value):
        if self.locked_by is not None and self.locked_by.IsGrabbing():
            raise FakeError("TLParamsLocked")     # camera thật từ chối đổi ROI khi đang grab
        self._value = value


class FakeError(Exception):
    pass


class FakeResult:
    def __init__(self, width, height, ok=True, valid=True, skipped=0):
        self.Array = np.full((height, width), 7, np.uint8)
        self._ok, self._valid, self._skipped = ok, valid, skipped
        self.released = False

    def IsValid(self):
        return self._valid

    def GrabSucceeded(self):
        return self._ok

    def GetNumberOfSkippedImages(self):
        return self._skipped

    def GetErrorDescription(self):
        return "fake"

    def Release(self):
        self.released = True


class FakeCamera:
    def __init__(self, device):
        self.device = device
        self.grabbing = self.opened = self.destroyed = False
        self.start_count = self.stop_count = 0
        self.PixelFormat = FakeParam("BayerRG8")
        self.TriggerSelector = FakeParam("FrameStart")
        self.TriggerMode = FakeParam("On")
        self.ExposureAuto = FakeParam("Continuous")
        self.GainAuto = FakeParam("Continuous")
        self.ExposureTime = FakeParam(5000.0, 20.0, 10000.0)
        self.Gain = FakeParam(0.0, 0.0, 36.0)
        self.AcquisitionFrameRateEnable = FakeParam(True)
        self.AcquisitionFrameRate = FakeParam(50.0, 1.0, 84.0)
        self.OffsetX = FakeParam(8, 0, 16, 4)
        self.OffsetY = FakeParam(4, 0, 8, 4)
        self.Width = FakeParam(2840, 64, 2856, 4)
        self.Height = FakeParam(2840, 64, 2848, 4)
        for roi in (self.OffsetX, self.OffsetY, self.Width, self.Height):
            roi.locked_by = self
        self.AcquisitionFrameRateEnable.locked_by = self
        self.PixelFormat.locked_by = self

    def Open(self):
        if self.device.GetSerialNumber() == "busy":
            raise FakeError("device busy")
        self.opened = True

    def Close(self):
        self.opened = False

    def DestroyDevice(self):
        self.destroyed = True

    def IsGrabbing(self):
        return self.grabbing

    def StartGrabbing(self, strategy):
        self.strategy = strategy
        self.grabbing = True
        self.start_count += 1

    def StopGrabbing(self):
        self.grabbing = False
        self.stop_count += 1

    def RetrieveResult(self, timeout_ms, handling):
        time.sleep(0.002)
        return FakeResult(self.Width.Value, self.Height.Value, skipped=1)


class FakeDevice:
    def __init__(self, serial="42023350", model="a2A2840-48umBAS", device_class="BaslerUsb"):
        self._serial, self._model, self._class = serial, model, device_class

    def GetSerialNumber(self):
        return self._serial

    def GetModelName(self):
        return self._model

    def GetDeviceClass(self):
        return self._class


def fake_pylon(devices):
    module = types.SimpleNamespace(
        GenericException=FakeError, GrabStrategy_LatestImageOnly="latest", TimeoutHandling_Return="return")
    factory = types.SimpleNamespace(EnumerateDevices=lambda: devices, CreateDevice=lambda d: d)
    module.TlFactory = types.SimpleNamespace(GetInstance=lambda: factory)
    module.InstantCamera = FakeCamera
    return module


def wait_for(condition, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.005)
    return False


class ManagerCase(unittest.TestCase):
    devices = (FakeDevice(),)

    def setUp(self):
        patcher = patch.object(basler_manager, "pylon", fake_pylon(list(self.devices)))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.mgr = basler_manager.BaslerCameraManager()
        self.addCleanup(self.mgr.close)


class ListTests(ManagerCase):
    def test_device_exposes_the_methods_demo_ui_reads(self):
        camera = self.mgr.list_cameras()[0]
        self.assertEqual(camera.GetSn(), "42023350")
        self.assertEqual(camera.GetFriendlyName(), "a2A2840-48umBAS (42023350)")
        self.assertEqual(camera.GetPortType(), "USB")
        self.assertEqual(self.mgr.camera_list, [camera])

    def test_enumeration_error_gives_empty_list(self):
        def raises():
            raise FakeError("no transport")
        basler_manager.pylon.TlFactory.GetInstance().EnumerateDevices = raises
        self.assertEqual(self.mgr.list_cameras(), [])


class OpenCloseTests(ManagerCase):
    def test_open_prepares_camera_and_publishes_bgr_frames(self):
        self.mgr.list_cameras()
        self.assertTrue(self.mgr.open(0))
        camera = self.mgr.handle
        self.assertEqual(camera.PixelFormat.Value, "Mono8")
        self.assertEqual(camera.TriggerMode.Value, "Off")
        self.assertEqual(camera.strategy, "latest")
        self.assertTrue(wait_for(lambda: self.mgr.latest_frame()[0] is not None))
        frame, seq = self.mgr.latest_frame()
        self.assertGreater(seq, 0)
        self.assertEqual(frame.shape, (2840, 2840, 3))
        self.assertEqual(frame.dtype, np.uint8)
        self.assertTrue(frame.flags["C_CONTIGUOUS"])

    def test_statistic_counts_frames_and_skipped_images(self):
        self.mgr.list_cameras()
        self.mgr.open(0)
        self.assertTrue(wait_for(lambda: self.mgr.frame_statistic()[0] >= 3))
        captured, skipped = self.mgr.frame_statistic()
        self.assertGreaterEqual(skipped, 3)
        self.assertGreater(captured, 0)

    def test_open_out_of_range_refused(self):
        self.assertFalse(self.mgr.open(0))
        self.assertIsNone(self.mgr.handle)

    def test_open_failure_leaves_manager_closed(self):
        basler_manager.pylon.TlFactory.GetInstance().EnumerateDevices = lambda: [FakeDevice("busy")]
        self.mgr.list_cameras()
        self.assertFalse(self.mgr.open(0))
        self.assertIsNone(self.mgr.handle)
        self.assertFalse(self.mgr.running)

    def test_close_releases_camera_and_clears_frame(self):
        self.mgr.list_cameras()
        self.mgr.open(0)
        camera = self.mgr.handle
        self.mgr.close()
        self.assertIsNone(self.mgr.handle)
        self.assertFalse(camera.grabbing)
        self.assertFalse(camera.opened)
        self.assertTrue(camera.destroyed)
        self.assertIsNone(self.mgr.latest_frame()[0])

    def test_close_without_open_is_harmless(self):
        self.mgr.close()
        self.assertIsNone(self.mgr.handle)

    def test_seq_keeps_growing_after_reopen(self):
        self.mgr.list_cameras()
        self.mgr.open(0)
        self.assertTrue(wait_for(lambda: self.mgr.latest_frame()[1] > 0))
        self.mgr.close()
        seq = self.mgr.latest_frame()[1]
        self.mgr.open(0)
        self.assertTrue(wait_for(lambda: self.mgr.latest_frame()[1] > seq))

    def test_failed_grab_is_skipped_and_released(self):
        results = [FakeResult(4, 4, ok=False), FakeResult(4, 4, valid=False)]
        self.mgr.list_cameras()
        with patch.object(FakeCamera, "RetrieveResult",
                          lambda cam, *_: results.pop(0) if results else FakeResult(4, 4)):
            bad = list(results)
            self.mgr.open(0)
            self.assertTrue(wait_for(lambda: self.mgr.latest_frame()[0] is not None))
        self.assertEqual(self.mgr.latest_frame()[0].shape, (4, 4, 3))
        self.assertTrue(all(result.released for result in bad))

    def test_capture_survives_sdk_exception(self):
        calls = []

        def retrieve(cam, *_):
            calls.append(1)
            if len(calls) == 1:
                raise FakeError("transient")
            return FakeResult(4, 4)

        self.mgr.list_cameras()
        with patch.object(FakeCamera, "RetrieveResult", retrieve):
            self.mgr.open(0)
            self.assertTrue(wait_for(lambda: self.mgr.latest_frame()[0] is not None))


class ApplySettingsTests(ManagerCase):
    def open(self):
        self.mgr.list_cameras()
        self.assertTrue(self.mgr.open(0))
        return self.mgr.handle

    def test_returns_none_when_closed(self):
        self.assertIsNone(self.mgr.apply_run_settings(RunSettings(1000.0, 1)))

    def test_turns_auto_off_and_applies_exposure_gain(self):
        camera = self.open()
        applied = self.mgr.apply_run_settings(RunSettings(12900.0 / 2, 6))
        self.assertTrue(applied["ok"])
        self.assertEqual(camera.ExposureAuto.Value, "Off")
        self.assertEqual(camera.GainAuto.Value, "Off")
        self.assertFalse(camera.AcquisitionFrameRateEnable.Value)
        self.assertEqual(applied["exposure_us"], 6450.0)
        self.assertEqual(applied["analog_gain"], 6.0)
        self.assertEqual(self.mgr.get_exposure_time(), 6450.0)
        self.assertEqual(self.mgr.get_analog_gain(), 6.0)

    def test_max_fps_env_limits_frame_rate(self):
        camera = self.open()
        with patch.dict(os.environ, {"QR_MAX_FPS": "15"}):
            applied = self.mgr.apply_run_settings(RunSettings(1000.0, 1))
        self.assertTrue(applied["ok"])
        self.assertTrue(camera.AcquisitionFrameRateEnable.Value)
        self.assertEqual((camera.AcquisitionFrameRate.Value, applied["max_fps"]), (15.0, 15.0))
        self.assertTrue(camera.grabbing)

    def test_max_fps_clamped_and_removed(self):
        camera = self.open()
        with patch.dict(os.environ, {"QR_MAX_FPS": "500"}):
            self.mgr.apply_run_settings(RunSettings(1000.0, 1))
        self.assertEqual(camera.AcquisitionFrameRate.Value, 84.0)
        with patch.dict(os.environ, {"QR_MAX_FPS": ""}):
            applied = self.mgr.apply_run_settings(RunSettings(1000.0, 1))
        self.assertFalse(camera.AcquisitionFrameRateEnable.Value)
        self.assertIsNone(applied["max_fps"])

    def test_clamps_to_camera_limits(self):
        self.open()
        applied = self.mgr.apply_run_settings(RunSettings(99999.0, 40))
        self.assertTrue(applied["ok"])
        self.assertEqual(applied["exposure_us"], 10000.0)
        self.assertEqual(applied["analog_gain"], 36.0)

    def test_no_window_reads_full_sensor(self):
        camera = self.open()
        applied = self.mgr.apply_run_settings(RunSettings(1000.0, 1))
        self.assertEqual(applied["resolution"], (2856, 2848))
        self.assertEqual(camera.OffsetX.Value, 0)
        self.assertEqual(camera.OffsetY.Value, 0)
        self.assertTrue(camera.grabbing)

    def test_window_is_aligned_and_grabbing_restarts(self):
        camera = self.open()
        starts = camera.start_count
        applied = self.mgr.apply_run_settings(RunSettings(1000.0, 1, band_x=(100, 1000), band_y=(640, 768)))
        self.assertTrue(applied["ok"])
        self.assertEqual(applied["resolution"], (992, 768))     # align_band: bội 16
        self.assertEqual((camera.OffsetX.Value, camera.OffsetY.Value), (96, 640))
        self.assertEqual(camera.start_count, starts + 1)
        self.assertTrue(camera.grabbing)

    def test_same_window_does_not_interrupt_grabbing(self):
        camera = self.open()
        self.mgr.apply_run_settings(RunSettings(1000.0, 1, band_y=(640, 768)))
        stops = camera.stop_count
        self.mgr.apply_run_settings(RunSettings(2000.0, 2, band_y=(640, 768)))
        self.assertEqual(camera.stop_count, stops)

    def test_frames_follow_new_window(self):
        self.open()
        self.mgr.apply_run_settings(RunSettings(1000.0, 1, band_y=(640, 768)))
        def new_window_frame():
            frame = self.mgr.latest_frame()[0]
            return frame is not None and frame.shape == (768, 2856, 3)
        self.assertTrue(wait_for(new_window_frame))

    def test_rejected_parameter_reports_not_ok_but_keeps_grabbing(self):
        camera = self.open()
        camera.Gain._writable = False
        applied = self.mgr.apply_run_settings(RunSettings(1000.0, 1))
        self.assertFalse(applied["ok"])
        self.assertTrue(camera.grabbing)

    def test_rejected_window_reports_not_ok_and_grabbing_resumes(self):
        camera = self.open()
        with patch.object(camera.Width, "_writable", False):
            applied = self.mgr.apply_run_settings(RunSettings(1000.0, 1, band_x=(0, 1024)))
        self.assertFalse(applied["ok"])
        self.assertTrue(camera.grabbing)

    def test_apply_while_capture_runs_from_other_thread(self):
        camera = self.open()
        errors = []

        def apply(index):
            band = (0, 1024) if index % 2 else (0, 512)
            if not self.mgr.apply_run_settings(RunSettings(1000.0, 1, band_y=band))["ok"]:
                errors.append(index)

        threads = [threading.Thread(target=apply, args=(i,)) for i in range(10)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(errors, [])
        self.assertTrue(camera.grabbing)

    def test_trigger_only_supports_continuous(self):
        self.open()
        self.assertTrue(self.mgr.set_trigger_mode(0))
        self.assertFalse(self.mgr.set_trigger_mode(1))


class SettingsTests(unittest.TestCase):
    def test_defaults_differ_from_mindvision_demo(self):
        settings = BaslerSettings()
        self.assertEqual(settings.analog_gain, 6)
        self.assertEqual(settings.band_w, 2840)
        self.assertEqual(AppSettings().analog_gain, 40)

    def test_round_trip_keeps_the_subclass_defaults(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "basler.json"
            self.assertEqual(BaslerSettings.load(path), BaslerSettings())
            settings = BaslerSettings(analog_gain=9)
            self.assertTrue(settings.save(path))
            loaded = BaslerSettings.load(path)
        self.assertIsInstance(loaded, BaslerSettings)
        self.assertEqual(loaded.analog_gain, 9)


if __name__ == "__main__":
    unittest.main()
