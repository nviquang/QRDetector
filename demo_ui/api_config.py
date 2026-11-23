"""Cấu hình gọi API báo cáo tấm (``docs/camera-integration.md``) — thuần Python, không Qt.

Đọc ``BASE_URL``, ``APP_TOKEN_SECRET``, ``API_KEY`` từ file ``.env`` ở gốc repo; biến môi trường của tiến trình
(khác rỗng) ghi đè giá trị trong file. Không dùng python-dotenv: chỉ cần dạng ``KEY=VALUE`` đơn giản.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
from typing import Mapping

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
REQUIRED_KEYS = ("BASE_URL", "APP_TOKEN_SECRET", "API_KEY")


@dataclass(frozen=True)
class ApiConfig:
    base_url: str
    app_secret: str = field(repr=False)     # không lộ secret khi log/in đối tượng
    api_key: str = field(repr=False)


def read_env_file(path: Path) -> dict[str, str]:
    """``KEY=VALUE`` mỗi dòng; bỏ dòng trống, ``#``, tiền tố ``export `` và một cặp nháy bao ngoài."""
    try:
        text = Path(path).read_text(encoding="utf-8-sig")     # PowerShell hay ghi kèm BOM
    except FileNotFoundError:
        return {}
    values = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        values[key.strip()] = value
    return values


def load_api_config(path: Path = ENV_PATH,
                    environ: Mapping[str, str] = os.environ) -> tuple[ApiConfig | None, list[str]]:
    """(cấu hình, []) khi đủ; (None, tên các biến thiếu) khi thiếu, rỗng hoặc BASE_URL không phải http(s)."""
    file_values = read_env_file(path)
    values = {key: environ.get(key) or file_values.get(key, "") for key in REQUIRED_KEYS}
    missing = [key for key in REQUIRED_KEYS if not values[key]]
    if values["BASE_URL"] and not values["BASE_URL"].startswith(("http://", "https://")):
        missing.insert(0, "BASE_URL")
    if missing:
        return None, missing
    return ApiConfig(values["BASE_URL"], values["APP_TOKEN_SECRET"], values["API_KEY"]), []
