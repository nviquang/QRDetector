"""Entry point của app hai camera (MindVision + Basler): python main_dual.py

Cấu hình lưu ở config/dual_settings.json; lần đầu lấy từ cấu hình của hai bản demo một camera.
"""

import sys

from logging_setup import setup_logging

logger = setup_logging()
logger.info("Application starting (dual)")


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

    from demo_ui.app_settings import DUAL_SETTINGS_PATH
    from demo_ui import theme
    from demo_ui.dual_window import DualWindow
    from ui.keyboard_output import KeyboardTyper
except (ImportError, FileNotFoundError, OSError) as e:
    _fail(
        "Không khởi tạo được ứng dụng.\n"
        "Kiểm tra: đã cài requirements.txt, MindVision SDK (MVCAMSDK_X64.dll) và pylon của Basler.\n"
        f"Chi tiết: {e}"
    )


if __name__ == "__main__":
    app = QApplication(sys.argv)
    theme.apply(app)
    window = DualWindow(settings_path=DUAL_SETTINGS_PATH, keyboard_typer=KeyboardTyper())
    window.show()
    sys.exit(app.exec_())
