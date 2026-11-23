"""ScanUploader — gửi mã QR lên API báo cáo tấm qua hàng đợi, thuần Python (không Qt).

``POST {BASE_URL}/api/v1/production/camera/product-item-reports`` với body ``{"productItemCode": mã}`` (mã = phần
sau dấu ``#`` nếu có, xem ``product_item_code``),
header ``X-App-Token`` (HMAC-SHA256 theo phút, tính lại mỗi lần gửi) và ``X-Api-Key`` — xem
``docs/camera-integration.md``. Một thread nền lấy từng mục trong hàng đợi nên mạng chậm không chặn decode.
Chống gửi trùng: mã đã chờ hoặc đã gửi thành công trong ``dedup_ttl`` giây bị bỏ qua; lỗi tạm thời (mạng,
5xx) thử lại có chờ lâu dần, lỗi 400/401/403/404 không thử lại. Thất bại không được nhớ là đã gửi nên lần
đọc sau vẫn được gửi lại (server chỉ tăng số lần quét, không tạo tấm trùng).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import queue
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

from demo_ui.api_config import ApiConfig

logger = logging.getLogger("solution.upload")

REPORT_PATH = "/api/v1/production/camera/product-item-reports"
INVALID_TOKEN = "invalid X-App-Token"
USER_AGENT = "QRDetector-camera/1.0"            # Cloudflare chặn UA mặc định Python-urllib (error 1010)


class TransientError(Exception):
    """Lỗi có thể hết khi thử lại (mất mạng, timeout, 5xx)."""


class PermanentError(Exception):
    """Server từ chối (400/401/403/404) — thử lại cũng vô ích."""


@dataclass(frozen=True)
class UploadStatus:
    pending: int
    sent: int
    failed: int
    last_text: str | None = None
    last_ok: bool | None = None
    last_error: str | None = None


def api_missing_text(missing: list[str]) -> str:
    return "Chưa cấu hình API trong .env: thiếu " + ", ".join(missing)


def upload_error_text(status: UploadStatus) -> str:
    return "Gửi mã {} lỗi: {} ({} mã chờ)".format(status.last_text, status.last_error or "không rõ", status.pending)


def product_item_code(text: str) -> str:
    """Mã gửi lên server: phần sau dấu ``#`` đầu tiên (tem dạng ``<số>#<mã tấm>``); không có ``#`` hoặc phần sau
    rỗng thì gửi nguyên chuỗi. Chống gửi trùng vẫn theo nội dung QR đầy đủ."""
    head, sep, tail = text.partition("#")
    return tail.strip() if sep and tail.strip() else text


def make_app_token(secret: str, method: str, path: str, now_ms: int) -> str:
    timestamp = now_ms // 60000 * 60000                 # làm tròn xuống đầu phút
    message = "{}\n{}\n{}".format(timestamp, method, path)
    return hmac.new(secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()


def _error_text(code: int, body: bytes) -> str:
    try:
        error = json.loads(body.decode("utf-8")).get("error")
    except (ValueError, UnicodeDecodeError, AttributeError):
        error = None
    return error if isinstance(error, str) and error else "HTTP {}".format(code)


class ReportClient:
    """``client(mã) -> warning``; ném TransientError / PermanentError (``str(exc)`` hiển thị được)."""

    def __init__(self, config: ApiConfig, timeout: float = 10.0,
                 now_ms=lambda: int(time.time() * 1000), opener=urllib.request.urlopen):
        self._config = config
        self._url = config.base_url.rstrip("/") + REPORT_PATH
        self._timeout = timeout
        self._now_ms = now_ms
        self._opener = opener
        self._authorization = None
        if config.basic_user or config.basic_password:
            pair = "{}:{}".format(config.basic_user, config.basic_password).encode("utf-8")
            self._authorization = "Basic " + base64.b64encode(pair).decode("ascii")

    def __call__(self, code: str) -> str:
        headers = {"Content-Type": "application/json", "User-Agent": USER_AGENT,
                   "X-App-Token": make_app_token(self._config.app_secret, "POST", REPORT_PATH, self._now_ms()),
                   "X-Api-Key": self._config.api_key}
        if self._authorization is not None:
            headers["Authorization"] = self._authorization
        request = urllib.request.Request(
            self._url, method="POST",
            data=json.dumps({"productItemCode": product_item_code(code)}, ensure_ascii=False).encode("utf-8"), headers=headers)
        try:
            with self._opener(request, timeout=self._timeout) as response:
                body = response.read()
        except urllib.error.HTTPError as exc:
            message = _error_text(exc.code, exc.read() or b"")
            if exc.code in (408, 429) or exc.code >= 500:
                raise TransientError(message) from exc
            if exc.code == 403 and message == INVALID_TOKEN:
                message += " — kiểm tra giờ máy"
            challenge = (exc.headers.get("WWW-Authenticate") if exc.headers is not None else None) or ""
            if exc.code == 401 and challenge.lower().startswith("basic"):
                message = ("Server đòi đăng nhập HTTP Basic: đặt BASIC_AUTH_USER, BASIC_AUTH_PASSWORD trong .env"
                           if self._authorization is None else "Sai BASIC_AUTH_USER / BASIC_AUTH_PASSWORD")
            raise PermanentError(message) from exc
        except (urllib.error.URLError, OSError) as exc:      # mất mạng, timeout
            raise TransientError(str(getattr(exc, "reason", exc))) from exc
        try:
            data = json.loads(body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise TransientError("HTTP 200 trả về không phải JSON") from exc
        warning = data.get("warning") if isinstance(data, dict) else None
        return warning if isinstance(warning, str) else ""


class ScanUploader:
    def __init__(self, send, maxsize: int = 500,
                 dedup_ttl: float = 30.0, max_retries: int = 3, on_status=None,
                 monotonic=time.monotonic, sleep=time.sleep, autostart: bool = True):
        """
        send:      ``send(mã) -> warning | None`` (thường là ``ReportClient``); ném TransientError /
                   PermanentError khi lỗi.
        on_status: ``on_status(UploadStatus)``, gọi trên thread gửi (và thread gọi submit) — nơi
                   nhận phải tự chuyển về GUI thread.
        autostart: False = không tạo thread, tự gọi ``drain()`` (dùng trong test).
        """
        self._send = send
        self._queue: queue.Queue[str] = queue.Queue(maxsize=maxsize)
        self._ttl = dedup_ttl
        self._max_retries = max_retries
        self._on_status = on_status
        self._monotonic = monotonic
        self._sleep = sleep
        self._lock = threading.Lock()
        self._seen: dict[str, float] = {}          # text → thời điểm vào hàng đợi / gửi xong
        self._stopped = False
        self._enabled = True
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
        """Đưa mã vào hàng đợi; False nếu bị bỏ qua (rỗng, trùng, đang tắt, đã dừng)."""
        if not text:
            return False
        with self._lock:
            if self._stopped or not self._enabled:
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

    def set_enabled(self, enabled: bool):
        """Tắt: bỏ các mã đang chờ và ngừng thử lại; lần gửi đang diễn ra thì không thu hồi được."""
        with self._lock:
            if self._stopped:
                return
            self._enabled = enabled
            if enabled:
                return
            while True:
                try:
                    self._seen.pop(self._queue.get_nowait(), None)
                except queue.Empty:
                    break
        self._notify()

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
        ok = False
        warning = None
        error = None
        for attempt in range(self._max_retries + 1):
            if self._stopped or not self._enabled:
                break
            try:
                warning = self._send(text)
                ok = True
                break
            except PermanentError as exc:
                error = str(exc)
                logger.warning("upload_rejected text=%s error=%s", text, exc)
                break
            except TransientError as exc:
                error = str(exc)
                logger.warning("upload_retry text=%s attempt=%d error=%s", text, attempt + 1, exc)
                if attempt < self._max_retries:
                    self._sleep(min(2 ** attempt, 8))
            except Exception as exc:               # lỗi lạ không được giết thread gửi
                error = str(exc) or type(exc).__name__
                logger.exception("upload_error text=%s error=%s", text, exc)
                break
        with self._lock:
            if ok:
                self.sent_count += 1
                self._seen[text] = self._monotonic()
            else:
                self._seen.pop(text, None)         # cho phép gửi lại ở lần đọc sau
                if not self._enabled:              # người dùng đã tắt gửi, không phải lỗi
                    return
                self.failed_count += 1
        if ok:
            logger.info("upload_ok text=%s warning=%s", text, warning or "")
        self._notify(text, ok, None if ok else error)

    def _notify(self, last_text: str | None = None, last_ok: bool | None = None, last_error: str | None = None):
        if self._on_status is not None:
            self._on_status(UploadStatus(self.pending, self.sent_count, self.failed_count,
                                         last_text, last_ok, last_error))
