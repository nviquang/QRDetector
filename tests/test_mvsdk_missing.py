"""Máy chỉ dùng camera Basler (Jetson Nano) không có MindVision SDK: mvsdk vẫn import được, app Basler vẫn nạp được.

Chạy trong tiến trình con, giả lập thiếu thư viện bằng cách làm ctypes.windll / cdll.LoadLibrary báo OSError trước khi
import mvsdk (tiến trình test chính đã nạp DLL thật).

Chạy (từ gốc repo):  python -m unittest tests.test_mvsdk_missing
"""
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]

SCRIPT = r"""
import ctypes, os
os.environ["QT_QPA_PLATFORM"] = "offscreen"

class _NoLib:
    def __getattr__(self, name):
        raise FileNotFoundError("không có " + name)
    def LoadLibrary(self, name):
        raise OSError("không có " + name)

real = (getattr(ctypes, "windll", None), ctypes.cdll)
ctypes.windll = _NoLib()
ctypes.cdll = _NoLib()
import mvsdk
ctypes.windll, ctypes.cdll = real     # trả lại cho pyzbar, OpenCV… nạp thư viện của chúng
assert mvsdk.AVAILABLE is False and mvsdk.LOAD_ERROR is not None
try:
    mvsdk.CameraEnumerateDevice()
except OSError as e:
    assert "MindVision" in str(e), e
else:
    raise AssertionError("gọi SDK khi thiếu thư viện phải báo OSError")

from qr import ImprovePipeline  # noqa: F401  (qr trước PyQt5 như main_basler.py)
from camera.basler_manager import BaslerCameraManager  # noqa: F401
from camera.camera_manager import CameraManager
from demo_ui.main_window import MainWindow  # noqa: F401
CameraManager()
print("ok")
"""


class MissingMvsdkTests(unittest.TestCase):
    def test_basler_app_imports_without_mindvision_sdk(self):
        done = subprocess.run([sys.executable, "-c", SCRIPT], cwd=ROOT, capture_output=True, text=True,
                              timeout=300)
        self.assertEqual(done.returncode, 0, done.stderr[-2000:])
        self.assertIn("ok", done.stdout)


if __name__ == "__main__":
    unittest.main()
