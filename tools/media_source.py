"""Nguồn media offline: đọc ảnh / video → frame BGR uint8 contiguous.

Ảnh đọc bằng np.fromfile + cv2.imdecode để chịu được đường dẫn Unicode (tiếng Việt)
trên Windows. Mọi frame trả ra đều qua ensure_bgr() — 3 kênh BGR, contiguous.
"""

from __future__ import annotations

import os

import cv2
import numpy as np

IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp")
VIDEO_EXTS = (".mp4", ".avi", ".mov", ".mkv", ".wmv", ".m4v")

DEFAULT_FPS = 25.0


class MediaError(Exception):
    """Không đọc được ảnh/video."""


def is_image(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in IMAGE_EXTS


def is_video(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in VIDEO_EXTS


def ensure_bgr(frame: np.ndarray) -> np.ndarray:
    """Chuẩn hoá mọi frame về BGR 3 kênh uint8 contiguous."""
    if frame.dtype != np.uint8:
        frame = cv2.convertScaleAbs(frame)
    if frame.ndim == 2:
        frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
    elif frame.shape[2] == 4:
        frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
    elif frame.shape[2] == 1:
        frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
    return np.ascontiguousarray(frame)


def read_image(path: str) -> np.ndarray:
    try:
        data = np.fromfile(path, dtype=np.uint8)
    except OSError as e:
        raise MediaError(f"Không mở được file ảnh: {path} ({e})") from e
    image = cv2.imdecode(data, cv2.IMREAD_UNCHANGED) if data.size else None
    if image is None:
        raise MediaError(f"File không phải ảnh hợp lệ: {path}")
    return ensure_bgr(image)


def write_image(path: str, image_bgr: np.ndarray) -> None:
    """Ghi ảnh (hỗ trợ đường dẫn Unicode). Định dạng theo đuôi file."""
    ext = os.path.splitext(path)[1] or ".png"
    ok, buf = cv2.imencode(ext, image_bgr)
    if not ok:
        raise MediaError(f"Không encode được ảnh với định dạng {ext}")
    buf.tofile(path)


def list_images(folder: str) -> list[str]:
    """Ảnh trong thư mục (không đệ quy), sắp xếp theo tên."""
    names = sorted(n for n in os.listdir(folder) if is_image(n))
    return [os.path.join(folder, n) for n in names]


class VideoSource:
    """Bọc cv2.VideoCapture: đọc tuần tự, seek, metadata. Không thread-safe."""

    def __init__(self, path: str):
        self.path = path
        self._cap = cv2.VideoCapture(path)
        if not self._cap.isOpened():
            self._cap.release()
            raise MediaError(
                f"Không mở được video: {path}\n"
                "(OpenCV có thể không mở được đường dẫn có ký tự đặc biệt — thử đường dẫn ASCII)")
        fps = self._cap.get(cv2.CAP_PROP_FPS)
        self.fps = fps if fps and fps > 0 and fps < 1000 else DEFAULT_FPS
        self.frame_count = max(0, int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT)))
        self.width = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.height = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self._next_index = 0

    @property
    def position(self) -> int:
        """Chỉ số frame sẽ được read() trả về tiếp theo."""
        return self._next_index

    def read(self) -> tuple[int, np.ndarray] | None:
        """Trả về (chỉ số frame, frame BGR) hoặc None khi hết video / lỗi đọc."""
        ok, frame = self._cap.read()
        if not ok or frame is None:
            return None
        index = self._next_index
        self._next_index += 1
        return index, ensure_bgr(frame)

    def grab(self) -> bool:
        """Bỏ qua 1 frame không decode ảnh (nhanh hơn read)."""
        ok = self._cap.grab()
        if ok:
            self._next_index += 1
        return ok

    def seek(self, index: int) -> None:
        index = max(0, index)
        if self.frame_count:
            index = min(index, self.frame_count - 1)
        self._cap.set(cv2.CAP_PROP_POS_FRAMES, index)
        self._next_index = index

    def timestamp(self, index: int) -> float:
        return index / self.fps

    def release(self) -> None:
        self._cap.release()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.release()


def format_time(seconds: float) -> str:
    m, s = divmod(max(0.0, seconds), 60)
    h, m = divmod(int(m), 60)
    return f"{h:d}:{m:02d}:{s:06.3f}" if h else f"{m:02d}:{s:06.3f}"
