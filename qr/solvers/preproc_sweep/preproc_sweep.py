"""preproc_sweep: giữ cascade hiện có làm bước đầu, thêm các bước rẻ cho frame/lượt chưa đọc được, vẫn giải mã bằng zxing/WeChat.

Các bước (bật/tắt bằng ``steps``, để đo lợi ích từng bước):
  photo  flat-field, gamma, NLM, bilateral rồi đưa vào decoder
  sweep  khử mờ miền ảnh, quét độ dài vệt mờ mịn (Wiener hoặc Richardson-Lucy), xếp hạng theo độ khớp ô chức năng
  warp   khớp lưới theo finder (matched filter đã mờ theo PSF + Gauss-Newton), warp về 8 px/ô với quiet zone sạch
  stack  căn nhiều frame theo vận tốc (hoặc theo lưới) rồi xếp chồng, khử mờ
  lsq    giải giá trị từng ô trên lưới đã khớp bằng bình phương tối thiểu với mô hình mờ đã biết, vẽ lại mã sạch cho zxing
  joint  như lsq nhưng gộp phương trình của nhiều frame
  dd     (bổ trợ lsq/joint) khớp lại lưới theo toàn bộ ô vừa giải, vì 3 finder không ràng buộc được góc dưới phải khi tem nghiêng
"""
import collections
import os
import sys

import cv2
import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla
import zxingcpp


def _find_root():
    here = os.path.dirname(os.path.abspath(__file__))
    while not os.path.exists(os.path.join(here, "qr", "decoder.py")):
        parent = os.path.dirname(here)
        if parent == here:
            raise RuntimeError("không tìm thấy thư mục qr/")
        here = parent
    return here


sys.path.insert(0, _find_root())

from qr.decoder import read_wechat_gray  # noqa: E402
from qr.content_filter import ACCEPT_SYMBOL, CODE_PATTERN, accept_text, inside, size_ok, symbol_ok  # noqa: E402
from qr.detector import Detection  # noqa: E402
from qr.multiframe import PassDecoder  # noqa: E402
from qr.preprocessor import UPSCALE_PAD_PER_SCALE, stretch_contrast, upscale_gray  # noqa: E402
from qr.tracker import Track  # noqa: E402

ALL_STEPS = "photo,sweep,warp,stack,lsq,joint,dd"
DEFAULT_STEPS = "photo,sweep,warp"   # lsq/joint/stack/dd là bản yếu hơn của B (grid_sr) và tốn thời gian: tắt mặc định
SIZES = (21, 25, 29, 33)             # số ô mỗi cạnh được thử khi khớp lưới (V1–V4); (25,) = chỉ tem V2
BLUR_FACTORS = (1.0, 0.94, 0.88, 0.82, 1.06)      # lệch về phía ngắn: ước lượng thiếu dễ chấp nhận hơn thừa
UEC_MIN = 0.25                                    # phần sửa lỗi còn dư tối thiểu (V1-L: tối đa 2 ký tự lỗi, như ISO)
ROTS_DEG = (-6.0, 0.0, 6.0)
GRID_FIT_MIN = 0.55


# ── đọc bằng decoder có sẵn ────────────────────────────────────────────────────

def zx_hit(gray, binarizer=None, uec_min=UEC_MIN):
    """zxing, chỉ nhận mã còn dư sửa lỗi, đúng định dạng và đúng ``ACCEPT_SYMBOL`` (mặc định mọi loại): trả (text, 4 góc)."""
    opts = {} if binarizer is None else {"binarizer": binarizer}
    for b in zxingcpp.read_barcodes(gray, formats=zxingcpp.BarcodeFormat.QRCode, try_rotate=True, **opts):
        if b.valid and b.text and symbol_ok(b, ACCEPT_SYMBOL) and accept_text(b.text, CODE_PATTERN):
            uec = b.extra.get("UEC", 1.0) if isinstance(b.extra, dict) else 1.0
            if uec >= uec_min:
                p = b.position
                pts = np.array([[p.top_left.x, p.top_left.y], [p.top_right.x, p.top_right.y],
                                [p.bottom_right.x, p.bottom_right.y], [p.bottom_left.x, p.bottom_left.y]], np.float32)
                return b.text, pts
    return None


def zx(gray, binarizer=None, uec_min=UEC_MIN):
    hit = zx_hit(gray, binarizer, uec_min)
    return hit[0] if hit else None


BINS = (None, zxingcpp.Binarizer.GlobalHistogram)


def read_any_hit(gray, wechat=True):
    """zxing hai binarizer rồi WeChat CNN trên ảnh đã phóng to: (text, 4 góc trong tọa độ ``gray``) hoặc None."""
    for bz in BINS:
        hit = zx_hit(gray, bz)
        if hit:
            return hit
    if wechat:
        hit = read_wechat_gray(gray, use_cnn=True)
        if hit and accept_text(hit[0], CODE_PATTERN) and size_ok(gray, hit[1], ACCEPT_SYMBOL):   # WeChat không báo version
            return hit
    return None


def read_any(gray, wechat=True):
    hit = read_any_hit(gray, wechat)
    return hit[0] if hit else None


# ── PSF ───────────────────────────────────────────────────────────────────────

def line_psf(length, angle, scale=1.0, sigma=0.0):
    """PSF vệt thẳng dài ``length`` px ở độ phân giải ``scale`` (vẽ siêu lấy mẫu ×8, chuẩn hóa tổng = 1)."""
    L = max(length * scale, 0.0)
    size = (int(np.ceil(L + 6 * sigma * scale)) + 3) | 1
    ss = 8
    k = np.zeros((size * ss, size * ss), np.float32)
    c = size * ss / 2.0
    dx, dy = np.cos(angle), np.sin(angle)
    n = int(L * ss * 2) + 1
    for t in np.linspace(-L * ss / 2, L * ss / 2, n):
        k[int(c + dy * t), int(c + dx * t)] = 1.0
    if sigma > 0:
        k = cv2.GaussianBlur(k, (0, 0), sigma * scale * ss)
    k = cv2.resize(k, (size, size), interpolation=cv2.INTER_AREA)
    return k / max(k.sum(), 1e-9)


def wiener(gray, psf, k):
    h, w = gray.shape
    size = psf.shape[0]
    pad = np.zeros((h, w), np.float32)
    pad[:size, :size] = psf
    pad = np.roll(pad, (-(size // 2), -(size // 2)), axis=(0, 1))
    g = np.float32(gray)
    win = (np.hanning(h)[:, None] ** 0.25) * (np.hanning(w)[None, :] ** 0.25)
    mean = float(g.mean())
    S = np.fft.rfft2((g - mean) * win)
    H = np.fft.rfft2(pad)
    out = np.fft.irfft2(S * np.conj(H) / (np.abs(H) ** 2 + k), s=(h, w)) + mean
    return np.float32(out)


def richardson_lucy(gray, psf, iters=12):
    g = np.float32(gray) + 1.0
    est = g.copy()
    flip = psf[::-1, ::-1]
    for _ in range(iters):
        blur = cv2.filter2D(est, -1, psf, borderType=cv2.BORDER_REPLICATE)
        ratio = g / np.maximum(blur, 1e-3)
        est = np.maximum(est * cv2.filter2D(ratio, -1, flip, borderType=cv2.BORDER_REPLICATE), 0)
    return est - 1.0


def to_u8(img):
    return np.clip(img, 0, 255).astype(np.uint8)


# ── ánh sáng ──────────────────────────────────────────────────────────────────

def flat_field(gray, mod_px):
    """Chia cho nền sáng cục bộ (đóng hình thái cỡ ~3 ô rồi làm mượt), đưa nền trắng về 200."""
    s = int(round(mod_px * 3)) | 1
    g = np.float32(gray)
    illum = cv2.morphologyEx(g, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (s, s)))
    illum = cv2.GaussianBlur(illum, (0, 0), s / 2.0)
    return to_u8(g * 200.0 / np.maximum(illum, 12.0))


def gamma(gray, g=0.6):
    lo, hi = np.percentile(gray, (0.5, 99.5))
    x = np.clip((np.float32(gray) - lo) / max(hi - lo, 1.0), 0, 1)
    return to_u8(255 * x ** g)


def photo_variants(gray, mod_px):
    ff = flat_field(gray, mod_px)
    yield "ff", ff
    yield "gamma", gamma(ff)
    yield "nlm", cv2.fastNlMeansDenoising(ff, None, h=8, templateWindowSize=3, searchWindowSize=9)
    yield "bilat", cv2.bilateralFilter(ff, 5, 30, 1.5)


# ── lưới QR: khuôn ô chức năng ─────────────────────────────────────────────────

def function_pattern(N):
    """(M, known): M giá trị ô (1 = trắng), known: ô đã biết (finder, phân cách, timing, alignment, dark module)."""
    M = np.full((N, N), 0.5, np.float32)
    known = np.zeros((N, N), bool)

    def finder(r0, c0):
        for r in range(-1, 8):
            for c in range(-1, 8):
                rr, cc = r0 + r, c0 + c
                if 0 <= rr < N and 0 <= cc < N:
                    ring = max(abs(r - 3), abs(c - 3))
                    M[rr, cc] = 0.0 if ring in (0, 1, 3) else 1.0
                    known[rr, cc] = True
    finder(0, 0)
    finder(0, N - 7)
    finder(N - 7, 0)
    for i in range(8, N - 8):
        M[6, i] = M[i, 6] = 0.0 if i % 2 == 0 else 1.0
        known[6, i] = known[i, 6] = True
    if N > 21:
        a = N - 7
        for r in range(-2, 3):
            for c in range(-2, 3):
                ring = max(abs(r), abs(c))
                M[a + r, a + c] = 0.0 if ring in (0, 2) else 1.0
                known[a + r, a + c] = True
    M[N - 8, 8] = 0.0
    known[N - 8, 8] = True
    return M, known


def finder_template(mod_px, theta, psf):
    """Finder + vành phân cách 1 ô, xoay theta, ở cỡ ảnh thật, đã mờ theo PSF. Trả (ảnh, mask)."""
    ss = 8
    grid = np.ones((9, 9), np.float32)
    for r in range(9):
        for c in range(9):
            ring = max(abs(r - 4), abs(c - 4))
            grid[r, c] = 0.0 if ring in (0, 1, 3) else 1.0
    big = cv2.resize(grid, None, fx=ss, fy=ss, interpolation=cv2.INTER_NEAREST)
    side = int(np.ceil(9 * mod_px * (abs(np.cos(theta)) + abs(np.sin(theta))))) + 4
    side |= 1
    scale = mod_px / ss
    ca, sa = np.cos(theta) * scale, np.sin(theta) * scale
    c = side / 2.0 - 0.5
    M = np.float32([[ca, -sa, c - (ca * 35.5 - sa * 35.5)], [sa, ca, c - (sa * 35.5 + ca * 35.5)]])
    tmpl = cv2.warpAffine(big, M, (side, side), flags=cv2.INTER_AREA, borderValue=1.0)
    mask = cv2.warpAffine(np.ones_like(big), M, (side, side), flags=cv2.INTER_NEAREST, borderValue=0.0)
    tmpl = cv2.GaussianBlur(tmpl, (0, 0), 0.6)
    if psf is not None:
        tmpl = cv2.filter2D(tmpl, -1, psf, borderType=cv2.BORDER_REPLICATE)
    return tmpl, np.float32(mask)


def rect_info(o):
    pts = o.polygon if o.polygon is not None and len(o.polygon) >= 3 else o.quad
    (cx, cy), (w, h), a = cv2.minAreaRect(np.float32(pts))
    return (cx, cy), max(w, h), np.deg2rad(a)


def find_triples(g, o, psf):
    """Tìm tâm finder bằng matched filter (template đã mờ theo PSF), trả các bộ ba (score, tl, tr, bl, m)."""
    (_, _), side, a0 = rect_info(o)
    a0 = ((a0 + np.pi / 4) % (np.pi / 2)) - np.pi / 4
    x1, y1, x2, y2 = o.bbox
    m_ext = 0.15 * max(x2 - x1, y2 - y1)
    h, w = g.shape
    X1, Y1 = int(max(0, x1 - m_ext)), int(max(0, y1 - m_ext))
    X2, Y2 = int(min(w, x2 + m_ext)), int(min(h, y2 + m_ext))
    roi = np.float32(g[Y1:Y2, X1:X2])
    peaks = []
    for m in np.geomspace(side / max(SIZES) * 0.85, side / min(SIZES) * 1.2, 7):
        for d in ROTS_DEG:
            th = a0 + np.deg2rad(d)
            tmpl, mask = finder_template(m, th, psf)
            if tmpl.shape[0] >= min(roi.shape):
                continue
            ncc = cv2.matchTemplate(roi, tmpl, cv2.TM_CCOEFF_NORMED, mask=mask)
            ncc = np.nan_to_num(ncc, nan=0.0, posinf=0.0, neginf=0.0)
            dil = cv2.dilate(ncc, np.ones((5, 5), np.uint8))
            ys, xs = np.where((ncc == dil) & (ncc > 0.35))
            off = tmpl.shape[0] / 2.0 - 0.5
            for x, y in zip(xs, ys):
                sx, sy = _subpixel(ncc, x, y)
                peaks.append((float(ncc[y, x]), sx + off + X1, sy + off + Y1, m, th))
    peaks.sort(reverse=True)
    kept = []
    for p in peaks:
        if all(np.hypot(p[1] - q[1], p[2] - q[2]) > 3.5 * max(p[3], q[3]) for q in kept):
            kept.append(p)
        if len(kept) >= 8:
            break
    out = []
    for i, tl in enumerate(kept):
        for j, tr in enumerate(kept):
            for l, bl in enumerate(kept):
                if len({i, j, l}) < 3:
                    continue
                v1 = np.array([tr[1] - tl[1], tr[2] - tl[2]])
                v2 = np.array([bl[1] - tl[1], bl[2] - tl[2]])
                d1, d2 = np.linalg.norm(v1), np.linalg.norm(v2)
                if d1 < 1 or d2 < 1 or not 0.75 < d1 / d2 < 1.33:
                    continue
                if v1[0] * v2[1] - v1[1] * v2[0] <= 0:      # ảnh không soi gương: tl→tr→bl thuận chiều kim đồng hồ
                    continue
                cos = float(v1 @ v2) / (d1 * d2)
                if abs(cos) > 0.3:
                    continue
                mm = float(np.mean([tl[3], tr[3], bl[3]]))
                s = tl[0] + tr[0] + bl[0] - 1.0 * abs(cos) - 0.5 * abs(np.log(d1 / d2))
                out.append((s, (tl[1], tl[2]), (tr[1], tr[2]), (bl[1], bl[2]), mm))
    out.sort(key=lambda t: -t[0])
    return out[:3]


def _subpixel(a, x, y):
    def off(l, c, r):
        d = l - 2 * c + r
        return 0.0 if abs(d) < 1e-6 else float(np.clip(0.5 * (l - r) / d, -0.5, 0.5))
    sx = x + (off(a[y, x - 1], a[y, x], a[y, x + 1]) if 0 < x < a.shape[1] - 1 else 0.0)
    sy = y + (off(a[y - 1, x], a[y, x], a[y + 1, x]) if 0 < y < a.shape[0] - 1 else 0.0)
    return sx, sy


def H_from_corners(C, N):
    src = np.float32([[0, 0], [N, 0], [N, N], [0, N]])
    return cv2.getPerspectiveTransform(src, np.float32(C))


def init_corners(tl, tr, bl, N):
    """Ánh xạ affine từ 3 tâm finder ra 4 góc lưới. Tọa độ ô: tâm finder TL ở (3.5, 3.5)."""
    src = np.float32([[3.5, 3.5], [N - 3.5, 3.5], [3.5, N - 3.5]])
    A = cv2.getAffineTransform(src, np.float32([tl, tr, bl]))
    pts = np.float32([[0, 0, 1], [N, 0, 1], [N, N, 1], [0, N, 1]])
    return (A @ pts.T).T


def render(M, s, q, white=1.0):
    big = cv2.resize(np.float32(M), None, fx=s, fy=s, interpolation=cv2.INTER_NEAREST)
    pad = int(q * s)
    return cv2.copyMakeBorder(big, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=white)


def refine_grid(g, C, N, M, known, psf, iters=10):
    """Gauss-Newton 8 bậc tự do trên 4 góc, khớp ô đã biết (đã mờ theo PSF) với ảnh. Trả (C, ncc)."""
    s, q = 6, 2
    tmpl = render(np.where(known, M, 0.5), s, q)
    mask = render(np.float32(known), s, q, white=0.0)
    h, w = g.shape
    S = np.float32([[1.0 / s, 0, -q], [0, 1.0 / s, -q], [0, 0, 1]])  # lưới phóng → tọa độ ô
    I = np.float32(g)
    C = np.float32(C).copy()
    best = (-1.0, C.copy())
    lam = 1e-3
    for _ in range(iters):
        H = H_from_corners(C, N) @ S
        T = cv2.warpPerspective(tmpl, np.float32(H), (w, h), flags=cv2.INTER_LINEAR, borderValue=1.0)
        W = cv2.warpPerspective(mask, np.float32(H), (w, h), flags=cv2.INTER_NEAREST, borderValue=0.0) > 0.5
        if psf is not None:
            T = cv2.filter2D(T, -1, psf, borderType=cv2.BORDER_REPLICATE)
        T = cv2.GaussianBlur(T, (0, 0), 0.6)
        ys, xs = np.where(W)
        if len(xs) < 50:
            break
        t, y = T[ys, xs], I[ys, xs]
        A = np.column_stack([np.ones_like(t), t])
        (a, b), *_ = np.linalg.lstsq(A, y, rcond=None)
        r = y - (a + b * t)
        ncc = float(np.corrcoef(t, y)[0, 1]) if t.std() > 1e-6 and y.std() > 1e-6 else 0.0
        if ncc > best[0]:
            best = (ncc, C.copy())
        Hinv = np.linalg.inv(H_from_corners(C, N))
        p = np.column_stack([xs, ys, np.ones_like(xs)]) @ Hinv.T
        u = p[:, 0] / p[:, 2] / N
        v = p[:, 1] / p[:, 2] / N
        wc = np.column_stack([(1 - u) * (1 - v), u * (1 - v), u * v, (1 - u) * v])
        Tx = cv2.Sobel(T, cv2.CV_32F, 1, 0, ksize=3, scale=1 / 8.0)[ys, xs]
        Ty = cv2.Sobel(T, cv2.CV_32F, 0, 1, ksize=3, scale=1 / 8.0)[ys, xs]
        J = np.zeros((len(xs), 8), np.float64)
        J[:, ::2] = wc * (b * Tx)[:, None]
        J[:, 1::2] = wc * (b * Ty)[:, None]
        JtJ = J.T @ J
        d = np.linalg.solve(JtJ + (lam * np.trace(JtJ) / 8 + 1e-6) * np.eye(8), -J.T @ r)
        d = np.clip(d, -1.5, 1.5)
        C = C + np.float32(d.reshape(4, 2))
        if np.max(np.abs(d)) < 0.01:
            break
    return best[1], best[0]


def fit_grid(g, o, ctx, sigma=0.7):
    """Trả danh sách lưới (ncc, N, C) tốt nhất trước, dùng ô chức năng và PSF đã biết."""
    psf = None
    if ctx.blur_px >= 1.0:
        psf = line_psf(ctx.blur_px, np.arctan2(ctx.velocity[1], ctx.velocity[0]))
    out = []
    for score, tl, tr, bl, m in find_triples(g, o, psf):
        d = (np.hypot(tr[0] - tl[0], tr[1] - tl[1]) + np.hypot(bl[0] - tl[0], bl[1] - tl[1])) / 2
        est = d / m + 7
        for N in SIZES:
            if abs(N - est) > 2.6:
                continue
            M, known = function_pattern(N)
            C0 = init_corners(tl, tr, bl, N)
            C, ncc = refine_grid(g, C0, N, M, known, psf)
            out.append((ncc, N, C))
    out.sort(key=lambda t: -t[0])
    uniq, seen = [], set()       # mỗi cỡ giữ lưới tốt nhất: finder chiếm phần lớn ô đã biết nên phân biệt cỡ kém
    for f in out:
        if f[1] not in seen:
            seen.add(f[1])
            uniq.append(f)
    return uniq[:2]


# ── warp về lưới nguyên ─────────────────────────────────────────────────────────

def warp_to_grid(g, C, N, s=8, q=4):
    """Warp vùng mã về s px/ô, chuẩn hóa theo ô finder, vùng quiet phủ trắng sạch."""
    src = np.float32([[0, 0], [N * s, 0], [N * s, N * s], [0, N * s]])
    Hg = cv2.getPerspectiveTransform(src, np.float32(C))
    out = cv2.warpPerspective(np.float32(g), Hg, (N * s, N * s), flags=cv2.INTER_CUBIC | cv2.WARP_INVERSE_MAP * 0,
                              borderMode=cv2.BORDER_REPLICATE) if False else None
    Hinv = np.linalg.inv(Hg)
    out = cv2.warpPerspective(np.float32(g), Hinv, (N * s, N * s), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    M, known = function_pattern(N)
    big_known = cv2.resize(np.uint8(known), None, fx=s, fy=s, interpolation=cv2.INTER_NEAREST) > 0
    big_M = cv2.resize(M, None, fx=s, fy=s, interpolation=cv2.INTER_NEAREST)
    white = np.percentile(out[big_known & (big_M > 0.9)], 70) if (big_known & (big_M > 0.9)).any() else out.max()
    black = np.percentile(out[big_known & (big_M < 0.1)], 30) if (big_known & (big_M < 0.1)).any() else out.min()
    norm = np.clip((out - black) / max(white - black, 1.0), 0, 1) * 255
    pad = q * s
    return cv2.copyMakeBorder(to_u8(norm), pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=255)


def fn_score(g, C, N):
    """Độ khớp ô chức năng của ảnh (đã khử mờ): NCC trung bình ô so với khuôn."""
    M, known = function_pattern(N)
    src = np.float32([[0, 0], [N, 0], [N, N], [0, N]])
    H = cv2.getPerspectiveTransform(np.float32(C), src * 8)
    out = cv2.warpPerspective(np.float32(g), H, (N * 8, N * 8), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    cell = cv2.resize(out, (N, N), interpolation=cv2.INTER_AREA)
    a, b = cell[known], M[known]
    return float(np.corrcoef(a, b)[0, 1]) if a.std() > 1e-6 else -1.0


# ── giải ô trên lưới ───────────────────────────────────────────────────────────

def fine_kernel(L, angle, sigma, ss=3):
    """Ma trận điểm (dx, dy, w) của pixel box ⊗ gauss ⊗ vệt, lưới 1/ss px."""
    size = (int(np.ceil(L + 6 * sigma + 2)) * ss) | 1
    k = np.zeros((size, size), np.float32)
    c = size // 2
    dx, dy = np.cos(angle), np.sin(angle)
    n = int(L * ss * 4) + 1
    for t in np.linspace(-L * ss / 2, L * ss / 2, n):
        k[int(round(c + dy * t)), int(round(c + dx * t))] = 1.0
    k = cv2.blur(k, (ss, ss), borderType=cv2.BORDER_CONSTANT)
    if sigma > 0:
        k = cv2.GaussianBlur(k, (0, 0), sigma * ss, borderType=cv2.BORDER_CONSTANT)
    k /= k.sum()
    ys, xs = np.where(k > 0.01 * k.max())
    w = k[ys, xs]
    return (xs - c) / ss, (ys - c) / ss, w / w.sum()


def build_forward(g, C, N, kernel, margin=1.0):
    """A: pixel ← ô; pixel ngoài lưới coi là trắng (quiet zone), phần đó nằm ở w_out."""
    H = H_from_corners(C, N)
    pts = np.float32(C)
    x0, y0 = np.floor(pts.min(0) - 1.0 * (np.linalg.norm(pts[1] - pts[0]) / N)).astype(int)
    x1, y1 = np.ceil(pts.max(0) + 1.0 * (np.linalg.norm(pts[1] - pts[0]) / N)).astype(int)
    h, w = g.shape
    x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, w - 1), min(y1, h - 1)
    xx, yy = np.meshgrid(np.arange(x0, x1 + 1, dtype=np.float64), np.arange(y0, y1 + 1, dtype=np.float64))
    xx, yy = xx.ravel(), yy.ravel()
    Hi = np.linalg.inv(H)
    d = Hi[2, 0] * xx + Hi[2, 1] * yy + Hi[2, 2]
    u = (Hi[0, 0] * xx + Hi[0, 1] * yy + Hi[0, 2]) / d
    v = (Hi[1, 0] * xx + Hi[1, 1] * yy + Hi[1, 2]) / d
    keep = (u > -margin) & (u < N + margin) & (v > -margin) & (v < N + margin)
    xx, yy, u, v = xx[keep], yy[keep], u[keep], v[keep]
    n = len(xx)
    if n < 50:
        return None
    kx, ky, kw = kernel
    m = len(kw)
    X = np.tile(xx, m) + np.repeat(kx, n)
    Y = np.tile(yy, m) + np.repeat(ky, n)
    W = np.repeat(kw, n)
    rows = np.tile(np.arange(n), m)
    d = Hi[2, 0] * X + Hi[2, 1] * Y + Hi[2, 2]
    U = (Hi[0, 0] * X + Hi[0, 1] * Y + Hi[0, 2]) / d
    V = (Hi[1, 0] * X + Hi[1, 1] * Y + Hi[1, 2]) / d
    iu, iv = np.floor(U).astype(np.int64), np.floor(V).astype(np.int64)
    inside = (iu >= 0) & (iu < N) & (iv >= 0) & (iv < N)
    A = sp.coo_matrix((W[inside], (rows[inside], (iv[inside] * N + iu[inside]))), shape=(n, N * N)).tocsr()
    w_out = np.bincount(rows[~inside], weights=W[~inside], minlength=n)
    b = np.float64(g)[yy.astype(int), xx.astype(int)]
    return A, w_out, b, u / N - 0.5, v / N - 0.5


def solve_modules(frames, N, rho0=0.02, rounds=4):
    """Giải giá trị ô trên lưới từ các frame (A, w_out, b, u, v); trả (M mềm, phần dư chuẩn hóa)."""
    M0, known = function_pattern(N)
    k = known.ravel()
    M = M0.ravel().astype(np.float64)
    Z = M.copy()
    res = 1.0
    AtA0 = sum((f[0].T @ f[0]) for f in frames).tocsc()
    tr = float(AtA0.diagonal().sum()) / (N * N)
    for rnd in range(rounds):
        Atb = np.zeros(N * N)
        tot, cnt = 0.0, 0
        for A, w_out, b, u, v in frames:
            pred = A @ M + w_out
            # B(u,v) + C(u,v)·pred: ánh sáng biến đổi chậm theo mặt phẳng
            X = np.column_stack([np.ones_like(u), u, v, pred, pred * u, pred * v])
            beta, *_ = np.linalg.lstsq(X, b, rcond=None)
            Bp = beta[0] + beta[1] * u + beta[2] * v
            Cp = np.maximum(beta[3] + beta[4] * u + beta[5] * v, 1.0)
            y = (b - Bp) / Cp
            tot += float(np.sum((y - pred) ** 2))
            cnt += len(y)
            Atb += A.T @ (y - w_out)
        res = tot / max(cnt, 1)
        rho = rho0 * tr * (1 + rnd * 2)
        D = np.full(N * N, rho)
        D[k] = 10 * tr
        M = spla.splu((AtA0 + sp.diags(D, format="csc")).tocsc()).solve(Atb + D * Z)
        M = np.clip(M, -0.2, 1.2)
        Zu = np.clip((M - 0.5) * (1.5 + rnd) + 0.5, 0, 1)
        Z = np.where(k, M0.ravel(), Zu)
    return M.reshape(N, N), res


def refine_on_modules(g, C, M, L, angle, iters=6):
    """Khớp lại 4 góc theo toàn bộ ô đã quyết định (không chỉ ô chức năng)."""
    N = M.shape[0]
    F, known = function_pattern(N)
    hard = np.where(known, F, (M > 0.5).astype(np.float32))
    psf = line_psf(L, angle) if L >= 1.0 else None
    return refine_grid(g, C, N, hard, np.ones_like(known), psf, iters=iters)[0]


def render_hard(M, s=8, q=4):
    Mh = (M > 0.5).astype(np.float32)
    F, known = function_pattern(M.shape[0])
    Mh = np.where(known, F, Mh)
    return to_u8(render(Mh, s, q) * 255)


# ── phương pháp ────────────────────────────────────────────────────────────────

class PreprocSweep:
    def __init__(self, steps=DEFAULT_STEPS, deblur="wiener", need=2, debug=False):
        self.steps = set(s for s in steps.split(",") if s)
        self.deblur = deblur
        self.need = need
        self.debug = debug
        self.log = []

    # từng bước đơn frame ----------------------------------------------------------
    def _step_photo(self, g, mod_px, bbox=None):
        """Đọc cả crop sau chỉnh sáng/khử nhiễu. Decoder tự tìm mã nên có thể đọc trúng tem bên cạnh lọt vào crop:
        chỉ nhận mã có tâm nằm trong ``bbox`` của tem đang đọc."""
        pad = UPSCALE_PAD_PER_SCALE * 4
        for name, img in photo_variants(g, mod_px):
            hit = read_any_hit(upscale_gray(img, 4))
            if hit and inside((np.asarray(hit[1], np.float32) - pad) / 4, bbox):
                return name, hit[0]
        return None

    def _deblur_candidates(self, g, ctx, grid):
        """Ảnh khử mờ ×2 theo từng độ dài trong bảng quét, xếp theo độ khớp ô chức năng (nếu có lưới)."""
        angle = float(np.arctan2(ctx.velocity[1], ctx.velocity[0]))
        up = cv2.resize(g, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        out = []
        for f in BLUR_FACTORS:
            L = ctx.blur_px * f
            psf = line_psf(L, angle, scale=2.0)
            for name, img in self._deblur_one(up, psf):
                score = 0.0
                if grid is not None:
                    C2 = grid[2] * 2 + 0.5
                    score = fn_score(img, C2, grid[1])
                out.append((score, name, f, img))
        out.sort(key=lambda c: -c[0])
        return out

    def _deblur_one(self, up, psf):
        if self.deblur in ("wiener", "both"):
            for k in (0.02, 0.06):
                yield f"w{k}", wiener(up, psf, k)
        if self.deblur in ("rl", "both"):
            yield "rl", richardson_lucy(up, psf)

    def _step_sweep(self, g, ctx, grid, top=4):
        for score, name, f, img in self._deblur_candidates(g, ctx, grid)[:top]:
            u8 = to_u8(stretch_contrast(to_u8(img)))
            t = read_any(upscale_gray(u8, 2))
            if t:
                return f"{name}@{f}", t
            if grid is not None and "warp" in self.steps:
                t = read_any(warp_to_grid(img, grid[2] * 2 + 0.5, grid[1]), wechat=False)
                if t:
                    return f"{name}@{f}+warp", t
        return None

    def _step_warp(self, g, grid):
        ff = flat_field(g, np.linalg.norm(grid[2][1] - grid[2][0]) / grid[1])
        for img in (g, ff):
            t = read_any(warp_to_grid(img, grid[2], grid[1]))
            if t:
                return "warp", t
        return None

    def _lsq_frame(self, g, ctx, grid, sigmas=(0.7,)):
        angle = float(np.arctan2(ctx.velocity[1], ctx.velocity[0]))
        best = []
        for f in BLUR_FACTORS:
            for sg in sigmas:
                L = ctx.blur_px * f
                kernel = fine_kernel(L, angle, sg)
                fr = build_forward(g, grid[2], grid[1], kernel)
                if fr is None:
                    return None
                M, res = solve_modules([fr], grid[1])
                best.append((res, f, sg, M))
        best.sort(key=lambda b: b[0])
        for res, f, sg, M in best[:3]:
            t = zx(render_hard(M))
            if t:
                return f"lsq@{f}", t
        if "dd" in self.steps:
            res, f, sg, M = best[0]
            L, kernel, N, C = ctx.blur_px * f, fine_kernel(ctx.blur_px * f, angle, sg), grid[1], grid[2]
            for _ in range(2):
                C = refine_on_modules(g, C, M, L, angle)
                fr = build_forward(g, C, N, kernel)
                if fr is None:
                    return None
                M, res = solve_modules([fr], N)
                t = zx(render_hard(M))
                if t:
                    return f"lsq+dd@{f}", t
        return None

    def _joint(self, frames_g, grids, ctx):
        angle = float(np.arctan2(ctx.velocity[1], ctx.velocity[0]))
        sizes = collections.Counter()
        for fits in grids:
            for f in fits:
                sizes[f[1]] += f[0]
        for N, _ in sizes.most_common(2):
            items = [(g, next(f for f in fits if f[1] == N)) for g, fits in zip(frames_g, grids)
                     if any(f[1] == N for f in fits)]
            if len(items) < 2:
                continue
            best = []
            for f in BLUR_FACTORS:
                kernel = fine_kernel(ctx.blur_px * f, angle, 0.7)
                frs = [fr for fr in (build_forward(g, gr[2], N, kernel) for g, gr in items) if fr is not None]
                if len(frs) < 2:
                    continue
                M, res = solve_modules(frs, N)
                best.append((res, f, M))
            best.sort(key=lambda b: b[0])
            for res, f, M in best[:3]:
                t = zx(render_hard(M))
                if t:
                    return f"joint@{f}", t
            if "dd" in self.steps and best:
                res, f, M = best[0]
                L, kernel = ctx.blur_px * f, fine_kernel(ctx.blur_px * f, angle, 0.7)
                Cs = [gr[2] for _, gr in items]
                for _ in range(2):
                    Cs = [refine_on_modules(g, C, M, L, angle) for (g, _), C in zip(items, Cs)]
                    frs = [fr for fr in (build_forward(g, C, N, kernel) for (g, _), C in zip(items, Cs)) if fr is not None]
                    if len(frs) < 2:
                        break
                    M, res = solve_modules(frs, N)
                    t = zx(render_hard(M))
                    if t:
                        return f"joint+dd@{f}", t
        return None

    def _stack_read(self, obs, ctx, grids):
        """Xếp chồng căn theo vận tốc + phase correlation trên ROI vuông rồi khử mờ quét; rồi xếp chồng trên lưới."""
        # căn theo lưới
        items = [(o.gray, gr) for o, gr in zip(obs, grids) if gr is not None]
        if len(items) >= 2:
            Ns = collections.Counter(gr[1] for _, gr in items)
            N = Ns.most_common(1)[0][0]
            acc, cnt = None, 0
            s = 8
            for g, gr in items:
                if gr[1] != N:
                    continue
                Hg = np.linalg.inv(cv2.getPerspectiveTransform(np.float32([[0, 0], [N * s, 0], [N * s, N * s], [0, N * s]]), np.float32(gr[2])))
                w = cv2.warpPerspective(np.float32(flat_field(g, np.linalg.norm(gr[2][1] - gr[2][0]) / N)), Hg, (N * s, N * s),
                                        flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
                acc = w if acc is None else acc + w
                cnt += 1
            if cnt >= 2:
                img = to_u8(stretch_contrast(to_u8(acc / cnt)))
                t = read_any(cv2.copyMakeBorder(img, 32, 32, 32, 32, cv2.BORDER_CONSTANT, value=255))
                if t:
                    return "stack_grid", t
                # khử mờ trên lưới: PSF đổi tỉ lệ theo px/ô của frame cuối
                g, gr = items[-1]
                mpx = np.linalg.norm(gr[2][1] - gr[2][0]) / N
                u = (gr[2][1] - gr[2][0]) / np.linalg.norm(gr[2][1] - gr[2][0])
                v = (gr[2][3] - gr[2][0]) / np.linalg.norm(gr[2][3] - gr[2][0])
                vel = np.array(ctx.velocity, float)
                ang = np.arctan2(vel @ v, vel @ u)
                for f in BLUR_FACTORS[:4]:
                    psf = line_psf(ctx.blur_px * f * s / mpx / s, ang, scale=s)
                    out = wiener(acc / cnt, psf, 0.03)
                    img = to_u8(stretch_contrast(to_u8(out)))
                    t = read_any(cv2.copyMakeBorder(img, 32, 32, 32, 32, cv2.BORDER_CONSTANT, value=255))
                    if t:
                        return f"stack_grid_w@{f}", t
        # căn theo vận tốc
        rois = self._velocity_aligned(obs, ctx)
        if rois is not None and len(rois) >= 2:
            ref = rois[-1]
            mean = np.mean(rois, axis=0)
            up = cv2.resize(mean, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
            t = read_any(upscale_gray(to_u8(stretch_contrast(to_u8(up))), 2))
            if t:
                return "stack_vel", t
            ang = float(np.arctan2(ctx.velocity[1], ctx.velocity[0]))
            for f in BLUR_FACTORS[:4]:
                img = wiener(up, line_psf(ctx.blur_px * f, ang, scale=2.0), 0.03)
                t = read_any(upscale_gray(to_u8(stretch_contrast(to_u8(img))), 2))
                if t:
                    return f"stack_vel_w@{f}", t
        return None

    @staticmethod
    def _velocity_aligned(obs, ctx):
        """Dịch các crop về cùng tọa độ của frame cuối bằng vận tốc, tinh chỉnh bằng phase correlation."""
        last = obs[-1]
        h, w = last.gray.shape
        ref = np.float32(last.gray)
        win = cv2.createHanningWindow((w, h), cv2.CV_32F)
        v = np.array(ctx.velocity, float)
        rois = [ref]
        for o in obs[:-1]:
            d = (o.origin - last.origin) + v * (last.frame - o.frame)
            d = np.array(d, float)
            warped = cv2.warpAffine(np.float32(o.gray), np.float32([[1, 0, d[0]], [0, 1, d[1]]]), (w, h),
                                    flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
            (dx, dy), resp = cv2.phaseCorrelate(warped, ref, win)
            if resp < 0.03 or np.hypot(dx, dy) > 12:
                continue
            warped = cv2.warpAffine(warped, np.float32([[1, 0, dx], [0, 1, dy]]), (w, h), flags=cv2.INTER_CUBIC,
                                    borderMode=cv2.BORDER_REPLICATE)
            rois.append(warped)
        return rois

    # đọc lượt ---------------------------------------------------------------------
    def read_pass(self, obs, ctx):
        need = min(self.need, len(obs))
        votes = collections.Counter()
        read = [False] * len(obs)
        dec = PassDecoder(CODE_PATTERN, symbol=ACCEPT_SYMBOL)
        track = Track(track_id=1, first_frame=0, last_frame=0, center=(0.0, 0.0), size=1.0, velocity=ctx.velocity)
        blur = [ctx.blur_px] if ctx.blur_px >= 1.0 else []

        def vote(i, text):
            if not accept_text(text, CODE_PATTERN):
                return False
            votes[text] += 1
            read[i] = True
            return votes[text] >= need

        for i, o in enumerate(obs):
            img = cv2.cvtColor(o.gray, cv2.COLOR_BGR2BGRA if False else cv2.COLOR_GRAY2BGR)
            det = Detection(bbox_xyxy=o.bbox, quad_xy=o.quad, confidence=o.conf, polygon_xy=o.polygon)
            hit = dec.read(img, o.bbox, det, track, blur)
            if hit and vote(i, hit.text):
                return hit.text

        # phần thêm chỉ chạy khi cascade chưa chốt được
        grids = [[] for _ in obs]
        steps = self.steps
        need_grid = steps & {"warp", "lsq", "joint", "stack", "sweep"}
        if need_grid:
            for i, o in enumerate(obs):
                try:
                    fits = fit_grid(o.gray, o, ctx)
                except cv2.error:
                    fits = []
                grids[i] = [f for f in fits if f[0] > GRID_FIT_MIN]

        single = []
        if "warp" in steps:
            single.append(("warp", lambda g, o, gr: self._step_warp(g, gr)))
        if "photo" in steps:
            single.append(("photo", lambda g, o, gr: self._step_photo(g, rect_info(o)[1] / 25, o.bbox)))
        if "sweep" in steps and ctx.blur_px >= 1.0:
            single.append(("sweep", lambda g, o, gr: self._step_sweep(g, ctx, gr)))
        if "lsq" in steps:
            single.append(("lsq", lambda g, o, gr: self._lsq_frame(g, ctx, gr)))

        for sname, fn in single:
            for i, o in enumerate(obs):
                if read[i]:
                    continue
                for gr in (grids[i] if sname in ("warp", "lsq") else (grids[i][:1] or [None])):
                    got = fn(o.gray, o, gr)
                    if got:
                        self.log.append((sname, got[0]))
                        if vote(i, got[1]):
                            return got[1]
                        break

        if len(obs) >= 2:
            if "joint" in steps:
                got = self._joint([o.gray for o in obs], grids, ctx)
                if got:
                    self.log.append(("joint", got[0]))
                    votes[got[1]] += 1
                    if votes[got[1]] >= need:
                        return got[1]
            if "stack" in steps:
                got = self._stack_read(obs, ctx, [g[0] if g else None for g in grids])
                if got:
                    self.log.append(("stack", got[0]))
                    votes[got[1]] += 1
                    if votes[got[1]] >= need:
                        return got[1]
        return None
