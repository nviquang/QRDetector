"""Đối soát tem khó đọc với danh sách mã còn hiệu lực (đề xuất: reports/Ý tưởng đối soát theo danh sách mã.md).

Không giải mã tem mà chọn mã khớp nhất trong danh sách ứng viên, so ở mức ô:
  1. Đọc ô format (mức sửa lỗi + mask) từ chính tem.
  2. Dựng lại bit dữ liệu + sửa lỗi của từng ứng viên đúng quy cách in (version 1, mức M, tách đoạn số/byte).
  3. Chấm log-likelihood của từng ứng viên trên xác suất "ô đen" ước lượng được; ô không biết (NaN, ví dụ chói) bỏ qua.
  4. Chỉ nhận khi qua đủ cổng: format đúng, đủ bằng chứng, khớp tuyệt đối, vượt hẳn ứng viên thứ hai.

Ngưỡng mặc định trong ``Gates`` là điểm khởi đầu, PHẢI hiệu chỉnh bằng mã mồi (experiments/candidate_match_sim.py).
Kiểm tra "mã chưa dùng" và đối chiếu cuối khung giờ thuộc về bên gọi (danh sách mã), không làm ở đây.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from .solvers.grid_sr.qrspec import FORMAT_CODES, Layout, codeword_map, expand_blocks, pad_bytes, rs_encode

LEVEL_M = 0                 # mã mức sửa lỗi trong ô format: L=1, M=0, Q=3, H=2
_EPS = 0.05                 # mỗi ô lệch hẳn chỉ bị trừ tối đa log(0.95/0.05) ≈ 2,9 điểm


@dataclass(frozen=True)
class Gates:
    max_format_errors: float = 3.0   # format có BCH sửa được 3 bit
    min_evidence: float = 30.0       # tổng độ tin của các ô dữ liệu (≈ số ô nhìn rõ)
    max_mismatch: float = 0.10       # tỉ lệ ô (theo độ tin) lệch với ứng viên tốt nhất; mã liền số lệch nhau ~20%
    min_margin: float = 10.0         # điểm ứng viên tốt nhất hơn ứng viên thứ hai
    # Cổng theo byte, giữ an toàn cả với mã KHÔNG có trong danh sách. Hai mã hợp lệ khác nhau ≥ d byte (version 1 mức M:
    # d = 11). Với e byte bị che và t byte nhìn rõ mà lệch, mọi mã khác phải lệch ≥ d − e − t byte nhìn rõ, nên chỉ nhận
    # khi e + 2t ≤ byte_budget (= d − 1 − dự trữ, giống điều kiện giải mã Reed–Solomon có xóa, chừa 2 byte dự trữ).
    byte_budget: int = 8


@dataclass
class MatchResult:
    text: str | None                 # mã được nhận; None nếu bị từ chối
    best: str | None                 # ứng viên điểm cao nhất (kể cả khi bị từ chối)
    second: str | None
    margin: float
    mismatch: float
    evidence: float
    mask: int | None
    reason: str                      # "ok" hoặc cổng đã chặn
    hidden: int = 0                  # số byte bị che / không đủ rõ
    byte_errors: int = 0             # số byte nhìn rõ mà lệch với ứng viên tốt nhất


def encode_segments(text: str, capacity: int) -> list[int] | None:
    """Mã hóa tách đoạn: dãy chữ số ở chế độ numeric, phần còn lại ở chế độ byte (UTF-8). None nếu quá chỗ."""
    bits: list[int] = []

    def put(v: int, k: int):
        bits.extend(v >> i & 1 for i in range(k - 1, -1, -1))

    for run in re.findall(r"\d+|\D+", text):
        if run.isdigit():
            put(1, 4)
            put(len(run), 10)
            for i in range(0, len(run), 3):
                g = run[i:i + 3]
                put(int(g), {1: 4, 2: 7, 3: 10}[len(g)])
        else:
            raw = run.encode("utf-8")
            put(4, 4)
            put(len(raw), 8)
            for b in raw:
                put(b, 8)
    if len(bits) > capacity * 8:
        return None
    bits += [0] * min(4, capacity * 8 - len(bits))
    bits += [0] * (-len(bits) % 8)
    data = [int("".join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8)]
    return data + pad_bytes(len(data), capacity)


def codewords(text: str, version: int = 1, level: int = LEVEL_M) -> list[int] | None:
    """Byte dữ liệu + sửa lỗi xếp theo khối (như ``codeword_map`` mong đợi)."""
    blocks = expand_blocks(version, level)
    data = encode_segments(text, sum(k for _, k, _ in blocks))
    if data is None:
        return None
    out, pos = [], 0
    for n, k, _ in blocks:
        part = data[pos:pos + k]
        pos += k
        out += part + rs_encode(part, n - k)
    return out


@lru_cache(maxsize=None)
def _layout(version: int) -> Layout:
    return Layout(version)


@lru_cache(maxsize=65536)
def data_bits(text: str, version: int = 1, level: int = LEVEL_M) -> np.ndarray | None:
    """Bit (1 = đen, chưa áp mask) theo thứ tự ô dữ liệu ``Layout.order``."""
    cw = codewords(text, version, level)
    if cw is None:
        return None
    layout = _layout(version)
    idx, bit, nb = codeword_map(layout, level)
    bits = np.zeros(nb, np.uint8)                       # ô dư (version 2–3) để 0
    bits[:len(idx)] = (np.asarray(cw)[idx] >> bit) & 1
    bits.setflags(write=False)
    return bits


def render(text: str, version: int = 1, level: int = LEVEL_M, mask: int = 0) -> np.ndarray:
    """Ma trận ô (True = đen) của QR, không có vùng trống."""
    layout = _layout(version)
    bits = data_bits(text, version, level)
    if bits is None:
        raise ValueError("nội dung không vừa version {} mức {}".format(version, level))
    dark = layout.known == 0
    fmt = FORMAT_CODES[level << 3 | mask].astype(bool)
    for copy in layout.fmt:
        dark[copy[:, 0], copy[:, 1]] = fmt
    rows, cols = layout.order.T
    dark[rows, cols] = bits.astype(bool) ^ layout.mask(mask)[rows, cols]
    return dark


def read_format(p_dark: np.ndarray, version: int = 1) -> tuple[int, int, float]:
    """(mức sửa lỗi, mask, số bit lệch mềm) từ hai bản ô format; mỗi bit lấy bản rõ hơn, ô NaN bỏ qua."""
    layout = _layout(version)
    copies = np.stack([p_dark[c[:, 0], c[:, 1]] for c in layout.fmt])      # (2, 15)
    conf = np.where(np.isnan(copies), -1.0, np.abs(2 * copies - 1))
    obs = copies[np.argmax(conf, axis=0), np.arange(15)]
    known = ~np.isnan(obs)
    dist = np.abs(FORMAT_CODES[:, known] - obs[known]).sum(axis=1)
    v = int(np.argmin(dist))
    return v >> 3, v & 7, float(dist[v])


def match(p_dark: np.ndarray, candidates: list[str], version: int = 1, level: int = LEVEL_M,
          gates: Gates = Gates()) -> MatchResult:
    """Chọn ứng viên khớp nhất với xác suất ô đen ``p_dark`` (n×n, giá trị 0..1, NaN = không biết)."""
    lvl, mask, fmt_err = read_format(p_dark, version)
    if lvl != level or fmt_err > gates.max_format_errors:
        return MatchResult(None, None, None, 0.0, 1.0, 0.0, None, "format")
    texts = [t for t in dict.fromkeys(candidates) if data_bits(t, version, level) is not None]
    if not texts:
        return MatchResult(None, None, None, 0.0, 1.0, 0.0, mask, "no_candidates")

    layout = _layout(version)
    rows, cols = layout.order.T
    p = p_dark[rows, cols]
    known = ~np.isnan(p)
    pc = np.clip(np.where(known, p, 0.5), _EPS, 1 - _EPS)
    lp1 = np.where(known, np.log(pc), 0.0)
    lp0 = np.where(known, np.log(1 - pc), 0.0)
    flip = layout.mask(mask)[rows, cols]
    dark = np.stack([data_bits(t, version, level) for t in texts]).astype(bool) ^ flip
    score = dark @ lp1 + (~dark) @ lp0

    order = np.argsort(-score)
    best = int(order[0])
    margin = float(score[best] - score[order[1]]) if len(texts) > 1 else float("inf")
    weight = np.where(known, np.abs(2 * pc - 1), 0.0)
    evidence = float(weight.sum())
    observed = pc > 0.5
    wrong = weight * (dark[best] != observed)
    mismatch = float(wrong.sum() / evidence) if evidence else 1.0
    second = texts[int(order[1])] if len(texts) > 1 else None

    cw = _byte_index(version, level)                     # byte của từng ô dữ liệu (-1: ô dư)
    used = cw >= 0
    n_bytes = int(cw[used].max()) + 1
    seen = np.bincount(cw[used], weights=weight[used], minlength=n_bytes)
    errs = np.bincount(cw[used], weights=wrong[used], minlength=n_bytes)
    visible = seen >= 1.5                                # ≈ 2 ô nhìn rõ trong 8 ô của byte
    hidden = int((~visible).sum())
    byte_errors = int((visible & (errs >= 1.0)).sum())   # ≈ một ô nhìn rất rõ mà lệch

    reason = "ok"
    if evidence < gates.min_evidence:
        reason = "evidence"
    elif mismatch > gates.max_mismatch:
        reason = "mismatch"
    elif hidden + 2 * byte_errors > gates.byte_budget:
        reason = "bytes"
    elif margin < gates.min_margin:
        reason = "margin"
    return MatchResult(texts[best] if reason == "ok" else None, texts[best], second,
                       margin, mismatch, evidence, mask, reason, hidden, byte_errors)


@lru_cache(maxsize=None)
def _byte_index(version: int, level: int) -> np.ndarray:
    """Chỉ số byte (theo thứ tự khối) của từng ô dữ liệu trong ``Layout.order``; -1 cho ô dư."""
    idx, _, nb = codeword_map(_layout(version), level)
    out = np.full(nb, -1, np.int64)
    out[:len(idx)] = idx
    return out
