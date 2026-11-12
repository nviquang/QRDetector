"""Entry point của bản demo dùng camera Basler: python main_basler.py

Cùng giao diện với main_demo.py, cấu hình lưu riêng ở config/basler_settings.json.
"""

import sys

from logging_setup import setup_logging

logger = setup_logging()
logger.info("Application starting (Basler)")


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
    from camera.basler_manager import BaslerCameraManager

    from PyQt5.QtWidgets import QApplication

    from demo_ui.app_settings import BASLER_SETTINGS_PATH, BaslerSettings
    from demo_ui import theme
    from ui.keyboard_output import KeyboardTyper
    from demo_ui.main_window import MainWindow
except (ImportError, FileNotFoundError, OSError) as e:
    _fail(
        "Không khởi tạo được ứng dụng.\n"
        "Kiểm tra: đã cài pypylon và pylon (pip install -r requirements.txt, bộ cài pylon của Basler);\n"
        "giao diện demo hiện vẫn nạp mvsdk nên máy cũng cần MindVision SDK (MVCAMSDK_X64.dll).\n"
        f"Chi tiết: {e}"
    )


if __name__ == "__main__":
    from qr import pass_fallback
    from qr.solvers import LABEL
    fallback = pass_fallback.enable()
    app = QApplication(sys.argv)
    theme.apply(app)
    window = MainWindow(settings_path=BASLER_SETTINGS_PATH, camera=BaslerCameraManager(),
                        settings_cls=BaslerSettings, keyboard_typer=KeyboardTyper())
    window.setWindowTitle("QR Conveyor Reader — Basler — " + (LABEL if fallback else "không đọc nền"))
    window.spin_gain.setSuffix(" dB")
    window.show()
    sys.exit(app.exec_())
