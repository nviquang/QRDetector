"""Cấu hình lưu giữa các lần chạy (JSON) — thuần Python, không phụ thuộc Qt/SDK.

Trường không còn dùng trong file cũ bị bỏ qua khi đọc và mất đi ở lần lưu sau.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
import json
import logging
import os
from pathlib import Path

from demo_ui.scan_uploader import DEFAULT_BASE_URL

logger = logging.getLogger("solution.settings")

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SETTINGS_PATH = ROOT / "config" / "app_settings.json"


def _is_int(lo: int, hi: int):
    return lambda v: type(v) is int and lo <= v <= hi


def _is_number(lo: float, hi: float):
    return lambda v: type(v) in (int, float) and lo <= v <= hi


def _is_bool(v) -> bool:
    return type(v) is bool


_VALID = {
    "camera_serial": lambda v: isinstance(v, str),
    "decode_enabled": _is_bool,
    "draw_quad": _is_bool,
    "use_gpu": _is_bool,
    "exposure_ms": _is_number(0.01, 2000.0),
    "analog_gain": _is_int(0, 1000),
    "band_enabled": _is_bool,
    "band_y": _is_int(0, 4096),
    "band_h": _is_int(16, 4096),
    "band_x_enabled": _is_bool,
    "band_x": _is_int(0, 4096),
    "band_w": _is_int(16, 4096),
    "upload_enabled": _is_bool,
    "upload_base_url": lambda v: isinstance(v, str) and v.startswith(("http://", "https://")),
}


@dataclass
class AppSettings:
    camera_serial: str = ""
    decode_enabled: bool = True
    draw_quad: bool = True
    use_gpu: bool = True            # detect bằng GPU nếu máy có CUDA
    exposure_ms: float = 12.9
    analog_gain: int = 40
    band_enabled: bool = False      # dải y
    band_y: int = 640
    band_h: int = 768
    band_x_enabled: bool = False
    band_x: int = 0
    band_w: int = 2448
    upload_enabled: bool = True     # gửi mã QR đọc được lên API
    upload_base_url: str = DEFAULT_BASE_URL

    @classmethod
    def load(cls, path: Path) -> "AppSettings":
        """Đọc file; file hỏng hoặc giá trị sai → dùng mặc định cho phần đó, app vẫn chạy."""
        try:
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("gốc JSON không phải object")
        except FileNotFoundError:
            return cls()
        except (OSError, ValueError) as exc:
            logger.warning("settings_unreadable path=%s error=%s", path, exc)
            return cls()
        values = {}
        for field in fields(cls):
            if field.name not in raw:
                continue
            if _VALID[field.name](raw[field.name]):
                values[field.name] = raw[field.name]
            else:
                logger.warning("settings_invalid field=%s value=%r", field.name, raw[field.name])
        return cls(**values)

    def save(self, path: Path) -> bool:
        """Ghi qua file tạm để mất điện giữa chừng không làm hỏng file cũ."""
        path = Path(path)
        tmp = path.with_name(path.name + ".tmp")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp, path)
            return True
        except OSError as exc:
            logger.warning("settings_save_failed path=%s error=%s", path, exc)
            return False
