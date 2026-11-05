"""Cấu hình lưu giữa các lần chạy (JSON) — thuần Python, không phụ thuộc Qt/SDK.

Trường không còn dùng trong file cũ bị bỏ qua khi đọc và mất đi ở lần lưu sau.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
import json
import logging
import os
from pathlib import Path

from demo_ui.scan_uploader import DEFAULT_BASE_URL

logger = logging.getLogger("solution.settings")

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SETTINGS_PATH = ROOT / "config" / "app_settings.json"
BASLER_SETTINGS_PATH = ROOT / "config" / "basler_settings.json"
DUAL_SETTINGS_PATH = ROOT / "config" / "dual_settings.json"


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
    "decode_every_n": _is_int(1, 1000),
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


def _write_json(path: Path, data: dict) -> bool:
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)
        return True
    except OSError as exc:
        logger.warning("settings_save_failed path=%s error=%s", path, exc)
        return False


@dataclass
class AppSettings:
    camera_serial: str = ""
    decode_enabled: bool = True
    draw_quad: bool = True
    use_gpu: bool = True            # detect bằng GPU nếu máy có CUDA
    decode_every_n: int = 5         # số frame capture giữa hai lần gửi decode (worker bận thì bỏ frame)
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
        return cls.from_dict(raw)

    @classmethod
    def from_dict(cls, raw: dict) -> "AppSettings":
        """Giá trị sai hoặc thiếu → dùng mặc định cho trường đó."""
        values = {}
        for item in fields(cls):
            if item.name not in raw:
                continue
            if _VALID[item.name](raw[item.name]):
                values[item.name] = raw[item.name]
            else:
                logger.warning("settings_invalid field=%s value=%r", item.name, raw[item.name])
        return cls(**values)

    def save(self, path: Path) -> bool:
        """Ghi qua file tạm để mất điện giữa chừng không làm hỏng file cũ."""
        return _write_json(path, asdict(self))


@dataclass
class BaslerSettings(AppSettings):
    """Mặc định cho camera Basler a2A2840-48umBAS: gain tính bằng dB, sensor 2856×2848."""
    analog_gain: int = 6
    band_w: int = 2840


@dataclass
class DualSettings:
    """Cấu hình app hai camera: mỗi camera một bản ghi; phần dùng chung (decode, quad, GPU, gửi server)
    lưu ở bản ghi ``a``."""
    a: AppSettings = field(default_factory=AppSettings)
    b: BaslerSettings = field(default_factory=BaslerSettings)

    @classmethod
    def load(cls, path: Path, seed_a: Path = DEFAULT_SETTINGS_PATH, seed_b: Path = BASLER_SETTINGS_PATH) -> "DualSettings":
        """Chưa có file hoặc file hỏng → lấy từ cấu hình của hai bản một camera."""
        try:
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("gốc JSON không phải object")
        except FileNotFoundError:
            return cls(AppSettings.load(seed_a), BaslerSettings.load(seed_b))
        except (OSError, ValueError) as exc:
            logger.warning("settings_unreadable path=%s error=%s", path, exc)
            return cls(AppSettings.load(seed_a), BaslerSettings.load(seed_b))
        return cls(AppSettings.from_dict(raw.get("a") or {}), BaslerSettings.from_dict(raw.get("b") or {}))

    def save(self, path: Path) -> bool:
        return _write_json(path, asdict(self))
