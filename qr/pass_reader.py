"""PassReader: đọc QR theo lượt trên luồng frame liên tục (băng chuyền).

Mỗi frame: detect một lần → ghép detection vào lượt (PassTracker) → chỉ chạy cascade cho QR chưa
đọc chắc. Cascade (CPU) tốn 200–350 ms cho mỗi detection không đọc được — QR đã có ``min_votes``
lần đọc giống nhau thì dùng lại kết quả của lượt, cứ ``recheck_every`` lần bỏ qua lại đọc kiểm tra
một lần (phòng nhãn bị thay tại chỗ). Mỗi detection kèm một Overlay để UI vẽ quad: góc decoder nếu
đọc được, ngược lại hình chữ nhật xoay của mask; kèm vận tốc lượt để bù độ trễ khi vẽ lên frame mới.

Pipeline có ``multi_frame=True`` (ImprovePipeline mặc định) thì đọc bằng PassDecoder thay cascade từng
frame: YOLO tối đa mỗi 400 ms, xen giữa là job đoán vị trí lượt chưa đọc được từ vận tốc (không detect,
không WeChat, nhịp 2 frame); bỏ QR chạm mép hoặc bị méo.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

import numpy as np

from .corrector import display_quad
from .detector import Detection
from .multiframe import PassDecoder
from .tracker import Observation, PassTracker, Track

logger = logging.getLogger("solution.qr")

YOLO_EVERY_S = 0.4          # giữa hai lần YOLO chạy job đoán vị trí nếu có lượt chưa đọc được
FAST_EVERY_N = 2            # nhịp gửi frame khi có lượt chờ đọc
UNKNOWN_EXPOSURE_BLUR_PX = [2.0, 3.0, 4.5, 6.5]
MIN_BLUR_PX = 1.5


@dataclass
class Overlay:
    quad_xy: np.ndarray                  # (4, 2) tọa độ trong frame ``seq``
    ok: bool                             # có nội dung (đọc được hoặc lấy từ lượt đã đọc chắc)
    velocity: tuple[float, float]        # px / seq của lượt (0 nếu QR mới)
    seq: int
    shape: tuple[int, int]

    def at(self, seq: int, shape: tuple[int, int], max_age: int) -> np.ndarray | None:
        """Quad dịch theo vận tốc tới frame ``seq``; None nếu khác kích thước frame, seq lùi hoặc quá cũ."""
        age = seq - self.seq
        if shape != self.shape or age < 0 or age > max_age:
            return None
        return self.quad_xy + np.array(self.velocity, np.float32) * age


@dataclass
class FrameResult:
    detections: list[Detection]
    texts: list[str | None]          # song song detections: từ cascade, hoặc từ lượt đã đọc chắc;
                                     # job đoán vị trí (detections rỗng): các mã vừa đọc được
    overlays: list[Overlay]          # song song detections; job đoán vị trí: giữ của lần YOLO trước
    skipped: int                     # số detection bỏ cascade nhờ lượt đã đọc chắc
    detect_ms: float
    cascade_ms: float
    finished: list[Track] = field(default_factory=list)   # lượt vừa kết thúc
    first_reads: list[Track] = field(default_factory=list)   # lượt vừa có nội dung lần đầu

    @property
    def results(self) -> list[str]:
        return [t for t in self.texts if t]


def _observation(det: Detection) -> Observation:
    x1, y1, x2, y2 = (float(v) for v in det.bbox_xyxy)
    return Observation(((x1 + x2) / 2, (y1 + y2) / 2), max(x2 - x1, y2 - y1))


class PassReader:
    def __init__(self, pipeline, tracker: PassTracker | None = None,
                 min_votes: int | None = None, recheck_every: int = 5, clock=time.monotonic,
                 announce_votes: int = 1):
        """
        pipeline:      có ``detect``, ``decode_detection`` và ``warmup`` (ImprovePipeline).
        tracker:       mặc định max_gap=100 theo seq camera (~2 s ở 50 fps) — frame được decode
                       cách nhau cỡ (thời gian decode × fps) seq; max_speed_px=30 px/seq (~1500 px/s ở
                       50 fps, đủ cho 30 cm/s ở 0,25 mm/px) để QR mới vẫn ghép được qua khoảng đó.
        min_votes:     số lần đọc giống nhau để coi lượt là đọc chắc; mặc định 1 khi có lọc định dạng
                       của chế độ nhiều frame, 2 khi không.
        recheck_every: số lần bỏ cascade liên tiếp trước khi đọc kiểm tra lại.
        clock:         nguồn thời gian (giây), test truyền đồng hồ giả.
        announce_votes: số lần đọc giống nhau trước khi báo trong first_reads.
        """
        self._pipeline = pipeline
        multi_frame = getattr(pipeline, "multi_frame", False) is True
        self._decoder = PassDecoder(pipeline.code_pattern, pipeline.roi_margin) if multi_frame else None
        self._tracker = tracker if tracker is not None else PassTracker(
            max_gap=100, max_speed_px=30.0, strict=multi_frame)
        self._min_votes = min_votes if min_votes is not None else (1 if multi_frame else 2)
        self._clock = clock
        self._exposure_ms: float | None = None
        self._seq_rate: float | None = None      # seq / giây, đo từ các frame được gửi
        self._last_seen: tuple[int, float] | None = None
        self._last_yolo_t = float("-inf")
        self._last_overlays: list[Overlay] = []
        self._announce_votes = announce_votes
        self._awaiting_read = False
        self._recheck_every = recheck_every
        self._skips: dict[int, int] = {}         # track_id → số lần bỏ cascade liên tiếp
        self._announced: set[int] = set()        # track_id đã báo trong first_reads, lượt còn mở
        self._last_idx: int | None = None
        self._shape: tuple[int, int] | None = None

    def warmup(self):
        self._pipeline.warmup()

    def set_exposure_ms(self, exposure_ms: float | None):
        """Exposure hiện tại của camera, để tính độ dài vệt mờ. None = chưa biết."""
        self._exposure_ms = exposure_ms

    def decode_every(self, default_n: int) -> int:
        """Số frame nên chờ giữa hai lần gửi decode; đọc được từ thread khác."""
        return min(default_n, FAST_EVERY_N) if self._awaiting_read else default_n

    def process(self, image_bgr: np.ndarray, frame_idx: int) -> FrameResult:
        finished: list[Track] = []
        shape = image_bgr.shape[:2]
        if self._last_idx is not None and (frame_idx < self._last_idx or shape != self._shape):
            finished += self._close(self._tracker.finish())   # camera mở lại / đổi ROI
            self._last_seen = None
        self._last_idx, self._shape = frame_idx, shape

        if self._decoder is not None:
            now = self._clock()
            self._measure_seq_rate(frame_idx, now)
            if now - self._last_yolo_t < YOLO_EVERY_S:
                waiting = self._waiting_tracks(frame_idx)
                if waiting:
                    return self._fast_job(image_bgr, frame_idx, waiting, finished)
            self._last_yolo_t = now

        t0 = time.perf_counter()
        detections = self._pipeline.detect(image_bgr)
        t1 = time.perf_counter()
        observations = [_observation(d) for d in detections]
        matched = self._tracker.match(frame_idx, observations)
        texts: list[str | None] = []
        overlays: list[Overlay] = []
        skipped = 0
        for i, det in enumerate(detections):
            track = matched.get(i)
            velocity = track.velocity if track is not None else (0.0, 0.0)
            if track is not None and self._can_skip(track):
                self._skips[track.track_id] = self._skips.get(track.track_id, 0) + 1
                text, quad = track.text, display_quad(det)
                skipped += 1
            else:
                if track is not None:
                    self._skips[track.track_id] = 0
                hit = self._decode(image_bgr, det, track)
                text = hit.text if hit else None
                quad = display_quad(det, hit.corners if hit else None)
                observations[i].text = text
            texts.append(text)
            overlays.append(Overlay(quad, text is not None, velocity, frame_idx, shape))
        t2 = time.perf_counter()
        finished += self._close(self._tracker.update(frame_idx, observations))
        first_reads = self._new_reads()
        self._last_overlays = overlays
        self._awaiting_read = self._decoder is not None and bool(self._waiting_tracks(frame_idx))
        return FrameResult(detections, texts, overlays, skipped,
                           (t1 - t0) * 1000.0, (t2 - t1) * 1000.0, finished, first_reads)

    def flush(self) -> list[Track]:
        """Đóng mọi lượt đang mở (dừng decode / đóng app)."""
        self._last_idx = self._shape = self._last_seen = None
        self._last_yolo_t = float("-inf")
        self._last_overlays = []
        self._awaiting_read = False
        return self._close(self._tracker.finish())

    def _new_reads(self) -> list[Track]:
        reads = [t for t in self._tracker.active
                 if t.text and t.votes >= self._announce_votes and t.track_id not in self._announced]
        self._announced.update(t.track_id for t in reads)
        return reads

    def _decode(self, image_bgr: np.ndarray, det: Detection, track: Track | None):
        if self._decoder is None:
            return self._pipeline.decode_detection(image_bgr, det)
        if self._gated(det):
            return None
        blur = self._blur_lengths(track) if track is not None else []
        return self._decoder.read(image_bgr, det.bbox_xyxy, det, track, blur)

    def _gated(self, det: Detection) -> bool:
        """QR chạm mép hoặc bị méo: khó đọc được, không đáng tốn cascade. Không xét cỡ: tem dài ngắn khác nhau."""
        h, w = self._shape
        x1, y1, x2, y2 = (float(v) for v in det.bbox_xyxy)
        if x1 <= 1 or y1 <= 1 or x2 >= w - 2 or y2 >= h - 2:
            return True
        side_w, side_h = x2 - x1, y2 - y1
        return min(side_w, side_h) <= 0 or max(side_w, side_h) / min(side_w, side_h) > 1.7

    def _measure_seq_rate(self, frame_idx: int, now: float):
        if self._last_seen is not None:
            seq, t = self._last_seen
            if frame_idx > seq and now > t:
                rate = (frame_idx - seq) / (now - t)
                self._seq_rate = rate if self._seq_rate is None else 0.8 * self._seq_rate + 0.2 * rate
        self._last_seen = (frame_idx, now)

    def _blur_lengths(self, track: Track) -> list[float]:
        speed = float(np.hypot(*track.velocity))
        if speed < 0.05:
            return []
        if self._exposure_ms is None or self._seq_rate is None:
            return list(UNKNOWN_EXPOSURE_BLUR_PX)
        length = speed * self._seq_rate * self._exposure_ms / 1000.0
        return [length, length * 1.3] if length >= MIN_BLUR_PX else []

    def _waiting_tracks(self, frame_idx: int) -> list[Track]:
        """Lượt đang chạy, chưa đọc chắc, vị trí dự đoán còn trong frame."""
        h, w = self._shape
        waiting = []
        for t in self._tracker.active:
            if t.observations < 2 or frame_idx - t.last_frame > self._tracker.max_gap or t.votes >= self._min_votes:
                continue
            px, py = t.predict(frame_idx)
            if t.size > 0 and t.size <= px <= w - t.size and t.size <= py <= h - t.size:
                waiting.append(t)
        return waiting

    def _fast_job(self, image_bgr, frame_idx, waiting: list[Track], finished: list[Track]) -> FrameResult:
        t0 = time.perf_counter()
        texts = []
        for t in waiting:
            px, py = t.predict(frame_idx)
            drift = 0.1 * float(np.hypot(*t.velocity)) * (frame_idx - t.last_frame)
            half = t.size * 0.5 + max(0.15 * t.size, drift)
            bbox = np.array([px - half, py - half, px + half, py + half], np.float32)
            hit = self._decoder.read(image_bgr, bbox, None, t, self._blur_lengths(t), cheap_only=True)
            if hit:
                t.texts[hit.text] += 1
                texts.append(hit.text)
        self._awaiting_read = bool(self._waiting_tracks(frame_idx))
        return FrameResult([], texts, self._last_overlays, 0, 0.0, (time.perf_counter() - t0) * 1000.0,
                           finished, self._new_reads())

    def _can_skip(self, track: Track) -> bool:
        return (track.votes >= self._min_votes and not track.conflicting
                and self._skips.get(track.track_id, 0) < self._recheck_every)

    def _close(self, tracks: list[Track]) -> list[Track]:
        for t in tracks:
            self._skips.pop(t.track_id, None)
            self._announced.discard(t.track_id)
            if self._decoder is not None:
                self._decoder.forget(t.track_id)
            logger.info("pass_finished id=%d text=%s votes=%d observations=%d conflicting=%s",
                        t.track_id, t.text, t.votes, t.observations, t.conflicting)
        return tracks
