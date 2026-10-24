"""Camera regression tests with a fake MindVision SDK; no camera or DLL needed."""
import importlib
import os
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class FakeCamera:
    def __init__(self):
        self.values = {
            "ae": True,
            "target": 120,
            "analog_gain": 6,
            "exposure": 20_000.0,
            "sharpness": 5,
            "gamma": 70,
            "contrast": 20,
            "gain": (100, 100, 100),
            "saturation": 50,
            "friendly_name": "Test camera",
            "serial": "TEST-001",
        }
        self.writes = []
        self.fail_writes = False


class Range:
    def __init__(self, lo, hi):
        self.iMin = lo
        self.iMax = hi


class ExposureRange:
    uiTargetMin = 1
    uiTargetMax = 255
    uiAnalogGainMin = 0
    uiAnalogGainMax = 24
    fAnalogGainStep = 1.0
    uiExposeTimeMin = 10
    uiExposeTimeMax = 1_000_000


class IspCapacity:
    bMonoSensor = 0
    bAutoExposure = 1


class Resolution:
    def GetDescription(self):
        return "640x480"


class Capability:
    iImageSizeDesc = 1
    pImageSizeDesc = [Resolution()]
    sExposeDesc = ExposureRange()
    sSharpnessRange = Range(0, 100)
    sGammaRange = Range(1, 250)
    sContrastRange = Range(0, 100)
    sIspCapacity = IspCapacity()


sdk = types.ModuleType("mvsdk")
sdk.CAMERA_MEDIA_TYPE_MONO8 = 1
sdk.CAMERA_MEDIA_TYPE_RGB8 = 3
sdk._last_error = 0


class CameraException(Exception):
    def __init__(self, error_code):
        self.error_code = error_code
        self.message = "fake SDK error"


sdk.CameraException = CameraException
sdk.GetLastError = lambda: sdk._last_error
sdk.CameraSdkInit = lambda *args: 0
sdk.CameraEnumerateDevice = lambda: []


def _get(key):
    def getter(camera, *args):
        sdk._last_error = 0
        return camera.values[key]
    return getter


def _set(key, label):
    def setter(camera, value, *args):
        camera.writes.append((label, value))
        if camera.fail_writes:
            sdk._last_error = 0x80000106
            return 0x80000106
        camera.values[key] = value
        sdk._last_error = 0
        return 0
    return setter


sdk.CameraGetAeState = _get("ae")
sdk.CameraSetAeState = _set("ae", "AeState")
sdk.CameraGetAeTarget = _get("target")
sdk.CameraSetAeTarget = _set("target", "AeTarget")
sdk.CameraGetAnalogGain = _get("analog_gain")
sdk.CameraSetAnalogGain = _set("analog_gain", "AnalogGain")
sdk.CameraGetExposureTime = _get("exposure")
sdk.CameraSetExposureTime = _set("exposure", "ExposureTime")
sdk.CameraGetSharpness = _get("sharpness")
sdk.CameraSetSharpness = _set("sharpness", "Sharpness")
sdk.CameraGetGamma = _get("gamma")
sdk.CameraSetGamma = _set("gamma", "Gamma")
sdk.CameraGetContrast = _get("contrast")
sdk.CameraSetContrast = _set("contrast", "Contrast")
sdk.CameraGetGain = _get("gain")
sdk.CameraGetSaturation = _get("saturation")
sdk.CameraSetSaturation = _set("saturation", "Saturation")
sdk.CameraGetFriendlyName = _get("friendly_name")
sdk.CameraSetFriendlyName = _set("friendly_name", "FriendlyName")
sdk.CameraReadSN = _get("serial")


def set_gain(camera, red, green, blue):
    camera.writes.append(("RgbGain", (red, green, blue)))
    if camera.fail_writes:
        sdk._last_error = 0x80000106
        return 0x80000106
    camera.values["gain"] = (red, green, blue)
    sdk._last_error = 0
    return 0


sdk.CameraSetGain = set_gain
for name in (
        "CameraSetTriggerMode", "CameraSoftTrigger", "CameraSetStrobeMode",
        "CameraSetStrobePolarity", "CameraSetAntiFlick",
        "CameraSetLightFrequency", "CameraSetMirror", "CameraSetOnceWB",
        "CameraSetMonochrome", "CameraSetInverse", "CameraSaveParameter",
        "CameraLoadParameter", "CameraSetImageResolution"):
    setattr(sdk, name, lambda *args: 0)

with patch.dict(sys.modules, {"mvsdk": sdk}):
    manager_module = importlib.import_module("camera.camera_manager")
CameraManager = manager_module.CameraManager

qr = types.ModuleType("qr")
qr.ImprovePipeline = type("UnusedPipeline", (), {})
with patch.dict(sys.modules, {"qr": qr, "mvsdk": sdk,
                              "camera.camera_manager": manager_module}):
    window_module = importlib.import_module("ui.main_window")
from PyQt5.QtWidgets import QApplication


class CameraTests(unittest.TestCase):
    def setUp(self):
        self.mgr = CameraManager()
        self.cam = FakeCamera()
        self.mgr._cam = self.mgr.handle = self.cam
        self.mgr.capability = Capability()

    def test_ae_target_uses_mindvision_brightness_target(self):
        self.assertEqual(self.mgr.get_ae_target(), 120)
        self.mgr.set_ae_target(125)
        self.assertEqual(self.cam.writes, [("AeTarget", 125)])

    def test_gamma_public_value_is_fractional(self):
        self.assertAlmostEqual(self.mgr.get_gamma(), 0.7, places=5)
        self.mgr.set_gamma(0.85)
        self.assertEqual(self.cam.values["gamma"], 85)

    def test_failed_set_logs_node_value_and_hex_status(self):
        self.cam.fail_writes = True
        with self.assertLogs("solution.camera", level="WARNING") as logs:
            self.mgr.set_exposure_time(15_000)
        output = " ".join(logs.output)
        for expected in ("ExposureTime", "15000", "0x80000106"):
            self.assertIn(expected, output)

    def test_repeated_sdk_errors_are_rate_limited(self):
        with patch.object(manager_module.time, "monotonic",
                          side_effect=(1.0, 2.0, 7.0)):
            with self.assertLogs("solution.camera", level="WARNING") as logs:
                self.mgr._log_sdk_error("capture", 0x80000007)
                self.mgr._log_sdk_error("capture", 0x80000007)
                self.mgr._log_sdk_error("capture", 0x80000007)
        output = " ".join(logs.output)
        self.assertEqual(output.count("operation=capture"), 2)
        self.assertIn("0x80000007", output)

    def test_frame_diagnostic_reports_brightness_every_five_seconds(self):
        frame = np.array([[[0, 0, 0], [10, 20, 30]],
                          [[100, 110, 120], [250, 250, 250]]], dtype=np.uint8)
        self.mgr._last_diag_at = 0.0
        with patch.object(manager_module.time, "monotonic", return_value=5.1):
            with self.assertLogs("solution.camera", level="INFO") as logs:
                self.mgr._set_frame(frame)
        output = " ".join(logs.output)
        for expected in ("frame_summary", "mean=", "min=0", "max=250",
                         "near_black_pct=25.0"):
            self.assertIn(expected, output)


class UiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = window_module.MainWindow()
        self.window.display_timer.stop()
        self.window.fps_timer.stop()
        self.window.worker.stop()
        self.cam = FakeCamera()
        mgr = self.window.mgr
        mgr._cam = mgr.handle = self.cam
        mgr.capability = Capability()
        mgr.f_exp_line_time = 1.0

    def tearDown(self):
        self.window.mgr._cam = self.window.mgr.handle = None
        self.window.close()

    def test_initializing_ui_is_read_only_and_keeps_exposure(self):
        self.window.ui_init_param()
        self.assertEqual(self.cam.writes, [])
        self.assertEqual(self.cam.values["exposure"], 20_000)
        self.assertEqual(self.window.ui.ae_manual_time_ledit.text(), "20.0")
        self.assertEqual(self.window.ui.ae_auto_hSlider.value(), 120)

    def test_gamma_ui_preserves_fraction_and_writes_native_integer(self):
        self.window.ui_init_param()
        self.assertEqual(self.window.ui.lut_gamma_hSlider.value(), 70)
        self.cam.writes.clear()
        self.window.ui.lut_gamma_hSlider.setValue(85)
        self.assertEqual(self.cam.values["gamma"], 85)

    def test_init_exception_restores_signals_and_guard(self):
        with patch.object(self.window.mgr, "get_exposure_time",
                          side_effect=RuntimeError("read failed")):
            with self.assertRaises(RuntimeError):
                self.window.ui_init_param()
        self.assertEqual(self.window.ui_initing, 0)
        self.assertFalse(self.window.ui.ae_manual_time_hSlider.signalsBlocked())

    def test_exposure_handler_does_not_write_during_initialization(self):
        self.window.ui_initing = 1
        self.window.on_ae_manual_time_hslider(10)
        self.assertEqual(self.cam.writes, [])


if __name__ == "__main__":
    unittest.main()
