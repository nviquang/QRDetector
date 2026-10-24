"""Acquisition-owned recording with isolated fake MVSDK modules."""
import ctypes
import importlib.util
from pathlib import Path
import sys
import tempfile
import threading
import types
import unittest
from unittest.mock import Mock, patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from camera.recording import RecordingOptions


class CameraException(Exception):
    def __init__(self, code):
        self.error_code = code
        self.message = "fake timeout"


class CameraRecordingTests(unittest.TestCase):
    def setUp(self):
        self.sdk = Mock()
        self.sdk.CameraException = CameraException
        self.sdk.CAMERA_MEDIA_TYPE_RGB8 = 3
        self.sdk.CAMERA_MEDIA_TYPE_MONO8 = 1
        for name in ("CameraInitRecord", "CameraPushFrame", "CameraStopRecord",
                     "CameraReleaseImageBuffer", "CameraStop", "CameraUnInit",
                     "CameraSetImageResolution", "CameraLoadParameter", "CameraSetTriggerMode"):
            getattr(self.sdk, name).return_value = 0
        self.sdk.GetLastError.return_value = 0
        self.sdk.CameraGetFrameStatistic.return_value = types.SimpleNamespace(iCapture=1, iLost=2)
        spec = importlib.util.spec_from_file_location(
            "camera._recording_test_manager", ROOT / "camera" / "camera_manager.py")
        self.module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"mvsdk": self.sdk}):
            spec.loader.exec_module(self.module)
        self.mgr = self.module.CameraManager()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.mgr.handle = self.mgr._cam = 7
        self.mgr._running = True
        self.buffer = (ctypes.c_ubyte * 12)(*range(12))
        self.mgr._frame_buffer = ctypes.addressof(self.buffer)
        self.mgr._frame_buffer_size = 12
        self.mgr._recorder._disk_free = lambda path: 10 ** 12
        self.info = types.SimpleNamespace(iWidth=2, iHeight=2, uiMediaType=3, uiTimeStamp=1000)
        self.finished = threading.Event()
        self.blocked = threading.Event()
        self.release = threading.Event()
        self.calls = []
        self.sdk.CameraImageProcess.side_effect = self.process
        self.sdk.CameraPushFrame.side_effect = self.push
        self.sdk.CameraGetImageBuffer.side_effect = self.get_frame
        self.sdk.CameraReleaseImageBuffer.side_effect = lambda *a: self.calls.append("release") or 0
        self.sdk.CameraStopRecord.side_effect = lambda *a: self.calls.append("finalize") or 0
        self.mgr._set_frame(np.zeros((2, 2, 3), dtype=np.uint8))
        self.mgr._record_head = self.info
        self.count = 0

    def process(self, *args):
        self.calls.append("process")
        return 0

    def push(self, handle, pointer, info):
        self.calls.append("push")
        self.assertEqual(threading.get_ident(), self.mgr._thread.ident)
        self.assertEqual(pointer, ctypes.addressof(self.buffer))
        self.assertEqual(info.uiMediaType, 3)
        self.assertEqual(info.uiTimeStamp, 1000)
        self.finished.set()
        return 0

    def get_frame(self, *args):
        if self.count:
            self.mgr._running = False
            raise CameraException(1)
        self.count += 1
        return 100, self.info

    def start_thread(self):
        self.mgr._thread = self.module._CaptureThread(self.mgr)
        self.mgr._thread.start()

    def join_thread(self):
        self.mgr._thread.join(3)
        self.assertFalse(self.mgr._thread.is_alive())

    def test_acquisition_pushes_without_preview_and_finalizes_before_teardown(self):
        self.assertTrue(self.mgr.start_recording(RecordingOptions(Path(self.tmp.name))))
        self.assertEqual(self.sdk.CameraInitRecord.call_count, 0)
        self.start_thread()
        self.join_thread()
        self.assertEqual(self.calls, ["process", "push", "release", "finalize"])
        self.assertEqual(self.mgr.recording_status().pushed_frames, 1)
        self.mgr.close()
        self.sdk.CameraUnInit.assert_called_once_with(7)
        self.sdk.CameraAlignFree.assert_called_once()
        self.assertIsNone(self.mgr.handle)

    def test_start_uses_next_processed_frame_not_stale_roi_header(self):
        self.assertTrue(self.mgr.start_recording(RecordingOptions(Path(self.tmp.name))))
        self.mgr._service_recording()
        self.sdk.CameraInitRecord.assert_not_called()
        self.info = types.SimpleNamespace(iWidth=1, iHeight=2, uiMediaType=3, uiTimeStamp=1000)
        self.start_thread()
        self.join_thread()
        self.assertEqual(self.mgr._recorder._geometry, (1, 2, 3))
        self.assertEqual(self.mgr.recording_status().pushed_frames, 1)
        self.assertFalse(self.mgr.recording_status().error)

    def test_process_error_never_pushes_and_still_releases(self):
        self.sdk.CameraImageProcess.side_effect = lambda *a: -1
        self.mgr.start_recording(RecordingOptions(Path(self.tmp.name)))
        self.start_thread()
        self.join_thread()
        self.sdk.CameraPushFrame.assert_not_called()
        self.assertIn("release", self.calls)
        self.assertEqual(self.mgr.recording_status().pushed_frames, 0)

    def test_stop_cancels_accepted_start_without_waiting_for_frame(self):
        self.assertTrue(self.mgr.start_recording(RecordingOptions(Path(self.tmp.name))))
        self.assertFalse(self.mgr.start_recording(RecordingOptions(Path(self.tmp.name))))
        self.assertTrue(self.mgr.stop_recording())
        self.assertTrue(self.mgr.stop_recording())
        self.start_thread()
        self.join_thread()
        self.sdk.CameraInitRecord.assert_not_called()
        self.assertEqual(self.mgr.recording_status().state, "COMPLETED")

    def test_pending_recording_blocks_camera_configuration_at_boundary(self):
        self.mgr.capability = types.SimpleNamespace(iImageSizeDesc=1, pImageSizeDesc=[object()])
        self.mgr.start_recording(RecordingOptions(Path(self.tmp.name)))
        self.assertFalse(self.mgr.set_roi(0))
        self.assertFalse(self.mgr.load_param(0))
        self.assertFalse(self.mgr.reset_param())
        self.assertFalse(self.mgr.set_trigger_mode(1))
        self.sdk.CameraSetImageResolution.assert_not_called()
        self.sdk.CameraLoadParameter.assert_not_called()
        self.sdk.CameraSetTriggerMode.assert_not_called()

    def test_blocked_push_keeps_status_readable_and_retains_native_resources(self):
        def push(*args):
            self.blocked.set()
            self.release.wait(10)
            return 0
        self.sdk.CameraPushFrame.side_effect = push
        self.mgr.start_recording(RecordingOptions(Path(self.tmp.name)))
        self.start_thread()
        self.assertTrue(self.blocked.wait(2))
        self.addCleanup(self.release.set)
        self.assertEqual(self.mgr.recording_status().state, "RECORDING")
        self.mgr.close()
        self.assertEqual(self.mgr.handle, 7)
        self.sdk.CameraUnInit.assert_not_called()
        self.sdk.CameraAlignFree.assert_not_called()
        self.sdk.CameraStop.assert_not_called()
        self.release.set()
        self.join_thread()
        self.mgr.close()
        self.assertIsNone(self.mgr.handle)

    def test_stop_error_prevents_teardown_and_reopen_over_old_handle(self):
        self.sdk.CameraStopRecord.side_effect = None
        self.sdk.CameraStopRecord.return_value = -1
        self.mgr.start_recording(RecordingOptions(Path(self.tmp.name)))
        self.start_thread()
        self.join_thread()
        self.mgr.close()
        self.assertEqual(self.mgr.handle, 7)
        self.sdk.CameraUnInit.assert_not_called()
        self.mgr.camera_list = [object()]
        self.assertFalse(self.mgr.open(0))
        self.sdk.CameraInit.assert_not_called()

    def test_explicit_stop_retry_after_capture_exit_can_resolve_native_ownership(self):
        self.sdk.CameraStopRecord.side_effect = None
        self.sdk.CameraStopRecord.return_value = -1
        self.mgr.start_recording(RecordingOptions(Path(self.tmp.name)))
        self.start_thread()
        self.join_thread()
        self.assertTrue(self.mgr.recording_status().native_open)
        self.sdk.CameraStopRecord.return_value = 0
        self.assertTrue(self.mgr.stop_recording())
        self.mgr._thread.join(2)
        self.assertFalse(self.mgr.recording_status().native_open)
        self.assertTrue(self.mgr.stop_recording())
        self.assertNotEqual(self.mgr.recording_status().state, "STOPPING")
        self.mgr.close()
        self.assertIsNone(self.mgr.handle)

    def test_capture_counter_failure_is_unknown_not_zero_loss(self):
        self.sdk.CameraGetFrameStatistic.side_effect = OSError("counter unavailable")
        self.mgr.start_recording(RecordingOptions(Path(self.tmp.name)))
        self.start_thread()
        self.join_thread()
        self.assertIsNone(self.mgr.recording_status().lost_delta)

    def test_soft_trigger_during_recording_is_serviced_by_capture_owner(self):
        self.sdk.CameraSoftTrigger.return_value = 0
        self.mgr.start_recording(RecordingOptions(Path(self.tmp.name)))
        self.assertTrue(self.mgr.soft_trigger())
        self.sdk.CameraSoftTrigger.assert_not_called()
        self.start_thread()
        self.join_thread()
        self.sdk.CameraSoftTrigger.assert_called_once_with(7)

    def test_close_keeps_owner_visible_until_join_has_finished(self):
        owner = Mock()
        owner.is_alive.return_value = False
        owner.join.side_effect = lambda **kwargs: self.assertIs(self.mgr._thread, owner)
        self.mgr._thread = owner
        self.mgr.close()
        self.assertIsNone(self.mgr.handle)

    def test_uninit_failure_retains_handle_and_buffer_and_refuses_reopen(self):
        self.mgr._running = False
        self.sdk.CameraUnInit.return_value = -7
        self.mgr.close()
        self.assertEqual(self.mgr.handle, 7)
        self.sdk.CameraAlignFree.assert_not_called()
        self.mgr.camera_list = [object()]
        self.assertFalse(self.mgr.open(0))
        self.sdk.CameraInit.assert_not_called()
        self.sdk.CameraUnInit.return_value = 0
        self.mgr.close()
        self.assertIsNone(self.mgr.handle)
        self.sdk.CameraAlignFree.assert_called_once()

    def test_start_requires_live_camera_and_valid_frame(self):
        self.mgr._running = False
        self.assertFalse(self.mgr.start_recording(RecordingOptions(Path(self.tmp.name))))
        self.sdk.CameraInitRecord.assert_not_called()


if __name__ == "__main__":
    unittest.main()
