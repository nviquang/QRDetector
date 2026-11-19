"""Tái tạo nhiều frame trên lưới ô với tiên nghiệm nhị phân.

read_pass: chạy mốc (PassDecoder) trước; nếu chưa chốt thì giải bài toán ngược chung trên k frame. Xem REPORT.md.
"""
from __future__ import annotations

import collections
import itertools
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def _find_root():
    p = HERE
    for _ in range(8):
        if os.path.exists(os.path.join(p, "qr", "multiframe.py")):
            return p
        p = os.path.dirname(p)
    raise RuntimeError("Không tìm thấy gói qr/")


ROOT = _find_root()
sys.path.insert(0, ROOT)

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from grid_model import (Warp, FrameData, Fitter, Hypothesis, LAYOUTS, Solver, Template, build_matrix, corners_to_h,  # noqa: E402
                        fit_photometric, initial_fit, align_by_finders, motion_offsets, pixel_set, psf_points, transfer_corners)
from qrspec import FORMAT_CODES, codeword_map, expand_blocks, format_info, pad_bytes, parse_payload, rs_decode  # noqa: E402
from qr.content_filter import CODE_PATTERN, EXPECTED_SYMBOL, accept_text, inside  # noqa: E402
from qr.detector import Detection  # noqa: E402
from qr.multiframe import PassDecoder  # noqa: E402
from qr.tracker import Track  # noqa: E402

PAD_W = 8          # số byte yếu nhất được thử xóa theo mọi tổ hợp, khi đã giả thiết vùng đệm
N_G = 5            # số điểm Gauss theo mỗi trục khi dựng ma trận PSF
SIGMA_GRID = (0.4, 0.7, 1.0, 1.3, 1.6, 1.9)   # lưới thô σ (px) theo mỗi trục, rồi tinh chỉnh quanh điểm tốt nhất
SIGMA_STEP = 0.15
VERSIONS = (2,)    # tem hiện trường: QR version 2 (README, mục Bài toán và ràng buộc) — chỉ nhận lời giải version này
SEARCH_VERSIONS = (1, 2, 3)   # vẫn tìm giả thiết lưới V1–V3: đo trên lượt V2 tổng hợp, chỉ tìm V2 mất 2/8 lượt đọc được
LEVEL_M = 0        # 2 bit mức sửa lỗi trong format: L=1, M=0, Q=3, H=2
LEVELS = (LEVEL_M,)   # mức được xếp hạng ở fix_format
MAX_ERASE = 10     # xóa tối đa trong Chase: xóa càng nhiều càng dễ "sửa" ra từ mã sai (16 xóa = mọi từ đều giải được)
CHASE_W = 6
RS_BUDGET = 12     # 2 × số lỗi + số xóa tối đa được chấp nhận (khối V2-M có 16 byte EC)
MIN_FIT_NCC = -1.0  # NCC ô chức năng của giả thiết tốt nhất (đo: ca đọc được vẫn có thể âm) — không dùng để loại
SIGMAS = (0.45, 0.6, 0.75, 0.95, 1.2)   # σ đẳng hướng thử theo NCC ô chức năng (SIGMA_MODE = "ncc")
SIGMA_MODE = "fit"   # "fit": (σx, σy) theo phần dư mô hình (đo: 6/8 ca khó so với 5/8); "ncc": σ đẳng hướng như cũ
SEARCH_CORNER = False  # V2 có ô alignment, refine đã neo góc 4; quét góc chỉ cho V1 (đo: bỏ không mất ca nào, nhanh hơn)
WARP_K = 4         # số nút theo mỗi trục của trường biến dạng nhãn
SEARCH_G = 4       # số điểm Gauss khi quét góc phải-dưới
SEARCH_N = 3       # số frame dùng khi quét góc


def _offs(ctx, blur_px=None):
    b = ctx.blur_px if blur_px is None else blur_px
    return motion_offsets(ctx.velocity, b, npts=int(np.ceil(b / 1.0)) + 1 if b > 0.4 else 1)


class Recon:
    """Một lần tái tạo cho một lượt: giữ khung, hình học, x, các ứng viên."""

    def __init__(self, obs, ctx):
        self.obs, self.ctx = obs, ctx
        self.offs = _offs(ctx)
        self.debug = {}
        self.warp = None

    # ---- hình học + PSF ---------------------------------------------------------------------------------------------
    def quick_margin(self, v, c, fi):
        """Giải nhanh trên một frame: độ chênh giữa mã format tốt nhất và nhì (điểm trên hai bản)."""
        r = Recon([self.obs[fi]], self.ctx)
        r.version, r.layout, r.n, r.corners, r.scores, r.sigma = v, LAYOUTS[v], LAYOUTS[v].size, [c], [1.0], 0.75
        r.pitch = float(np.linalg.norm(c[1] - c[0]) / r.n)
        r.build_frames()
        x = r.init_x()
        r.photometric(x, known_only=True)
        sol = Solver(r.frames, r.n)
        r.x = sol.solve(x, r.fixed, mus=(0.0, 0.3, 0.8), iters=50)
        r.sol = sol
        _, sc = r.fix_format()
        return r.fmt_sc[0] - r.fmt_sc[1]

    def search_corner(self):
        """Góc phải-dưới không có finder để neo: quét δ chung cho các frame, chọn theo sai số mô hình sau khi giải x."""
        n = self.n
        order = np.argsort(-np.asarray(self.scores))[:SEARCH_N]
        pts, wts = psf_points(0.75, self.offs, n_gauss=SEARCH_G)
        best = (None, np.zeros(2))
        centre = np.zeros(2)
        for rnd, step in enumerate((1.2, 0.5)):
            grid = range(-2, 3) if rnd == 0 else range(-1, 2)
            for dx in grid:
                for dy in grid:
                    if rnd == 1 and dx == 0 and dy == 0:
                        continue
                    delta = centre + step * np.array([dx, dy], float)
                    frames = []
                    for i in order:
                        o = self.obs[i]
                        q = self.corners[i].copy()
                        q[2] = q[2] + delta
                        gx, gy = pixel_set(q, n, o.gray.shape, br_only=True)
                        y = o.gray[gy, gx].astype(np.float64)
                        frames.append(FrameData(y=y, A=build_matrix(q, n, gx, gy, pts, wts), gx=gx.astype(np.float64),
                                                gy=gy.astype(np.float64)))
                    r = Recon([], self.ctx)
                    r.version, r.layout, r.n, r.frames = self.version, self.layout, n, frames
                    x = r.init_x()
                    r.photometric(x, known_only=True)
                    sol = Solver(frames, n)
                    x = sol.solve(x, r.fixed, mus=(0.0, 0.5, 1.2), iters=30)
                    r.photometric(x)
                    xb = np.where(r.fixed, x, (x > 0.5).astype(float))
                    e = sum(float(np.mean((fr.y - fr.predict(r.full(xb))) ** 2)) / max(float(fr.g.mean()) ** 2, 1.0) for fr in frames)
                    if best[0] is None or e < best[0]:
                        best = (e, delta)
            centre = best[1]
        for i in range(len(self.corners)):
            self.corners[i] = self.corners[i].copy()
            self.corners[i][2] = self.corners[i][2] + best[1]

    def fit_geometry(self):
        obs, offs = self.obs, self.offs
        cands = initial_fit(obs, [offs] * len(obs), versions=SEARCH_VERSIONS)
        self.debug["fit_ncc"] = cands[0][0] if cands else None
        if not cands or cands[0][0] < MIN_FIT_NCC:
            return False
        # giữ tối đa 4 giả thiết (mỗi (version, góc) một), chọn theo độ phân biệt của format
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
        best = None
        for s, v, c, fi in pool:
            m = self.quick_margin(v, c, fi)
            if best is None or m > best[0]:
                best = (m, s, v, c, fi)
        _, s, v, c, fi = best
        self.version, self.layout = v, LAYOUTS[v]
        self.n = n = self.layout.size
        hy = Hypothesis(v, 0.75 / (float(np.linalg.norm(c[1] - c[0])) / n))
        self.hy = hy
        corners = [None] * len(obs)
        scores = [0.0] * len(obs)
        corners[fi], scores[fi] = c, s
        for i, o in enumerate(obs):
            if i == fi:
                continue
            fit = Fitter(o.gray, offs)
            c0, m = align_by_finders(c, n, obs[fi], o, offs, 0.75)
            corners[i], scores[i] = fit.refine(c0, hy.tpl, hy.mask, n)
        self.corners = corners
        self.scores = scores
        self.pitch = float(np.linalg.norm(c[1] - c[0]) / n)
        if SIGMA_MODE == "fit":
            self.sigma_xy = self.estimate_sigma(fi)
        else:
            fit = Fitter(obs[fi].gray, offs)
            best_s = max(SIGMAS, key=lambda sg: fit.score(c, Hypothesis(v, sg / self.pitch).tpl,
                                                          Hypothesis(v, sg / self.pitch).mask, n))
            self.sigma_xy = (best_s, best_s)
        self.sigma = float(np.mean(self.sigma_xy))     # mẫu hình học (Template) dùng σ đẳng hướng
        self.debug["sigma_xy"] = self.sigma_xy
        self.score0 = scores[fi]
        if self.version == 1 or SEARCH_CORNER:
            self.search_corner()
        return True

    def estimate_sigma(self, fi):
        """(σx, σy) theo trục ảnh: cực tiểu phần dư mô hình trên pixel chỉ phụ thuộc ô đã biết của frame tốt nhất.
        Lưới thô SIGMA_GRID² rồi dò từng bước SIGMA_STEP — thay cho 5 σ đẳng hướng cố định (mờ thật lệch trục)."""
        o, c, n = self.obs[fi], self.corners[fi], self.n
        gx, gy = pixel_set(c, n, o.gray.shape)
        y = o.gray[gy, gx].astype(np.float64)
        known = self.layout.known.ravel()
        fixed = known >= 0
        xfull = np.append(np.where(fixed, known, 0.5), 1.0)
        memo = {}

        def cost(sx, sy):
            key = (round(sx, 3), round(sy, 3))
            if key not in memo:
                pts, wts = psf_points((sx, sy), self.offs, n_gauss=N_G)
                A = build_matrix(c, n, gx, gy, pts, wts)
                keep = A[:, :n * n].dot((~fixed).astype(float)) < 0.15
                if keep.sum() < 80:
                    memo[key] = np.inf
                else:
                    fr = FrameData(y=y, A=A, gx=gx.astype(np.float64), gy=gy.astype(np.float64))
                    fit_photometric(fr, xfull, keep=keep)
                    memo[key] = fr.sig2
            return memo[key]

        best = min(((sx, sy) for sx in SIGMA_GRID for sy in SIGMA_GRID), key=lambda p: cost(*p))
        for _ in range(4):
            sx, sy = best
            cand = [(max(0.2, sx + dx), max(0.2, sy + dy)) for dx in (-SIGMA_STEP, 0, SIGMA_STEP)
                    for dy in (-SIGMA_STEP, 0, SIGMA_STEP)]
            nxt = min(cand, key=lambda p: cost(*p))
            if nxt == best:
                break
            best = nxt
        self.debug["sigma_xy"] = best
        return best

    def build_frames(self):
        n = self.n
        pts, wts = psf_points(getattr(self, "sigma_xy", self.sigma), self.offs, n_gauss=N_G)
        self.frames = []
        self.valid = [i for i, s in enumerate(self.scores) if s > max(self.scores) - 0.25]
        if not self.valid:
            self.valid = [int(np.argmax(self.scores))]
        for i in self.valid:
            o = self.obs[i]
            gx, gy = pixel_set(self.corners[i], n, o.gray.shape)
            y = o.gray[gy, gx].astype(np.float64)
            A = build_matrix(self.corners[i], n, gx, gy, pts, wts, warp=self.warp)
            self.frames.append(FrameData(y=y, A=A, gx=gx.astype(np.float64), gy=gy.astype(np.float64)))

    def init_x(self):
        k = self.layout.known
        x = np.full(self.n * self.n, 0.5)
        x[k.ravel() >= 0] = k.ravel()[k.ravel() >= 0]
        self.fixed = (k.ravel() >= 0).copy()
        return x

    def full(self, x):
        return np.append(x, 1.0)

    def photometric(self, x, known_only=False):
        for fr in self.frames:
            keep = None
            if known_only:
                u = fr.A[:, :self.n * self.n].dot((~self.fixed).astype(float))
                keep = u < 0.15
                if keep.sum() < 80:
                    keep = None
            fit_photometric(fr, self.full(x), keep=keep)
            # chặn pixel chói (phản xạ) để không làm hỏng bình phương tối thiểu
            lim = fr.b + 1.3 * fr.g + 4
            fr.y = np.minimum(fr.y, lim)

    def refine_geometry(self, x, steps=(0.2, 0.1, 0.05)):
        n = self.n
        tpl = Template(x.reshape(n, n).astype(np.float32), self.sigma / self.pitch)
        mask = Template(np.ones((n, n), np.float32), 0.0)
        mask.img[:] = 1.0
        for j, i in enumerate(self.valid):
            fit = Fitter(self.obs[i].gray, self.offs)
            self.corners[i], self.scores[i] = fit.refine(self.corners[i], tpl, mask, n, steps=steps, thr=0.5)

    def fit_warp(self, x, iters=2, h=0.08, ridge=1.0, limit=0.45):
        """GN cho trường biến dạng chung, Jacobian sai phân trên template mờ, dùng trường sáng tối hiện tại."""
        n = self.n
        tpl = Template(x.reshape(n, n).astype(np.float32), self.sigma / self.pitch)
        warp = self.warp or Warp(n, kw=WARP_K)
        kw = warp.kw
        for it in range(iters):
            JTJ, JTr = 0, 0
            order = np.argsort([-self.scores[i] for i in self.valid])[:3]
            for j in order:
                i = self.valid[j]
                fr = self.frames[j]
                hinv = np.linalg.inv(corners_to_h(self.corners[i], n))
                gx, gy = fr.gx.astype(np.float32), fr.gy.astype(np.float32)
                m0 = tpl.sample(hinv, gx, gy, self.offs, warp=warp).astype(np.float64).ravel()
                g = fr.g
                r = fr.y - fr.b - g * m0
                J = np.empty((len(r), 2 * kw * kw))
                for p in range(2 * kw * kw):
                    a, b, c = p // (2 * kw), (p // 2) % kw, p % 2
                    save = warp.d[a, b, c]
                    warp.d[a, b, c] = save + h
                    J[:, p] = g * (tpl.sample(hinv, gx, gy, self.offs, warp=warp).astype(np.float64).ravel() - m0) / h
                    warp.d[a, b, c] = save
                w = 1.0 / fr.sig2
                JTJ = JTJ + J.T.dot(J) * w
                JTr = JTr + J.T.dot(r) * w
            lam = ridge * float(np.trace(JTJ)) / JTJ.shape[0] + 1e-6
            delta = np.linalg.solve(JTJ + lam * np.eye(JTJ.shape[0]), JTr)
            delta = np.clip(delta, -0.3, 0.3)
            warp.d = np.clip(warp.d + delta.reshape(warp.d.shape), -limit, limit)
        self.warp = warp

    # ---- giải x -----------------------------------------------------------------------------------------------------
    def solve(self):
        x = self.init_x()
        self.photometric(x, known_only=True)
        sol = Solver(self.frames, self.n)
        x = sol.solve(x, self.fixed)
        for it in range(3):
            self.refine_geometry(x)
            self.build_frames()
            self.photometric(x, known_only=False)
            if WARP_K and it >= 1:
                self.fit_warp(x)
                self.build_frames()
                self.photometric(x, known_only=False)
            sol = Solver(self.frames, self.n)
            x = sol.solve(x, self.fixed, mus=(0.2, 0.6, 1.2), iters=80)
        self.sol = sol
        self.x = x

    def fix_format(self):
        """Hợp lý cực đại các mã format trên cả hai bản. Tem là mức M nên chỉ xếp hạng 8 mã mức M (mask 0–7): khi ảnh
        mờ, mã sai mức (thường là mã gần đảo bit) hay vượt mã đúng, ép mức đúng giữ được lời giải."""
        layout, n = self.layout, self.n
        L = self.sol.llr(self.x)
        idx = [fm[:, 0] * n + fm[:, 1] for fm in layout.fmt]
        wh = 1.0 - FORMAT_CODES.astype(float)       # bit 1 = đen
        sc = np.zeros(32)
        for i, code in enumerate(wh):
            for ids in idx:
                sc[i] += float(np.sum((2 * code - 1) * L[ids])) / 2
        allowed = np.array([i for i in range(32) if format_info(i)[0] in LEVELS])
        order = allowed[np.argsort(-sc[allowed])]
        self.fmt_sc = sc[order]
        self.fmt_order = order
        return order, sc

    def apply_format(self, fmt, iters=2):
        layout, n = self.layout, self.n
        x = self.x.copy()
        fixed = self.fixed.copy()
        wh = 1.0 - FORMAT_CODES[fmt].astype(float)
        for fm in layout.fmt:
            ids = fm[:, 0] * n + fm[:, 1]
            x[ids] = wh
            fixed[ids] = True
        sol = self.sol
        for _ in range(iters):
            x = sol.solve(x, fixed, mus=(0.3, 0.8, 1.5, 2.5), iters=80)
            self.photometric(x)
            sol = Solver(self.frames, n)
        xb = (x > 0.5).astype(float)
        xb[fixed] = x[fixed]
        xb = sol.icm(xb, fixed)
        return x, xb, fixed, sol

    # ---- giải mã ----------------------------------------------------------------------------------------------------
    def bit_llr(self, sol, xb, fmt):
        """Trả mảng byte cứng và độ tin cậy theo thứ tự codeword, kèm hàm vị trí."""
        layout, n = self.layout, self.n
        level, m = format_info(fmt)
        mask = layout.mask(m)
        L = sol.llr(xb)
        order = layout.order
        ids = order[:, 0] * n + order[:, 1]
        v = L[ids] * (1 - 2 * mask[order[:, 0], order[:, 1]])     # dương = bit 0
        cw, bit, nb = codeword_map(layout, level)
        cnt = len(cw)
        v = v[:cnt]
        return v, cw, bit, ids[:cnt], mask[order[:, 0], order[:, 1]][:cnt]

    def render_bits(self, cws_all, xb, cw, bit, ids, maskbit, fixed):
        x = xb.copy()
        vals = (cws_all[cw] >> bit) & 1
        x[ids] = 1.0 - (vals ^ maskbit)
        return x


def _byte_from_bits(v, cw, bit, ncw):
    hard = np.zeros(ncw, np.int32)
    rel = np.full(ncw, np.inf)
    sums = np.zeros(ncw)
    bad = v < 0
    np.bitwise_or.at(hard, cw, bad.astype(np.int32) << bit)
    np.minimum.at(rel, cw, np.abs(v))
    np.add.at(sums, cw, np.abs(v))
    return hard, rel, sums


def chase_block(block_hard, rel, nsym, width=CHASE_W, fixed_pos=None, limit=4000, max_erase=MAX_ERASE,
                budget=RS_BUDGET):
    """Sinh các ứng viên RS bằng xóa các byte kém tin cậy nhất và mọi tổ hợp xóa của ``width`` byte yếu nhất.

    Giới hạn số xóa (``max_erase``) và ngân sách 2×lỗi + xóa (``budget``): với khối (44, 28), xóa 8 byte đã cho xác suất
    "sửa" một từ rác thành từ mã hợp lệ khoảng 1e-5, xóa 16 byte thì mọi từ đều giải được."""
    cands = {}
    forb = set(fixed_pos or ())
    order = [i for i in np.argsort(rel) if i not in forb]
    max_erase = min(nsym, max_erase)
    tries = 0

    def add(er):
        r = rs_decode(list(block_hard), nsym, erase=er)
        if r is not None and 2 * r[1] + len(er) <= budget:
            cands.setdefault(tuple(r[0]), (len(er), r[1]))

    for j in range(0, max_erase + 1):                # xóa dần các byte yếu nhất
        add(order[:j])
    pool = order[:width]
    for size in range(0, min(max_erase, width) + 1):
        for er in itertools.combinations(pool, size):
            add(er)
            tries += 1
            if tries >= limit:
                return cands
    return cands


def decode_candidates(R, fmt, x_fmt, xb, sol, fixed, chase_w=CHASE_W):
    """Trả (danh sách ứng viên RS-hợp lệ, chi phí cơ sở). Hỗ trợ nhiều khối: Chase từng khối, rồi tổ hợp."""
    layout, n = R.layout, R.n
    level, _ = format_info(fmt)
    blocks = expand_blocks(layout.version, level)
    v, cw, bit, ids, maskbit = R.bit_llr(sol, xb, fmt)
    total = sum(b[0] for b in blocks)
    K = sum(b[1] for b in blocks)
    msg2arr = np.array([off + i for nb, kb, off in blocks for i in range(kb)])
    hard, rel, _ = _byte_from_bits(v, cw, bit, total)
    base_cost = sol.cost(xb)
    out = {}

    def add(arr, tag):
        key = tuple(int(a) for a in arr)
        if key in out:
            return
        cws = np.array(key, np.int32)
        x_c = R.render_bits(cws, xb, cw, bit, ids, maskbit, fixed)
        flips = ((cws[cw] >> bit) & 1) != (v < 0)
        dcost = float(sol.cost(x_c) - base_cost)
        msg = bytes(int(cws[i]) for i in msg2arr)
        out[key] = dict(data=key, tag=tag, flips=int(flips.sum()), pen=float(np.abs(v[flips]).sum()), dcost=dcost,
                        parse=parse_payload(msg), nbit=len(v))

    def run(h, rl, known, tag):
        """Chase từng khối với ``known`` là tập vị trí mảng đã biết."""
        lists = []
        for nb, kb, off in blocks:
            hb = [int(a) for a in h[off:off + nb]]
            fp = [a - off for a in known if off <= a < off + nb]
            cs = chase_block(hb, rl[off:off + nb], nb - kb, width=(chase_w if not known else PAD_W) if len(blocks) == 1 else 6,
                             fixed_pos=fp)
            ranked = []
            for d in cs:
                dd = np.array(d, np.int32)
                sel = (cw >= off) & (cw < off + nb)
                bits = (dd[cw[sel] - off] >> bit[sel]) & 1
                fl = bits != (v[sel] < 0)
                ranked.append((float(np.abs(v[sel][fl]).sum()), d))
            ranked.sort(key=lambda t: t[0])
            lists.append([d for _, d in ranked[:(60 if len(blocks) == 1 else 4)]])
            if not lists[-1]:
                return
        for combo in itertools.product(*lists):
            add([b for d in combo for b in d], tag)

    run(hard, rel, set(), "chase")
    # giả thiết vùng đệm: byte từ vị trí p của bản tin trở đi là EC/11 luân phiên
    scores = []
    for p in range(1, K):
        known = msg2arr[p:]
        pads = np.array(pad_bytes(p, K), np.int32)
        where = {int(a): int(b) for a, b in zip(known, pads)}
        sel = np.isin(cw, known)
        b = (np.array([where[int(c)] for c in cw[sel]], np.int32) >> bit[sel]) & 1
        scores.append((float(np.sum(v[sel] * (1 - 2 * b))), p))
    scores.sort(reverse=True)
    for s, p in scores[:3]:
        if s <= 0:
            continue
        known = msg2arr[p:]
        pads = np.array(pad_bytes(p, K), np.int32)
        where = {int(a): int(b) for a, b in zip(known, pads)}
        sel = np.isin(cw, known)
        b = (np.array([where[int(c)] for c in cw[sel]], np.int32) >> bit[sel]) & 1
        fp = fixed.copy()
        xp = x_fmt.copy()
        xp[ids[sel]] = 1.0 - (b ^ maskbit[sel])
        fp[ids[sel]] = True
        xp = sol.solve(xp, fp, mus=(0.4, 1.0, 2.0), iters=50)
        xq = (xp > 0.5).astype(float)
        xq[fp] = xp[fp]
        xq = sol.icm(xq, fp)
        v2, *_ = R.bit_llr(sol, xq, fmt)
        h2, rel2, _ = _byte_from_bits(v2, cw, bit, total)
        h2[known] = pads
        rel2[known] = 1e12
        run(h2, rel2, set(int(a) for a in known), f"pad{p}")
        h3, rel3 = hard.copy(), rel.copy()
        h3[known] = pads
        rel3[known] = 1e12
        run(h3, rel3, set(int(a) for a in known), f"Pad{p}")
    return sorted(out.values(), key=lambda c: c["dcost"]), base_cost


def read_recon(obs, ctx):
    """Trả (Recon, danh sách ứng viên) hoặc (None, []) nếu không tìm được bộ ba finder."""
    R = Recon(obs, ctx)
    if not R.fit_geometry():
        return None, []
    if R.version not in VERSIONS:          # lưới tốt nhất không phải V2: không phải tem cần đọc, khỏi giải
        R.debug["version"] = R.version
        return R, []
    R.build_frames()
    R.solve()
    order, sc = R.fix_format()
    # Mã format mức M tốt nhất phải chênh rõ mã nhì (cổng cũng đòi điều này): không thì dừng trước bước giải mã tốn kém
    fm0, fm1 = float(R.fmt_sc[0]), float(R.fmt_sc[1])
    R.debug["format"] = (int(order[0]), fm0, fm1)
    if fm0 <= 0 or fm0 < GATE_FM_MIN * max(fm1, 1.0):
        return R, []
    out = []
    for fmt in order[:2]:
        x, xb, fixed, sol = R.apply_format(int(fmt))
        cands, _ = decode_candidates(R, int(fmt), x, xb, sol, fixed)
        for c in cands:
            c["fmt"] = int(fmt)
        out += cands
    return R, out


GATE_FM_MIN = 1.4


def gate(R, cs, hint, d_max=0.6, fl_max=0.085, gap_min=0.25, fm_min=GATE_FM_MIN, pattern=CODE_PATTERN):
    """Cổng chống báo sai dựa trên độ dư mô hình, số bit phải lật, tính hợp lệ của bản tin và đối thủ gần nhất.

    Điểm chuẩn hóa: d = (chi phí ứng viên − chi phí tự do) / độ chênh format tốt nhất, nên không phụ thuộc k và độ tương phản.
    Nội dung phải khớp ``pattern``. Ứng viên sinh từ giả thiết byte đệm (tag pad…/Pad…) đã ghim chính các byte đệm nên
    không dùng chúng làm bằng chứng, và chỉ được nhận ở nhánh ``strong``.
    """
    valid = sorted((c for c in cs if c["parse"] and accept_text(c["parse"]["text"], pattern)), key=lambda c: c["dcost"])
    if not valid or R is None:
        return None
    fm0, fm1 = float(R.fmt_sc[0]), float(R.fmt_sc[1])
    if fm0 <= 0 or fm0 < fm_min * max(fm1, 1.0):
        return None
    top = valid[0]
    p = top["parse"]
    ratio = top["dcost"] / fm0
    fl = top["flips"] / top["nbit"]
    pinned = top["tag"].lower().startswith("pad")
    if not pinned and p["npad"] and p["pad_good"] < p["npad"] - 1:
        return None
    rival = next((c for c in valid[1:] if c["parse"]["text"] != p["text"]), None)
    gap = (rival["dcost"] - top["dcost"]) / fm0 if rival else 9.9
    strong = ratio <= d_max and fl <= fl_max and gap >= gap_min
    agrees = (not pinned and hint is not None and hint == p["text"] and accept_text(hint, pattern)
              and ratio <= 2 * d_max and fl <= 1.4 * fl_max and gap >= 0.5 * gap_min)
    return p["text"] if strong or agrees else None


class GridSR:
    def __init__(self, recon=True, baseline=True, **gate_kw):
        self.recon, self.baseline = recon, baseline
        self.gate_kw = gate_kw

    def read_pass(self, obs, ctx):
        need = min(2, len(obs))
        votes = collections.Counter()
        dec = PassDecoder(CODE_PATTERN, symbol=EXPECTED_SYMBOL)
        track = Track(track_id=1, first_frame=0, last_frame=0, center=(0.0, 0.0), size=1.0, velocity=ctx.velocity)
        blur = [ctx.blur_px] if ctx.blur_px >= 1.0 else []
        for o in (obs if self.baseline else []):
            img = cv2.cvtColor(o.gray, cv2.COLOR_GRAY2BGR)
            det = Detection(bbox_xyxy=o.bbox, quad_xy=o.quad, confidence=o.conf, polygon_xy=o.polygon)
            hit = dec.read(img, o.bbox, det, track, blur)
            if hit:
                votes[hit.text] += 1
                if votes[hit.text] >= need:
                    return hit.text
        if not self.recon:
            return None
        hint = votes.most_common(1)[0][0] if votes else None
        try:
            R, cs = read_recon(obs, ctx)
        except (ValueError, IndexError, np.linalg.LinAlgError, cv2.error, FloatingPointError):
            return None
        text = gate(R, cs, hint, **self.gate_kw)
        if text and not self._centered(R):
            return None
        return text

    @staticmethod
    def _centered(R):
        """Lưới giải ra phải nằm quanh tem đang đọc (bbox của crop), không phải tem bên cạnh lọt vào crop."""
        votes = [inside(R.corners[i], R.obs[i].bbox) for i in getattr(R, "valid", range(len(R.corners)))]
        return sum(votes) * 2 > len(votes)
