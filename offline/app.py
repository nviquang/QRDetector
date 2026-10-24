"""Entry point app offline (không cần camera):  python offline/app.py [ảnh|thư mục|video ...]"""

import logging
import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("offline")


def _fail(msg: str) -> "NoReturn":
    try:
        sys.stderr.reconfigure(encoding="utf-8")   # console Windows hay không phải UTF-8
    except Exception:
        pass
    logger.error(msg)
    sys.exit(1)


try:
    # qr (torch) phải load trước PyQt5 — tránh WinError 1114 (c10.dll)
    from qr import ImprovePipeline

    from PyQt5.QtWidgets import QApplication

    from main_window import MainWindow
    from media_source import is_image, is_video, list_images
except (ImportError, FileNotFoundError, OSError) as e:
    _fail(
        "Không khởi tạo được ứng dụng.\n"
        "Kiểm tra đã cài: PyQt5 opencv-contrib-python pyzbar zxing-cpp qrdet torch.\n"
        f"Chi tiết: {e}"
    )


def main() -> int:
    app = QApplication(sys.argv)
    logger.info("Đang nạp model QR (qrdet)…")
    pipeline = ImprovePipeline()
    window = MainWindow(pipeline)
    window.show()

    args = sys.argv[1:]
    videos = [p for p in args if is_video(p)]
    images = [p for p in args if is_image(p)]
    for p in args:
        if os.path.isdir(p):
            images.extend(list_images(p))
    if videos:
        window.load_video(videos[0])
    elif images:
        window.load_images(images)
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
