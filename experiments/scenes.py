"""Nguồn frame cho thử nghiệm: băng chuyền mô phỏng (biết đáp án) và video thật.

Cả hai có cùng giao diện: ``frame(idx)``, ``detect(idx)`` (nhớ kết quả YOLO để mọi cấu hình nhận cùng
detection và chỉ tính ``detect_ms`` cố định), ``fps``, ``n_frames``, ``key``, ``passes``.
"""

from __future__ import annotations

import os
import pickle
import statistics
import time
from dataclasses import dataclass

import cv2
import numpy as np
import zxingcpp

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out", "cache")


@dataclass
class GtPass:
    text: str | None
    first: int
    last: int
    x: np.ndarray | None = None   # (frame, cx, cy) theo thời gian với video thật


class _DetectCache:
    def __init__(self, key: str, detector):
        self.key, self._detector = key, detector
        os.makedirs(CACHE_DIR, exist_ok=True)
        self._path = os.path.join(CACHE_DIR, f"det_{key}.pkl")
        self._dets, self._times, self._dirty = {}, [], 0
        if os.path.exists(self._path):
            with open(self._path, "rb") as f:
                self._dets, self._times = pickle.load(f)

    def get(self, idx: int, frame_fn):
        if idx not in self._dets:
            frame = frame_fn(idx)
            t0 = time.perf_counter()
            try:
                self._dets[idx] = self._detector.detect(frame)
            except MemoryError:  # qrdet crop_qr gặp mask suy biến: coi như frame không có QR, xem báo cáo
                print("detect_memerror", self.key, idx, flush=True)
                self._dets[idx] = []
            self._times.append((time.perf_counter() - t0) * 1000.0)
            self._dirty += 1
            if self._dirty >= 200:
                self.save()
        return self._dets[idx]

    def save(self):
        if self._dirty:
            with open(self._path, "wb") as f:
                pickle.dump((self._dets, self._times), f)
            self._dirty = 0

    @property
    def detect_ms(self) -> float:
        # Bỏ vài lần đầu (nạp kernel) khi đã đủ mẫu
        times = self._times[5:] if len(self._times) > 10 else self._times
        return statistics.median(times) if times else 0.0


@dataclass(frozen=True)
class SimParams:
    name: str
    speed_mm_s: float
    exposure_ms: float
    contrast: tuple[int, int]     # (giá trị ô đen, giá trị nhãn trắng)
    noise: float
    seed: int = 1
    n_passes: int = 40
    fps: float = 50.0
    mm_per_px: float = 0.43
    qr_mm: float = 25.0
    width: int = 2448
    height: int = 768
    sigma: float = 0.7            # mềm quang học (px)
    pitch_mm: tuple[int, int] = (350, 800)
    belt: int = 70                # độ sáng nền băng khi nhãn trắng = 255
    noise_blur: float = 0.0       # >0: nhiễu tương quan không gian (giống sau demosaic)
    speed_jitter: float = 0.0     # >0: tốc độ băng dao động ± tỉ lệ này

    @property
    def blur_px(self) -> float:
        return self.speed_mm_s * self.exposure_ms * 1e-3 / self.mm_per_px

    @property
    def speed_px_frame(self) -> float:
        return self.speed_mm_s / self.mm_per_px / self.fps


_R = 6     # số điểm độ phân giải cao trên một pixel sensor


class _SimLabel:
    def __init__(self, text: str, p: SimParams, angle: float, cy: float, start_x_mm: float):
        self.text, self.cy = text, cy
        self.start_px = start_x_mm / p.mm_per_px
        modules = np.array(zxingcpp.create_barcode(text, zxingcpp.BarcodeFormat.QRCode, ec_level="M")
                           .to_image(scale=1, add_quiet_zones=False))
        n = modules.shape[0]
        ppm = p.qr_mm / p.mm_per_px / n
        scale = _R * ppm
        qr_side = int(round(n * scale))
        big = cv2.resize(modules, (qr_side, qr_side), interpolation=cv2.INTER_NEAREST).astype(np.float32)
        quiet = int(round(4 * scale))
        big = cv2.copyMakeBorder(big, quiet, quiet, quiet, quiet, cv2.BORDER_CONSTANT, value=255)
        # Tem thật có dòng chữ in cạnh QR: thêm một cột "chữ" bên trái để không dễ hơn thực tế
        text_w = int(round(20 * scale))
        block = np.full((big.shape[0], text_w), 255, np.float32)
        tr = np.random.default_rng(int(text[-6:]))
        row_h = int(round(1.2 * scale))
        y = quiet
        while y + row_h < big.shape[0] - quiet:
            x, end = int(round(2 * scale)), int(text_w * tr.uniform(0.5, 1.0))
            while x < end:
                w = int(tr.uniform(0.4, 1.6) * scale)
                block[y:y + row_h, x:x + w] = 40
                x += w + int(tr.uniform(0.3, 0.8) * scale)
            y += row_h * 3
        big = np.hstack([block, big])
        side = big.shape[1]
        pad_v = side - big.shape[0]
        big = cv2.copyMakeBorder(big, pad_v // 2, pad_v - pad_v // 2, 0, 0, cv2.BORDER_CONSTANT, value=p.belt)
        out_px = int(np.ceil(big.shape[0] * 1.45 / _R)) + 2 + int(np.ceil(p.blur_px))
        canvas = out_px * _R
        off = (canvas - big.shape[0]) // 2
        big = cv2.copyMakeBorder(big, off, canvas - big.shape[0] - off, off, canvas - big.shape[0] - off,
                                 cv2.BORDER_CONSTANT, value=p.belt)
        rot = cv2.getRotationMatrix2D((canvas / 2, canvas / 2), angle, 1.0)
        big = cv2.warpAffine(big, rot, (canvas, canvas), flags=cv2.INTER_LINEAR, borderValue=p.belt)
        length = int(round(p.blur_px * _R))
        if length > 1:
            big = cv2.filter2D(big, -1, np.ones((1, length), np.float32) / length,
                               borderType=cv2.BORDER_REPLICATE)
        self.big = big
        self.out_px = out_px

    def sprite(self, frac_x: float, frac_y: float) -> np.ndarray:
        """Thu nhỏ có lệch subpixel; kết quả (out_px - 1)² pixel."""
        dx, dy = int(frac_x * _R), int(frac_y * _R)
        side = (self.out_px - 1) * _R
        crop = self.big[dy:dy + side, dx:dx + side]
        return cv2.resize(crop, (self.out_px - 1, self.out_px - 1), interpolation=cv2.INTER_AREA)


class SimScene:
    """Băng chuyền chạy theo trục x với các nhãn QR 25 mm, mỗi nhãn một mã 12 chữ số khác nhau."""

    kind = "sim"

    def __init__(self, params: SimParams, detector):
        self.p = params
        self.fps = params.fps
        self.exposure_ms: float | None = params.exposure_ms
        self.key = (f"{params.name}_s{params.seed}_n{params.n_passes}_v{params.speed_mm_s:g}"
                    f"_e{params.exposure_ms:g}_c{params.contrast[0]}-{params.contrast[1]}_g{params.noise:g}"
                    f"_h{params.height}_nb{params.noise_blur:g}_j{params.speed_jitter:g}")
        rng = np.random.default_rng(params.seed)
        self.labels: list[_SimLabel] = []
        self.passes: list[GtPass] = []
        x_mm = -60.0
        margin = 80
        for i in range(params.n_passes):
            text = f"{585000 + params.seed * 1000 + i:012d}"
            cy = float(rng.uniform(margin, params.height - margin))
            label = _SimLabel(text, params, float(rng.uniform(-180, 180)), cy, -x_mm)
            self.labels.append(label)
            first = int((label.start_px - margin) / params.speed_px_frame)
            last = int((label.start_px + params.width + margin) / params.speed_px_frame)
            self.passes.append(GtPass(text, max(0, first), last))
            x_mm -= float(rng.uniform(*params.pitch_mm))
        self.n_frames = self.passes[-1].last + 1
        belt_rng = np.random.default_rng(params.seed + 7)
        tex = belt_rng.normal(0, 6, (params.height // 8, params.width // 8)).astype(np.float32)
        tex = cv2.resize(tex, (params.width, params.height), interpolation=cv2.INTER_CUBIC)
        self._bg = params.belt + tex
        self.codes = {p.text for p in self.passes}
        self._cache = _DetectCache(self.key, detector)
        self._last: tuple[int, np.ndarray] | None = None

    def center(self, label: _SimLabel, idx: int) -> tuple[float, float]:
        x = idx * self.p.speed_px_frame
        if self.p.speed_jitter:
            period = self.p.fps * 1.3
            amp = self.p.speed_jitter * self.p.speed_px_frame * period / (2 * np.pi)
            x += amp * np.sin(2 * np.pi * idx / period)
        return (x - label.start_px, label.cy)

    def frame(self, idx: int) -> np.ndarray:
        if self._last is not None and self._last[0] == idx:
            return self._last[1]
        p = self.p
        img = self._bg.copy()
        for label in self.labels:
            cx, cy = self.center(label, idx)
            half = label.out_px
            if cx < -half or cx > p.width + half:
                continue
            ix, iy = int(np.floor(cx)), int(np.floor(cy))
            spr = label.sprite(cx - ix, cy - iy)
            s = spr.shape[0]
            x0, y0 = ix - s // 2, iy - s // 2
            x1, y1 = max(0, x0), max(0, y0)
            x2, y2 = min(p.width, x0 + s), min(p.height, y0 + s)
            if x2 > x1 and y2 > y1:
                img[y1:y2, x1:x2] = spr[y1 - y0:y2 - y0, x1 - x0:x2 - x0]
        if p.sigma > 0:
            img = cv2.GaussianBlur(img, (0, 0), p.sigma)
        lo, hi = p.contrast
        rng = np.random.default_rng(p.seed * 1_000_003 + idx)
        img = lo + img * ((hi - lo) / 255.0)
        # Nhiễu đọc + nhiễu lượng tử (tỉ lệ căn bậc hai độ sáng), chuẩn hóa để tại nhãn trắng đúng p.noise
        sigma = p.noise * np.sqrt(0.5 + 0.5 * np.clip(img, 0, None) / max(hi, 1))
        n = rng.standard_normal(img.shape, dtype=np.float32)
        if p.noise_blur:
            n = cv2.GaussianBlur(n, (0, 0), p.noise_blur)
            n /= max(float(n.std()), 1e-6)
        img = img + n * sigma
        gray = np.clip(img, 0, 255).astype(np.uint8)
        out = np.ascontiguousarray(cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR))
        self._last = (idx, out)
        return out

    def detect(self, idx: int):
        return self._cache.get(idx, self.frame)

    @property
    def detect_ms(self) -> float:
        return 150.0   # đo riêng GTX 1650, dải 2448×768; cố định để chạy song song không làm sai lệch

    def save(self):
        self._cache.save()


class VideoScene:
    """Video thật. Đáp án lượt lấy bằng cách detect MỌI frame rồi ghép chặt (xem ``oracle_passes``)."""

    kind = "video"

    def __init__(self, path: str, detector, name: str | None = None):
        self.path = path
        self.key = name or os.path.splitext(os.path.basename(path))[0]
        cap = cv2.VideoCapture(path)
        self.fps = cap.get(cv2.CAP_PROP_FPS) or 15.0
        self.n_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        cap.release()
        self.exposure_ms = None
        self._cap = None
        self._next = 0
        self._last: tuple[int, np.ndarray] | None = None
        self._cache = _DetectCache(self.key, detector)
        self.passes: list[GtPass] = []
        self.codes: set[str] = set()

    def frame(self, idx: int) -> np.ndarray:
        if self._last is not None and self._last[0] == idx:
            return self._last[1]
        if self._cap is None or idx < self._next:
            if self._cap is not None:
                self._cap.release()
            self._cap = cv2.VideoCapture(self.path)
            self._next = 0
        while self._next < idx:
            self._cap.grab()
            self._next += 1
        ok, frame = self._cap.read()
        self._next += 1
        if not ok:
            raise IndexError(idx)
        frame = np.ascontiguousarray(frame)
        self._last = (idx, frame)
        return frame

    def detect(self, idx: int):
        return self._cache.get(idx, self.frame)

    @property
    def detect_ms(self) -> float:
        return 200.0   # đo riêng GTX 1650, toàn khung 2448×2048; cố định để so sánh công bằng

    def save(self):
        self._cache.save()

    def build_oracle(self, min_obs: int = 4):
        """Detect mọi frame, ghép chặt theo khoảng cách để biết QR nào đi qua khi nào."""
        tracks: list[dict] = []
        for idx in range(self.n_frames):
            used = set()
            for det in self.detect(idx):
                x1, y1, x2, y2 = det.bbox_xyxy
                c = ((x1 + x2) / 2, (y1 + y2) / 2)
                size = max(x2 - x1, y2 - y1)
                best, best_d = None, 1e9
                for i, t in enumerate(tracks):
                    if i in used or idx - t["last"] > 6:
                        continue
                    d = np.hypot(c[0] - t["c"][0], c[1] - t["c"][1])
                    if d < max(3 * size, 40 * (idx - t["last"])) and d < best_d:
                        best, best_d = i, d
                if best is None:
                    tracks.append(dict(first=idx, last=idx, c=c, path=[(idx, *c)], obs=1))
                    used.add(len(tracks) - 1)
                else:
                    t = tracks[best]
                    t.update(last=idx, c=c, obs=t["obs"] + 1)
                    t["path"].append((idx, *c))
                    used.add(best)
        self.save()
        self.passes = [GtPass(None, t["first"], t["last"], np.array(t["path"], np.float32))
                       for t in tracks if t["obs"] >= min_obs]


class SemiScene:
    """Bán thực: ảnh BMP KHÔNG NÉN từ camera thật (tem, in, quang học, góc đặt thật), trượt trên băng ảo.

    Chuyển động, vệt mờ, độ tối và nhiễu là mô phỏng theo cùng điều kiện với SimScene; mỗi ảnh đi qua
    ``repeats`` lượt với lệch subpixel khác nhau. Đáp án là mã đọc được trên ảnh gốc sáng, nguyên vẹn.
    """

    kind = "semi"

    def __init__(self, name: str, image_paths: list[str], detector, seed: int, repeats: int, reader, **cond):
        self.p = SimParams(name=name, seed=seed, n_passes=1, noise_blur=0.7, **cond)
        self.fps = self.p.fps
        self.exposure_ms = self.p.exposure_ms
        self.key = (f"semi_{name}_s{seed}_r{repeats}_v{self.p.speed_mm_s:g}_e{self.p.exposure_ms:g}"
                    f"_c{self.p.contrast[0]}-{self.p.contrast[1]}_g{self.p.noise:g}")
        self.items, self.passes, self.codes = [], [], set()
        h = self.p.height
        for path in image_paths:
            img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
            if img is None:
                continue
            bgr = np.ascontiguousarray(cv2.cvtColor(img, cv2.COLOR_GRAY2BGR))
            for det in detector.detect(bgr):
                text = reader(bgr, det)
                if not text:
                    continue
                x1, y1, x2, y2 = (float(v) for v in det.bbox_xyxy)
                cy, side = (y1 + y2) / 2, max(x2 - x1, y2 - y1)
                y0 = int(np.clip(cy - h / 2, 0, img.shape[0] - h))
                band = np.float32(img[y0:y0 + h])
                r = int(side)
                patch = img[max(0, int(cy) - r):int(cy) + r, max(0, int(x1) - r // 2):int(x2) + r // 2]
                white = max(float(np.percentile(patch, 97)), 30.0)
                self.items.append(dict(band=band, text=text, qx=(x1 + x2) / 2, white=white))
                self.codes.add(text)
        rng = np.random.default_rng(seed)
        order = [i for _ in range(repeats) for i in rng.permutation(len(self.items))]
        speed = self.p.speed_px_frame
        travel = self.p.width - 200.0
        duration = int(travel / speed)
        gap = int(2.2 * self.fps) + 5
        self._schedule = []
        idx = 0
        for i in order:
            first, last = idx, idx + duration
            self._schedule.append((first, last, i, float(rng.uniform(0, 1))))
            self.passes.append(GtPass(self.items[i]["text"], first, last))
            idx = last + gap
        self.n_frames = idx
        self._cache = _DetectCache(self.key, detector)
        self._last = None
        self._black = None

    def _item_at(self, idx: int):
        for first, last, i, frac in self._schedule:
            if first <= idx <= last:
                return first, i, frac
        return None

    def frame(self, idx: int) -> np.ndarray:
        if self._last is not None and self._last[0] == idx:
            return self._last[1]
        p = self.p
        hit = self._item_at(idx)
        if hit is None:
            img = np.full((p.height, p.width), p.belt * 0.3, np.float32)
        else:
            first, i, frac = hit
            item = self.items[i]
            target_x = 100.0 + (idx - first) * p.speed_px_frame + frac
            dx = target_x - item["qx"]
            M = np.float32([[1, 0, dx], [0, 1, 0]])
            img = cv2.warpAffine(item["band"], M, (p.width, p.height), flags=cv2.INTER_LINEAR,
                                 borderMode=cv2.BORDER_CONSTANT, borderValue=float(np.percentile(item["band"], 5)))
            length = p.blur_px
            if length > 1.0:
                n = int(np.ceil(length))
                kernel = np.ones((1, n), np.float32)
                kernel[0, -1] = length - (n - 1)
                kernel /= kernel.sum()
                img = cv2.filter2D(img, -1, kernel, borderType=cv2.BORDER_REPLICATE)
            img = img * 255.0 / item["white"]
        lo, hi = p.contrast
        img = lo + np.clip(img, 0, 255) * ((hi - lo) / 255.0)
        rng = np.random.default_rng(p.seed * 1_000_003 + idx)
        sigma = p.noise * np.sqrt(0.5 + 0.5 * np.clip(img, 0, None) / max(hi, 1))
        n = cv2.GaussianBlur(rng.standard_normal(img.shape, dtype=np.float32), (0, 0), p.noise_blur)
        n /= max(float(n.std()), 1e-6)
        gray = np.clip(img + n * sigma, 0, 255).astype(np.uint8)
        out = np.ascontiguousarray(cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR))
        self._last = (idx, out)
        return out

    def detect(self, idx: int):
        return self._cache.get(idx, self.frame)

    @property
    def detect_ms(self) -> float:
        return 150.0

    def save(self):
        self._cache.save()
