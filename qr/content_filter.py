"""Lọc chống đọc sai: nội dung, loại ký hiệu (version/mức sửa lỗi) và vị trí mã so với vùng đang đọc.

Tem hiện trường (README, mục Bài toán và ràng buộc): QR version 2 mức M, nội dung ``dãy số#dãy số`` độ dài thay đổi.
Mọi kết quả đọc (cascade nhiều frame, bộ đọc nền B/C) phải qua các hàm ở đây trước khi được tính là một phiếu.
"""

from __future__ import annotations

import re

import cv2
import numpy as np

CODE_PATTERN = r"[0-9]+#[0-9]+"   # [0-9] chứ không \d: \d khớp cả chữ số Unicode (１２…)
EXPECTED_SYMBOL = ("2", "M")      # V2-M theo cách zxing-cpp ghi trong ``extra`` — chỉ dùng khi muốn ép loại tem
ACCEPT_SYMBOL = None              # chính sách mặc định của pipeline và bộ giải: nhận mọi version, mọi mức sửa lỗi
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


def symbol_ok(result, expected: tuple[str, str] | None = None) -> bool:
    """Kết quả zxing-cpp đúng version và mức sửa lỗi mong đợi. ``expected=None`` = không kiểm tra."""
    if expected is None:
        return True
    return symbol_of(result) == tuple(expected)


SIZES = (21, 25, 29, 33)          # số ô mỗi cạnh của version 1–4
_WARP = 240


def module_count(gray: np.ndarray, corners, sizes=SIZES) -> tuple[int | None, float]:
    """Ước số ô mỗi cạnh từ đường timing (hàng/cột 6, đen-trắng xen kẽ giữa hai finder) của mã có 4 góc ``corners``.

    Dùng cho decoder không trả version (WeChat). Không biết góc nào là góc finder nên thử cả 4 hướng; mỗi kích thước N
    lấy điểm tương quan tốt nhất giữa vạch timing đo được và mẫu xen kẽ. Trả (N tốt nhất, điểm); điểm < 0,3 là không rõ.
    """
    src = np.asarray(corners, np.float32).reshape(4, 2)
    dst = np.float32([[0, 0], [_WARP, 0], [_WARP, _WARP], [0, _WARP]])
    try:
        warped = cv2.warpPerspective(gray, cv2.getPerspectiveTransform(src, dst), (_WARP, _WARP),
                                     flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE).astype(np.float32)
    except cv2.error:
        return None, 0.0
    best_n, best = None, -1.0
    for n in sizes:
        k = np.arange(8, n - 8)
        if len(k) < 3:
            continue
        expect = np.where(k % 2 == 0, -1.0, 1.0)          # ô chẵn đen
        pos = (k + 0.5) * _WARP / n
        line = 6.5 * _WARP / n
        r = max(1, int(_WARP / n / 4))
        for img in (warped, np.rot90(warped, 1), np.rot90(warped, 2), np.rot90(warped, 3)):
            for prof in (np.array([img[int(line) - r:int(line) + r + 1, int(p) - r:int(p) + r + 1].mean() for p in pos]),
                         np.array([img[int(p) - r:int(p) + r + 1, int(line) - r:int(line) + r + 1].mean() for p in pos])):
                sd = prof.std()
                if sd < 1e-6:
                    continue
                score = float(np.mean((prof - prof.mean()) / sd * expect))
                if score > best:
                    best_n, best = n, score
    return best_n, best


def size_ok(gray, corners, expected: tuple[str, str] | None = None, min_score: float = 0.3) -> bool:
    """Mã (từ decoder không báo version) có số ô khớp version mong đợi. ``expected=None`` = không kiểm tra."""
    if expected is None:
        return True
    n, score = module_count(gray, corners)
    return n == 17 + 4 * int(expected[0]) and score >= min_score


def inside(corners, bbox, margin: float = POSITION_MARGIN) -> bool:
    """Tâm 4 góc mã nằm trong ``bbox`` [x1, y1, x2, y2] nới thêm ``margin`` × cạnh — chặn đọc nhầm tem bên cạnh."""
    if corners is None or bbox is None:
        return True
    pts = np.asarray(corners, np.float64).reshape(-1, 2)
    cx, cy = pts.mean(axis=0)
    x1, y1, x2, y2 = (float(v) for v in bbox)
    mx, my = margin * (x2 - x1), margin * (y2 - y1)
    return x1 - mx <= cx <= x2 + mx and y1 - my <= cy <= y2 + my
