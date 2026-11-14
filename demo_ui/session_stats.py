"""Số liệu của phiên demo — thuần Python, không phụ thuộc Qt.

Dòng trong danh sách mã xuất hiện ngay khi một lượt đọc được lần đầu, trạng thái chốt khi lượt kết
thúc. Các chỉ số chỉ tính trên lượt đã kết thúc. Lượt không đọc được và chỉ có 1 detection coi là
nhận nhầm của detector: không hiện, không tính vào tỉ lệ (vẫn có trong log ``pass_finished``).
"""

from __future__ import annotations

from collections import deque
from dataclasses import KW_ONLY, dataclass
from enum import Enum
import time

SPEED_WINDOW_S = 60.0
SPEED_MIN_WINDOW_S = 10.0    # vài giây đầu: tránh một lượt đọc được quy ra tốc độ rất cao


class RowState(Enum):
    READING = "reading"     # đã đọc được, lượt chưa kết thúc
    OK = "ok"
    CONFLICT = "conflict"   # lượt có hơn một nội dung khác nhau
    FAILED = "failed"
    SOLVING = "solving"     # lượt chưa đọc được, đang chờ / chạy bộ đọc nền (B, C)


STAGE_QUEUED = "queued"     # như qr.pass_reader.STAGE_QUEUED; module này không import qr


@dataclass
class PassRow:
    track_id: int
    text: str | None
    clock: str
    state: RowState
    _: KW_ONLY                      # MergedRow kế thừa và tạo theo vị trí: trường mới không được chen vào
    stage: str | None = None       # SOLVING: STAGE_QUEUED, "B", "C"…
    since: float | None = None      # SOLVING: monotonic lúc vào hàng đợi / giai đoạn
    position: int = 0               # SOLVING + STAGE_QUEUED: thứ tự trong hàng đợi


def solving_text(row: PassRow, now: float) -> str:
    seconds = max(0.0, now - (row.since if row.since is not None else now))
    if row.stage == STAGE_QUEUED:
        return "chờ đọc lại (thứ {}) · {:.0f} s".format(row.position, seconds)
    return "đang đọc lại · {} {:.0f} s".format(row.stage, seconds)


def age_text(seconds: float) -> str:
    if seconds < 1:
        return "vừa xong"
    if seconds < 60:
        return "{:.0f} giây trước".format(seconds)
    return "{:.0f} phút trước".format(seconds // 60)


def _is_noise(track) -> bool:
    return not track.text and track.observations < 2


class SessionStats:
    def __init__(self, monotonic=time.monotonic, clock=lambda: time.strftime("%H:%M:%S")):
        self._monotonic = monotonic
        self._clock = clock
        self.reset()

    def reset(self):
        self.read_count = 0
        self.conflict_count = 0
        self.noise_count = 0
        self.finished_count = 0
        self.latest_text: str | None = None
        self.latest_clock = ""
        self.latest_at: float | None = None
        self._open: dict[int, PassRow] = {}
        self.solving: dict[int, PassRow] = {}    # track_id → dòng đang đọc nền
        self._read_times: deque[float] = deque()
        self._elapsed = 0.0
        self._run_started: float | None = None
        self._rate_started: float | None = None

    def begin_run(self):
        now = self._monotonic()
        self._run_started = now
        self._rate_started = now
        self._read_times.clear()     # thời gian dừng không được kéo tụt tốc độ của lần chạy mới

    def end_run(self):
        if self._run_started is not None:
            self._elapsed += self._monotonic() - self._run_started
            self._run_started = None

    def elapsed(self) -> float:
        running = self._monotonic() - self._run_started if self._run_started is not None else 0.0
        return self._elapsed + running

    def on_reads(self, tracks) -> list[PassRow]:
        rows = []
        for track in tracks:
            clock = self._clock()
            row = PassRow(track.track_id, track.text, clock, RowState.READING)
            self._open[track.track_id] = row
            self.solving.pop(track.track_id, None)
            self.latest_text, self.latest_clock = track.text, clock
            self.latest_at = self._monotonic()
            rows.append(row)
        return rows

    def on_fallback(self, statuses) -> list[PassRow]:
        """Ảnh chụp các lượt đang đọc nền (qr.pass_reader.FallbackStatus). Không đổi chỉ số: lượt chỉ được
        tính khi kết thúc qua ``on_passes``. Lượt không còn trong danh sách đã/ sẽ được chốt bởi reads/passes."""
        listed = {s.track_id for s in statuses}
        self.solving = {tid: row for tid, row in self.solving.items() if tid in listed}
        rows = []
        for s in statuses:
            row = self.solving.get(s.track_id)
            if row is None:
                row = PassRow(s.track_id, None, self._clock(), RowState.SOLVING)
                self.solving[s.track_id] = row
                self._open[s.track_id] = row
            row.stage, row.since, row.position = s.stage, s.since, s.position
            rows.append(row)
        return rows

    def on_passes(self, tracks) -> list[PassRow]:
        rows = []
        for track in tracks:
            row = self._open.pop(track.track_id, None)
            self.solving.pop(track.track_id, None)
            if _is_noise(track):
                self.noise_count += 1
                continue
            self.finished_count += 1
            if row is None:
                row = PassRow(track.track_id, track.text, self._clock(), RowState.FAILED)
            row.text = track.text
            if not track.text:
                row.state = RowState.FAILED
            else:
                self.read_count += 1
                self._read_times.append(self._monotonic())
                row.state = RowState.OK
                if track.conflicting:
                    self.conflict_count += 1
                    row.state = RowState.CONFLICT
            rows.append(row)
        return rows

    @property
    def read_rate(self) -> float | None:
        return self.read_count / self.finished_count if self.finished_count else None

    def per_minute(self) -> float | None:
        """Mã/phút trong 60 giây gần nhất (mới chạy chưa đủ 60 giây thì chia theo thời gian đã chạy)."""
        if not self.finished_count:
            return None
        now = self._monotonic()
        while self._read_times and now - self._read_times[0] > SPEED_WINDOW_S:
            self._read_times.popleft()
        started = self._rate_started if self._rate_started is not None else now
        window = min(SPEED_WINDOW_S, max(SPEED_MIN_WINDOW_S, now - started))
        return len(self._read_times) * 60.0 / window
