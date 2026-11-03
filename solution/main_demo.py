"""Entry point của phiên bản demo cho khách hàng: python main_demo.py

App test camera / chỉnh thông số vẫn chạy bằng main.py.
"""

import logging
import sys

from logging_setup import setup_logging

logger = setup_logging()
logger.info("Application starting")


def _fail(msg: str) -> "NoReturn":
    try:
        sys.stderr.reconfigure(encoding="utf-8")   # console Windows hay không phải UTF-8
    except Exception:
        pass
    logger.error(msg)
    sys.exit(1)


try:
    # qr (torch) phải load trước PyQt5 — tránh WinError 1114 (c10.dll)
    from qr import ImprovePipeline  # noqa: F401

    from PyQt5.QtWidgets import QApplication

    from demo_ui.app_settings import DEFAULT_SETTINGS_PATH
    from demo_ui import theme
    from demo_ui.main_window import MainWindow
except (ImportError, FileNotFoundError, OSError) as e:
    _fail(
        "Không khởi tạo được ứng dụng.\n"
        "Kiểm tra: đã cài PyQt5 (pip install PyQt5) và MindVision SDK/driver camera\n"
        "(MVCAMSDK_X64.dll cho Python 64-bit, MVCAMSDK.dll cho Python 32-bit) chưa.\n"
        f"Chi tiết: {e}"
    )


if __name__ == "__main__":
    app = QApplication(sys.argv)
    theme.apply(app)
    window = MainWindow(settings_path=DEFAULT_SETTINGS_PATH)
    window.show()
    sys.exit(app.exec_())
