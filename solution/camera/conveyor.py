"""Công thức chế độ băng chuyền — thuần Python, không phụ thuộc SDK/Qt.

Băng chạy theo trục x của ảnh. Trong thời gian phơi sáng, QR trôi ``v × t`` mm, tức
``v × t ÷ mm_per_px`` pixel — đó là độ dài vệt mờ chuyển động. Giữ vệt mờ ≤ ``max_blur_px``:

    t_max = max_blur_px × mm_per_px ÷ v

Ví dụ lab (~0.43 mm/px, mờ ≤ 1 px): 10 cm/s → 4.3 ms, 20 cm/s → 2.15 ms, 30 cm/s → 1.43 ms.
"""

from __future__ import annotations

from dataclasses import dataclass

SPEEDS_MM_S = (100.0, 200.0, 300.0)   # 10 / 20 / 30 cm/s


def max_exposure_us(speed_mm_s: float, mm_per_px: float, max_blur_px: float = 1.0) -> float:
    """Exposure lớn nhất (µs) để vệt mờ chuyển động không vượt ``max_blur_px``."""
    if speed_mm_s <= 0:
        raise ValueError("speed_mm_s phải > 0")
    return max_blur_px * mm_per_px / speed_mm_s * 1e6


def blur_px(speed_mm_s: float, mm_per_px: float, exposure_us: float) -> float:
    """Độ dài vệt mờ chuyển động (px) với exposure cho trước."""
    return speed_mm_s * exposure_us * 1e-6 / mm_per_px


def px_per_module(mm_per_px: float, qr_mm: float = 25.0, modules: int = 21) -> float:
    """Số pixel trên mỗi ô QR (QR version 1 = 21 ô, 12 chữ số)."""
    return qr_mm / mm_per_px / modules


def frames_in_view(fov_along_mm: float, speed_mm_s: float, fps: float, qr_mm: float = 25.0) -> float:
    """Số frame một QR nằm trọn trong vùng nhìn theo hướng băng chạy."""
    return max(0.0, fov_along_mm - qr_mm) / speed_mm_s * fps


def align_band(y: int, height: int, sensor_height: int, step: int = 16) -> tuple[int, int]:
    """Căn dải ROI (y, height) theo bội ``step`` và nằm trong sensor.

    MindVision yêu cầu offset/kích thước ROI chia hết cho bước của sensor; 16 an toàn cho
    đa số model — cần kiểm chứng trên camera thật nếu SDK từ chối.
    """
    height = max(step, min(sensor_height, int(round(height / step)) * step))
    y = max(0, min(sensor_height - height, int(y) // step * step))
    return y, height


@dataclass(frozen=True)
class ConveyorSettings:
    speed_mm_s: float = 300.0
    mm_per_px: float = 0.43
    max_blur_px: float = 1.0
    max_frame_speed: bool = True                  # chọn chế độ tốc độ khung cao nhất của camera
    band: tuple[int, int] | None = None           # (y, height) dải sensor cần đọc; None = toàn khung

    @property
    def exposure_us(self) -> float:
        return max_exposure_us(self.speed_mm_s, self.mm_per_px, self.max_blur_px)


@dataclass(frozen=True)
class RunSettings:
    """Cấu hình đặt trực tiếp của bản demo (không tính exposure theo tốc độ băng)."""
    exposure_us: float
    analog_gain: int
    band_x: tuple[int, int] | None = None         # (x, width) vùng sensor cần đọc; None = toàn bề rộng
    band_y: tuple[int, int] | None = None         # (y, height) vùng sensor cần đọc; None = toàn chiều cao
