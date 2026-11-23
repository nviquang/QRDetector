"""Backend TensorRT của OnnxQRDetector (GPU Jetson qua tools/trt_service.py): chọn thiết bị, lùi về CPU khi dịch vụ lỗi,
và giao thức socket + /dev/shm với một dịch vụ giả (chỉ chạy nơi có AF_UNIX).

Chạy (từ gốc repo):  python -m unittest tests.test_detector_trt
"""
from pathlib import Path
import os
import socket
import sys
import tempfile
import threading
import unittest
from unittest import mock

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from qr import detector_onnx  # noqa: E402
from qr.detector_onnx import OnnxQRDetector  # noqa: E402
from qr.improved_pipeline import make_detector  # noqa: E402

IMG = np.zeros((1072, 2856, 3), np.uint8)


class FakeGpu:
    def __init__(self, fail=False):
        self.fail, self.calls = fail, 0

    def __call__(self, tensor):
        self.calls += 1
        if self.fail:
            raise ConnectionError("dịch vụ tắt")
        return np.zeros((1, 5, 10), np.float32)


class TrtBackendTests(unittest.TestCase):
    def make(self, gpu):
        with mock.patch.object(detector_onnx, "_TrtClient", return_value=gpu):
            return OnnxQRDetector(backend="tensorrt")

    def test_reports_gpu_device(self):
        det = self.make(FakeGpu())
        self.assertEqual((det.device, det.gpu_available), ("cuda:trt", True))
        self.assertEqual(det.detect(IMG), [])

    def test_service_error_falls_back_to_cpu(self):
        gpu = FakeGpu(fail=True)
        det = self.make(gpu)
        with self.assertLogs("solution.qr", "WARNING"):
            self.assertEqual(det.detect(IMG), [])
        self.assertEqual(det.device, "cpu")
        det.detect(IMG)
        self.assertEqual(gpu.calls, 1)           # đã chuyển hẳn sang CPU
        det.set_device("auto")                   # bật lại ô Dùng GPU thì thử GPU lại
        self.assertEqual(det.device, "cuda:trt")

    def test_set_device_cpu_and_back(self):
        gpu = FakeGpu()
        det = self.make(gpu)
        det.set_device("cpu")
        det.detect(IMG)
        self.assertEqual((det.device, gpu.calls), ("cpu", 0))
        det.set_device("auto")
        det.detect(IMG)
        self.assertEqual(gpu.calls, 1)

    def test_make_detector_falls_back_when_service_missing(self):
        with mock.patch.dict(os.environ, {"QR_DETECTOR": "tensorrt"}), \
                mock.patch.object(detector_onnx, "_TrtClient", side_effect=FileNotFoundError("không có socket")), \
                self.assertLogs("solution.qr", "WARNING"):
            det = make_detector()
        self.assertIn(det.backend, ("openvino", "onnxruntime"))
        self.assertFalse(det.gpu_available)


@unittest.skipUnless(hasattr(socket, "AF_UNIX"), "cần Unix socket")
class TrtProtocolTests(unittest.TestCase):
    def test_round_trip_with_fake_service(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        sock_path, shm_path = os.path.join(tmp.name, "s.sock"), os.path.join(tmp.name, "in")
        with open(shm_path, "wb") as f:
            f.truncate(3 * 64 * 64 * 2)
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(sock_path)
        server.listen(1)
        seen = {}

        def serve():
            conn, _ = server.accept()
            magic, h, w = detector_onnx.TRT_REQUEST.unpack(conn.recv(detector_onnx.TRT_REQUEST.size))
            with open(shm_path, "rb") as f:
                seen["tensor"] = np.frombuffer(f.read(3 * h * w * 2), np.float16).copy()
            out = np.arange(10, dtype=np.float32).reshape(5, 2)
            conn.sendall(detector_onnx.TRT_RESPONSE.pack(magic, 0, 5, 2) + out.tobytes())
            conn.close()

        thread = threading.Thread(target=serve)
        thread.start()
        client = detector_onnx._TrtClient(sock_path, shm_path)
        tensor = np.full((1, 3, 32, 64), 0.5, np.float32)
        out = client(tensor)
        thread.join(5)
        server.close()
        self.assertEqual(out.shape, (1, 5, 2))
        self.assertEqual(float(out[0, 4, 1]), 9.0)
        self.assertTrue(np.all(seen["tensor"] == np.float16(0.5)))


if __name__ == "__main__":
    unittest.main()
