"""Mô hình quan sát ô → pixel và bộ giải: hình học homography, PSF, sáng tối, QP ràng buộc hai mức."""
from __future__ import annotations

from dataclasses import dataclass
import itertools

import cv2
import numpy as np
import scipy.sparse as sp

from qrspec import Layout

S = 8          # độ phân giải mẫu trong template (px/ô)
QUIET = 2      # số ô vùng trống đưa vào mô hình
LAYOUTS = {v: Layout(v) for v in (1, 2, 3)}


def unit_square(n):
    return np.array([[0, 0], [n, 0], [n, n], [0, n]], np.float32)


def corners_to_h(corners, n):
    return cv2.getPerspectiveTransform(unit_square(n), np.float32(corners)).astype(np.float64)


def motion_offsets(vel, blur_px, npts=5):
    """Các mẫu đều trên đoạn vệt mờ, đơn vị px, theo hướng ``vel``."""
    if blur_px < 0.4:
        return np.zeros((1, 2), np.float32)
    v = np.asarray(vel, np.float64)
    d = v / (np.hypot(*v) + 1e-9)
    s = (np.arange(npts) + 0.5) / npts - 0.5
    return np.float32(np.outer(s * blur_px, d))


class Warp:
    """(u, v) -> (u, v) + D(u, v): D nội suy bilinear từ lưới KW×KW nút trải trên ký hiệu, đơn vị ô."""

    def __init__(self, n, kw=4):
        self.n, self.kw = n, kw
        self.d = np.zeros((kw, kw, 2))

    def apply(self, u, v):
        k = self.kw
        fu = np.clip(u / self.n * (k - 1), 0, k - 1 - 1e-6)
        fv = np.clip(v / self.n * (k - 1), 0, k - 1 - 1e-6)
        iu, iv = fu.astype(np.int32), fv.astype(np.int32)
        fu, fv = fu - iu, fv - iv
        d = self.d
        du = (d[iv, iu, 0] * (1 - fu) + d[iv, iu + 1, 0] * fu) * (1 - fv) + (d[iv + 1, iu, 0] * (1 - fu) + d[iv + 1, iu + 1, 0] * fu) * fv
        dv = (d[iv, iu, 1] * (1 - fu) + d[iv, iu + 1, 1] * fu) * (1 - fv) + (d[iv + 1, iu, 1] * (1 - fu) + d[iv + 1, iu + 1, 1] * fu) * fv
        return u + du, v + dv


class Template:
    """Ảnh mức xám của ký hiệu ở S px/ô, vùng trống ``QUIET`` ô; trắng = 1, đen = 0, chưa biết = 0,5."""

    def __init__(self, x, sigma_mod):
        n = x.shape[0]
        q = QUIET + 2
        big = np.ones((n + 2 * q, n + 2 * q), np.float32)
        big[q:q + n, q:q + n] = x
        self.q = q
        t = cv2.resize(big, None, fx=S, fy=S, interpolation=cv2.INTER_NEAREST)
        s = max(sigma_mod, 0.02) * S
        self.img = cv2.GaussianBlur(t, (0, 0), s) if s > 0.3 else t

    def sample(self, hinv, gx, gy, offs, warp=None):
        out = None
        for dx, dy in offs:
            X, Y = gx + dx, gy + dy
            w = hinv[2, 0] * X + hinv[2, 1] * Y + hinv[2, 2]
            u = (hinv[0, 0] * X + hinv[0, 1] * Y + hinv[0, 2]) / w
            v = (hinv[1, 0] * X + hinv[1, 1] * Y + hinv[1, 2]) / w
            if warp is not None:
                u, v = warp.apply(u, v)
            mx = (u + self.q) * S - 0.5
            my = (v + self.q) * S - 0.5
            r = cv2.remap(self.img, mx.astype(np.float32), my.astype(np.float32), cv2.INTER_LINEAR,
                          borderMode=cv2.BORDER_CONSTANT, borderValue=1.0)
            out = r if out is None else out + r
        return out / len(offs)


def known_matrix(layout):
    x = np.full(layout.known.shape, 0.5, np.float32)
    x[layout.known >= 0] = layout.known[layout.known >= 0]
    return x


class Fitter:
    """Khớp 8 tham số hình học bằng tìm mẫu theo NCC có trọng số, trên pixel của crop."""

    def __init__(self, gray, offs):
        self.g = gray.astype(np.float32)
        self.offs = offs
        h, w = gray.shape
        yy, xx = np.mgrid[0:h, 0:w]
        self.gx = xx.astype(np.float32)
        self.gy = yy.astype(np.float32)

    def roi(self, corners, n, margin):
        c = np.asarray(corners)
        p = (np.linalg.norm(c[1] - c[0]) + np.linalg.norm(c[3] - c[2])) / 2 / n
        m = margin * p + 3
        x1 = int(max(0, np.floor(c[:, 0].min() - m)))
        y1 = int(max(0, np.floor(c[:, 1].min() - m)))
        x2 = int(min(self.g.shape[1], np.ceil(c[:, 0].max() + m)))
        y2 = int(min(self.g.shape[0], np.ceil(c[:, 1].max() + m)))
        return y1, y2, x1, x2

    def score(self, corners, tpl, mask_tpl, n, thr=0.9):
        y1, y2, x1, x2 = self.roi(corners, n, QUIET)
        if y2 - y1 < 10 or x2 - x1 < 10:
            return -1.0
        H = corners_to_h(corners, n)
        try:
            hinv = np.linalg.inv(H)
        except np.linalg.LinAlgError:
            return -1.0
        gx, gy = self.gx[y1:y2, x1:x2], self.gy[y1:y2, x1:x2]
        m = tpl.sample(hinv, gx, gy, self.offs)
        w = mask_tpl.sample(hinv, gx, gy, self.offs) > thr
        if w.sum() < 60:
            return -1.0
        a = self.g[y1:y2, x1:x2][w]
        b = m[w]
        a = a - a.mean()
        b = b - b.mean()
        d = np.sqrt((a * a).sum() * (b * b).sum())
        return float((a * b).sum() / d) if d > 0 else -1.0

    def refine(self, corners, tpl, mask_tpl, n, steps=None, thr=0.9, iters=7):
        """Gauss-Newton trên 8 tọa độ góc, Jacobian sai phân; ``steps`` được bỏ qua (giữ chữ ký cũ)."""
        c = np.array(corners, np.float64)
        y1, y2, x1, x2 = self.roi(c, n, QUIET)
        if y2 - y1 < 10 or x2 - x1 < 10:
            return c, -1.0
        gx, gy, g = self.gx[y1:y2, x1:x2], self.gy[y1:y2, x1:x2], self.g[y1:y2, x1:x2]

        def render(cc):
            try:
                hinv = np.linalg.inv(corners_to_h(cc, n))
            except np.linalg.LinAlgError:
                return None
            return tpl.sample(hinv, gx, gy, self.offs)

        def ncc(a, b):
            a = a - a.mean()
            b = b - b.mean()
            d = np.sqrt((a * a).sum() * (b * b).sum())
            return float((a * b).sum() / d) if d > 0 else -1.0

        m = render(c)
        if m is None:
            return c, -1.0
        hinv = np.linalg.inv(corners_to_h(c, n))
        w = mask_tpl.sample(hinv, gx, gy, self.offs) > thr
        if w.sum() < 60:
            return c, -1.0
        best = ncc(g[w], m[w])
        lam = 1e-2
        h = 0.3
        for _ in range(iters):
            M = m[w].astype(np.float64)
            Y = g[w].astype(np.float64)
            X = np.stack([np.ones_like(M), M], 1)
            (a, b), *_ = np.linalg.lstsq(X, Y, rcond=None)
            r = Y - a - b * M
            J = np.empty((len(M), 8))
            for p in range(8):
                e = np.zeros(8)
                e[p] = h
                mp = render(c + e.reshape(4, 2))
                if mp is None:
                    return c, best
                J[:, p] = b * (mp[w] - M) / h
            JTJ = J.T.dot(J)
            JTr = J.T.dot(r)
            improved = False
            for _try in range(4):
                try:
                    d = np.linalg.solve(JTJ + lam * np.diag(np.diag(JTJ) + 1e-6), JTr)
                except np.linalg.LinAlgError:
                    lam *= 4
                    continue
                d = np.clip(d, -2.0, 2.0)
                nc = c + d.reshape(4, 2)
                nm = render(nc)
                if nm is not None:
                    s = ncc(g[w], nm[w])
                    if s > best + 1e-5:
                        c, m, best = nc, nm, s
                        lam = max(lam * 0.5, 1e-4)
                        improved = True
                        break
                lam *= 4
            if not improved or np.max(np.abs(d)) < 0.015:
                break
        return c, best


class Hypothesis:
    """Template ô chức năng cho một version với σ đã chọn."""

    def __init__(self, version, sigma_mod):
        self.version = version
        self.layout = LAYOUTS[version]
        self.n = self.layout.size
        self.tpl = Template(known_matrix(self.layout), sigma_mod)
        k = np.float32(self.layout.known >= 0)
        self.mask = Template(k, sigma_mod)
        # vùng trống được coi là đã biết
        q = self.mask.q
        S_ = S
        im = self.mask.img
        n = self.n
        ring = np.zeros_like(im, np.float32)
        ring[(q - 1) * S_:(q + n + 1) * S_, (q - 1) * S_:(q + n + 1) * S_] = 1      # chỉ 1 ô quanh mã được coi là trắng
        ring[q * S_:(q + n) * S_, q * S_:(q + n) * S_] = 0
        im = im.copy()
        inner = np.zeros_like(im, np.bool_)
        inner[q * S_:(q + n) * S_, q * S_:(q + n) * S_] = True
        im[~inner] = 0
        self.mask.img = im


def finder_patch(pitch, theta, offs, sigma_px):
    """Mẫu finder + 1 ô trắng quanh, xoay ``theta``, đã qua PSF."""
    half = int(np.ceil(4.5 * pitch * 1.45)) + 2
    y, x = np.mgrid[-half:half + 1, -half:half + 1].astype(np.float32)
    ct, st = np.cos(theta), np.sin(theta)
    big = np.ones((13 * S, 13 * S), np.float32)
    pat = np.ones((9, 9), np.float32)
    for r in range(9):
        for c in range(9):
            ring = max(abs(r - 4), abs(c - 4))
            pat[r, c] = 1.0 if ring in (2, 4) else 0.0
    big[2 * S:11 * S, 2 * S:11 * S] = cv2.resize(pat, None, fx=S, fy=S, interpolation=cv2.INTER_NEAREST)
    s = sigma_px / pitch * S
    big = cv2.GaussianBlur(big, (0, 0), max(s, 0.3))
    out = 0
    for dx, dy in offs:
        X, Y = x + dx, y + dy
        u = (ct * X + st * Y) / pitch
        v = (-st * X + ct * Y) / pitch
        out = out + cv2.remap(big, np.float32((u + 6.5) * S - 0.5), np.float32((v + 6.5) * S - 0.5), cv2.INTER_LINEAR,
                              borderMode=cv2.BORDER_CONSTANT, borderValue=1.0)
    out = out / len(offs)
    r = 4.4 * pitch
    mask = (np.abs(ct * x + st * y) < r) & (np.abs(-st * x + ct * y) < r)
    return out, mask


def peaks(resp, nmax, rad):
    r = resp.copy()
    out = []
    for _ in range(nmax):
        _, m, _, loc = cv2.minMaxLoc(r)
        if m < 0.15:
            break
        x, y = loc
        dx = dy = 0.0
        if 0 < x < r.shape[1] - 1:
            a, b, c = resp[y, x - 1], resp[y, x], resp[y, x + 1]
            d = a - 2 * b + c
            dx = 0.5 * (a - c) / d if abs(d) > 1e-6 else 0.0
        if 0 < y < r.shape[0] - 1:
            a, b, c = resp[y - 1, x], resp[y, x], resp[y + 1, x]
            d = a - 2 * b + c
            dy = 0.5 * (a - c) / d if abs(d) > 1e-6 else 0.0
        out.append((float(m), x + dx, y + dy))
        cv2.circle(r, (int(x), int(y)), int(rad), -1.0, -1)
    return out


def finder_triples(gray, quad, offs, sigma_px, versions):
    """Tìm các bộ ba finder: trả [(điểm, version, góc, độ lệch)]; không dùng thứ tự góc của quad."""
    q = np.asarray(quad, np.float64)
    e = q[1] - q[0]
    side = (np.linalg.norm(q[1] - q[0]) + np.linalg.norm(q[2] - q[1]) + np.linalg.norm(q[3] - q[2]) +
            np.linalg.norm(q[0] - q[3])) / 4
    theta = float(np.arctan2(e[1], e[0]))
    g = gray.astype(np.float32)
    x1, y1 = np.maximum(np.floor(q.min(0) - 8).astype(int), 0)
    x2, y2 = np.minimum(np.ceil(q.max(0) + 8).astype(int), [gray.shape[1], gray.shape[0]])
    sub = g[y1:y2, x1:x2]
    out = []
    for pitch in side / np.array([20, 22.5, 25, 28, 31.0]):
        if pitch < 1.0:
            continue
        pat, mask = finder_patch(pitch, theta, offs, sigma_px)
        if pat.shape[0] >= sub.shape[0] or pat.shape[1] >= sub.shape[1]:
            continue
        res = cv2.matchTemplate(sub, pat, cv2.TM_CCOEFF_NORMED, mask=np.uint8(mask) * 255)
        res = np.nan_to_num(res, nan=-1.0, posinf=-1.0, neginf=-1.0)
        off = (pat.shape[1] - 1) / 2
        pk = peaks(res.astype(np.float32), 8, 3.0 * pitch)
        pts = [(m, x + off + x1, y + off + y1) for m, x, y in pk]
        for ia, ib, ic in itertools.permutations(range(len(pts)), 3):
            a, b, c = pts[ia], pts[ib], pts[ic]
            pa, pb, pc = np.array(a[1:]), np.array(b[1:]), np.array(c[1:])
            ab, ac = pb - pa, pc - pa
            la, lc = np.linalg.norm(ab), np.linalg.norm(ac)
            if la < 8 or lc < 8:
                continue
            cross = ab[0] * ac[1] - ab[1] * ac[0]
            dot = ab.dot(ac)
            if cross <= 0 or abs(dot) > 0.25 * la * lc or abs(la - lc) > 0.2 * max(la, lc):
                continue
            mods = (la + lc) / 2 / pitch
            for v in versions:
                n = 17 + 4 * v
                d = n - 7
                if not 0.78 * d <= mods <= 1.28 * d:
                    continue
                ux, uy = ab / d, ac / d
                c0 = pa - 3.5 * ux - 3.5 * uy
                cs = np.array([c0, c0 + n * ux, c0 + n * ux + n * uy, c0 + n * uy])
                out.append((a[0] + b[0] + c[0], v, cs, abs(mods / d - 1)))
    out.sort(key=lambda t: -t[0])
    return out


def initial_fit(frames, offs_list, versions=(1, 2, 3), sigma_px=0.8, nframes=3):
    """Trả danh sách giả thiết (điểm, version, góc, chỉ số frame) sắp giảm dần theo NCC, gộp từ vài frame đầu."""
    res = []
    for fi, (o, offs) in enumerate(zip(frames[:nframes], offs_list)):
        fit = Fitter(o.gray, offs)
        seen = {}
        cand = []
        for ts, v, cs, dev in finder_triples(o.gray, o.quad, offs, sigma_px, versions):
            key = (v, tuple(np.round(cs[0] / 2.0).astype(int)), tuple(np.round(cs[1] / 2.0).astype(int)))
            if key in seen:
                continue
            seen[key] = 1
            cand.append((v, cs))
            if len(cand) >= 5:
                break
        for v, cs in cand:
            side = (np.linalg.norm(cs[1] - cs[0]) + np.linalg.norm(cs[2] - cs[1])) / 2
            hy = Hypothesis(v, sigma_px / (side / (17 + 4 * v)))
            c, s = fit.refine(cs, hy.tpl, hy.mask, hy.n)
            res.append((s, v, c, fi))
    res.sort(key=lambda r: -r[0])
    return res


def finder_centers(c, n):
    H = corners_to_h(c, n)
    p = np.array([[3.5, 3.5, 1.0], [n - 3.5, 3.5, 1.0], [3.5, n - 3.5, 1.0]])
    q = H.dot(p.T).T
    return q[:, :2] / q[:, 2:]


def align_by_finders(c_ref, n, ref_obs, dst_obs, offs, sigma_px, search=14.0):
    """Tìm 3 finder trên frame đích quanh vị trí dự đoán (từ tâm bbox) rồi suy góc bằng affine từ 3 điểm."""
    c0 = transfer_corners(c_ref, ref_obs, dst_obs)
    pc = finder_centers(c0, n)
    pref = finder_centers(c_ref, n)
    side = (np.linalg.norm(c_ref[1] - c_ref[0]) + np.linalg.norm(c_ref[2] - c_ref[1])) / 2
    pitch = side / n
    e = c_ref[1] - c_ref[0]
    theta = float(np.arctan2(e[1], e[0]))
    pat, mask = finder_patch(pitch, theta, offs, sigma_px)
    half = pat.shape[0] // 2
    g = dst_obs.gray.astype(np.float32)
    h, w = g.shape
    found = []
    score = 0.0
    for p in pc:
        x1 = int(max(0, np.floor(p[0] - search - half)))
        y1 = int(max(0, np.floor(p[1] - search - half)))
        x2 = int(min(w, np.ceil(p[0] + search + half + 1)))
        y2 = int(min(h, np.ceil(p[1] + search + half + 1)))
        if x2 - x1 <= pat.shape[1] or y2 - y1 <= pat.shape[0]:
            return c0, -1.0
        res = cv2.matchTemplate(g[y1:y2, x1:x2], pat, cv2.TM_CCOEFF_NORMED, mask=np.uint8(mask) * 255)
        res = np.nan_to_num(res, nan=-1.0, posinf=-1.0, neginf=-1.0).astype(np.float32)
        pk = peaks(res, 1, 2.0)
        if not pk:
            return c0, -1.0
        m, x, y = pk[0]
        found.append([x + x1 + half, y + y1 + half])
        score += m
    A = cv2.getAffineTransform(np.float32(pref), np.float32(found)).astype(np.float64)
    return np.column_stack([c_ref, np.ones(4)]).dot(A.T), score / 3.0


def transfer_corners(c, src, dst):
    """Chuyển góc giữa hai frame theo tâm bbox (tọa độ crop riêng của mỗi frame)."""
    a = np.array([(src.bbox[0] + src.bbox[2]) / 2, (src.bbox[1] + src.bbox[3]) / 2], float)
    b = np.array([(dst.bbox[0] + dst.bbox[2]) / 2, (dst.bbox[1] + dst.bbox[3]) / 2], float)
    return c + (b - a)


def pixel_set(corners, n, shape, br_only=False):
    """Chỉ số pixel trong ký hiệu + 1,5 ô quanh; trả (y1,y2,x1,x2), mặt nạ."""
    H = corners_to_h(corners, n)
    c = np.asarray(corners)
    p = (np.linalg.norm(c[1] - c[0]) + np.linalg.norm(c[3] - c[2])) / 2 / n
    m = 2 * p
    x1, y1 = np.maximum(np.floor(c.min(0) - m).astype(int), 0)
    x2 = int(min(shape[1], np.ceil(c[:, 0].max() + m)))
    y2 = int(min(shape[0], np.ceil(c[:, 1].max() + m)))
    gy, gx = np.mgrid[y1:y2, x1:x2]
    hinv = np.linalg.inv(H)
    X, Y = gx.ravel(), gy.ravel()
    w = hinv[2, 0] * X + hinv[2, 1] * Y + hinv[2, 2]
    u = (hinv[0, 0] * X + hinv[0, 1] * Y + hinv[0, 2]) / w
    v = (hinv[1, 0] * X + hinv[1, 1] * Y + hinv[1, 2]) / w
    keep = (u > -0.5) & (u < n + 0.5) & (v > -0.5) & (v < n + 0.5)
    if br_only:
        keep &= (u > 0.4 * n) & (v > 0.4 * n)
    return gx.ravel()[keep], gy.ravel()[keep]


def psf_points(sigma_px, offs, n_gauss=5):
    """Điểm mẫu và trọng số của PSF px = hộp pixel 1×1 ⊛ Gauss σ ⊛ đoạn vệt mờ."""
    if sigma_px > 0.05:
        s = np.sqrt(sigma_px ** 2 + 1.0 / 12.0)
    else:
        s = np.sqrt(1.0 / 12.0)
    if n_gauss == 5:
        t, wt = np.array([-2.0, -1.0, 0.0, 1.0, 2.0]), np.array([1, 4, 6, 4, 1], float)
    elif n_gauss == 4:
        t, wt = np.array([-1.5, -0.5, 0.5, 1.5]), np.array([1, 3, 3, 1], float)
    elif n_gauss == 3:
        t, wt = np.array([-1.0, 0.0, 1.0]), np.array([1, 2, 1], float)
    else:
        t, wt = np.array([-1.0, 1.0]), np.array([1.0, 1.0])
    wt = wt / wt.sum()
    d = t * s * (1.0 if n_gauss == 5 else 1.15)
    # chuẩn hóa để phương sai = s²
    var = (wt * d * d).sum()
    d = d * s / np.sqrt(var)
    dx, dy = np.meshgrid(d, d)
    wx, wy = np.meshgrid(wt, wt)
    w = (wx * wy).ravel()
    px, py = dx.ravel(), dy.ravel()
    allp = []
    allw = []
    for ox, oy in offs:
        allp.append(np.stack([px + ox, py + oy], 1))
        allw.append(w / len(offs))
    return np.concatenate(allp), np.concatenate(allw)


def build_matrix(corners, n, gx, gy, pts, wts, warp=None):
    """A[p, m] = phần PSF của pixel p rơi vào ô m; cột n*n là vùng trắng ngoài ký hiệu."""
    hinv = np.linalg.inv(corners_to_h(corners, n))
    np_ = len(gx)
    X = np.repeat(gx[:, None], len(pts), 1).astype(np.float64) + pts[:, 0][None, :]
    Y = np.repeat(gy[:, None], len(pts), 1).astype(np.float64) + pts[:, 1][None, :]
    w = hinv[2, 0] * X + hinv[2, 1] * Y + hinv[2, 2]
    u = (hinv[0, 0] * X + hinv[0, 1] * Y + hinv[0, 2]) / w
    v = (hinv[1, 0] * X + hinv[1, 1] * Y + hinv[1, 2]) / w
    if warp is not None:
        u, v = warp.apply(u, v)
    iu, iv = np.floor(u).astype(np.int32), np.floor(v).astype(np.int32)
    inside = (iu >= 0) & (iu < n) & (iv >= 0) & (iv < n)
    col = np.where(inside, iv * n + iu, n * n)
    rows = np.repeat(np.arange(np_), len(pts))
    data = np.repeat(wts[None, :], np_, 0).ravel()
    return sp.csr_matrix((data, (rows, col.ravel())), shape=(np_, n * n + 1))


def bilinear_basis(gx, gy, k):
    """Cơ sở bilinear k×k nút phủ khung chứa các pixel."""
    x1, x2 = gx.min(), gx.max() + 1e-6
    y1, y2 = gy.min(), gy.max() + 1e-6
    u = (gx - x1) / (x2 - x1) * (k - 1)
    v = (gy - y1) / (y2 - y1) * (k - 1)
    iu = np.minimum(u.astype(int), k - 2)
    iv = np.minimum(v.astype(int), k - 2)
    fu, fv = u - iu, v - iv
    B = np.zeros((len(gx), k * k))
    rows = np.arange(len(gx))
    B[rows, iv * k + iu] = (1 - fu) * (1 - fv)
    B[rows, iv * k + iu + 1] = fu * (1 - fv)
    B[rows, (iv + 1) * k + iu] = (1 - fu) * fv
    B[rows, (iv + 1) * k + iu + 1] = fu * fv
    return B


KB, KG = 3, 4      # số nút theo mỗi trục của trường cộng (lóa, nền) và trường nhân (độ tương phản)


@dataclass
class FrameData:
    y: np.ndarray
    A: sp.csr_matrix
    gx: np.ndarray
    gy: np.ndarray
    sig2: float = 1.0
    th_b: np.ndarray = None
    th_g: np.ndarray = None
    phi_b: np.ndarray = None
    phi_g: np.ndarray = None

    def bases(self):
        if self.phi_b is None:
            self.phi_b = bilinear_basis(self.gx, self.gy, KB)
            self.phi_g = bilinear_basis(self.gx, self.gy, KG)

    @property
    def b(self):
        return self.phi_b.dot(self.th_b)

    @property
    def g(self):
        return self.phi_g.dot(self.th_g)

    def predict(self, xfull):
        return self.b + self.g * self.A.dot(xfull)


def fit_photometric(fr, xfull, keep=None, ridge=0.02):
    """y ≈ b(p) + g(p)·Ax: hồi quy tuyến tính theo các nút b, g; ridge kéo về mức chung để vùng ít mẫu không trôi."""
    fr.bases()
    m = fr.A.dot(xfull)
    if keep is None:
        keep = np.ones(len(fr.y), bool)
    y, mk = fr.y[keep], m[keep]
    X0 = np.stack([1 - mk, mk], 1)
    (d, w), *_ = np.linalg.lstsq(X0, y, rcond=None)
    g0 = max(float(w - d), 1.0)
    pb, pg = fr.phi_b[keep], fr.phi_g[keep]
    X = np.hstack([pb, pg * mk[:, None]])
    th0 = np.r_[np.full(KB * KB, float(d)), np.full(KG * KG, g0)]
    r = y - X.dot(th0)
    XTX = X.T.dot(X)
    lam = ridge * np.trace(XTX) / XTX.shape[0] + 1e-6
    delta = np.linalg.solve(XTX + lam * np.eye(XTX.shape[0]), X.T.dot(r))
    th = th0 + delta
    fr.th_b, fr.th_g = th[:KB * KB], th[KB * KB:]
    e = fr.y - fr.predict(xfull)
    fr.sig2 = float(np.mean(e[keep] ** 2)) + 1e-3


class Solver:
    """min Σ‖y−d−(w−d)Ax‖²/σ² + μ·Σx(1−x), 0≤x≤1, ô ``fixed`` giữ nguyên."""

    def __init__(self, frames, n):
        self.frames, self.n = frames, n
        self.N = n * n
        self.build()

    def build(self):
        Q = None
        c = 0
        rhs_full = 0
        for fr in self.frames:
            B = sp.diags(fr.g).dot(fr.A)
            Bi = B[:, :self.N]
            b0 = fr.y - fr.b - np.asarray(B[:, self.N].sum(1)).ravel()
            q = Bi.T.dot(Bi) / fr.sig2
            ci = Bi.T.dot(b0) / fr.sig2
            Q = q if Q is None else Q + q
            c = c + ci
        self.Q = sp.csr_matrix(Q)
        self.c = c
        self.diag = self.Q.diagonal()

    def cost(self, x):
        return 0.5 * x.dot(self.Q.dot(x)) - self.c.dot(x)

    def solve(self, x0, fixed, mus=(0.0, 0.1, 0.3, 0.6, 1.0, 1.6), iters=120):
        """Gradient chiếu có gia tốc, tăng dần μ (tính theo tỉ lệ đường chéo Q)."""
        x = x0.copy()
        free = ~fixed
        L = float(sp.linalg.norm(self.Q, 1)) + 1e-9
        scale = float(np.median(self.diag[self.diag > 0])) if (self.diag > 0).any() else 1.0
        for mu_r in mus:
            mu = mu_r * scale
            lip = L + 2 * mu
            z = x.copy()
            t = 1.0
            for _ in range(iters):
                g = self.Q.dot(z) - self.c + mu * (1 - 2 * z)
                nx = z - g / lip
                nx = np.where(free, np.clip(nx, 0, 1), x)
                t1 = (1 + np.sqrt(1 + 4 * t * t)) / 2
                z = nx + (t - 1) / t1 * (nx - x)
                z = np.where(free, np.clip(z, 0, 1), x)
                x, t = nx, t1
        return x

    def icm(self, x, fixed, max_sweeps=8):
        """Lật từng ô chừng nào còn giảm chi phí (x đã nhị phân)."""
        x = x.copy()
        free = np.flatnonzero(~fixed)
        g = self.Q.dot(x) - self.c
        q_csc = self.Q.tocsc()
        for _ in range(max_sweeps):
            changed = 0
            d = 1 - 2 * x[free]
            gain = g[free] * d + 0.5 * self.diag[free] * d * d
            order = np.argsort(gain)
            for k in order:
                if gain[k] >= -1e-9:
                    break
                i = free[k]
                di = 1 - 2 * x[i]
                ga = g[i] * di + 0.5 * self.diag[i] * di * di
                if ga < -1e-9:
                    x[i] += di
                    col = q_csc[:, i]
                    g[col.indices] += col.data * di
                    changed += 1
            if not changed:
                break
        return x

    def llr(self, x):
        """Chênh chi phí (đen − trắng) khi lật từng ô, các ô khác giữ ở x: dương nghĩa là nghiêng về trắng."""
        g = self.Q.dot(x) - self.c
        c1 = g * (1 - x) + 0.5 * self.diag * (1 - x) ** 2
        c0 = g * (0 - x) + 0.5 * self.diag * x ** 2
        return c0 - c1
