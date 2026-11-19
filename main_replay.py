"""Entry point bản phát lại: chạy đúng luồng main_basler.py trên dữ liệu đã ghi, không cần camera.

python main_replay.py [--data data/field/raw] [--speed 1.0]
Mỗi thư mục con của --data (frame_NNNN.tiff + meta.json, xem tools/clean_field_data.py) là một "camera" trong tab
Kết nối. Phát theo thời gian ghi gốc × speed; hết frame thì tự Dừng. Cấu hình lưu ở config/replay_settings.json,
mặc định không gửi mã lên server.
"""

import argparse
import os
import sys

from logging_setup import setup_logging

logger = setup_logging()
logger.info("Application starting (Replay)")

ROOT = os.path.dirname(os.path.abspath(__file__))
REPLAY_FLUSH_WAIT_S = 180.0   # Dừng / hết dữ liệu chờ đọc nền tối đa chừng này (bản camera: 5 s)


def _fail(msg: str) -> "NoReturn":
    try:
        sys.stderr.reconfigure(encoding="utf-8")   # console Windows hay không phải UTF-8
    except Exception:
        pass
    logger.error(msg)
    print(msg, file=sys.stderr)
    sys.exit(1)


try:
    # qr (torch) phải load trước PyQt5 — tránh WinError 1114 (c10.dll)
    from qr import ImprovePipeline  # noqa: F401
    from camera.replay_manager import ReplayCameraManager

    from PyQt5.QtWidgets import QApplication

    from demo_ui.app_settings import REPLAY_SETTINGS_PATH, ReplaySettings
    from demo_ui import theme
    from demo_ui.replay_end import ReplayEndWatcher
    from ui.keyboard_output import KeyboardTyper
    from demo_ui.main_window import MainWindow
except (ImportError, FileNotFoundError, OSError) as e:
    _fail(
        "Không khởi tạo được ứng dụng.\n"
        "Kiểm tra: đã cài thư viện (pip install -r requirements.txt); giao diện demo hiện vẫn nạp mvsdk nên máy "
        "cần MindVision SDK (MVCAMSDK_X64.dll).\n"
        f"Chi tiết: {e}"
    )


def parse_args(argv: list[str]):
    ap = argparse.ArgumentParser(description="Phát lại dữ liệu đã ghi qua luồng đọc QR của bản demo Basler")
    ap.add_argument("--data", default=os.path.join(ROOT, "data", "field", "raw"),
                    help="thư mục chứa các lần ghi (mặc định data/field/raw)")
    ap.add_argument("--speed", type=float, default=1.0, help="hệ số tốc độ phát, 1 = thời gian thật")
    return ap.parse_known_args(argv)


if __name__ == "__main__":
    args, qt_args = parse_args(sys.argv[1:])
    if args.speed <= 0:
        _fail("--speed phải lớn hơn 0")
    camera = ReplayCameraManager(args.data, speed=args.speed)
    if not camera.list_cameras():
        _fail(f"Không thấy lần ghi nào trong {args.data} (cần các thư mục con chứa frame_NNNN.tiff).")
    from qr import pass_fallback
    from qr.solvers import LABEL
    fallback = pass_fallback.enable()
    # Lượt cuối video chỉ đóng khi Dừng chốt lượt (hết frame thì seq không tăng nữa), rồi mới gửi đọc nền B/C mất
    # 8–110 s; Dừng của bản camera chỉ chờ 5 s nên kết quả sẽ bị bỏ. Phát lại thì chờ tới khi giải xong.
    pass_fallback.FLUSH_WAIT_S = REPLAY_FLUSH_WAIT_S
    app = QApplication([sys.argv[0]] + qt_args)
    theme.apply(app)
    window = MainWindow(settings_path=REPLAY_SETTINGS_PATH, camera=camera, settings_cls=ReplaySettings,
                        keyboard_typer=KeyboardTyper(), tray=False)
    speed = "" if args.speed == 1.0 else f" ×{args.speed:g}"
    window.setWindowTitle(f"QR Conveyor Reader — Phát lại{speed} — " + (LABEL if fallback else "không đọc nền"))
    window.spin_gain.setSuffix(" dB")
    watcher = ReplayEndWatcher(window, camera)
    window.show()
    sys.exit(app.exec_())
