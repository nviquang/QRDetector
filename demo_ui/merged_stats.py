"""Số liệu khi hai camera cùng soi một băng — thuần Python, không phụ thuộc Qt.

Cùng một mã đọc trong ``MERGE_WINDOW_S`` kể từ lần đầu chỉ là một dòng, ghi camera đã đọc (khớp thời
gian chống trùng của ScanUploader). "Đã đọc" và "Mã/phút" tính theo dòng đã gộp. Lượt không đọc được
không có nội dung nên không ghép được với camera kia: tỉ lệ đọc chỉ có theo từng camera.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .session_stats import PassRow, RowState, SessionStats, _is_noise

MERGE_WINDOW_S = 30.0
CAMERA_NAMES = ("A", "B")


@dataclass
class MergedRow(PassRow):
    cameras: set[int] = field(default_factory=set)
    first_at: float = 0.0
    counted: bool = False
    conflict: bool = False

    @property
    def camera_text(self) -> str:
        return "+".join(CAMERA_NAMES[cam] for cam in sorted(self.cameras))


class MergedStats(SessionStats):
    def reset(self):
        super().reset()
        self.camera_finished = [0] * len(CAMERA_NAMES)
        self.camera_read = [0] * len(CAMERA_NAMES)
        self._recent: dict[str, MergedRow] = {}     # mã → dòng còn trong cửa sổ gộp
        self._next_id = 0

    def camera_rate(self, cam: int) -> float | None:
        finished = self.camera_finished[cam]
        return self.camera_read[cam] / finished if finished else None

    def _new_row(self, text: str | None, state: RowState, cam: int) -> MergedRow:
        self._next_id += 1
        return MergedRow(self._next_id, text, self._clock(), state, {cam}, self._monotonic())

    def _row_for(self, cam: int, text: str) -> MergedRow:
        now = self._monotonic()
        self._recent = {code: row for code, row in self._recent.items()
                        if now - row.first_at <= MERGE_WINDOW_S}
        row = self._recent.get(text)
        if row is None:
            row = self._new_row(text, RowState.READING, cam)
            self._recent[text] = row
        row.cameras.add(cam)
        return row

    def on_reads(self, cam: int, tracks) -> list[MergedRow]:
        rows = []
        for track in tracks:
            row = self._row_for(cam, track.text)
            row.state = RowState.READING
            self._open[(cam, track.track_id)] = row
            self.latest_text, self.latest_clock = track.text, self._clock()
            self.latest_at = self._monotonic()
            rows.append(row)
        return rows

    def on_passes(self, cam: int, tracks) -> list[MergedRow]:
        rows = []
        for track in tracks:
            row = self._open.pop((cam, track.track_id), None)
            if _is_noise(track):
                self.noise_count += 1
                continue
            self.finished_count += 1
            self.camera_finished[cam] += 1
            if not track.text:
                rows.append(self._new_row(None, RowState.FAILED, cam))
                continue
            if row is None:
                row = self._row_for(cam, track.text)
            self.camera_read[cam] += 1
            if track.text != row.text:      # đọc nhiều nhất của lượt khác lần đọc đầu
                row.text = track.text
            if not row.counted:
                row.counted = True
                self.read_count += 1
                self._read_times.append(self._monotonic())
            if track.conflicting:
                row.conflict = True
                self.conflict_count += 1
            still_open = any(other is row for other in self._open.values())
            row.state = (RowState.READING if still_open
                         else RowState.CONFLICT if row.conflict else RowState.OK)
            rows.append(row)
        return rows
