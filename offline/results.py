"""Gom kết quả QR theo (nguồn, nội dung): lần đầu/cuối xuất hiện, số lần đọc được; xuất CSV."""

from __future__ import annotations

import csv
import os
from dataclasses import dataclass

from media_source import format_time


@dataclass
class QRRecord:
    source: str
    text: str
    first_frame: int | None   # None với ảnh tĩnh
    first_time: float | None
    last_frame: int | None
    last_time: float | None
    hits: int = 1


class ResultLog:
    def __init__(self):
        self._records: dict[tuple[str, str], QRRecord] = {}

    def __len__(self) -> int:
        return len(self._records)

    def records(self) -> list[QRRecord]:
        return list(self._records.values())

    def clear(self) -> None:
        self._records.clear()

    def add(self, source: str, text: str,
            frame: int | None = None, time_s: float | None = None) -> tuple[QRRecord, bool]:
        """Ghi nhận 1 lần đọc được. Trả về (record, True nếu là nội dung mới của nguồn này)."""
        key = (source, text)
        rec = self._records.get(key)
        if rec is None:
            rec = QRRecord(source, text, frame, time_s, frame, time_s)
            self._records[key] = rec
            return rec, True
        rec.hits += 1
        if frame is not None:
            if rec.first_frame is None or frame < rec.first_frame:
                rec.first_frame, rec.first_time = frame, time_s
            if rec.last_frame is None or frame > rec.last_frame:
                rec.last_frame, rec.last_time = frame, time_s
        return rec, False

    def export_csv(self, path: str) -> None:
        # utf-8-sig để Excel mở đúng tiếng Việt
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["file", "qr_text", "first_frame", "first_time",
                        "last_frame", "last_time", "hits"])
            for r in self._records.values():
                w.writerow([
                    os.path.basename(r.source), r.text,
                    "" if r.first_frame is None else r.first_frame,
                    "" if r.first_time is None else format_time(r.first_time),
                    "" if r.last_frame is None else r.last_frame,
                    "" if r.last_time is None else format_time(r.last_time),
                    r.hits,
                ])
