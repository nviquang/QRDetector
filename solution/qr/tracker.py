"""Gom detection qua các frame thành "lượt" — mỗi lượt là một QR đi qua khung hình một lần.

Copy từ offline/qr/tracker.py (không import chéo giữa hai app), thêm ``match()`` để hỏi trước
detection sẽ ghép vào track nào mà không đổi trạng thái — PassReader dùng để bỏ cascade cho QR
đã đọc chắc. Ghép tham lam theo khoảng cách từ vị trí dự đoán (tâm + vận tốc × số frame) tới
tâm detection mới. Lượt kết thúc khi mất dấu quá ``max_gap`` frame. Kết quả đọc của lượt là nội
dung decode xuất hiện nhiều nhất.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

import numpy as np


@dataclass
class Observation:
    center: tuple[float, float]
    size: float
    text: str | None = None


@dataclass
class Track:
    track_id: int
    first_frame: int
    last_frame: int
    center: tuple[float, float]
    size: float
    velocity: tuple[float, float] = (0.0, 0.0)   # px / frame
    observations: int = 1
    texts: Counter = field(default_factory=Counter)

    def predict(self, frame_idx: int) -> tuple[float, float]:
        dt = frame_idx - self.last_frame
        return (self.center[0] + self.velocity[0] * dt, self.center[1] + self.velocity[1] * dt)

    @property
    def text(self) -> str | None:
        """Nội dung đọc được nhiều nhất trong lượt (None nếu chưa frame nào decode được)."""
        return self.texts.most_common(1)[0][0] if self.texts else None

    @property
    def votes(self) -> int:
        """Số lần đọc ra nội dung ``text`` (0 nếu chưa đọc được)."""
        return self.texts.most_common(1)[0][1] if self.texts else 0

    @property
    def conflicting(self) -> bool:
        """Lượt có hơn một nội dung khác nhau — dấu hiệu đọc sai hoặc ghép nhầm hai QR."""
        return len(self.texts) > 1


class PassTracker:
    def __init__(self, max_gap: int = 5, gate_px: float = 400.0, gate_sizes: float = 3.0,
                 max_speed_px: float = 0.0):
        """
        max_gap:      số frame (theo chỉ số frame gốc) được phép mất dấu trước khi đóng lượt.
        gate_px:      khoảng cách tối đa (px) từ vị trí dự đoán khi track chưa có vận tốc.
        gate_sizes:   khi đã có vận tốc, cổng = gate_sizes × kích thước QR (dự đoán đã bù chuyển động).
        max_speed_px: tốc độ QR lớn nhất (px / frame) — track chưa có vận tốc được nới cổng thêm
                      max_speed_px × số frame đã qua (app chỉ decode cách nhau hàng chục seq).
        """
        self.max_gap = max_gap
        self.gate_px = gate_px
        self.gate_sizes = gate_sizes
        self.max_speed_px = max_speed_px
        self._active: list[Track] = []
        self._next_id = 0

    def match(self, frame_idx: int, observations: list[Observation]) -> dict[int, Track]:
        """Observation thứ i sẽ ghép vào track nào nếu gọi ``update`` ngay — không đổi trạng thái."""
        live = [t for t in self._active if frame_idx - t.last_frame <= self.max_gap]
        return {oi: live[ti] for ti, oi in self._pairs(live, frame_idx, observations)}

    def update(self, frame_idx: int, observations: list[Observation]) -> list[Track]:
        """Ghép observation của frame ``frame_idx`` vào các track, trả về các lượt vừa kết thúc."""
        # Đóng track mất dấu quá lâu TRƯỚC khi ghép — tránh nối QR xuất hiện lại vào lượt cũ.
        finished = [t for t in self._active if frame_idx - t.last_frame > self.max_gap]
        self._active = [t for t in self._active if frame_idx - t.last_frame <= self.max_gap]
        pairs = self._pairs(self._active, frame_idx, observations)
        for ti, oi in pairs:
            self._extend(self._active[ti], frame_idx, observations[oi])
        used_o = {oi for _, oi in pairs}
        for oi, obs in enumerate(observations):
            if oi not in used_o:
                self._active.append(self._start(frame_idx, obs))
        return finished

    def finish(self) -> list[Track]:
        """Đóng mọi lượt còn mở (gọi khi hết video)."""
        finished, self._active = self._active, []
        return finished

    def _pairs(self, tracks: list[Track], frame_idx: int,
               observations: list[Observation]) -> list[tuple[int, int]]:
        """Ghép tham lam (chỉ số track, chỉ số observation) theo khoảng cách tăng dần trong cổng."""
        candidates = []
        for ti, track in enumerate(tracks):
            px, py = track.predict(frame_idx)
            moving = track.observations > 1
            if moving:
                gate = self.gate_sizes * max(track.size, 1.0)
            else:
                gate = self.gate_px + self.max_speed_px * (frame_idx - track.last_frame)
            for oi, obs in enumerate(observations):
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

    def _start(self, frame_idx: int, obs: Observation) -> Track:
        track = Track(self._next_id, frame_idx, frame_idx, obs.center, obs.size)
        self._next_id += 1
        if obs.text:
            track.texts[obs.text] += 1
        return track

    @staticmethod
    def _extend(track: Track, frame_idx: int, obs: Observation):
        dt = max(1, frame_idx - track.last_frame)
        vx = (obs.center[0] - track.center[0]) / dt
        vy = (obs.center[1] - track.center[1]) / dt
        if track.observations > 1:   # làm mượt vận tốc, tránh nhảy theo nhiễu detect
            vx = 0.5 * (vx + track.velocity[0])
            vy = 0.5 * (vy + track.velocity[1])
        track.velocity = (vx, vy)
        track.center = obs.center
        track.size = 0.7 * track.size + 0.3 * obs.size
        track.last_frame = frame_idx
        track.observations += 1
        if obs.text:
            track.texts[obs.text] += 1
