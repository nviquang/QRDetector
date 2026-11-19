"""Lọc chống đọc sai: nội dung, loại ký hiệu (version/mức sửa lỗi) và vị trí mã so với vùng đang đọc.

Tem hiện trường (README, mục Bài toán và ràng buộc): QR version 2 mức M, nội dung ``dãy số#dãy số`` độ dài thay đổi.
Mọi kết quả đọc (cascade nhiều frame, bộ đọc nền B/C) phải qua các hàm ở đây trước khi được tính là một phiếu.
"""

from __future__ import annotations

import re

import numpy as np

CODE_PATTERN = r"[0-9]+#[0-9]+"   # [0-9] chứ không \d: \d khớp cả chữ số Unicode (１２…)
EXPECTED_SYMBOL = ("2", "M")      # (version, mức sửa lỗi) theo cách zxing-cpp ghi trong ``extra``
POSITION_MARGIN = 0.15            # tâm mã được lệch ra ngoài bbox tối đa chừng này × cạnh bbox

_compiled: dict[str, re.Pattern] = {}


def accept_text(text: str | None, pattern: str | None = CODE_PATTERN) -> bool:
    """Toàn bộ chuỗi phải khớp ``pattern`` (fullmatch: không nhận ký tự thừa, kể cả xuống dòng ở cuối)."""
    if not text:
        return False
    if pattern is None:
        return True
    rx = _compiled.get(pattern)
    if rx is None:
        rx = _compiled[pattern] = re.compile(pattern)
    return rx.fullmatch(text) is not None


def symbol_of(result) -> tuple[str | None, str | None]:
    """(version, mức sửa lỗi) của một kết quả zxing-cpp; None nếu thư viện không trả."""
    extra = getattr(result, "extra", None)
    if not isinstance(extra, dict):
        return None, None
    return extra.get("Version"), extra.get("ECLevel")


def symbol_ok(result, expected: tuple[str, str] | None = EXPECTED_SYMBOL) -> bool:
    """Kết quả zxing-cpp đúng version và mức sửa lỗi mong đợi. ``expected=None`` = không kiểm tra."""
    if expected is None:
        return True
    return symbol_of(result) == tuple(expected)


def inside(corners, bbox, margin: float = POSITION_MARGIN) -> bool:
    """Tâm 4 góc mã nằm trong ``bbox`` [x1, y1, x2, y2] nới thêm ``margin`` × cạnh — chặn đọc nhầm tem bên cạnh."""
    if corners is None or bbox is None:
        return True
    pts = np.asarray(corners, np.float64).reshape(-1, 2)
    cx, cy = pts.mean(axis=0)
    x1, y1, x2, y2 = (float(v) for v in bbox)
    mx, my = margin * (x2 - x1), margin * (y2 - y1)
    return x1 - mx <= cx <= x2 + mx and y1 - my <= cy <= y2 + my
