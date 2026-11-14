"""PassReader: đọc QR theo lượt trên luồng frame liên tục (băng chuyền).

Mỗi frame: detect một lần → ghép detection vào lượt (PassTracker) → chỉ chạy cascade cho QR chưa
đọc chắc. Cascade (CPU) tốn 200–350 ms cho mỗi detection không đọc được — QR đã có ``min_votes``
lần đọc giống nhau thì dùng lại kết quả của lượt, cứ ``recheck_every`` lần bỏ qua lại đọc kiểm tra
một lần (phòng nhãn bị thay tại chỗ). Mỗi detection kèm một Overlay để UI vẽ quad: góc decoder nếu
đọc được, ngược lại hình chữ nhật xoay của mask; kèm vận tốc lượt để bù độ trễ khi vẽ lên frame mới.

Pipeline có ``multi_frame=True`` (ImprovePipeline mặc định) thì đọc bằng PassDecoder thay cascade từng
frame: YOLO tối đa mỗi 400 ms, xen giữa là job đoán vị trí lượt chưa đọc chắc từ vận tốc (không detect,
nhịp 2 frame); bỏ QR chạm mép hoặc bị méo; 2 lần đọc giống nhau mới báo mã, lượt kết thúc với 1 lần đọc thì
coi như không đọc được (log ``pass_unconfirmed``) vì tem không có định dạng cố định để lọc đọc sai.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

import numpy as np

from . import pass_fallback
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
    fallback: list[FallbackStatus] | None = None   # lượt đang chờ đọc nền; None = không đổi từ lần trước

    @property
    def results(self) -> list[str]:
        return [t for t in self.texts if t]


STAGE_QUEUED = "queued"


@dataclass
class FallbackStatus:
    track_id: int
    stage: str          # STAGE_QUEUED, "B", "C" (ComboBC) hoặc pass_fallback.STAGE_SOLVING
    since: float        # time.monotonic() lúc vào hàng đợi / vào giai đoạn
    position: int       # thứ tự trong hàng đợi (1 = kế tiếp); 0 khi đang giải


def _observation(det: Detection) -> Observation:
    x1, y1, x2, y2 = (float(v) for v in det.bbox_xyxy)
    return Observation(((x1 + x2) / 2, (y1 + y2) / 2), max(x2 - x1, y2 - y1))


class PassReader:
    def __init__(self, pipeline, tracker: PassTracker | None = None,
                 min_votes: int = 2, recheck_every: int = 5, clock=time.monotonic,
                 announce_votes: int | None = None, fallback=None):
        """
        pipeline:      có ``detect``, ``decode_detection`` và ``warmup`` (ImprovePipeline).
        tracker:       mặc định max_gap=100 theo seq camera (~2 s ở 50 fps) — frame được decode
                       cách nhau cỡ (thời gian decode × fps) seq; max_speed_px=30 px/seq (~1500 px/s ở
                       50 fps, đủ cho 30 cm/s ở 0,25 mm/px) để QR mới vẫn ghép được qua khoảng đó.
        min_votes:     số lần đọc giống nhau để coi lượt là đọc chắc.
        recheck_every: số lần bỏ cascade liên tiếp trước khi đọc kiểm tra lại.
        clock:         nguồn thời gian (giây), test truyền đồng hồ giả.
        announce_votes: số lần đọc giống nhau trước khi báo trong first_reads; mặc định bằng min_votes ở
                       chế độ nhiều frame, 1 ở chế độ từng frame.
        fallback:      bộ đọc nền cho lượt không đọc được (qr/pass_fallback.py); mặc định theo enable().
        """
        self._pipeline = pipeline
        multi_frame = getattr(pipeline, "multi_frame", False) is True
        self._decoder = PassDecoder(pipeline.code_pattern, pipeline.roi_margin) if multi_frame else None
        self._tracker = tracker if tracker is not None else PassTracker(
            max_gap=100, max_speed_px=30.0, strict=multi_frame)
        self._min_votes = min_votes
        self._clock = clock
        self._exposure_ms: float | None = None
        self._seq_rate: float | None = None      # seq / giây, đo từ các frame được gửi
        self._last_seen: tuple[int, float] | None = None
        self._last_yolo_t = float("-inf")
        self._last_overlays: list[Overlay] = []
        self._announce_votes = announce_votes if announce_votes is not None else (min_votes if multi_frame else 1)
        self._awaiting_read = False
        self._recheck_every = recheck_every
        self._skips: dict[int, int] = {}         # track_id → số lần bỏ cascade liên tiếp
        self._announced: set[int] = set()        # track_id đã báo trong first_reads, lượt còn mở
        self._last_idx: int | None = None
        self._shape: tuple[int, int] | None = None
        self._fallback = fallback if fallback is not None else pass_fallback.active()
        self._crops: dict[int, list] = {}        # track_id → crop của lượt chưa đọc chắc
        self._held: dict[int, Track] = {}        # khóa việc nền → lượt đang chờ kết quả
        self._late_reads: list[Track] = []       # lượt bộ đọc nền vừa đọc được, chờ báo
        self._held_at: dict[int, float] = {}     # khóa việc nền → monotonic lúc gửi
        self._fallback_mark: tuple = ((), 0)     # trạng thái đọc nền lần báo gần nhất

    def warmup(self):
        self._pipeline.warmup()

    def set_exposure_ms(self, exposure_ms: float | None):
        """Exposure hiện tại của camera, để tính độ dài vệt mờ. None = chưa biết."""
        self._exposure_ms = exposure_ms

    def decode_every(self, default_n: int) -> int:
        """Số frame nên chờ giữa hai lần gửi decode; đọc được từ thread khác."""
        return min(default_n, FAST_EVERY_N) if self._awaiting_read else default_n

    def process(self, image_bgr: np.ndarray, frame_idx: int) -> FrameResult:
        result = self._process_frame(image_bgr, frame_idx)
        result.fallback = self._fallback_changes()
        return result

    def fallback_status(self) -> list[FallbackStatus]:
        """Các lượt đang chờ bộ đọc nền, theo thứ tự gửi."""
        statuses = []
        queued = 0
        for key, t in sorted(self._held.items()):
            stage = self._fallback.stage(key) if hasattr(self._fallback, "stage") else None
            if stage is None:
                queued += 1
                statuses.append(FallbackStatus(t.track_id, STAGE_QUEUED, self._held_at.get(key, 0.0), queued))
            else:
                statuses.append(FallbackStatus(t.track_id, stage[0], stage[1], 0))
        return statuses

    def _fallback_changes(self) -> list[FallbackStatus] | None:
        mark = (tuple(self._held), getattr(self._fallback, "revision", 0))
        if mark == self._fallback_mark:
            return None
        self._fallback_mark = mark
        return self.fallback_status()

    def _process_frame(self, image_bgr: np.ndarray, frame_idx: int) -> FrameResult:
        finished: list[Track] = self._poll_fallback()
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
        self._collect_crops(image_bgr, detections, observations, matched, frame_idx)
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
        finished = self._close(self._tracker.finish())
        finished += self._drain_fallback()
        self._fallback_mark = ((), getattr(self._fallback, "revision", 0))   # người gọi tự xóa trạng thái cũ
        return finished

    def take_late_reads(self) -> list[Track]:
        """Lượt đọc nền xong trong lúc flush — chưa được báo qua ``first_reads``."""
        late, self._late_reads = self._late_reads, []
        return late

    def _new_reads(self) -> list[Track]:
        reads = [t for t in self._tracker.active
                 if t.text and t.votes >= self._announce_votes and t.track_id not in self._announced]
        self._announced.update(t.track_id for t in reads)
        return reads + self.take_late_reads()

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
            hit = self._decoder.read(image_bgr, bbox, None, t, self._blur_lengths(t))
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
        done = []
        for t in tracks:
            if t.text and t.votes < self._announce_votes and t.track_id not in self._announced:
                logger.info("pass_unconfirmed id=%d text=%s votes=%d", t.track_id, t.text, t.votes)
                t.texts.clear()
            self._skips.pop(t.track_id, None)
            self._announced.discard(t.track_id)
            if self._decoder is not None:
                self._decoder.forget(t.track_id)
            if self._send_to_fallback(t):
                continue
            self._log_finished(t)
            done.append(t)
        return done

    @staticmethod
    def _log_finished(t: Track):
        logger.info("pass_finished id=%d text=%s votes=%d observations=%d conflicting=%s",
                    t.track_id, t.text, t.votes, t.observations, t.conflicting)

    # ── Đọc nền cho lượt PassDecoder không đọc được ───────────────────────────

    def _collect_crops(self, image_bgr, detections, observations, matched, frame_idx: int):
        if self._fallback is None or self._decoder is None:
            return
        active = self._tracker.active
        for i, det in enumerate(detections):
            track = matched.get(i) or next((t for t in active if t.first_frame == frame_idx
                                            and t.center == observations[i].center), None)
            if track is None:
                continue
            if track.votes >= self._min_votes:
                self._crops.pop(track.track_id, None)
                continue
            obs = pass_fallback.make_obs(image_bgr, det, frame_idx, self._clock())
            if obs is not None:
                crops = self._crops.setdefault(track.track_id, [])
                crops.append(obs)
                if len(crops) > pass_fallback.MAX_CROPS:
                    del crops[1::2]

    def _send_to_fallback(self, t: Track) -> bool:
        crops = self._crops.pop(t.track_id, [])
        if self._fallback is None or self._decoder is None or t.text or len(crops) < pass_fallback.MIN_CROPS:
            return False
        index = np.linspace(0, len(crops) - 1, min(pass_fallback.K_FRAMES, len(crops))).astype(int)
        fps = self._seq_rate or 25.0
        exposure = self._exposure_ms or 0.0
        blur = float(np.hypot(*t.velocity)) * fps * exposure / 1000.0
        ctx = pass_fallback.PassCtx(tuple(float(v) for v in t.velocity), fps, exposure, blur)
        key = self._fallback.submit([crops[i] for i in index], ctx)
        if key is None:
            logger.warning("pass_fallback_skipped id=%d (hàng đợi đầy hoặc bộ giải lỗi)", t.track_id)
            return False
        self._held[key] = t
        self._held_at[key] = time.monotonic()
        return True

    def _poll_fallback(self) -> list[Track]:
        return self._resolve(self._fallback.poll()) if self._held else []

    def _resolve(self, results) -> list[Track]:
        done = []
        for key, text, ms, error in results:
            t = self._held.pop(key, None)
            self._held_at.pop(key, None)
            if t is None:
                continue
            if error:
                logger.warning("pass_fallback_error id=%d: %s", t.track_id, error)
            if text:
                t.texts[text] = max(self._min_votes, self._announce_votes)
                self._late_reads.append(t)
            logger.info("pass_fallback_done id=%d text=%s ms=%.0f", t.track_id, text, ms)
            self._log_finished(t)
            done.append(t)
        return done

    def _drain_fallback(self) -> list[Track]:
        if not self._held:
            return []
        done = self._resolve(self._fallback.wait(pass_fallback.FLUSH_WAIT_S))
        for t in self._held.values():
            logger.info("pass_fallback_abandoned id=%d", t.track_id)
            self._log_finished(t)
            done.append(t)
        self._held.clear()
        self._held_at.clear()
        self._fallback.discard()
        return done
