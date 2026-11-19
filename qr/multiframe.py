"""Đọc QR bằng nhiều frame của cùng một lượt: khử mờ theo hướng chạy và xếp chồng các ROI đọc hỏng.

``PassDecoder.read`` chạy từ rẻ đến đắt, dừng ở bước đầu tiên đọc được mã đúng định dạng:
  1. ROI × 4 → zxing (ba binarizer)
  2. Warp + Quiet Zone → zxing (chỉ khi có Detection)
  3. WeChat trên từng frame: stretch × 4 CNN, CLAHE × 4, ROI × 3 CNN
  4. Wiener theo vận tốc lượt → zxing
  5. Từ 3 ROI hỏng trở lên: xếp chồng tối đa 8 ảnh → zxing, Wiener → zxing, WeChat CNN

Đo trên Basler ở f/4 (tem phẳng, nét): zxing một mình đọc 84% frame, thêm WeChat từng frame 99%; xếp chồng
+ Wiener giữ được 83–93% ở vệt mờ 3–4 px, lúc đọc từng frame đã tụt mạnh. Xem ``experiments/README.md``.
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field

import cv2
import numpy as np
import zxingcpp

from .content_filter import accept_text, inside, size_ok
from .decoder import read_wechat_gray, read_zxing_gray
from .improved_pipeline import Decoded, _warp_zxing_step
from .preprocessor import UPSCALE_PAD_PER_SCALE, clahe, roi_bounds, stretch_contrast, upscale_gray
from .tracker import Track

logger = logging.getLogger("solution.qr")

STACK_MIN = 3
STACK_MAX = 8
STACK_SCALE = 4
STACK_PAD = 64
WIENER_K = 0.05
_MAX_LOGGED_REJECTS = 200
_WECHAT_STEPS = ((stretch_contrast, 4, True), (clahe, 4, False), (None, 3, True))   # (tiền xử lý, phóng, CNN)


def wiener_motion(gray: np.ndarray, length: float, angle_rad: float, k: float) -> np.ndarray:
    """Khử mờ chuyển động thẳng dài ``length`` px theo hướng ``angle_rad``."""
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
    window = (np.hanning(h)[:, None] ** 0.25) * (np.hanning(w)[None, :] ** 0.25)
    mean = float(g.mean())
    spectrum = np.fft.rfft2((g - mean) * window)
    otf = np.fft.rfft2(pad)
    out = np.fft.irfft2(spectrum * np.conj(otf) / (np.abs(otf) ** 2 + k), s=(h, w)) + mean
    return np.clip(out, 0, 255).astype(np.uint8)


def stack_rois(rois: list[np.ndarray], scale: int = STACK_SCALE) -> np.ndarray:
    """Căn subpixel theo ROI cuối bằng phase correlation, phóng ``scale`` lần, lấy trung bình rồi giãn dải xám."""
    ref = np.float32(rois[-1])
    h, w = ref.shape
    window = cv2.createHanningWindow((w, h), cv2.CV_32F)
    acc = cv2.resize(ref, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    count = 1
    for roi in rois[:-1]:
        moving = np.float32(roi)
        (dx, dy), response = cv2.phaseCorrelate(moving, ref, window)
        if response < 0.05 or abs(dx) > w / 3 or abs(dy) > h / 3:
            continue
        up = cv2.resize(moving, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        shift = np.float32([[1, 0, dx * scale], [0, 1, dy * scale]])
        acc += cv2.warpAffine(up, shift, (up.shape[1], up.shape[0]), flags=cv2.INTER_LINEAR,
                              borderMode=cv2.BORDER_REPLICATE)
        count += 1
    mean = acc / count
    lo, hi = np.percentile(mean, (1, 99))
    return np.clip((mean - lo) * 255.0 / max(hi - lo, 1.0), 0, 255).astype(np.uint8)


def square_roi(image_bgr: np.ndarray, bbox, side: int = 0) -> tuple[np.ndarray, np.ndarray] | None:
    """ROI xám vuông quanh tâm bbox, cùng kích thước qua các frame: (ảnh, gốc x/y). None nếu ra ngoài frame."""
    x1, y1, x2, y2 = (float(v) for v in bbox)
    if not side:
        side = max(96, int(round(max(x2 - x1, y2 - y1) * 1.8 / 16)) * 16)
    ax, ay = int(round((x1 + x2 - side) / 2)), int(round((y1 + y2 - side) / 2))
    h, w = image_bgr.shape[:2]
    if ax < 0 or ay < 0 or ax + side > w or ay + side > h:
        return None
    gray = cv2.cvtColor(image_bgr[ay:ay + side, ax:ax + side], cv2.COLOR_BGR2GRAY)
    return gray, np.array([ax, ay], np.float32)


@dataclass
class _PassState:
    rois: deque = field(default_factory=lambda: deque(maxlen=STACK_MAX))
    origin: np.ndarray | None = None      # gốc của ROI mới nhất, để quy góc về tọa độ frame


class PassDecoder:
    def __init__(self, code_pattern: str | None, roi_margin: float = 0.25, symbol=None):
        """code_pattern: regex nội dung hợp lệ (fullmatch); đọc ra mã khác thì coi như chưa đọc được.
        symbol: (version, mức sửa lỗi) bắt buộc với kết quả zxing; None = nhận mọi loại.
        Mã có tâm nằm ngoài bbox đang đọc (nới ``content_filter.POSITION_MARGIN``) cũng bị loại: đó là tem bên cạnh."""
        self._pattern = code_pattern
        self._symbol = symbol
        self._margin = roi_margin
        self._bbox = None
        self._rejected: set[tuple[str, str]] = set()
        self.states: dict[int, _PassState] = {}

    def forget(self, track_id: int):
        self.states.pop(track_id, None)

    def read(self, image_bgr: np.ndarray, bbox, det, track: Track | None,
             blur_lengths: list[float]) -> Decoded | None:
        """det=None: ROI đoán từ vận tốc lượt. track=None: chỉ đọc frame này, không gom ảnh."""
        self._bbox = bbox
        x1, y1, x2, y2 = roi_bounds(image_bgr.shape, bbox, self._margin)
        roi = image_bgr[y1:y2, x1:x2]
        if roi.size == 0:
            return None
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        origin = np.array([x1, y1], np.float32)
        hit = self._read_single(image_bgr, det, gray, origin)
        if hit is None and track is not None:
            hit = self._read_deblurred(gray, origin, track, blur_lengths)
            if hit is None:
                state = self.states.setdefault(track.track_id, _PassState())
                self._collect(state, image_bgr, bbox)
                if len(state.rois) >= STACK_MIN:
                    hit = self._read_stacked(state, track, blur_lengths)
        return hit

    def _accept(self, hit, to_frame, image=None) -> Decoded | None:
        """image: ảnh decoder vừa đọc, truyền khi decoder không báo version (WeChat) để đếm số ô qua đường timing."""
        if hit is None:
            return None
        text, pts = hit
        corners = to_frame(pts).astype(np.float32)
        if not accept_text(text, self._pattern):
            return self._reject(text, "sai định dạng, kiểm tra code_pattern nếu đây là mã thật")
        if image is not None and not size_ok(image, pts, self._symbol):
            return self._reject(text, "số ô không khớp version mong đợi")
        if not inside(corners, self._bbox):
            return self._reject(text, "tâm mã nằm ngoài vùng đang đọc (tem bên cạnh)")
        return Decoded(text, corners)

    def _reject(self, text: str, reason: str) -> None:
        if (text, reason) not in self._rejected and len(self._rejected) < _MAX_LOGGED_REJECTS:
            self._rejected.add((text, reason))
            logger.warning("code_rejected text=%r reason=%s", text, reason)
        return None

    def _read_single(self, image_bgr, det, gray, origin) -> Decoded | None:
        up = upscale_gray(gray, 4)
        pad = UPSCALE_PAD_PER_SCALE * 4
        to_frame = lambda pts: (pts - pad) / 4 + origin  # noqa: E731
        for binarizer in (None, zxingcpp.Binarizer.GlobalHistogram, zxingcpp.Binarizer.FixedThreshold):
            hit = self._accept(read_zxing_gray(up, binarizer, self._symbol), to_frame)
            if hit:
                return hit
        if det is not None:
            warped = _warp_zxing_step(image_bgr, det, gray, origin, self._symbol)
            if warped is not None:
                hit = self._accept((warped.text, warped.corners), lambda pts: pts)
                if hit:
                    return hit
        for preprocess, scale, cnn in _WECHAT_STEPS:
            source = gray if preprocess is None else preprocess(gray)
            pad = UPSCALE_PAD_PER_SCALE * scale
            up = upscale_gray(source, scale)
            hit = self._accept(read_wechat_gray(up, use_cnn=cnn), lambda pts: (pts - pad) / scale + origin, up)
            if hit:
                return hit
        return None

    def _read_deblurred(self, gray, origin, track, blur_lengths) -> Decoded | None:
        if not blur_lengths:
            return None
        angle = float(np.arctan2(track.velocity[1], track.velocity[0]))
        up = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        pad = UPSCALE_PAD_PER_SCALE * 2
        to_frame = lambda pts: (pts - pad) / 4 + origin  # noqa: E731
        for length in blur_lengths:
            out = wiener_motion(up, length * 2, angle, WIENER_K)
            hit = self._accept(read_zxing_gray(upscale_gray(out, 2), symbol=self._symbol), to_frame)
            if hit:
                return hit
        return None

    @staticmethod
    def _collect(state: _PassState, image_bgr, bbox):
        side = state.rois[-1].shape[0] if state.rois else 0
        got = square_roi(image_bgr, bbox, side)
        if got is not None:
            state.rois.append(got[0])
            state.origin = got[1]

    def _read_stacked(self, state: _PassState, track, blur_lengths) -> Decoded | None:
        stacked = stack_rois(list(state.rois))
        origin = state.origin
        to_frame = lambda pts: (pts - STACK_PAD) / STACK_SCALE + origin  # noqa: E731
        pad = lambda g: cv2.copyMakeBorder(g, STACK_PAD, STACK_PAD, STACK_PAD, STACK_PAD,  # noqa: E731
                                           cv2.BORDER_REPLICATE)
        hit = self._accept(read_zxing_gray(pad(stacked), symbol=self._symbol), to_frame)
        if hit:
            return hit
        if blur_lengths:
            angle = float(np.arctan2(track.velocity[1], track.velocity[0]))
            for length in blur_lengths:
                out = wiener_motion(stacked, length * STACK_SCALE, angle, WIENER_K / STACK_SCALE)
                hit = self._accept(read_zxing_gray(pad(out), symbol=self._symbol), to_frame)
                if hit:
                    return hit
        padded = pad(stacked)
        return self._accept(read_wechat_gray(padded, use_cnn=True), to_frame, padded)
