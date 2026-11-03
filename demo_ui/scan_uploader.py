"""ScanUploader — gửi nội dung QR lên API qua hàng đợi, thuần Python (không Qt).

``PUT {base_url}/{text}`` (text được URL-encode), không body. Một thread nền lấy từng mục trong
hàng đợi nên mạng chậm không chặn decode. Chống gửi trùng: mã đã chờ hoặc đã gửi thành công trong
``dedup_ttl`` giây bị bỏ qua; lỗi tạm thời (mạng, 5xx) thử lại có chờ lâu dần, lỗi 4xx không thử lại.
Thất bại không được nhớ là đã gửi nên lần đọc sau vẫn được gửi lại.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import quote

logger = logging.getLogger("solution.upload")

DEFAULT_BASE_URL = "https://qr-scan-gp1.vercel.app/api/scans"


class TransientError(Exception):
    """Lỗi có thể hết khi thử lại (mất mạng, timeout, 5xx)."""


class PermanentError(Exception):
    """Server từ chối (4xx) — thử lại cũng vô ích."""


@dataclass(frozen=True)
class UploadStatus:
    pending: int
    sent: int
    failed: int
    last_text: str | None = None
    last_ok: bool | None = None


def build_url(base_url: str, text: str) -> str:
    return base_url.rstrip("/") + "/" + quote(text, safe="")


def http_put(url: str, timeout: float = 10.0) -> None:
    request = urllib.request.Request(url, method="PUT")
    try:
        with urllib.request.urlopen(request, timeout=timeout):
            return
    except urllib.error.HTTPError as exc:
        if exc.code == 409:                       # server đã có bản ghi này
            return
        if exc.code == 429 or exc.code >= 500:
            raise TransientError("HTTP {}".format(exc.code)) from exc
        raise PermanentError("HTTP {}".format(exc.code)) from exc
    except (urllib.error.URLError, OSError) as exc:
        raise TransientError(str(exc)) from exc


class ScanUploader:
    def __init__(self, send=http_put, base_url: str = DEFAULT_BASE_URL, maxsize: int = 500,
                 dedup_ttl: float = 30.0, max_retries: int = 3, on_status=None,
                 monotonic=time.monotonic, sleep=time.sleep, autostart: bool = True):
        """
        send:      ``send(url)``; ném TransientError / PermanentError khi lỗi.
        on_status: ``on_status(UploadStatus)``, gọi trên thread gửi (và thread gọi submit) — nơi
                   nhận phải tự chuyển về GUI thread.
        autostart: False = không tạo thread, tự gọi ``drain()`` (dùng trong test).
        """
        self._send = send
        self._base_url = base_url
        self._queue: queue.Queue[str] = queue.Queue(maxsize=maxsize)
        self._ttl = dedup_ttl
        self._max_retries = max_retries
        self._on_status = on_status
        self._monotonic = monotonic
        self._sleep = sleep
        self._lock = threading.Lock()
        self._seen: dict[str, float] = {}          # text → thời điểm vào hàng đợi / gửi xong
        self._stopped = False
        self.sent_count = 0
        self.failed_count = 0
        self.dropped_count = 0
        self._thread = None
        if autostart:
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()

    @property
    def pending(self) -> int:
        return self._queue.qsize()

    def submit(self, text: str | None) -> bool:
        """Đưa mã vào hàng đợi; False nếu bị bỏ qua (rỗng, trùng, đã dừng)."""
        if not text:
            return False
        with self._lock:
            if self._stopped:
                return False
            now = self._monotonic()
            seen = self._seen.get(text)
            if seen is not None and now - seen < self._ttl:
                return False
            self._seen[text] = now                 # giữ chỗ tới khi gửi xong
            while True:
                try:
                    self._queue.put_nowait(text)
                    break
                except queue.Full:
                    try:
                        old = self._queue.get_nowait()
                    except queue.Empty:
                        continue
                    self._seen.pop(old, None)
                    self.dropped_count += 1
                    logger.warning("upload_dropped text=%s (hàng đợi đầy)", old)
        self._notify()
        return True

    def drain(self):
        """Gửi hết hàng đợi trên thread hiện tại (chế độ autostart=False)."""
        while True:
            try:
                text = self._queue.get_nowait()
            except queue.Empty:
                return
            self._process(text)

    def stop(self, timeout: float = 2.0):
        with self._lock:
            self._stopped = True
        while True:                                # bỏ phần chưa gửi, không chặn lúc đóng app
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break
        self._queue.put(None)
        if self._thread is not None:
            self._thread.join(timeout)

    def _loop(self):
        while True:
            text = self._queue.get()
            if text is None:
                return
            self._process(text)

    def _process(self, text: str):
        url = build_url(self._base_url, text)
        ok = False
        for attempt in range(self._max_retries + 1):
            if self._stopped:
                break
            try:
                self._send(url)
                ok = True
                break
            except PermanentError as exc:
                logger.warning("upload_rejected text=%s error=%s", text, exc)
                break
            except TransientError as exc:
                logger.warning("upload_retry text=%s attempt=%d error=%s", text, attempt + 1, exc)
                if attempt < self._max_retries:
                    self._sleep(min(2 ** attempt, 8))
            except Exception as exc:               # lỗi lạ không được giết thread gửi
                logger.exception("upload_error text=%s error=%s", text, exc)
                break
        with self._lock:
            if ok:
                self.sent_count += 1
                self._seen[text] = self._monotonic()
            else:
                self.failed_count += 1
                self._seen.pop(text, None)         # cho phép gửi lại ở lần đọc sau
        if ok:
            logger.info("upload_ok text=%s", text)
        self._notify(text, ok)

    def _notify(self, last_text: str | None = None, last_ok: bool | None = None):
        if self._on_status is not None:
            self._on_status(UploadStatus(self.pending, self.sent_count, self.failed_count,
                                         last_text, last_ok))
