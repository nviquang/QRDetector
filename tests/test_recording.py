"""Native recorder contracts without camera DLLs or large output files."""
import importlib
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def head(width=640, height=480, media=3, stamp=1000):
    return types.SimpleNamespace(iWidth=width, iHeight=height,
                                 uiMediaType=media, uiTimeStamp=stamp)


class RecordingTests(unittest.TestCase):
    def setUp(self):
        self.module = importlib.import_module("camera.recording")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.sdk = Mock()
        self.sdk.CAMERA_MEDIA_TYPE_RGB8 = 3
        self.sdk.CAMERA_MEDIA_TYPE_MONO8 = 1
        self.sdk.CameraInitRecord.return_value = 0
        self.sdk.CameraPushFrame.return_value = 0
        self.sdk.CameraStopRecord.return_value = 0
        self.now = 0.0
        self.free = 10 ** 12
        self.rec = self.module.NativeRecorder(
            self.sdk, clock=lambda: self.now,
            disk_free=lambda path: self.free)

    def options(self, **kwargs):
        return self.module.RecordingOptions(Path(self.tmp.name), **kwargs)

    def start(self, **kwargs):
        self.rec.start(7, self.options(**kwargs), head())

    def test_native_arguments_and_original_header_are_preserved(self):
        self.start()
        info = head()
        self.rec.push(7, 12345, info)
        args = self.sdk.CameraInitRecord.call_args.args
        self.assertEqual((args[0], args[1], args[3:]), (7, 0, (False, 100, 60)))
        self.assertTrue(Path(args[2]).is_absolute())
        self.sdk.CameraPushFrame.assert_called_once_with(7, 12345, info)
        self.assertEqual(self.rec.status().pushed_frames, 1)
        self.rec.stop(7)
        self.rec.stop(7)
        self.sdk.CameraStopRecord.assert_called_once_with(7)
        self.assertEqual(self.rec.status().state, "COMPLETED")
        self.assertFalse(self.rec.status().native_open)

    def test_color_diagnostic_records_native_mutation_without_changing_push(self):
        import ctypes
        import json
        self.start(color_diagnostics=True)
        info = head(width=640, height=480)
        buffer = (ctypes.c_ubyte * (640 * 480 * 3))()
        buffer[0] = 255
        pointer = ctypes.addressof(buffer)
        def mutate(handle, received_pointer, received_info):
            self.assertEqual(received_pointer, pointer)
            self.assertIs(received_info, info)
            buffer[0], buffer[2] = 0, 255
            return 0
        self.sdk.CameraPushFrame.side_effect = mutate
        self.rec.push(7, pointer, info)
        self.rec.stop(7)
        self.assertTrue(self.rec._diagnostics.wait(5))
        target = Path(self.rec.status().current_path).parent / "color_diagnostics" / "sample_0001"
        metadata = json.loads((target / "metadata.json").read_text(encoding="utf-8"))
        self.assertTrue(metadata["buffer_changed"])
        self.assertTrue(metadata["push_succeeded"])
        self.assertEqual((target / "before.bin").read_bytes()[:3], bytes([255, 0, 0]))
        self.assertEqual((target / "after.bin").read_bytes()[:3], bytes([0, 0, 255]))
        self.assertEqual(self.rec.status().state, "COMPLETED")

    def test_init_failure_never_reports_recording(self):
        self.sdk.CameraInitRecord.return_value = 0x80000106
        self.start()
        status = self.rec.status()
        self.assertEqual(status.state, "ERROR")
        self.assertIn("80000106", status.error)
        self.assertFalse(status.native_open)

    def test_push_error_finalizes_but_preserves_error(self):
        self.start()
        self.sdk.CameraPushFrame.side_effect = OSError("disk failed")
        self.rec.push(7, 123, head())
        self.assertEqual(self.rec.status().state, "ERROR")
        self.assertIn("disk failed", self.rec.status().error)
        self.assertFalse(self.rec.status().native_open)
        self.assertEqual(self.rec.status().pushed_frames, 0)
        self.sdk.CameraStopRecord.assert_called_once()

    def test_stop_error_retains_native_ownership_until_explicit_retry(self):
        self.start()
        self.sdk.CameraStopRecord.return_value = -1
        self.rec.stop(7)
        self.assertTrue(self.rec.status().native_open)
        self.assertEqual(self.rec.status().state, "ERROR")
        self.sdk.CameraStopRecord.return_value = 0
        self.rec.stop(7)
        self.assertFalse(self.rec.status().native_open)
        self.assertEqual(self.rec.status().state, "ERROR")

    def test_clock_and_timestamp_advances_do_not_split_recording(self):
        for elapsed, stamp in ((120.0, 1000), (0.0, 1201000), (120.0, 1201000)):
            with self.subTest(elapsed=elapsed, stamp=stamp):
                self.sdk.reset_mock()
                self.start()
                first = self.rec.status().current_path
                info = head(stamp=stamp)
                self.rec.push(7, 123, head())
                self.now += elapsed
                self.rec.push(7, 456, info)
                self.sdk.CameraInitRecord.assert_called_once()
                self.sdk.CameraStopRecord.assert_not_called()
                self.sdk.CameraPushFrame.assert_called_with(7, 456, info)
                self.assertEqual(self.sdk.CameraPushFrame.call_count, 2)
                self.assertEqual(self.rec.status().current_path, first)
                self.assertEqual(Path(first).name, "video.avi")
                self.assertEqual(self.rec.status().segment, 1)
                self.assertEqual(self.rec.status().pushed_frames, 2)
                self.assertEqual(self.rec.status().state, "RECORDING")
                self.rec.stop(7)
                self.rec.stop(7)
                self.sdk.CameraStopRecord.assert_called_once_with(7)

    def test_large_observed_file_does_not_split_recording(self):
        for size in ((1 << 30) + 1, (2 << 30) + 1, (4 << 30) + 1):
            with self.subTest(size=size):
                self.sdk.reset_mock()
                self.start()
                first = self.rec.status().current_path
                info = head()
                with patch.object(Path, "exists", return_value=True), \
                        patch.object(Path, "stat", return_value=types.SimpleNamespace(st_size=size)):
                    self.rec.push(7, 123, info)
                self.sdk.CameraInitRecord.assert_called_once()
                self.sdk.CameraStopRecord.assert_not_called()
                self.sdk.CameraPushFrame.assert_called_once_with(7, 123, info)
                self.assertEqual(self.rec.status().current_path, first)
                self.assertEqual(self.rec.status().segment, 1)
                self.assertEqual(self.rec.status().state, "RECORDING")
                self.rec.stop(7)
                self.sdk.CameraStopRecord.assert_called_once_with(7)

    def test_invalid_options_and_non_gbk_path_do_not_initialize_sdk(self):
        for options in (self.options(fps=0), self.options(fps=1001),
                        self.module.RecordingOptions(Path(self.tmp.name) / "😀")):
            with self.subTest(options=options):
                self.rec.start(7, options, head())
                self.assertEqual(self.rec.status().state, "ERROR")
                self.assertFalse(self.rec.status().native_open)
        self.sdk.CameraInitRecord.assert_not_called()

    def test_low_disk_during_recording_stops_with_persistent_error(self):
        self.start()
        self.free = 1
        self.now = 2
        self.rec.maintain(7)
        self.assertEqual(self.rec.status().state, "ERROR")
        self.assertFalse(self.rec.status().native_open)
        self.assertIn("dung", self.rec.status().error.lower())
        self.sdk.CameraPushFrame.assert_not_called()
        self.sdk.CameraStopRecord.assert_called_once_with(7)
        self.sdk.CameraInitRecord.assert_called_once()

    def test_format_change_is_not_written_into_existing_file(self):
        self.start()
        self.rec.push(7, 123, head(width=320))
        self.sdk.CameraPushFrame.assert_not_called()
        self.assertEqual(self.rec.status().state, "ERROR")

    def test_timestamp_wrap_is_valid_but_backward_reset_stops_recording(self):
        self.rec.start(7, self.options(), head(stamp=0xFFFFFF00))
        self.rec.push(7, 1, head(stamp=0xFFFFFF00))
        self.rec.push(7, 2, head(stamp=200))
        self.assertEqual(self.rec.status().pushed_frames, 2)
        self.rec.push(7, 3, head(stamp=100))
        self.assertEqual(self.rec.status().state, "ERROR")
        self.assertEqual(self.rec.status().pushed_frames, 2)

    def test_mono_records_without_bgr_conversion(self):
        info = head(media=1)
        self.rec.start(7, self.options(), info)
        self.rec.push(7, 555, info)
        self.sdk.CameraPushFrame.assert_called_once_with(7, 555, info)

    def test_sessions_have_distinct_directories_and_preserve_existing_data(self):
        self.start()
        first = Path(self.rec.status().current_path)
        first.write_bytes(b"existing")
        self.rec.stop(7)
        self.start()
        self.assertNotEqual(first.parent, Path(self.rec.status().current_path).parent)
        self.assertEqual(first.read_bytes(), b"existing")


if __name__ == "__main__":
    unittest.main()
