"""Máy không cài torch/qrdet (Jetson Nano, docs/jetson-nano.md) vẫn import được gói qr và dùng bộ phát hiện ONNX.

Chạy trong tiến trình con với torch, qrdet, ultralytics bị chặn (sys.modules[...] = None làm import báo ImportError),
vì tiến trình test chính đã nạp torch.

Chạy (từ gốc repo):  python -m unittest tests.test_no_torch
"""
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]

SCRIPT = r"""
import os, sys
for name in ("torch", "torchvision", "qrdet", "ultralytics"):
    sys.modules[name] = None
os.environ["QR_DETECTOR"] = "onnx"
from qr import ImprovePipeline, QRDetector
from qr.improved_pipeline import make_detector
from qr.detector_onnx import OnnxQRDetector
assert isinstance(make_detector(), OnnxQRDetector)
try:
    QRDetector()
except ImportError as e:
    assert "QR_DETECTOR" in str(e), e
else:
    raise AssertionError("QRDetector phải báo ImportError khi thiếu torch")
assert "torch" not in [m for m, v in sys.modules.items() if v is not None]
print("ok")
"""


class NoTorchTests(unittest.TestCase):
    def test_qr_package_runs_without_torch(self):
        done = subprocess.run([sys.executable, "-c", SCRIPT], cwd=ROOT, capture_output=True, text=True,
                              timeout=300)
        self.assertEqual(done.returncode, 0, done.stderr[-2000:])
        self.assertIn("ok", done.stdout)


if __name__ == "__main__":
    unittest.main()
