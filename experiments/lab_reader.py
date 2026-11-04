"""Bộ đọc thử nghiệm: tái hiện PassReader và bật/tắt từng hướng cải tiến bằng ``LabConfig``.

Không sửa ``qr/``. Bước nào cũng đo thời gian thật; kết quả và thời gian của các bước trên cùng frame/ROI
được nhớ lại để mọi cấu hình so sánh công bằng và chạy nhanh hơn.
"""

from __future__ import annotations

import re
import time
from collections import deque
from dataclasses import dataclass, field, replace

import cv2
import numpy as np
import zxingcpp

from qr.corrector import add_quiet_zone, warp_qr
from qr.decoder import read_wechat_gray, read_zxing_gray
from qr.detector import Detection
from qr.preprocessor import clahe, roi_bounds, stretch_contrast, upscale_gray
from qr.tracker import Observation, PassTracker, Track

CODE_RE = re.compile(r"^\d{12}$")


@dataclass(frozen=True)
class LabConfig:
    name: str = "base"
    fix_tracker: bool = False     # H0: thu hẹp cổng, nội dung khác → tách lượt
    validate: bool = False        # H1: chỉ tính phiếu cho mã đúng định dạng
    min_votes: int = 2
    gate: bool = False            # H2: bỏ cascade cho QR chạm mép / kích thước bất thường
    binarizers: bool = False      # H3
    fast_roi: bool = False        # H4: đoán vị trí, đọc không cần YOLO giữa các lần detect
    yolo_every_ms: float = 400.0
    fast_every_n: int = 2
    best_frame: bool = False      # H5: chạy WeChat chỉ trên frame nét nhất/định kỳ
    stack: int = 0                # H6: số ROI tối thiểu để xếp chồng (0 = tắt)
    stack_max: int = 8
    deblur: bool = False          # H7
    deblur_k: float = 0.02
    refine: bool = False          # H8: tìm lại 4 góc QR rồi warp
    modules: bool = False         # H9: đọc lưới V1 từ giá trị ô, cộng dồn nhiều frame
    modules_every: int = 2
    best_period: int = 4
    expensive: bool = True        # False: bỏ WeChat trên từng frame
    stack_wechat: bool = True     # WeChat trên ảnh đã xếp chồng


BASE = LabConfig()


# ── các phép xử lý ảnh ────────────────────────────────────────────────────────

def read_zxing_binarizer(gray: np.ndarray, binarizer) -> str | None:
    for b in zxingcpp.read_barcodes(gray, formats=zxingcpp.BarcodeFormat.QRCode, binarizer=binarizer,
                                    try_rotate=True):
        if b.valid and b.text:
            return b.text
    return None


def sharpness(gray: np.ndarray) -> float:
    return float(cv2.Laplacian(gray, cv2.CV_32F).var())


def wiener_motion(gray: np.ndarray, length: float, angle_rad: float, k: float) -> np.ndarray:
    """Khử mờ chuyển động thẳng độ dài ``length`` px theo hướng ``angle_rad`` trên ảnh xám."""
    h, w = gray.shape
    size = int(np.ceil(length)) | 1
    psf = np.zeros((size, size), np.float32)
    c = size / 2 - 0.5
    dx, dy = np.cos(angle_rad), np.sin(angle_rad)
    half = (length - 1) / 2
    cv2.line(psf, (int(round(c - dx * half)), int(round(c - dy * half))),
             (int(round(c + dx * half)), int(round(c + dy * half))), 1.0, 1)
    psf /= max(psf.sum(), 1e-6)
    pad = np.zeros((h, w), np.float32)
    pad[:size, :size] = psf
    pad = np.roll(pad, (-(size // 2), -(size // 2)), axis=(0, 1))
    g = np.float32(gray)
    # Làm mềm biên để FFT không tạo vòng nhiễu
    win_y = np.hanning(h)[:, None] ** 0.25
    win_x = np.hanning(w)[None, :] ** 0.25
    mean = float(g.mean())
    G = np.fft.rfft2((g - mean) * (win_y * win_x))
    H = np.fft.rfft2(pad)
    F = G * np.conj(H) / (np.abs(H) ** 2 + k)
    out = np.fft.irfft2(F, s=(h, w)) + mean
    return np.clip(out, 0, 255).astype(np.uint8)


def refined_quad(roi_gray: np.ndarray, scale: int = 4) -> np.ndarray | None:
    """4 góc QR trong tọa độ ROI (H8): mảng ô đen trên nhãn sáng, nối lại rồi lấy hình chữ nhật xoay."""
    up = cv2.resize(roi_gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    up = cv2.GaussianBlur(up, (0, 0), scale * 0.6)
    _, binary = cv2.threshold(up, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    k = cv2.getStructuringElement(cv2.MORPH_RECT, (int(scale * 6) | 1, int(scale * 6) | 1))
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, k)
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    center = np.array(up.shape[::-1], np.float32) / 2
    best, best_score = None, -1.0
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < (scale * 20) ** 2:
            continue
        rect = cv2.minAreaRect(cnt)
        w, h = rect[1]
        if min(w, h) <= 0 or max(w, h) / min(w, h) > 1.6:
            continue
        score = area / (1.0 + np.linalg.norm(np.array(rect[0], np.float32) - center))
        if score > best_score:
            best, best_score = rect, score
    if best is None:
        return None
    return cv2.boxPoints(best).astype(np.float32) / scale


def read_refined(roi_gray: np.ndarray) -> str | None:
    quad = refined_quad(roi_gray)
    if quad is None:
        return None
    dst = np.float32([[0, 0], [255, 0], [255, 255], [0, 255]])
    # Nới 4% vì đường bao sau khi đóng hình có thể cắt lẹm hàng ô ngoài
    c = quad.mean(axis=0)
    src = c + (quad - c) * 1.04
    warped = cv2.warpPerspective(roi_gray, cv2.getPerspectiveTransform(src, dst), (256, 256),
                                 flags=cv2.INTER_CUBIC)
    hit = read_zxing_gray(add_quiet_zone(warped, pad_px=32))
    return hit[0] if hit else None


# ── H9: lấy giá trị từng ô của QR version 1 ──────────────────────────────────

_N = 21


def _v1_pattern() -> tuple[np.ndarray, np.ndarray]:
    """(mẫu cố định 21×21: 0 đen / 1 trắng, mask các ô cố định)."""
    pat, mask = np.ones((_N, _N), np.float32), np.zeros((_N, _N), bool)

    def finder(y, x):
        for j in range(-1, 8):
            for i in range(-1, 8):
                yy, xx = y + j, x + i
                if not (0 <= yy < _N and 0 <= xx < _N):
                    continue
                mask[yy, xx] = True
                ring = max(abs(j - 3), abs(i - 3))
                pat[yy, xx] = 0.0 if ring in (0, 1, 3) else 1.0
    finder(0, 0), finder(0, _N - 7), finder(_N - 7, 0)
    for i in range(8, _N - 8):
        pat[6, i] = pat[i, 6] = 0.0 if i % 2 == 0 else 1.0
        mask[6, i] = mask[i, 6] = True
    pat[_N - 8, 8] = 0.0   # ô đen cố định
    mask[_N - 8, 8] = True
    return pat, mask


_PAT, _MASK = _v1_pattern()


def _sample(gray: np.ndarray, quad: np.ndarray) -> np.ndarray:
    side = _N * 6
    dst = np.float32([[0, 0], [side - 1, 0], [side - 1, side - 1], [0, side - 1]])
    warped = cv2.warpPerspective(gray, cv2.getPerspectiveTransform(quad, dst), (side, side),
                                 flags=cv2.INTER_LINEAR)
    # Lấy vùng giữa ô (bỏ 1/6 mỗi cạnh) để ít lẫn ô bên cạnh
    return cv2.resize(warped[1:-1, 1:-1], (_N, _N), interpolation=cv2.INTER_AREA).astype(np.float32)


def _score(values: np.ndarray) -> float:
    a, b = values[_MASK], _PAT[_MASK]
    sa, sb = a.std(), b.std()
    if sa < 1e-3:
        return -1.0
    return float(((a - a.mean()) * (b - b.mean())).mean() / (sa * sb))


def _finder_template(ppm: float, angle: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Mẫu 3 finder + timing đã xoay: (ảnh mẫu, mask, 4 góc QR trong tọa độ mẫu)."""
    scale = 6
    side = int(round(_N * ppm * scale))
    pat = cv2.resize(_PAT, (side, side), interpolation=cv2.INTER_NEAREST)
    mask = cv2.resize(_MASK.astype(np.uint8), (side, side), interpolation=cv2.INTER_NEAREST).astype(np.float32)
    diag = int(np.ceil(side * 1.5))
    off = (diag - side) // 2
    M = cv2.getRotationMatrix2D((diag / 2, diag / 2), angle, 1.0)
    corners = np.float32([[off, off], [off + side, off], [off + side, off + side], [off, off + side]])
    canvas = np.zeros((diag, diag), np.float32)
    canvas[off:off + side, off:off + side] = pat
    weight = np.zeros((diag, diag), np.float32)
    weight[off:off + side, off:off + side] = mask
    canvas = cv2.warpAffine(canvas, M, (diag, diag), flags=cv2.INTER_LINEAR)
    weight = cv2.warpAffine(weight, M, (diag, diag), flags=cv2.INTER_LINEAR)
    corners = cv2.transform(corners[None], M)[0] / scale
    out = int(round(diag / scale))
    return (cv2.resize(canvas, (out, out), interpolation=cv2.INTER_AREA),
            (cv2.resize(weight, (out, out), interpolation=cv2.INTER_AREA) > 0.5).astype(np.uint8),
            corners)


_TEMPLATES: dict = {}


def pose_search(gray: np.ndarray, ppm_list=(2.5, 2.77, 3.05, 3.4), angles=None):
    """Tìm 4 góc QR V1 bằng cách so mẫu cố định theo góc và tỉ lệ. Trả (4 góc, độ khớp, ppm, góc)."""
    g = np.float32(gray)
    best = None
    best_score = -1.0
    if angles is None:
        angles = range(0, 360, 4)
    for ppm in ppm_list:
        for angle in angles:
            angle = int(angle) % 360
            key = (ppm, angle)
            if key not in _TEMPLATES:
                _TEMPLATES[key] = _finder_template(ppm, angle)
            tpl, mask, corners = _TEMPLATES[key]
            if tpl.shape[0] > g.shape[0] or tpl.shape[1] > g.shape[1]:
                continue
            r = cv2.matchTemplate(g, tpl, cv2.TM_CCOEFF_NORMED, mask=mask)
            r = np.nan_to_num(r, posinf=-1.0, neginf=-1.0)
            _, score, _, loc = cv2.minMaxLoc(r)
            if score > best_score:
                best_score = score
                best = (corners + np.float32(loc), score, ppm, angle)
    return best


def refine_quad(gray: np.ndarray, quad0: np.ndarray, unit: float = 1.0):
    """Dò cục bộ 4 góc để khớp mẫu cố định nhất. ``unit``: số px ảnh trên 1 px sensor."""
    best_quad = np.float32(quad0)
    best_values = _sample(gray, best_quad)
    best_score = _score(best_values)
    for shift, ds in ((1.0, 0.04), (0.5, 0.02), (0.25, 0.01)):
        shift *= unit
        improved, rounds = True, 0
        while improved and rounds < 4:
            improved = False
            rounds += 1
            c = best_quad.mean(axis=0)
            u = best_quad[1] - best_quad[0]
            v = best_quad[3] - best_quad[0]
            trials = [best_quad + np.float32([dx, dy])
                      for dx, dy in ((shift, 0), (-shift, 0), (0, shift), (0, -shift))]
            for sign in (1, -1):
                for axis in (u, v):
                    n = axis / max(np.linalg.norm(axis), 1e-6)
                    trials.append(best_quad + np.outer(((best_quad - c) @ n) * (sign * ds), n).astype(np.float32))
                th = sign * ds * 0.5    # xoay nhẹ
                R = np.float32([[np.cos(th), -np.sin(th)], [np.sin(th), np.cos(th)]])
                trials.append((best_quad - c) @ R.T + c)
            for q in trials:
                values = _sample(gray, q)
                score = _score(values)
                if score > best_score + 1e-4:
                    best_values, best_score, best_quad = values, score, q
                    improved = True
    return best_values, best_score, best_quad


def sample_modules(gray: np.ndarray, quad0: np.ndarray | None = None):
    if quad0 is None:
        found = pose_search(gray)
        if found is None:
            return None
        quad0 = found[0]
    return refine_quad(gray, quad0)


def decode_modules(values: np.ndarray) -> str | None:
    """Ngưỡng hóa giá trị ô (vài ngưỡng), vẽ lại QR sạch với mẫu cố định đúng rồi cho zxing giải + RS."""
    dark = float(np.median(values[_MASK & (_PAT == 0)]))
    light = float(np.median(values[_MASK & (_PAT == 1)]))
    if light - dark < 2:
        return None
    norm = (values - dark) / (light - dark)
    # Ô nhỏ + mờ làm ô lẫn sang hàng xóm: thử làm nét trên lưới ô trước khi ngưỡng hóa
    lap = cv2.Laplacian(norm, cv2.CV_32F, ksize=1, borderType=cv2.BORDER_REPLICATE)
    for sharp in (0.0, 0.15, 0.3):
        v = norm - sharp * lap
        for th in (0.5, 0.42, 0.58):
            modules = (v > th).astype(np.uint8) * 255
            modules[_MASK] = (_PAT[_MASK] * 255).astype(np.uint8)
            img = cv2.resize(modules, None, fx=6, fy=6, interpolation=cv2.INTER_NEAREST)
            img = cv2.copyMakeBorder(img, 24, 24, 24, 24, cv2.BORDER_CONSTANT, value=255)
            for b in zxingcpp.read_barcodes(img, formats=zxingcpp.BarcodeFormat.QRCode, try_rotate=False,
                                            try_downscale=False):
                if b.valid and b.text:
                    return b.text
    return None


# ── xếp chồng ─────────────────────────────────────────────────────────────────

def stack_rois(rois: list[np.ndarray], scale: int = 4) -> np.ndarray:
    """Căn subpixel theo ROI cuối bằng phase correlation, nội suy lên ``scale`` lần rồi lấy trung bình."""
    ref = np.float32(rois[-1])
    h, w = ref.shape
    win = cv2.createHanningWindow((w, h), cv2.CV_32F)
    acc = cv2.resize(ref, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    count = 1
    for roi in rois[:-1]:
        moving = np.float32(roi)
        (dx, dy), response = cv2.phaseCorrelate(moving, ref, win)
        if response < 0.05 or abs(dx) > w / 3 or abs(dy) > h / 3:
            continue
        up = cv2.resize(moving, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        M = np.float32([[1, 0, dx * scale], [0, 1, dy * scale]])
        acc += cv2.warpAffine(up, M, (up.shape[1], up.shape[0]), flags=cv2.INTER_LINEAR,
                              borderMode=cv2.BORDER_REPLICATE)
        count += 1
    mean = acc / count
    lo, hi = np.percentile(mean, (1, 99))
    # Kéo dải xám: sau khi cộng dồn, tín hiệu rất hẹp (thiếu sáng) vẫn đủ sạch để giãn ra
    return np.clip((mean - lo) * 255.0 / max(hi - lo, 1.0), 0, 255).astype(np.uint8)


@dataclass
class _TrackState:
    rois: deque = field(default_factory=lambda: deque(maxlen=16))   # ROI vuông cùng kích thước
    side: int = 0
    best_sharp: float = 0.0
    pose: tuple | None = None           # (ppm, góc) QR đã dò được
    pose_tries: int = 0
    attempts: int = 0
    skips: int = 0


class LabReader:
    def __init__(self, cfg: LabConfig, scene, memo: dict):
        self.cfg = cfg
        self.scene = scene
        self.memo = memo
        fps = scene.fps
        max_gap = round(2.0 * fps)
        max_speed = 1500.0 / fps
        self.tracker = _FixedTracker(max_gap, max_speed) if cfg.fix_tracker else \
            PassTracker(max_gap=max_gap, max_speed_px=max_speed)
        self.states: dict[int, _TrackState] = {}
        self.announced: set[int] = set()
        self.emitted: list[tuple[str, int, float, float, int]] = []   # text, frame, cx, cy, track
        self.all_finished: list[Track] = []
        self.sizes: deque = deque(maxlen=30)
        self.last_yolo_t = -1e9
        self.step_hits: dict[str, int] = {}
        self.step_ms: dict[str, float] = {}
        self.attempts = 0
        self.jobs = dict(yolo=0, fast=0)
        self.total_ms = 0.0
        self.gated = 0
        self.skipped = 0

    # ── chạy bước có đo thời gian và nhớ kết quả ───────────────────────────────

    def _timed(self, name: str, key: tuple | None, fn) -> tuple[str | None, float]:
        if key is not None:
            hit = self.memo.get((name, *key))
            if hit is not None:
                return hit
        t0 = time.perf_counter()
        text = fn()
        ms = (time.perf_counter() - t0) * 1000.0
        if key is not None:
            self.memo[(name, *key)] = (text, ms)
        return text, ms

    def _run(self, name: str, key, fn, state: list) -> str | None:
        text, ms = self._timed(name, key, fn)
        state[0] += ms
        self.step_ms[name] = self.step_ms.get(name, 0.0) + ms
        if text and self.cfg.validate and not CODE_RE.match(text):
            return None
        if text:
            self.step_hits[name] = self.step_hits.get(name, 0) + 1
        return text

    # ── giải một QR ───────────────────────────────────────────────────────────

    def _attempt(self, frame, idx, bbox, det: Detection | None, track: Track | None, cost: list,
                 cheap_only: bool = False) -> str | None:
        cfg = self.cfg
        x1, y1, x2, y2 = roi_bounds(frame.shape, bbox, 0.25)
        roi = frame[y1:y2, x1:x2]
        if roi.size == 0:
            return None
        self.attempts += 1
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        key = (idx, x1, y1, x2, y2)
        state = self.states.setdefault(track.track_id, _TrackState()) if track is not None else _TrackState()
        state.attempts += 1

        text = self._run("zxing4", key, lambda: _z(upscale_gray(gray, 4)), cost)
        if text:
            return text
        if cfg.binarizers:
            up = upscale_gray(gray, 4)
            for binname, b in (("hist", zxingcpp.Binarizer.GlobalHistogram),
                               ("fixed", zxingcpp.Binarizer.FixedThreshold)):
                text = self._run("zxing_" + binname, key, lambda: read_zxing_binarizer(up, b), cost)
                if text:
                    return text
        if det is not None:
            text = self._run("warp", key, lambda: _warp(frame, det), cost)
            if text:
                return text
        if cfg.refine:
            text = self._run("refine", key, lambda: read_refined(gray), cost)
            if text:
                return text
        if cfg.deblur and track is not None:
            text = self._deblur(gray, track, key, cost)
            if text:
                return text

        sq = self._square(frame, bbox, state.side)
        if sq is not None and track is not None:
            state.side = sq.shape[0]
            state.rois.append(sq)

        if cfg.modules and track is not None and sq is not None and state.attempts % cfg.modules_every == 0:
            text = self._modules(track, state, cost, cheap_only)
            if text:
                return text
        if cfg.stack and track is not None and len(state.rois) >= cfg.stack:
            text = self._stacked(state, track, cost, cheap_only)
            if text:
                return text

        run_expensive = cfg.expensive and not cheap_only
        if run_expensive and cfg.best_frame:
            # Laplacian thô bị nhiễu chi phối (mọi frame như nhau): đo trên ảnh đã làm mờ nhẹ
            s = sharpness(cv2.GaussianBlur(gray, (0, 0), 1.0))
            run_expensive = s >= 1.02 * state.best_sharp or state.attempts % cfg.best_period == 0
            state.best_sharp = max(state.best_sharp, s)
        if run_expensive:
            text = self._run("wechat_clahe", key,
                             lambda: _w(upscale_gray(clahe(gray), 4), False), cost)
            if text:
                return text
            text = self._run("wechat_cnn_stretch", key,
                             lambda: _w(upscale_gray(stretch_contrast(gray), 4), True), cost)
            if text:
                return text
            text = self._run("wechat_cnn3", key, lambda: _w(upscale_gray(gray, 3), True), cost)
            if text:
                return text
        return None

    def _square(self, frame, bbox, side: int = 0) -> np.ndarray | None:
        """ROI vuông kích thước cố định theo QR, dùng để cộng dồn qua frame."""
        x1, y1, x2, y2 = (float(v) for v in bbox)
        if not side:
            side = max(96, int(round(max(x2 - x1, y2 - y1) * 1.8 / 16)) * 16)
        cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
        ax, ay = int(round(cx - side / 2)), int(round(cy - side / 2))
        h, w = frame.shape[:2]
        if ax < 0 or ay < 0 or ax + side > w or ay + side > h:
            return None
        return cv2.cvtColor(frame[ay:ay + side, ax:ax + side], cv2.COLOR_BGR2GRAY)

    def _blur_lengths(self, track: Track) -> list[float]:
        speed = float(np.hypot(*track.velocity))
        if speed < 0.05:
            return []
        if self.scene.exposure_ms is not None:
            length = speed * self.scene.fps * self.scene.exposure_ms * 1e-3
            return [length, length * 1.3] if length >= 1.5 else []
        return [2.0, 3.0, 4.5, 6.5]   # video cũ không biết exposure

    def _deblur(self, gray, track, key, cost) -> str | None:
        lengths = self._blur_lengths(track)
        if not lengths:
            return None
        angle = float(np.arctan2(track.velocity[1], track.velocity[0]))
        for length in lengths:
            def run():
                up = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
                out = wiener_motion(up, length * 2, angle, self.cfg.deblur_k)
                return _z(upscale_gray(out, 2))
            k2 = (*key, round(length, 1), round(angle, 1), self.cfg.deblur_k)
            text = self._run("wiener", k2, run, cost)
            if text:
                return text
        return None

    def _stacked(self, state: _TrackState, track, cost, cheap_only) -> str | None:
        cfg = self.cfg
        rois = list(state.rois)[-cfg.stack_max:]
        t0 = time.perf_counter()
        stacked = stack_rois(rois)
        ms = (time.perf_counter() - t0) * 1000.0
        cost[0] += ms
        self.step_ms["stack_align"] = self.step_ms.get("stack_align", 0.0) + ms
        pad = lambda g: cv2.copyMakeBorder(g, 64, 64, 64, 64, cv2.BORDER_REPLICATE)  # noqa: E731
        text = self._run("stack_zxing", None, lambda: _z(pad(stacked)), cost)
        if text:
            return text
        if cfg.deblur:
            lengths = self._blur_lengths(track)
            angle = float(np.arctan2(track.velocity[1], track.velocity[0]))
            for length in lengths:
                def run():
                    out = wiener_motion(stacked, length * 4, angle, cfg.deblur_k / 4)
                    return _z(pad(out))
                text = self._run("stack_wiener", None, run, cost)
                if text:
                    return text
        if cfg.stack_wechat and not cheap_only and (state.attempts % 3 == 0 or not cfg.best_frame):
            text = self._run("stack_wechat", None, lambda: _w(pad(stacked), True), cost)
            if text:
                return text
        return None

    def _modules(self, track, state: _TrackState, cost, cheap_only: bool) -> str | None:
        """H9: dò hình học QR V1 trên ảnh đã xếp chồng, rồi đọc lưới ô + Reed-Solomon.

        Dò đủ góc/tỉ lệ rất tốn nên mỗi lượt chỉ làm vài lần; tìm được rồi thì giữ góc (tem không xoay
        khi băng chạy) và chỉ dò hẹp quanh đó.
        """
        rois = list(state.rois)[-self.cfg.stack_max:]
        if not rois or (state.pose is None and (cheap_only or len(rois) < 2 or state.pose_tries >= 3)):
            return None
        t0 = time.perf_counter()
        unit = 3
        img = stack_rois(rois, scale=unit) if len(rois) > 1 else cv2.resize(
            rois[-1], None, fx=unit, fy=unit, interpolation=cv2.INTER_CUBIC)
        if self.cfg.deblur:
            lengths = self._blur_lengths(track)
            if lengths:
                img = wiener_motion(img, lengths[0] * unit,
                                    float(np.arctan2(track.velocity[1], track.velocity[0])),
                                    self.cfg.deblur_k / max(len(rois), 1) * 2)
        small = cv2.resize(img, (rois[-1].shape[1], rois[-1].shape[0]), interpolation=cv2.INTER_AREA)
        if state.pose is None:
            state.pose_tries += 1
            found = pose_search(small)
        else:
            ppm, angle = state.pose
            found = pose_search(small, (ppm,), range(angle - 4, angle + 5, 4))
        sampled = None
        if found is not None and found[1] >= 0.3:
            sampled = refine_quad(img, found[0] * unit, unit)
            if sampled[1] >= 0.45:
                state.pose = (found[2], found[3])
        ms = (time.perf_counter() - t0) * 1000.0
        cost[0] += ms
        self.step_ms["module_sample"] = self.step_ms.get("module_sample", 0.0) + ms
        if sampled is None or sampled[1] < 0.35:
            return None
        return self._run("module_read", None, lambda: decode_modules(sampled[0]), cost)

    # ── một job ───────────────────────────────────────────────────────────────

    def _eligible(self, idx: int) -> list[Track]:
        out = []
        for t in self.tracker.active:
            if t.observations < 2 or idx - t.last_frame > self.tracker.max_gap:
                continue
            if t.votes >= self.cfg.min_votes:
                continue
            px, py = t.predict(idx)
            h, w = self._shape
            s = t.size
            if s <= 0 or px < s or py < s or px > w - s or py > h - s:
                continue
            out.append(t)
        return out

    def next_gap_frames(self, idx: int, base_n: int) -> int:
        if self.cfg.fast_roi and self._last_eligible:
            return self.cfg.fast_every_n
        return base_n

    _last_eligible: bool = False
    _shape: tuple[int, int] = (0, 0)

    def process(self, frame: np.ndarray, idx: int, now_s: float) -> float:
        """Xử lý một frame; trả về thời gian (ms) job này chiếm."""
        cfg = self.cfg
        self._shape = frame.shape[:2]
        cost = [0.0]
        if cfg.fast_roi and (now_s - self.last_yolo_t) * 1000.0 < cfg.yolo_every_ms:
            eligible = self._eligible(idx)
            if eligible:
                self._fast_job(frame, idx, eligible, cost)
                self._last_eligible = True
                self.jobs["fast"] += 1
                self.total_ms += cost[0]
                return cost[0]
        self._yolo_job(frame, idx, cost)
        self.last_yolo_t = now_s
        self._last_eligible = bool(cfg.fast_roi and self._eligible(idx))
        self.jobs["yolo"] += 1
        self.total_ms += cost[0]
        return cost[0]

    def _fast_job(self, frame, idx, eligible: list[Track], cost: list):
        t0 = time.perf_counter()
        for t in eligible:
            px, py = t.predict(idx)
            half = t.size * 0.5 + max(0.15 * t.size, 0.1 * np.hypot(*t.velocity) * (idx - t.last_frame))
            bbox = np.float32([px - half, py - half, px + half, py + half])
            text = self._attempt(frame, idx, bbox, None, t, cost, cheap_only=True)
            if text:
                t.texts[text] += 1
                self._emit(t, idx, (px, py))
        cost[0] += 0.0 * (time.perf_counter() - t0)

    def _yolo_job(self, frame, idx, cost: list):
        cfg = self.cfg
        dets = self.scene.detect(idx)
        cost[0] += self.scene.detect_ms
        observations = []
        for d in dets:
            x1, y1, x2, y2 = (float(v) for v in d.bbox_xyxy)
            observations.append(Observation(((x1 + x2) / 2, (y1 + y2) / 2), max(x2 - x1, y2 - y1)))
        matched = self.tracker.match(idx, observations)
        h, w = frame.shape[:2]
        for i, det in enumerate(dets):
            track = matched.get(i)
            if track is not None and self._can_skip(track):
                st = self.states.setdefault(track.track_id, _TrackState())
                st.skips += 1
                self.skipped += 1
                continue
            if track is not None:
                self.states.setdefault(track.track_id, _TrackState()).skips = 0
            if cfg.gate and self._gated(det, w, h):
                self.gated += 1
                continue
            text = self._attempt(frame, idx, det.bbox_xyxy, det, track, cost)
            observations[i].text = text
            if text:
                self.sizes.append(observations[i].size)
        finished = self.tracker.update(idx, observations)
        self._close(finished)
        for t in self.tracker.active:
            if t.text and t.track_id not in self.announced:
                self._emit(t, idx, t.center)

    def _can_skip(self, track: Track) -> bool:
        st = self.states.get(track.track_id)
        skips = st.skips if st else 0
        return track.votes >= self.cfg.min_votes and not track.conflicting and skips < 5

    def _gated(self, det, w, h) -> bool:
        x1, y1, x2, y2 = (float(v) for v in det.bbox_xyxy)
        if x1 <= 1 or y1 <= 1 or x2 >= w - 2 or y2 >= h - 2:
            return True
        side_w, side_h = x2 - x1, y2 - y1
        if min(side_w, side_h) <= 0 or max(side_w, side_h) / min(side_w, side_h) > 1.7:
            return True
        if len(self.sizes) >= 3:
            exp = float(np.median(self.sizes))
            size = max(side_w, side_h)
            if size < exp * 0.6 or size > exp * 1.7:
                return True
        return False

    def _emit(self, track: Track, idx: int, center):
        if track.track_id in self.announced:
            return
        self.announced.add(track.track_id)
        self.emitted.append((track.text, idx, float(center[0]), float(center[1]), track.track_id))

    def _close(self, finished: list[Track]):
        for t in finished:
            self.states.pop(t.track_id, None)
            self.all_finished.append(t)

    def finish(self):
        self._close(self.tracker.finish())


class _FixedTracker(PassTracker):
    """H0: cổng cho lượt mới tăng theo thời gian nhưng có trần; khác nội dung thì không ghép."""

    def __init__(self, max_gap: int, max_speed_px: float):
        super().__init__(max_gap=max_gap, max_speed_px=max_speed_px)

    def _pairs(self, tracks, frame_idx, observations):
        candidates = []
        for ti, track in enumerate(tracks):
            px, py = track.predict(frame_idx)
            dt = frame_idx - track.last_frame
            if track.observations > 1:
                gate = self.gate_sizes * max(track.size, 1.0) + 0.25 * np.hypot(*track.velocity) * dt
            else:
                gate = min(self.gate_px + self.max_speed_px * dt, 900.0)
            for oi, obs in enumerate(observations):
                if obs.text and track.text and obs.text != track.text:
                    continue
                d = float(np.hypot(obs.center[0] - px, obs.center[1] - py))
                if d <= gate:
                    candidates.append((d, ti, oi))
        used_t, used_o, pairs = set(), set(), []
        for _, ti, oi in sorted(candidates):
            if ti in used_t or oi in used_o:
                continue
            used_t.add(ti)
            used_o.add(oi)
            pairs.append((ti, oi))
        return pairs


def _z(gray) -> str | None:
    hit = read_zxing_gray(gray)
    return hit[0] if hit else None


def _w(gray, cnn: bool) -> str | None:
    hit = read_wechat_gray(gray, use_cnn=cnn)
    return hit[0] if hit else None


def _warp(frame, det) -> str | None:
    warped = cv2.cvtColor(warp_qr(frame, det, out_size=256), cv2.COLOR_BGR2GRAY)
    hit = read_zxing_gray(add_quiet_zone(warped, pad_px=32))
    return hit[0] if hit else None


__all__ = ["LabConfig", "LabReader", "BASE", "replace"]
