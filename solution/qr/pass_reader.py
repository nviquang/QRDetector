"""PassReader: đọc QR theo lượt trên luồng frame liên tục (băng chuyền).

Mỗi frame: detect một lần → ghép detection vào lượt (PassTracker) → chỉ chạy cascade cho QR chưa
đọc chắc. Cascade (CPU) tốn 200–350 ms cho mỗi detection không đọc được — QR đã có ``min_votes``
lần đọc giống nhau thì dùng lại kết quả của lượt, cứ ``recheck_every`` lần bỏ qua lại đọc kiểm tra
một lần (phòng nhãn bị thay tại chỗ). Mỗi detection kèm một Overlay để UI vẽ quad: góc decoder nếu
đọc được, ngược lại hình chữ nhật xoay của mask; kèm vận tốc lượt để bù độ trễ khi vẽ lên frame mới.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

import numpy as np

from .corrector import display_quad
from .detector import Detection
from .tracker import Observation, PassTracker, Track

logger = logging.getLogger("solution.qr")


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
    texts: list[str | None]          # song song detections: từ cascade, hoặc từ lượt đã đọc chắc
    overlays: list[Overlay]          # song song detections
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
                 min_votes: int = 2, recheck_every: int = 5):
        """
        pipeline:      có ``detect``, ``decode_detection`` và ``warmup`` (ImprovePipeline).
        tracker:       mặc định max_gap=100 theo seq camera (~2 s ở 50 fps) — frame được decode
                       cách nhau cỡ (thời gian decode × fps) seq; max_speed_px=30 px/seq (~1500 px/s ở
                       50 fps, đủ cho 30 cm/s ở 0,25 mm/px) để QR mới vẫn ghép được qua khoảng đó.
        min_votes:     số lần đọc giống nhau để coi lượt là đọc chắc.
        recheck_every: số lần bỏ cascade liên tiếp trước khi đọc kiểm tra lại.
        """
        self._pipeline = pipeline
        self._tracker = tracker if tracker is not None else PassTracker(max_gap=100, max_speed_px=30.0)
        self._min_votes = min_votes
        self._recheck_every = recheck_every
        self._skips: dict[int, int] = {}         # track_id → số lần bỏ cascade liên tiếp
        self._announced: set[int] = set()        # track_id đã báo trong first_reads, lượt còn mở
        self._last_idx: int | None = None
        self._shape: tuple[int, int] | None = None

    def warmup(self):
        self._pipeline.warmup()

    def process(self, image_bgr: np.ndarray, frame_idx: int) -> FrameResult:
        finished: list[Track] = []
        shape = image_bgr.shape[:2]
        if self._last_idx is not None and (frame_idx < self._last_idx or shape != self._shape):
            finished += self._close(self._tracker.finish())   # camera mở lại / đổi ROI
        self._last_idx, self._shape = frame_idx, shape

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
                hit = self._pipeline.decode_detection(image_bgr, det)
                text = hit.text if hit else None
                quad = display_quad(det, hit.corners if hit else None)
                observations[i].text = text
            texts.append(text)
            overlays.append(Overlay(quad, text is not None, velocity, frame_idx, shape))
        t2 = time.perf_counter()
        finished += self._close(self._tracker.update(frame_idx, observations))
        first_reads = [t for t in self._tracker.active if t.text and t.track_id not in self._announced]
        self._announced.update(t.track_id for t in first_reads)
        return FrameResult(detections, texts, overlays, skipped,
                           (t1 - t0) * 1000.0, (t2 - t1) * 1000.0, finished, first_reads)

    def flush(self) -> list[Track]:
        """Đóng mọi lượt đang mở (dừng decode / đóng app)."""
        self._last_idx = self._shape = None
        return self._close(self._tracker.finish())

    def _can_skip(self, track: Track) -> bool:
        return (track.votes >= self._min_votes and not track.conflicting
                and self._skips.get(track.track_id, 0) < self._recheck_every)

    def _close(self, tracks: list[Track]) -> list[Track]:
        for t in tracks:
            self._skips.pop(t.track_id, None)
            self._announced.discard(t.track_id)
            logger.info("pass_finished id=%d text=%s votes=%d observations=%d conflicting=%s",
                        t.track_id, t.text, t.votes, t.observations, t.conflicting)
        return tracks
