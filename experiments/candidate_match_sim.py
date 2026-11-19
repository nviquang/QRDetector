"""Thử nghiệm offline: đối soát theo danh sách mã (qr/candidate_match.py) trên QR tổng hợp đúng quy cách, có mã mồi.

Mỗi lượt: dựng tem version 1 mức M (mask ngẫu nhiên), làm xấu ảnh (vệt mờ ngang, nhòe quang, tối, nhiễu, vùng chói),
thu nhỏ về px/ô hiện trường, lệch lưới dưới 1 px ngẫu nhiên. Ước lượng xác suất ô đen bằng lấy mẫu tâm ô (thô: không
khử mờ) với vị trí lưới ĐÃ BIẾT (lạc quan: bỏ qua lỗi khớp lưới). Danh sách ứng viên = mã mồi ngẫu nhiên + 20 mã liền số
±1…±10 + mã đúng; lượt "không có trong danh sách" bỏ mã đúng ra, mọi lần nhận khi đó là gán nhầm.
Mốc so sánh: zxing trên 1 frame phóng ×4 (yếu hơn PassDecoder thật).

Chạy từ gốc repo:  python experiments/candidate_match_sim.py [--trials 200] [--pool 300] [--seed 1]
"""

from __future__ import annotations

import argparse
import warnings
import os
import random
import sys

import cv2
import numpy as np
import zxingcpp

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from qr.candidate_match import Gates, data_bits, match, render  # noqa: E402

N = 21
QUIET = 4
HI = 16                      # px/ô khi dựng ảnh gốc trước khi thu nhỏ

CONDITIONS = [               # tên, px/ô, vệt mờ (ô), nhòe σ (px), trắng, đen, nhiễu σ, tỉ lệ chói
    ("sạch", 2.57, 0.0, 0.6, 200, 30, 3, 0.0),
    ("mờ 1 ô", 2.57, 1.0, 0.6, 200, 30, 3, 0.0),
    ("mờ 1,6 ô", 2.57, 1.6, 0.6, 200, 30, 3, 0.0),
    ("tối + nhiễu", 2.57, 0.2, 0.6, 70, 15, 5, 0.0),
    ("chói 20%", 2.57, 0.2, 0.6, 200, 30, 3, 0.20),
    ("chói 35%", 2.57, 0.2, 0.6, 200, 30, 3, 0.35),
    ("nhỏ 2,0 px/ô", 2.0, 0.2, 0.6, 200, 30, 3, 0.0),
    ("khó tổng hợp", 2.57, 1.0, 0.7, 70, 15, 5, 0.20),
]


def random_code(rng: random.Random) -> str:
    return "{:012d}#{:012d}".format(rng.randrange(10 ** 12), rng.randrange(10 ** 12))


def neighbors(code: str, k: int = 10) -> list[str]:
    head, tail = code.split("#")
    return ["{}#{:012d}".format(head, (int(tail) + s) % 10 ** 12) for s in range(-k, k + 1) if s]


def make_frame(code, mask, cond, rng: random.Random, glare_box):
    _, ppm, blur, sigma, white, black, noise, _ = cond
    dark = render(code, mask=mask)
    img = np.where(dark, 0.0, 1.0).astype(np.float32)
    img = cv2.copyMakeBorder(img, QUIET, QUIET, QUIET, QUIET, cv2.BORDER_CONSTANT, value=1.0)
    img = cv2.resize(img, None, fx=HI, fy=HI, interpolation=cv2.INTER_NEAREST)
    dx, dy = rng.uniform(0, HI), rng.uniform(0, HI)          # lệch lưới dưới 1 px ở ảnh đích
    img = cv2.warpAffine(img, np.float32([[1, 0, dx], [0, 1, dy]]), (img.shape[1] + HI, img.shape[0] + HI),
                         borderValue=1.0)
    if blur > 0:
        length = max(1, int(round(blur * HI)))
        img = cv2.filter2D(img, -1, np.full((1, length), 1.0 / length, np.float32), borderType=cv2.BORDER_REPLICATE)
    scale = ppm / HI
    small = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    small = cv2.GaussianBlur(small, (0, 0), sigma)
    out = black + (white - black) * small + np.random.default_rng(rng.randrange(2 ** 31)).normal(0, noise, small.shape)
    if glare_box is not None:
        r0, c0, r1, c1 = (int(round(v * ppm)) for v in glare_box)
        out[r0:r1, c0:c1] = 255
    centers = (QUIET + np.arange(N) + 0.5) * ppm
    off_x, off_y = dx * scale, dy * scale
    return np.clip(out, 0, 255).astype(np.uint8), centers + off_x, centers + off_y


def estimate_probs(img, cx, cy) -> np.ndarray:
    xs, ys = np.meshgrid(cx, cy)
    v = cv2.remap(img.astype(np.float32), xs.astype(np.float32), ys.astype(np.float32), cv2.INTER_LINEAR)
    v[v >= 250] = np.nan                                   # cháy sáng: không biết
    if np.isnan(v).all():
        return v
    lo, hi = np.nanpercentile(v, (5, 95))
    if hi - lo < 10:
        return np.full_like(v, np.nan)
    return np.clip((hi - v) / (hi - lo), 0.0, 1.0)


def zxing_reads(img, code) -> bool:
    up = cv2.resize(img, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
    up = cv2.copyMakeBorder(up, 32, 32, 32, 32, cv2.BORDER_REPLICATE)
    return any(h.text == code for h in zxingcpp.read_barcodes(up, formats=zxingcpp.BarcodeFormat.QRCode))


def glare_for(cond, rng: random.Random):
    frac = cond[7]
    if frac <= 0:
        return None
    side = (frac ** 0.5) * N                               # hình vuông chiếm frac diện tích ký hiệu
    r0 = QUIET + rng.uniform(0, N - side)
    c0 = QUIET + rng.uniform(0, N - side)
    return r0, c0, r0 + side, c0 + side


def run_condition(cond, k, pool, trials, rng):
    stats = dict(zx=0, ok=0, wrong=0, rejected=0, fa=0, wrong_margins=[], ok_margins=[])
    for _ in range(trials):
        code = random_code(rng)
        mask = rng.randrange(8)
        glare = glare_for(cond, rng)
        frames = [make_frame(code, mask, cond, rng, glare) for _ in range(k)]
        stats["zx"] += zxing_reads(frames[0][0], code)
        probs = np.nanmean(np.stack([estimate_probs(*f) for f in frames]), axis=0) if k > 1 else estimate_probs(*frames[0])
        decoys = rng.sample(pool, len(pool)) + neighbors(code)
        result = match(probs, decoys + [code])
        if result.text == code:
            stats["ok"] += 1
            stats["ok_margins"].append(result.margin)
        elif result.text is not None:
            stats["wrong"] += 1
        else:
            stats["rejected"] += 1
        if result.best is not None and result.best != code:
            stats["wrong_margins"].append(result.margin)
        stats["fa"] += match(probs, decoys).text is not None          # mã đúng không có trong danh sách
    return stats


def neighbor_distance(rng, n=300):
    d = []
    for _ in range(n):
        code = random_code(rng)
        a = data_bits(code)
        d += [int((a != data_bits(b)).sum()) for b in neighbors(code, 1)]
    return np.array(d), len(a)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=200)
    ap.add_argument("--pool", type=int, default=300)
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    warnings.filterwarnings("ignore", "Mean of empty slice")
    rng = random.Random(args.seed)
    pool = [random_code(rng) for _ in range(args.pool)]
    d, total = neighbor_distance(rng)
    print("Mã liền số (±1) khác nhau: min {} / TB {:.1f} / max {} trên {} ô dữ liệu ({:.0%} TB)".format(
        d.min(), d.mean(), d.max(), total, d.mean() / total))
    g = Gates()
    print("Ngưỡng: bằng chứng ≥ {}, lệch ≤ {:.0%}, chênh ≥ {}; {} lượt/ô; danh sách {} mã mồi + 20 liền số\n".format(
        g.min_evidence, g.max_mismatch, g.min_margin, args.trials, args.pool))
    print("| Điều kiện | k | zxing 1 frame | Đối soát đúng | Nhận nhầm | Từ chối | Gán nhầm khi mã không có trong DS "
          "| Chênh lớn nhất khi top-1 sai | Chênh trung vị khi đúng |")
    print("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for cond in CONDITIONS:
        for k in (1, 3):
            s = run_condition(cond, k, pool, args.trials, rng)
            t = args.trials
            wm = "{:.1f}".format(max(s["wrong_margins"])) if s["wrong_margins"] else "—"
            om = "{:.0f}".format(float(np.median(s["ok_margins"]))) if s["ok_margins"] else "—"
            print("| {} | {} | {:.0%} | {:.0%} | {} | {:.0%} | {} | {} | {} |".format(
                cond[0], k, s["zx"] / t, s["ok"] / t, s["wrong"], s["rejected"] / t, s["fa"], wm, om))


if __name__ == "__main__":
    main()
