"""Chạy từng bước của bộ đọc nền B (grid_sr) và C (preproc_sweep) trên MỘT lượt, lưu ảnh minh họa mỗi bước.

python tools/explain_solvers.py [--track xa_04] [--cond goc] [--k 5] [--seed 0] [--out reports/giai_thich_BC]

Lượt lấy từ tập phát triển của bộ chấm điểm (experiments/out/bench/tracks_dev), dựng obs/ctx giống hệt
experiments/bench/run.py. Khác với read_pass thật (dừng ở bước đầu tiên đọc được), script này chạy MỌI bước để thấy
ảnh của từng bước; summary.json ghi bước nào thật sự trả kết quả khi chạy read_pass.
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import pickle
import sys
import time
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "experiments", "bench"))
sys.path.insert(0, os.path.join(ROOT, "qr", "solvers", "grid_sr"))
sys.path.insert(0, os.path.join(ROOT, "qr", "solvers", "preproc_sweep"))

import torch  # noqa: F401,E402  (nạp trước thư viện khác trên Windows)
import cv2  # noqa: E402
import numpy as np  # noqa: E402
import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Polygon  # noqa: E402

import grid_model as GM  # noqa: E402
import grid_sr as GS  # noqa: E402
import preproc_sweep as PS  # noqa: E402
import qrspec as QS  # noqa: E402
from api import Ctx, Obs  # noqa: E402
from qr.detector import Detection  # noqa: E402
from qr.multiframe import PassDecoder  # noqa: E402
from qr.preprocessor import stretch_contrast, upscale_gray  # noqa: E402
from qr.tracker import Track  # noqa: E402

plt.rcParams.update({"font.size": 9, "figure.dpi": 110, "axes.titlesize": 9, "figure.constrained_layout.use": True})
OUT = "."
SUMMARY: dict = {}
CODE = None       # đáp án của lượt, chỉ để ghi nhãn đúng/sai trên ảnh


# ── tiện ích ───────────────────────────────────────────────────────────────────

def save(fig, name):
    path = os.path.join(OUT, name)
    fig.savefig(path)
    plt.close(fig)
    print("  ->", name, flush=True)


def show(ax, img, title="", vmin=None, vmax=None, cmap="gray"):
    ax.imshow(img, cmap=cmap, vmin=vmin, vmax=vmax, interpolation="nearest")
    ax.set_title(title)
    ax.set_xticks([])
    ax.set_yticks([])


def show_cells(ax, x, n, title="", fixed=None):
    """Lưới ô N×N, 1 = trắng."""
    m = np.asarray(x, float).reshape(n, n)
    ax.imshow(m, cmap="gray", vmin=0, vmax=1, interpolation="nearest")
    if fixed is not None:
        f = np.asarray(fixed).reshape(n, n)
        ov = np.zeros((n, n, 4))
        ov[f] = (0.1, 0.4, 1.0, 0.25)
        ax.imshow(ov, interpolation="nearest")
    ax.set_title(title)
    ax.set_xticks([])
    ax.set_yticks([])


def draw_grid(ax, corners, n, color="lime", lw=0.5, step=1):
    H = cv2.getPerspectiveTransform(np.float32([[0, 0], [n, 0], [n, n], [0, n]]), np.float32(corners)).astype(float)
    t = np.linspace(0, n, 60)
    for i in range(0, n + 1, step):
        for pts in (np.c_[np.full_like(t, i), t], np.c_[t, np.full_like(t, i)]):
            p = np.c_[pts, np.ones(len(t))] @ H.T
            ax.plot(p[:, 0] / p[:, 2], p[:, 1] / p[:, 2], color=color, lw=lw if 0 < i < n else 1.2)


def quad(ax, pts, color="r", lw=1.2, ls="-"):
    ax.add_patch(Polygon(np.asarray(pts), closed=True, fill=False, ec=color, lw=lw, ls=ls))


def scatter_img(shape, gx, gy, val, fill=np.nan):
    img = np.full(shape, fill, float)
    img[gy.astype(int), gx.astype(int)] = val
    return img


def cells_text(text):
    if not text:
        return "—"
    if CODE is None:
        return text
    return f"{text} ✓" if text == CODE else f"{text} ✗ SAI"


# ── dựng lượt giống experiments/bench/run.py ───────────────────────────────────

def load_pass(track, cond, k, seed):
    import run as bench
    path = os.path.join(ROOT, "experiments", "out", "bench", "tracks_dev", f"{track}.pkl")
    tr = pickle.load(open(path, "rb"))
    rng = np.random.default_rng(zlib.crc32(f"{tr['id']}|{cond}|{k}|{seed}".encode()))
    n = len(tr["obs"])
    idx = sorted(rng.choice(n, size=min(k, n), replace=False).tolist())
    s = bench.SCALES.get(cond, 1.0)
    vel = tuple(float(v) * s for v in tr["velocity"])
    obs = [bench.apply_cond(tr["obs"][i], cond, tr["velocity"], rng) for i in idx]
    speed = float(np.hypot(*vel))
    blur = speed * bench.FPS * bench.EXPOSURE_MS / 1000.0 + (4.0 if cond == "mo" else 0.0)
    ctx = Ctx(velocity=vel, fps=bench.FPS, exposure_ms=bench.EXPOSURE_MS, blur_px=blur)
    return tr, obs, ctx, idx


# ── bước 0: cách đọc thường (chung cho B và C) ────────────────────────────────

def step_baseline(obs, ctx):
    dec = PassDecoder(None)
    track = Track(track_id=1, first_frame=0, last_frame=0, center=(0.0, 0.0), size=1.0, velocity=ctx.velocity)
    blur = [ctx.blur_px] if ctx.blur_px >= 1.0 else []
    hits = []
    for o in obs:
        img = cv2.cvtColor(o.gray, cv2.COLOR_GRAY2BGR)
        det = Detection(bbox_xyxy=o.bbox, quad_xy=o.quad, confidence=o.conf, polygon_xy=o.polygon)
        hit = dec.read(img, o.bbox, det, track, blur)
        hits.append(hit.text if hit else None)
    fig, axs = plt.subplots(2, len(obs), figsize=(3.0 * len(obs), 6.2))
    for i, (o, h) in enumerate(zip(obs, hits)):
        show(axs[0, i], o.gray, f"crop {i}: frame {o.frame}\n{o.gray.shape[1]}×{o.gray.shape[0]} px")
        x1, y1, x2, y2 = o.bbox
        quad(axs[0, i], [[x1, y1], [x2, y1], [x2, y2], [x1, y2]], "yellow", 1.0, "--")
        quad(axs[0, i], o.quad, "r")
        x1, y1, x2, y2 = (int(v) for v in o.bbox)
        z = o.gray[max(0, y1 - 4):y2 + 4, max(0, x1 - 4):x2 + 4]
        show(axs[1, i], z, f"phóng to vùng tem\nPassDecoder: {cells_text(h)}")
    fig.suptitle("Bước 0 — 5 crop của lượt (vàng: bbox YOLO, đỏ: quad) và kết quả cách đọc thường")
    save(fig, "00_crops_baseline.png")
    votes = collections.Counter(h for h in hits if h)
    SUMMARY["baseline"] = dict(hits=hits, hint=votes.most_common(1)[0][0] if votes else None)
    return SUMMARY["baseline"]["hint"]


# ── B: grid_sr ────────────────────────────────────────────────────────────────

def b_finders(obs, R):
    o = obs[0]
    offs = R.offs
    q = np.asarray(o.quad, float)
    side = np.mean([np.linalg.norm(q[(i + 1) % 4] - q[i]) for i in range(4)])
    theta = float(np.arctan2(*(q[1] - q[0])[::-1]))
    pitch = side / 25.0
    pat, mask = GM.finder_patch(pitch, theta, offs, 0.8)
    x1, y1 = np.maximum(np.floor(q.min(0) - 8).astype(int), 0)
    x2, y2 = np.minimum(np.ceil(q.max(0) + 8).astype(int), [o.gray.shape[1], o.gray.shape[0]])
    res = cv2.matchTemplate(o.gray[y1:y2, x1:x2].astype(np.float32), pat, cv2.TM_CCOEFF_NORMED, mask=np.uint8(mask) * 255)
    res = np.nan_to_num(res, nan=-1.0)
    trip = GM.finder_triples(o.gray, o.quad, offs, 0.8, (1, 2, 3))
    fig, axs = plt.subplots(1, 4, figsize=(14, 3.8))
    show(axs[0], pat, f"mẫu finder đã mờ\n(ô {pitch:.2f} px, xoay {np.rad2deg(theta):.0f}°)")
    show(axs[1], res, "NCC của mẫu trên crop 0\n(sáng = giống finder)", cmap="magma")
    show(axs[2], o.gray, "3 bộ ba finder điểm cao nhất")
    cols = ["lime", "cyan", "orange"]
    for (s, v, cs, dev), c in zip(trip[:3], cols):
        quad(axs[2], cs, c, 1.0)
    axs[2].legend([plt.Line2D([], [], c=c) for c in cols[:len(trip[:3])]],
                  [f"V{v} điểm {s:.2f}" for s, v, cs, dev in trip[:3]], fontsize=7, loc="lower right")
    s, v, cs, dev = trip[0]
    show(axs[3], o.gray, f"bộ ba tốt nhất → lưới V{v} ({17 + 4 * v}×{17 + 4 * v} ô)\nchưa tinh chỉnh")
    draw_grid(axs[3], cs, 17 + 4 * v)
    fig.suptitle("B1a — Tìm finder bằng matched filter, ghép bộ ba thành lưới")
    save(fig, "B1a_finders.png")
    SUMMARY.setdefault("B", {})["triples"] = [dict(score=float(s), version=int(v)) for s, v, cs, dev in trip[:5]]


def b_fit_geometry(R):
    """Sao chép Recon.fit_geometry, ghi lại giả thiết, quick_margin, σ."""
    obs, offs = R.obs, R.offs
    cands = GM.initial_fit(obs, [offs] * len(obs))
    pool, keys = [], set()
    for s, v, c, fi in cands:
        if s < cands[0][0] - 0.3:
            break
        k = (v, tuple(np.round(c[0] / 3.0).astype(int)))
        if k in keys or sum(1 for p in pool if p[1] == v) >= 3:
            continue
        keys.add(k)
        pool.append((s, v, c, fi))
        if len(pool) >= 9:
            break
    margins = []
    best = None
    for s, v, c, fi in pool:
        m = R.quick_margin(v, c, fi)
        margins.append(m)
        if best is None or m > best[0]:
            best = (m, s, v, c, fi)
    _, s, v, c, fi = best
    R.version, R.layout = v, GM.LAYOUTS[v]
    R.n = n = R.layout.size
    hy = GM.Hypothesis(v, 0.75 / (float(np.linalg.norm(c[1] - c[0])) / n))
    R.hy = hy
    corners, scores, initial = [None] * len(obs), [0.0] * len(obs), [None] * len(obs)
    corners[fi], scores[fi], initial[fi] = c, s, c
    for i, o in enumerate(obs):
        if i == fi:
            continue
        fit = GM.Fitter(o.gray, offs)
        c0, _ = GM.align_by_finders(c, n, obs[fi], o, offs, 0.75)
        initial[i] = c0
        corners[i], scores[i] = fit.refine(c0, hy.tpl, hy.mask, n)
    R.corners, R.scores = corners, scores
    R.pitch = float(np.linalg.norm(c[1] - c[0]) / n)
    sig_scores = []
    fit = GM.Fitter(obs[fi].gray, offs)
    for sg in GS.SIGMAS:
        h2 = GM.Hypothesis(v, sg / R.pitch)
        sig_scores.append(fit.score(c, h2.tpl, h2.mask, n))
    R.sigma = GS.SIGMAS[int(np.argmax(sig_scores))]
    R.score0 = max(sig_scores)

    # hình: giả thiết + margin
    fig, axs = plt.subplots(1, len(pool) + 1, figsize=(2.8 * (len(pool) + 1), 3.4))
    axs = np.atleast_1d(axs)
    for j, ((s_, v_, c_, fi_), m) in enumerate(zip(pool, margins)):
        show(axs[j], obs[fi_].gray, f"giả thiết {j}: V{v_}, crop {fi_}\nNCC {s_:.3f}, chênh format {m:.1f}"
             + ("  ← chọn" if m == best[0] else ""))
        draw_grid(axs[j], c_, 17 + 4 * v_, "lime" if m == best[0] else "orange")
    axs[-1].bar(range(len(GS.SIGMAS)), sig_scores, color="tab:blue")
    axs[-1].set_xticks(range(len(GS.SIGMAS)), [str(s) for s in GS.SIGMAS])
    axs[-1].set_xlabel("σ quang học (px)")
    axs[-1].set_ylim(min(sig_scores) - 0.02, max(sig_scores) + 0.01)
    axs[-1].set_title(f"NCC ô chức năng theo σ\n→ chọn σ = {R.sigma}")
    fig.suptitle("B1b — Tinh chỉnh 8 tọa độ góc (LM, tối đa NCC), chọn giả thiết theo độ chênh format, chọn σ")
    save(fig, "B1b_hypotheses_sigma.png")

    fig, axs = plt.subplots(2, len(obs), figsize=(3.0 * len(obs), 6.4))
    for i, o in enumerate(obs):
        show(axs[0, i], o.gray, f"crop {i}: góc ban đầu\n(affine từ 3 finder)")
        draw_grid(axs[0, i], initial[i], n, "orange")
        show(axs[1, i], o.gray, f"sau LM: NCC {scores[i]:.3f}")
        draw_grid(axs[1, i], corners[i], n)
    fig.suptitle(f"B1c — Căn lưới V{v} ({n}×{n}) cho từng crop: dò lại 3 finder quanh vị trí dự đoán, rồi tinh chỉnh")
    save(fig, "B1c_align_frames.png")
    SUMMARY["B"].update(version=int(v), n=int(n), chosen_frame=int(fi), sigma=float(R.sigma),
                        hypotheses=[dict(version=int(p[1]), ncc=float(p[0]), margin=float(m)) for p, m in zip(pool, margins)],
                        sigma_scores=[float(x) for x in sig_scores], frame_scores=[float(x) for x in scores],
                        pitch=float(R.pitch))


def b_search_corner(R):
    """Sao chép Recon.search_corner, ghi sai số mỗi δ."""
    n = R.n
    order = np.argsort(-np.asarray(R.scores))[:GS.SEARCH_N]
    pts, wts = GM.psf_points(0.75, R.offs, n_gauss=GS.SEARCH_G)
    best = (None, np.zeros(2))
    centre = np.zeros(2)
    rec = []
    before = [c.copy() for c in R.corners]
    for rnd, step in enumerate((1.2, 0.5)):
        grid = range(-2, 3) if rnd == 0 else range(-1, 2)
        E = np.full((len(grid), len(grid)), np.nan)
        for a, dx in enumerate(grid):
            for b, dy in enumerate(grid):
                if rnd == 1 and dx == 0 and dy == 0:
                    E[b, a] = best[0]
                    continue
                delta = centre + step * np.array([dx, dy], float)
                frames = []
                for i in order:
                    o = R.obs[i]
                    q = R.corners[i].copy()
                    q[2] = q[2] + delta
                    gx, gy = GM.pixel_set(q, n, o.gray.shape, br_only=True)
                    y = o.gray[gy, gx].astype(np.float64)
                    frames.append(GM.FrameData(y=y, A=GM.build_matrix(q, n, gx, gy, pts, wts), gx=gx.astype(np.float64),
                                               gy=gy.astype(np.float64)))
                r = GS.Recon([], R.ctx)
                r.version, r.layout, r.n, r.frames = R.version, R.layout, n, frames
                x = r.init_x()
                r.photometric(x, known_only=True)
                sol = GM.Solver(frames, n)
                x = sol.solve(x, r.fixed, mus=(0.0, 0.5, 1.2), iters=30)
                r.photometric(x)
                xb = np.where(r.fixed, x, (x > 0.5).astype(float))
                e = sum(float(np.mean((fr.y - fr.predict(r.full(xb))) ** 2)) / max(float(fr.g.mean()) ** 2, 1.0) for fr in frames)
                E[b, a] = e
                if best[0] is None or e < best[0]:
                    best = (e, delta)
        rec.append((step, centre.copy(), list(grid), E))
        centre = best[1]
    for i in range(len(R.corners)):
        R.corners[i] = R.corners[i].copy()
        R.corners[i][2] = R.corners[i][2] + best[1]

    fi = int(order[0])
    fig, axs = plt.subplots(1, 3, figsize=(12, 3.8))
    for j, (step, c0, grid, E) in enumerate(rec):
        im = axs[j].imshow(E, cmap="viridis", origin="upper")
        axs[j].set_xticks(range(len(grid)), [f"{c0[0] + step * g:+.1f}" for g in grid])
        axs[j].set_yticks(range(len(grid)), [f"{c0[1] + step * g:+.1f}" for g in grid])
        axs[j].set_xlabel("δx (px)")
        axs[j].set_ylabel("δy (px)")
        axs[j].set_title(f"vòng {j + 1}: bước {step} px\nsai số mô hình (tối = tốt)")
        plt.colorbar(im, ax=axs[j], fraction=0.046)
    o = R.obs[fi]
    show(axs[2], o.gray, f"góc phải-dưới dịch δ = ({best[1][0]:+.1f}, {best[1][1]:+.1f}) px")
    draw_grid(axs[2], before[fi], n, "orange", 0.4, step=n)
    draw_grid(axs[2], R.corners[fi], n, "lime", 0.4)
    fig.suptitle("B1d — Quét vị trí góc phải-dưới (không có finder để neo): giải ô cho mỗi δ, giữ δ có sai số nhỏ nhất")
    save(fig, "B1d_search_corner.png")
    SUMMARY["B"]["corner_delta"] = [float(x) for x in best[1]]


def b_model(R):
    R.build_frames()
    x = R.init_x()
    R.photometric(x, known_only=True)
    j = int(np.argmax([R.scores[i] for i in R.valid]))
    i = R.valid[j]
    fr, o = R.frames[j], R.obs[i]
    sh = o.gray.shape
    Ax = fr.A.dot(R.full(x))
    fig, axs = plt.subplots(1, 6, figsize=(17, 3.4))
    show(axs[0], scatter_img(sh, fr.gx, fr.gy, fr.y), f"y: pixel quan sát (crop {i})\n{len(fr.y)} pixel trong vùng mã")
    show_cells(axs[1], x, R.n, "x ban đầu: ô chức năng biết trước\n(xám = 0,5 chưa biết; xanh = cố định)", R.fixed)
    show(axs[2], scatter_img(sh, fr.gx, fr.gy, Ax), "A·x: ô → pixel qua PSF\n(hộp pixel ⊛ Gauss σ ⊛ vệt mờ)", 0, 1)
    show(axs[3], scatter_img(sh, fr.gx, fr.gy, fr.b), f"b(p): nền/lóa (3×3 nút)\n{fr.b.min():.0f}…{fr.b.max():.0f}", cmap="viridis")
    show(axs[4], scatter_img(sh, fr.gx, fr.gy, fr.g), f"g(p): tương phản (4×4 nút)\n{fr.g.min():.0f}…{fr.g.max():.0f}", cmap="viridis")
    show(axs[5], scatter_img(sh, fr.gx, fr.gy, fr.predict(R.full(x))), "dự đoán b + g·A·x", fr.y.min(), fr.y.max())
    for k in (0, 2, 3, 4, 5):
        axs[k].set_xlim(fr.gx.min() - 3, fr.gx.max() + 3)
        axs[k].set_ylim(fr.gy.max() + 3, fr.gy.min() - 3)
    fig.suptitle("B2 — Mô hình quan sát y(p) = b(p) + g(p)·(A·x)(p), sáng tối ước từ pixel chỉ phụ thuộc ô đã biết")
    save(fig, "B2_model.png")
    SUMMARY["B"]["frames_used"] = [int(v) for v in R.valid]
    SUMMARY["B"]["pixels_per_frame"] = [int(len(f.y)) for f in R.frames]
    return j


def b_solve(R, jbest):
    n = R.n
    # một frame, để so sánh
    single = GS.Recon([R.obs[R.valid[jbest]]], R.ctx)
    single.version, single.layout, single.n = R.version, R.layout, n
    single.corners, single.scores, single.sigma, single.warp = [R.corners[R.valid[jbest]]], [1.0], R.sigma, None
    single.build_frames()
    xs = single.init_x()
    single.photometric(xs, known_only=True)
    xs = GM.Solver(single.frames, n).solve(xs, single.fixed)

    x = R.init_x()
    R.photometric(x, known_only=True)
    sol = GM.Solver(R.frames, n)
    snaps = []
    for mu in (0.0, 0.1, 0.3, 0.6, 1.0, 1.6):
        x = sol.solve(x, R.fixed, mus=(mu,))
        snaps.append((f"μ = {mu}×", x.copy()))
    outer = []
    for it in range(3):
        R.refine_geometry(x)
        R.build_frames()
        R.photometric(x, known_only=False)
        if GS.WARP_K and it >= 1:
            R.fit_warp(x)
            R.build_frames()
            R.photometric(x, known_only=False)
        sol = GM.Solver(R.frames, n)
        x = sol.solve(x, R.fixed, mus=(0.2, 0.6, 1.2), iters=80)
        outer.append(x.copy())
    R.sol, R.x = sol, x

    fig, axs = plt.subplots(2, 6, figsize=(16, 6.2))
    for k, (t, xx) in enumerate(snaps):
        amb = float(np.mean(np.abs(xx[~R.fixed] - 0.5) < 0.3))
        show_cells(axs[0, k], xx, n, f"{t} trung vị diag Q\n{amb:.0%} ô dữ liệu còn lưỡng lự")
    show_cells(axs[1, 0], xs, n, "đối chứng: chỉ 1 frame\n(cùng bộ giải)")
    for k, xx in enumerate(outer):
        show_cells(axs[1, k + 1], xx, n, f"vòng ngoài {k + 1}: khớp lại góc theo x"
                   + ("\n+ trường biến dạng" if k >= 1 else "\n"))
    w = R.warp
    if w is not None:
        kw = w.kw
        uu, vv = np.meshgrid(np.linspace(0, n, kw), np.linspace(0, n, kw))
        axs[1, 4].quiver(uu, vv, w.d[:, :, 0], w.d[:, :, 1], angles="xy", scale_units="xy", scale=0.1, color="tab:red")
        axs[1, 4].set_xlim(-2, n + 2)
        axs[1, 4].set_ylim(n + 2, -2)
        axs[1, 4].set_aspect("equal")
        axs[1, 4].set_title(f"trường biến dạng 4×4 (phóng ×10)\nmax {np.abs(w.d).max():.2f} ô")
    else:
        axs[1, 4].axis("off")
    i = R.valid[jbest]
    fr, o = R.frames[jbest], R.obs[i]
    xb = np.where(R.fixed, x, (x > 0.5).astype(float))
    resid = fr.y - fr.predict(R.full(xb))
    show(axs[1, 5], scatter_img(o.gray.shape, fr.gx, fr.gy, resid), f"phần dư y − dự đoán (crop {i})\nRMS {np.sqrt(np.mean(resid ** 2)):.1f}",
         -15, 15, cmap="RdBu_r")
    axs[1, 5].set_xlim(fr.gx.min() - 3, fr.gx.max() + 3)
    axs[1, 5].set_ylim(fr.gy.max() + 3, fr.gy.min() - 3)
    fig.suptitle(f"B3 — Giải x trên {len(R.frames)} frame: min Σ‖y − b − g·A·x‖²/σ² + μ·Σx(1−x); μ tăng dần ép ô về 0/1")
    save(fig, "B3_solve.png")
    SUMMARY["B"]["warp_max"] = float(np.abs(R.warp.d).max()) if R.warp is not None else 0.0


def b_format_and_decode(R, hint):
    n = R.n
    order, sc = R.fix_format()
    L = R.sol.llr(R.x)
    fig, axs = plt.subplots(1, 3, figsize=(15, 3.8), gridspec_kw=dict(width_ratios=[1, 1, 2.2]))
    lim = np.percentile(np.abs(L), 95)
    axs[0].imshow(L.reshape(n, n), cmap="RdBu", vmin=-lim, vmax=lim, interpolation="nearest")
    axs[0].set_title("LLR từng ô (xanh = nghiêng trắng,\nđỏ = nghiêng đen, nhạt = không chắc)")
    axs[0].set_xticks([])
    axs[0].set_yticks([])
    fm = np.zeros((n, n))
    for k, f in enumerate(R.layout.fmt):
        fm[f[:, 0], f[:, 1]] = k + 1
    show(axs[1], fm, "2 bản sao format (15 bit mỗi bản)", cmap="viridis")
    names = [f"{'LMQH'[[1, 0, 3, 2][QS.format_info(v)[0]]]}{QS.format_info(v)[1]}" for v in range(32)]
    colors = ["tab:green" if v == order[0] else ("tab:orange" if v == order[1] else "tab:gray") for v in range(32)]
    axs[2].bar(range(32), sc, color=colors)
    axs[2].set_xticks(range(32), names, rotation=90, fontsize=7)
    axs[2].set_title(f"điểm 32 mã format (mức EC + mask). Nhất {names[order[0]]} = {sc[order[0]]:.1f}, "
                     f"nhì {names[order[1]]} = {sc[order[1]]:.1f}")
    fig.suptitle("B4 — Chốt format bằng hợp lý cực đại trên cả hai bản sao")
    save(fig, "B4_format.png")

    all_c = []
    fmt_info = []
    for f_ in order[:2]:
        x, xb, fixed, sol = R.apply_format(int(f_))
        cands, base = GS.decode_candidates(R, int(f_), x, xb, sol, fixed)
        for c in cands:
            c["fmt"] = int(f_)
        all_c += cands
        fmt_info.append((int(f_), x, xb, fixed, sol, cands))
    f0, x0, xb0, fixed0, sol0, cands0 = fmt_info[0]
    level, mask = QS.format_info(f0)
    v, cw, bit, ids, maskbit = R.bit_llr(sol0, xb0, f0)
    blocks = QS.expand_blocks(R.version, level)
    total = sum(b[0] for b in blocks)
    hard, rel, _ = GS._byte_from_bits(v, cw, bit, total)
    thr = np.where(fixed0, x0, (x0 > 0.5).astype(float))
    valid = sorted((c for c in cands0 if c["parse"]), key=lambda c: c["dcost"])
    top = valid[0] if valid else None

    fig, axs = plt.subplots(2, 4, figsize=(16, 7.4))
    show_cells(axs[0, 0], x0, n, "x sau khi cố định format\n(giải lại, μ lớn hơn)", fixed0)
    show_cells(axs[0, 1], thr, n, "ngưỡng 0,5")
    show_cells(axs[0, 2], xb0, n, f"sau ICM: lật {int(np.sum(thr != xb0))} ô\nđể giảm chi phí")
    show(axs[0, 3], R.layout.mask(mask).astype(float), f"mask {mask} (đảo bit dữ liệu)")
    nsym = blocks[0][0] - blocks[0][1]
    axs[1, 0].bar(range(total), np.minimum(rel, np.percentile(rel, 99)), color=["tab:red" if r in np.argsort(rel)[:8] else "tab:blue" for r in range(total)])
    axs[1, 0].set_title(f"độ tin từng byte ({total} codeword, {nsym} byte EC)\nđỏ: 8 byte yếu nhất đưa vào Chase")
    axs[1, 0].set_xlabel("chỉ số codeword")
    if top is not None:
        x_c = R.render_bits(np.array(top["data"], np.int32), xb0, cw, bit, ids, maskbit, fixed0)
        show_cells(axs[1, 1], x_c, n, f"ứng viên RS tốt nhất vẽ lại\n'{top['parse']['text']}'")
        diff = np.zeros((n * n, 4))
        dd = x_c != xb0
        diff[dd] = (1, 0, 0, 1)
        axs[1, 2].imshow(xb0.reshape(n, n), cmap="gray", vmin=0, vmax=1, interpolation="nearest")
        axs[1, 2].imshow(diff.reshape(n, n, 4), interpolation="nearest")
        axs[1, 2].set_title(f"ô phải sửa so với ICM: {int(dd.sum())} ô (đỏ)\n{top['flips']}/{top['nbit']} bit")
        axs[1, 2].set_xticks([])
        axs[1, 2].set_yticks([])
    lines = ["ứng viên (sắp theo Δchi phí)", ""]
    seen = set()
    for c in sorted(all_c, key=lambda c: c["dcost"]):
        t = c["parse"]["text"] if c["parse"] else "(bản tin hỏng)"
        if (t, c["fmt"]) in seen:
            continue
        seen.add((t, c["fmt"]))
        lines.append(f"{names[c['fmt']]} {c['tag']:<7} Δ={c['dcost']:8.1f} lật {c['flips']:3d}  {t[:26]}")
        if len(lines) >= 12:
            break
    axs[1, 3].axis("off")
    axs[1, 3].text(0, 1, "\n".join(lines), va="top", family="monospace", fontsize=7.5)
    fig.suptitle("B5 — Nhị phân hóa, LLR bit → byte, Reed–Solomon kiểu Chase (+ giả thiết vùng đệm)")
    save(fig, "B5_decode.png")

    text = GS.gate(R, all_c, hint)
    validall = sorted((c for c in all_c if c["parse"]), key=lambda c: c["dcost"])
    g = {}
    if validall:
        t0 = validall[0]
        fm0, fm1 = float(R.fmt_sc[0]), float(R.fmt_sc[1])
        rival = next((c for c in validall[1:] if c["parse"]["text"] != t0["parse"]["text"]), None)
        g = dict(fm0=fm0, fm1=fm1, fmt_ratio=fm0 / max(fm1, 1.0), d_ratio=t0["dcost"] / fm0, flips=t0["flips"] / t0["nbit"],
                 gap=(rival["dcost"] - t0["dcost"]) / fm0 if rival else None, top_text=t0["parse"]["text"],
                 rival_text=rival["parse"]["text"] if rival else None, tag=t0["tag"], npad=t0["parse"].get("npad"),
                 pad_good=t0["parse"].get("pad_good"))
    SUMMARY["B"].update(format=names[order[0]], format_second=names[order[1]], fmt_scores=[float(sc[order[0]]), float(sc[order[1]])],
                        n_candidates=len(all_c), n_valid=len(validall), gate=g, hint=hint, result=text,
                        icm_flips=int(np.sum(thr != xb0)), n_codewords=int(total), nsym=int(nsym))


def run_B(obs, ctx, hint):
    print("== B", flush=True)
    t = time.time()
    R = GS.Recon(obs, ctx)
    b_finders(obs, R)
    b_fit_geometry(R)
    b_search_corner(R)
    j = b_model(R)
    b_solve(R, j)
    b_format_and_decode(R, hint)
    SUMMARY["B"]["seconds_instrumented"] = round(time.time() - t, 1)


# ── C: preproc_sweep ──────────────────────────────────────────────────────────

def unread_crop(grids):
    """Crop đầu tiên cách đọc thường chưa đọc được và có lưới: read_pass thật cũng bỏ qua crop đã đọc."""
    hits = SUMMARY["baseline"]["hits"]
    for k, g in enumerate(grids):
        if g and not hits[k]:
            return k
    return next((k for k, g in enumerate(grids) if g), None)


def c_grids(obs, ctx):
    grids = []
    psf = PS.line_psf(ctx.blur_px, np.arctan2(ctx.velocity[1], ctx.velocity[0])) if ctx.blur_px >= 1.0 else None
    o = obs[0]
    (_, _), side, a0 = PS.rect_info(o)
    a0 = ((a0 + np.pi / 4) % (np.pi / 2)) - np.pi / 4
    m = side / 25
    tmpl, mask = PS.finder_template(m, a0, psf)
    x1, y1, x2, y2 = o.bbox
    me = 0.15 * max(x2 - x1, y2 - y1)
    X1, Y1, X2, Y2 = int(max(0, x1 - me)), int(max(0, y1 - me)), int(min(o.gray.shape[1], x2 + me)), int(min(o.gray.shape[0], y2 + me))
    ncc = cv2.matchTemplate(np.float32(o.gray[Y1:Y2, X1:X2]), tmpl, cv2.TM_CCOEFF_NORMED, mask=mask)
    trips = PS.find_triples(o.gray, o, psf)
    detail = []
    for i, ob in enumerate(obs):
        fits = PS.fit_grid(ob.gray, ob, ctx)
        tr = PS.find_triples(ob.gray, ob, psf)
        init = None
        if tr and fits:
            s, tl, trr, bl, mm = tr[0]
            init = PS.init_corners(tl, trr, bl, fits[0][1])
        detail.append((tr[0] if tr else None, init, fits))
        grids.append([f for f in fits if f[0] > PS.GRID_FIT_MIN])

    fig, axs = plt.subplots(1, 3, figsize=(11, 3.6))
    show(axs[0], tmpl, f"mẫu finder (ô {m:.2f} px)\nđã mờ theo PSF vệt {ctx.blur_px:.1f} px")
    show(axs[1], ncc, "NCC trên crop 0", cmap="magma")
    show(axs[2], o.gray, "bộ ba tl/tr/bl tốt nhất")
    if trips:
        s, tl, trr, bl, mm = trips[0]
        for p, lab in ((tl, "tl"), (trr, "tr"), (bl, "bl")):
            axs[2].plot(*p, "o", ms=6, mfc="none", mec="lime")
            axs[2].text(p[0] + 2, p[1] - 2, lab, color="lime", fontsize=8)
    fig.suptitle("C1a — Matched filter tìm tâm finder (9 cỡ ô × 3 góc xoay), ghép bộ ba tl/tr/bl")
    save(fig, "C1a_finders.png")

    fig, axs = plt.subplots(2, len(obs), figsize=(3.0 * len(obs), 6.4))
    for i, (ob, (tr, init, fits)) in enumerate(zip(obs, detail)):
        show(axs[0, i], ob.gray, f"crop {i}: affine từ 3 tâm" + (f"\nN = {fits[0][1]}" if fits else ""))
        if init is not None:
            draw_grid(axs[0, i], init, fits[0][1], "orange")
        tt = " / ".join(f"N{f[1]}:{f[0]:.2f}" for f in fits)
        show(axs[1, i], ob.gray, f"Gauss–Newton: NCC {tt}\n" + ("dùng" if grids[i] else "bỏ (≤ 0,55)"))
        if fits:
            draw_grid(axs[1, i], fits[0][2], fits[0][1], "lime" if fits[0][0] > PS.GRID_FIT_MIN else "red")
    fig.suptitle("C1b — Khớp lưới trên từng crop: góc ban đầu (cam) → sau tinh chỉnh 8 tham số (xanh)")
    save(fig, "C1b_grids.png")
    SUMMARY.setdefault("C", {})["grids"] = [[dict(N=int(f[1]), ncc=float(f[0])) for f in d[2]] for d in detail]
    return grids


def c_warp(obs, grids):
    hits = SUMMARY["baseline"]["hits"]
    fig, axs = plt.subplots(3, len(obs), figsize=(3.0 * len(obs), 9.0))
    res = []
    for i, (o, gs) in enumerate(zip(obs, grids)):
        show(axs[0, i], o.gray, f"crop {i}" + (" (đã đọc ở bước 0,\nread_pass bỏ qua)" if hits[i] else "\n"))
        if not gs:
            axs[1, i].axis("off")
            axs[2, i].axis("off")
            res.append(None)
            continue
        g, gr = o.gray, gs[0]
        N = gr[1]
        draw_grid(axs[0, i], gr[2], N, "lime", 0.3)
        ff = PS.flat_field(g, np.linalg.norm(gr[2][1] - gr[2][0]) / N)
        w1, w2 = PS.warp_to_grid(g, gr[2], N), PS.warp_to_grid(ff, gr[2], N)
        r1, r2 = PS.read_any(w1), PS.read_any(w2)
        show(axs[1, i], w1, f"warp từ ảnh gốc\nđọc: {cells_text(r1)}")
        show(axs[2, i], w2, f"warp từ flat-field\nđọc: {cells_text(r2)}")
        res.append(dict(raw=r1, flat=r2))
    fig.suptitle("C2 — warp: nắn mã về lưới vuông 8 px/ô, chuẩn hóa đen/trắng theo ô finder, viền trắng sạch → zxing/WeChat")
    save(fig, "C2_warp.png")
    SUMMARY["C"]["warp"] = res


def c_photo(obs, grids):
    i = unread_crop(grids) or 0
    o = obs[i]
    mod = PS.rect_info(o)[1] / 23
    fig, axs = plt.subplots(1, 5, figsize=(15, 3.4))
    show(axs[0], o.gray, f"crop {i} gốc")
    res = {"crop": i}
    for k, (name, img) in enumerate(PS.photo_variants(o.gray, mod)):
        t = PS.read_any(upscale_gray(img, 4))
        res[name] = t
        show(axs[k + 1], img, f"{name}\nđọc (×4): {cells_text(t)}")
    fig.suptitle("C3 — photo: flat-field, gamma 0,6, khử nhiễu NLM, bilateral → phóng ×4 → zxing/WeChat")
    save(fig, "C3_photo.png")
    SUMMARY["C"]["photo"] = res


def c_sweep(obs, ctx, grids):
    if ctx.blur_px < 1.0:
        SUMMARY["C"]["sweep"] = "bỏ qua (vệt < 1 px)"
        return
    i = unread_crop(grids) or 0
    gr = grids[i][0] if grids[i] else None
    sw = PS.PreprocSweep()
    cands = sw._deblur_candidates(obs[i].gray, ctx, gr)
    fig, axs = plt.subplots(2, 6, figsize=(16, 6.0))
    up = cv2.resize(obs[i].gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    show(axs[0, 0], up, f"crop {i} ×2 (trước khử mờ)\nvệt ước tính {ctx.blur_px:.2f} px")
    rows = []
    for k, (score, name, f, img) in enumerate(cands):
        t = None
        if k < 4:
            t = PS.read_any(upscale_gray(PS.to_u8(stretch_contrast(PS.to_u8(img))), 2))
        rows.append(dict(rank=k, filter=name, factor=f, fn_score=float(score), read=t))
        ax = axs.flat[k + 1]
        show(ax, PS.to_u8(img), f"#{k} {name} L×{f}: khớp {score:.3f}" + (f"\nđọc: {cells_text(t)}" if k < 4 else "\n(ngoài top 4)"))
    for ax in axs.flat[len(cands) + 1:]:
        ax.axis("off")
    fig.suptitle("C4 — sweep: khử mờ Wiener với 5 độ dài vệt × 2 mức k, xếp hạng theo độ khớp ô chức năng, đọc 4 ảnh đầu")
    save(fig, "C4_sweep.png")
    SUMMARY["C"]["sweep"] = dict(crop=i, candidates=rows)


def solve_modules_trace(frames, N, rho0=0.02, rounds=4):
    """Sao chép PS.solve_modules, giữ M mỗi vòng."""
    import scipy.sparse as sp
    import scipy.sparse.linalg as spla
    M0, known = PS.function_pattern(N)
    k = known.ravel()
    M = M0.ravel().astype(np.float64)
    Z = M.copy()
    AtA0 = sum((f[0].T @ f[0]) for f in frames).tocsc()
    tr = float(AtA0.diagonal().sum()) / (N * N)
    trace = []
    for rnd in range(rounds):
        Atb = np.zeros(N * N)
        tot, cnt = 0.0, 0
        for A, w_out, b, u, v in frames:
            pred = A @ M + w_out
            X = np.column_stack([np.ones_like(u), u, v, pred, pred * u, pred * v])
            beta, *_ = np.linalg.lstsq(X, b, rcond=None)
            Bp = beta[0] + beta[1] * u + beta[2] * v
            Cp = np.maximum(beta[3] + beta[4] * u + beta[5] * v, 1.0)
            y = (b - Bp) / Cp
            tot += float(np.sum((y - pred) ** 2))
            cnt += len(y)
            Atb += A.T @ (y - w_out)
        rho = rho0 * tr * (1 + rnd * 2)
        D = np.full(N * N, rho)
        D[k] = 10 * tr
        M = spla.splu((AtA0 + sp.diags(D, format="csc")).tocsc()).solve(Atb + D * Z)
        M = np.clip(M, -0.2, 1.2)
        Zu = np.clip((M - 0.5) * (1.5 + rnd) + 0.5, 0, 1)
        Z = np.where(k, M0.ravel(), Zu)
        trace.append((M.reshape(N, N).copy(), Z.reshape(N, N).copy(), tot / max(cnt, 1)))
    return trace


def c_lsq(obs, ctx, grids):
    i = unread_crop(grids)
    if i is None:
        return
    g, gr = obs[i].gray, grids[i][0]
    N, C = gr[1], gr[2]
    angle = float(np.arctan2(ctx.velocity[1], ctx.velocity[0]))
    res = []
    for f in PS.BLUR_FACTORS:
        fr = PS.build_forward(g, C, N, PS.fine_kernel(ctx.blur_px * f, angle, 0.7))
        M, r = PS.solve_modules([fr], N)
        res.append((r, f, M))
    res.sort(key=lambda t: t[0])
    f = res[0][1]
    fr = PS.build_forward(g, C, N, PS.fine_kernel(ctx.blur_px * f, angle, 0.7))
    trace = solve_modules_trace([fr], N)
    reads = [(ff, PS.zx(PS.render_hard(M))) for r, ff, M in res[:3]]
    fig, axs = plt.subplots(2, 5, figsize=(15, 6.4))
    show(axs[0, 0], g, f"crop {i}, lưới N = {N}")
    draw_grid(axs[0, 0], C, N, "lime", 0.4)
    for k, (M, Z, r) in enumerate(trace):
        show_cells(axs[0, k + 1], np.clip(M, 0, 1), N, f"vòng {k + 1}: M mềm\nphần dư {r:.4f}")
    axs[1, 0].bar([str(t[1]) for t in sorted(res, key=lambda t: t[1])], [t[0] for t in sorted(res, key=lambda t: t[1])])
    axs[1, 0].set_title(f"phần dư theo hệ số độ dài vệt\n(nhỏ nhất: ×{f})")
    hard = PS.render_hard(trace[-1][0])
    show(axs[1, 1], hard, f"render_hard (ngưỡng 0,5, 8 px/ô)\nzxing: {cells_text(reads[0][1])}")
    # dd
    Cd = C
    M = trace[-1][0]
    Md, td = M, None
    for _ in range(2):
        Cd = PS.refine_on_modules(g, Cd, Md, ctx.blur_px * f, angle)
        frd = PS.build_forward(g, Cd, N, PS.fine_kernel(ctx.blur_px * f, angle, 0.7))
        Md, _ = PS.solve_modules([frd], N)
        td = PS.zx(PS.render_hard(Md))
        if td:
            break
    show(axs[1, 2], g, "dd: khớp lại góc theo mọi ô\n(cam trước, xanh sau)")
    draw_grid(axs[1, 2], C, N, "orange", 0.3, step=N)
    draw_grid(axs[1, 2], Cd, N, "lime", 0.3)
    show(axs[1, 3], PS.render_hard(Md), f"sau dd\nzxing: {cells_text(td)}")
    diff = (np.where(PS.function_pattern(N)[1], 0, (M > 0.5) != (Md > 0.5))).astype(float)
    show(axs[1, 4], diff, f"ô đổi màu nhờ dd: {int(diff.sum())}", 0, 1, cmap="Reds")
    fig.suptitle("C5 — lsq: giải giá trị ô bằng bình phương tối thiểu với mô hình mờ đã biết, kéo dần về 0/1, vẽ lại mã sạch cho zxing")
    save(fig, "C5_lsq.png")
    SUMMARY["C"]["lsq"] = dict(crop=i, N=int(N), best_factor=float(f), reads=reads, dd=td,
                               residuals={str(t[1]): float(t[0]) for t in res})


def c_joint(obs, ctx, grids):
    angle = float(np.arctan2(ctx.velocity[1], ctx.velocity[0]))
    sizes = collections.Counter()
    for fits in grids:
        for f in fits:
            sizes[f[1]] += f[0]
    if not sizes:
        return
    N = sizes.most_common(1)[0][0]
    items = [(o.gray, next(f for f in fits if f[1] == N)) for o, fits in zip(obs, grids) if any(f[1] == N for f in fits)]
    best = []
    for f in PS.BLUR_FACTORS:
        kernel = PS.fine_kernel(ctx.blur_px * f, angle, 0.7)
        frs = [fr for fr in (PS.build_forward(g, gr[2], N, kernel) for g, gr in items) if fr is not None]
        if len(frs) < 2:
            continue
        M, r = PS.solve_modules(frs, N)
        best.append((r, f, M, frs))
    if not best:
        return
    best.sort(key=lambda b: b[0])
    r, f, M, frs = best[0]
    single = PS.solve_modules(frs[:1], N)[0]
    t1, tj = PS.zx(PS.render_hard(single)), PS.zx(PS.render_hard(M))
    fig, axs = plt.subplots(1, 4, figsize=(13, 3.6))
    show_cells(axs[0], np.clip(single, 0, 1), N, "chỉ 1 crop: M mềm")
    show(axs[1], PS.render_hard(single), f"1 crop → zxing: {cells_text(t1)}")
    show_cells(axs[2], np.clip(M, 0, 1), N, f"gộp {len(frs)} crop: M mềm (L×{f})")
    show(axs[3], PS.render_hard(M), f"{len(frs)} crop → zxing: {cells_text(tj)}")
    fig.suptitle("C6 — joint: gộp phương trình của mọi crop (mỗi crop giữ lưới riêng) vào cùng một bài toán")
    save(fig, "C6_joint.png")
    SUMMARY["C"]["joint"] = dict(N=int(N), frames=len(frs), factor=float(f), single=t1, joint=tj)


def c_stack(obs, ctx, grids):
    items = [(o.gray, g[0]) for o, g in zip(obs, grids) if g]
    out = {}
    fig, axs = plt.subplots(2, 5, figsize=(15, 6.4))
    if len(items) >= 2:
        N = collections.Counter(gr[1] for _, gr in items).most_common(1)[0][0]
        s = 8
        ws = []
        for g, gr in items:
            if gr[1] != N:
                continue
            Hg = np.linalg.inv(cv2.getPerspectiveTransform(np.float32([[0, 0], [N * s, 0], [N * s, N * s], [0, N * s]]), np.float32(gr[2])))
            ws.append(cv2.warpPerspective(np.float32(PS.flat_field(g, np.linalg.norm(gr[2][1] - gr[2][0]) / N)), Hg, (N * s, N * s),
                                          flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE))
        for k, w in enumerate(ws[:3]):
            show(axs[0, k], w, f"crop đã warp về lưới #{k}")
        avg = np.mean(ws, axis=0)
        img = PS.to_u8(stretch_contrast(PS.to_u8(avg)))
        t = PS.read_any(cv2.copyMakeBorder(img, 32, 32, 32, 32, cv2.BORDER_CONSTANT, value=255))
        show(axs[0, 3], img, f"trung bình {len(ws)} ảnh trên lưới\nđọc: {cells_text(t)}")
        g, gr = items[-1]
        mpx = np.linalg.norm(gr[2][1] - gr[2][0]) / N
        u = (gr[2][1] - gr[2][0]) / np.linalg.norm(gr[2][1] - gr[2][0])
        v = (gr[2][3] - gr[2][0]) / np.linalg.norm(gr[2][3] - gr[2][0])
        vel = np.array(ctx.velocity, float)
        ang = np.arctan2(vel @ v, vel @ u)
        psf = PS.line_psf(ctx.blur_px * 1.0 * s / mpx / s, ang, scale=s)
        wi = PS.to_u8(stretch_contrast(PS.to_u8(PS.wiener(avg, psf, 0.03))))
        tw = PS.read_any(cv2.copyMakeBorder(wi, 32, 32, 32, 32, cv2.BORDER_CONSTANT, value=255))
        show(axs[0, 4], wi, f"+ Wiener (PSF quy về lưới)\nđọc: {cells_text(tw)}")
        out.update(grid_mean=t, grid_wiener=tw, grid_frames=len(ws))
    rois = PS.PreprocSweep._velocity_aligned(obs, ctx)
    for k, r in enumerate(rois[:3]):
        show(axs[1, k], r, "crop cuối (mốc)" if k == 0 else f"crop dịch theo vận tốc\n+ phase correlation #{k}")
    if len(rois) >= 2:
        mean = np.mean(rois, axis=0)
        up = cv2.resize(mean, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        t = PS.read_any(upscale_gray(PS.to_u8(stretch_contrast(PS.to_u8(up))), 2))
        show(axs[1, 3], up, f"trung bình {len(rois)} crop\nđọc: {cells_text(t)}")
        ang = float(np.arctan2(ctx.velocity[1], ctx.velocity[0]))
        img = PS.wiener(up, PS.line_psf(ctx.blur_px, ang, scale=2.0), 0.03)
        tw = PS.read_any(upscale_gray(PS.to_u8(stretch_contrast(PS.to_u8(img))), 2))
        show(axs[1, 4], PS.to_u8(img), f"+ Wiener\nđọc: {cells_text(tw)}")
        out.update(vel_mean=t, vel_wiener=tw, vel_frames=len(rois))
    for ax in axs.flat:
        if not ax.images:
            ax.axis("off")
    fig.suptitle("C7 — stack: xếp chồng nhiều crop (hàng trên: căn theo lưới; hàng dưới: căn theo vận tốc) rồi khử mờ")
    save(fig, "C7_stack.png")
    SUMMARY["C"]["stack"] = out


def run_C(obs, ctx):
    print("== C", flush=True)
    t = time.time()
    grids = c_grids(obs, ctx)
    c_warp(obs, grids)
    c_photo(obs, grids)
    c_sweep(obs, ctx, grids)
    c_lsq(obs, ctx, grids)
    if len(obs) >= 2:
        c_joint(obs, ctx, grids)
        c_stack(obs, ctx, grids)
    SUMMARY["C"]["seconds_instrumented"] = round(time.time() - t, 1)


def real_runs(obs, ctx):
    """read_pass thật của B và C (mỗi bộ chạy riêng), để biết kết quả và bước trả kết quả."""
    out = {}
    for name, cls in (("B", GS.GridSR), ("C", PS.PreprocSweep)):
        m = cls()
        t = time.time()
        text = m.read_pass(obs, ctx)
        out[name] = dict(text=text, seconds=round(time.time() - t, 1), log=getattr(m, "log", None))
        print(f"  read_pass {name}: {text} ({out[name]['seconds']} s) {out[name]['log'] or ''}", flush=True)
    SUMMARY["real"] = out


def main():
    global OUT, CODE
    ap = argparse.ArgumentParser()
    ap.add_argument("--track", default="xa_04")
    ap.add_argument("--cond", default="goc")
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default=os.path.join(ROOT, "reports", "giai_thich_BC"))
    ap.add_argument("--skip-real", action="store_true")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    cv2.setNumThreads(1)
    OUT = a.out
    os.makedirs(OUT, exist_ok=True)
    tr, obs, ctx, idx = load_pass(a.track, a.cond, a.k, a.seed)
    SUMMARY["pass"] = dict(track=a.track, cond=a.cond, k=a.k, seed=a.seed, code=tr["code"], frames=[int(o.frame) for o in obs],
                           velocity=[float(v) for v in ctx.velocity], blur_px=float(ctx.blur_px),
                           crop_shapes=[list(o.gray.shape) for o in obs])
    CODE = tr["code"]
    print(SUMMARY["pass"], flush=True)
    hint = step_baseline(obs, ctx)
    print("  baseline:", SUMMARY["baseline"], flush=True)
    run_B(obs, ctx, hint)
    run_C(obs, ctx)
    if not a.skip_real:
        real_runs(obs, ctx)
    json.dump(SUMMARY, open(os.path.join(OUT, "summary.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1,
              default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o))
    print("xong", flush=True)


if __name__ == "__main__":
    main()
