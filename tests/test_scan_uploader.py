"""ScanUploader — hàng đợi gửi QR lên API, không cần Qt/mạng.

Chạy (từ gốc repo):  python -m unittest tests.test_scan_uploader
"""
import io
import json
from pathlib import Path
import sys
import threading
import unittest
import urllib.error

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from demo_ui.api_config import ApiConfig  # noqa: E402
from demo_ui.scan_uploader import (REPORT_PATH, PermanentError, ReportClient, ScanUploader,  # noqa: E402
                                   TransientError, make_app_token)


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def make(send, clock=None, **kw):
    """Uploader chạy đồng bộ: autostart=False, dùng drain() thay thread."""
    return ScanUploader(send=send, monotonic=clock or Clock(), sleep=lambda s: None,
                        autostart=False, **kw)


class UploaderTests(unittest.TestCase):
    def test_sends_code_verbatim(self):
        sent = []
        up = make(sent.append)
        up.submit("12#34")
        up.drain()
        self.assertEqual(sent, ["12#34"])

    def test_disabled_ignores_submit_and_enabling_sends_again(self):
        sent = []
        up = make(sent.append)
        up.set_enabled(False)
        self.assertFalse(up.submit("A"))
        up.drain()
        self.assertEqual(sent, [])
        up.set_enabled(True)
        self.assertTrue(up.submit("A"))
        up.drain()
        self.assertEqual(sent, ["A"])

    def test_disabling_drops_queue_and_forgets_dropped_codes(self):
        sent = []
        up = make(sent.append)
        up.submit("A")
        up.set_enabled(False)
        self.assertEqual(up.pending, 0)
        up.set_enabled(True)
        self.assertTrue(up.submit("A"))      # không bị coi là trùng
        up.drain()
        self.assertEqual(sent, ["A"])

    def test_disabling_during_retry_stops_without_counting_failure(self):
        calls, statuses = [], []
        def send(url):
            calls.append(url)
            up.set_enabled(False)            # người dùng tắt giữa hai lần thử
            raise TransientError("mất mạng")
        up = make(send, on_status=statuses.append)
        up.submit("A")
        statuses.clear()
        up.drain()
        self.assertEqual(len(calls), 1)
        self.assertEqual(up.failed_count, 0)
        self.assertFalse([s for s in statuses if s.last_ok is False])    # không báo "gửi lỗi" lên màn hình
        up.set_enabled(True)
        self.assertTrue(up.submit("A"))

    def test_duplicate_within_ttl_sent_once_then_again_after_ttl(self):
        sent, clock = [], Clock()
        up = make(sent.append, clock, dedup_ttl=30.0)
        up.submit("A"); up.submit("A"); up.drain()
        clock.now = 29.0
        up.submit("A"); up.drain()
        self.assertEqual(len(sent), 1)
        clock.now = 31.0
        up.submit("A"); up.drain()
        self.assertEqual(len(sent), 2)

    def test_empty_text_ignored(self):
        sent = []
        up = make(sent.append)
        up.submit(""); up.submit(None); up.drain()
        self.assertEqual(sent, [])

    def test_transient_error_retried_then_succeeds(self):
        calls = []

        def send(url):
            calls.append(url)
            if len(calls) < 3:
                raise TransientError("503")
        up = make(send, max_retries=3)
        up.submit("A"); up.drain()
        self.assertEqual(len(calls), 3)
        self.assertEqual(up.sent_count, 1)

    def test_transient_error_gives_up_and_allows_resubmit(self):
        calls = []

        def send(url):
            calls.append(url)
            raise TransientError("down")
        up = make(send, max_retries=2)
        up.submit("A"); up.drain()
        self.assertEqual(len(calls), 3)          # 1 lần đầu + 2 lần thử lại
        self.assertEqual(up.failed_count, 1)
        up.submit("A"); up.drain()               # thất bại không bị nhớ là đã gửi
        self.assertEqual(len(calls), 6)

    def test_permanent_error_not_retried(self):
        calls = []

        def send(url):
            calls.append(url)
            raise PermanentError("404")
        up = make(send)
        up.submit("A"); up.drain()
        self.assertEqual(len(calls), 1)
        self.assertEqual(up.failed_count, 1)

    def test_failure_status_carries_server_error(self):
        def send(text):
            raise PermanentError("Không tìm thấy tấm")
        statuses = []
        up = make(send, on_status=statuses.append)
        up.submit("A"); up.drain()
        self.assertIs(statuses[-1].last_ok, False)
        self.assertEqual(statuses[-1].last_error, "Không tìm thấy tấm")

    def test_full_queue_drops_oldest(self):
        sent = []
        up = make(sent.append, maxsize=2)
        for t in "ABC":
            up.submit(t)
        up.drain()
        self.assertEqual(sent, ["B", "C"])
        self.assertEqual(up.dropped_count, 1)

    def test_status_callback_reports_pending_and_results(self):
        events = []
        up = make(lambda url: None, on_status=lambda s: events.append((s.pending, s.sent, s.failed)))
        up.submit("A"); up.drain()
        self.assertEqual(events[0], (1, 0, 0))
        self.assertEqual(events[-1], (0, 1, 0))

    def test_thread_mode_sends_and_stop_does_not_hang(self):
        done = threading.Event()
        up = ScanUploader(send=lambda text: done.set())
        up.submit("A")
        self.assertTrue(done.wait(2.0))
        up.stop()
        up.submit("B")                            # sau stop: bỏ qua, không lỗi
        self.assertEqual(up.pending, 0)


CFG = ApiConfig("https://x.test", "s", "k")
NOW = 1763631234567                      # → ts 1763631180000


class FakeResponse:
    def __init__(self, body: bytes):
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeOpener:
    """Ghi lại (Request, timeout); trả body 200 hoặc ném HTTPError/URLError đã cài."""

    def __init__(self, status=200, body=b'{"status":"REPORTED","warning":""}', exc=None, headers=None):
        self.status, self.body, self.exc = status, body, exc
        self.headers = headers or {}
        self.calls = []

    def __call__(self, request, timeout=None):
        self.calls.append((request, timeout))
        if self.exc is not None:
            raise self.exc
        if self.status != 200:
            raise urllib.error.HTTPError(request.full_url, self.status, "err", self.headers, io.BytesIO(self.body))
        return FakeResponse(self.body)


def client(opener, config=CFG, now=lambda: NOW):
    return ReportClient(config, now_ms=now, opener=opener)


class ReportClientTests(unittest.TestCase):
    def test_signature_vector(self):
        self.assertEqual(make_app_token("test-secret", "POST", REPORT_PATH, 1763631180000),
                         "5b0b785e50ed64bdcfa810bf3b57a9622097f6a14412a9318ec93f20b5233a2b")

    def test_request_shape(self):
        opener = FakeOpener()
        client(opener)("A")
        request, timeout = opener.calls[0]
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.full_url, "https://x.test/api/v1/production/camera/product-item-reports")
        self.assertEqual(request.get_header("X-api-key"), "k")
        self.assertEqual(request.get_header("X-app-token"), make_app_token("s", "POST", REPORT_PATH, 1763631180000))
        self.assertEqual(request.get_header("Content-type"), "application/json")
        self.assertEqual(timeout, 10.0)

    def test_trailing_slash_in_base_url(self):
        opener = FakeOpener()
        client(opener, ApiConfig("https://x.test/", "s", "k"))("A")
        self.assertNotIn("//api", opener.calls[0][0].full_url)

    def test_body_sends_code_verbatim(self):
        opener = FakeOpener()
        client(opener)("12 #34é")
        self.assertEqual(json.loads(opener.calls[0][0].data), {"productItemCode": "12 #34é"})

    def test_returns_warning(self):
        warning = "Tấm đã được quét trước đó, số lần quét đã tăng"
        body = json.dumps({"status": "REPORTED", "warning": warning}).encode()
        self.assertEqual(client(FakeOpener(body=body))("A"), warning)

    def test_404_is_permanent_with_server_message(self):
        body = json.dumps({"error": "Không tìm thấy tấm"}).encode()
        with self.assertRaises(PermanentError) as ctx:
            client(FakeOpener(404, body))("A")
        self.assertEqual(str(ctx.exception), "Không tìm thấy tấm")

    def test_403_message_hints_clock(self):
        with self.assertRaises(PermanentError) as ctx:
            client(FakeOpener(403, b'{"error":"invalid X-App-Token"}'))("A")
        self.assertIn("kiểm tra giờ máy", str(ctx.exception))

    def test_500_and_network_are_transient(self):
        with self.assertRaises(TransientError):
            client(FakeOpener(500, b'{"error":"B\u00e1o c\u00e1o t\u1ea5m th\u1ea5t b\u1ea1i: x"}'))("A")
        with self.assertRaises(TransientError):
            client(FakeOpener(exc=urllib.error.URLError("down")))("A")

    def test_non_json_5xx_is_transient(self):
        with self.assertRaises(TransientError) as ctx:
            client(FakeOpener(502, b"<html>"))("A")
        self.assertEqual(str(ctx.exception), "HTTP 502")

    def test_sends_custom_user_agent(self):
        opener = FakeOpener()
        client(opener)("A")
        self.assertTrue(opener.calls[0][0].get_header("User-agent").startswith("QRDetector"))

    def test_no_authorization_header_by_default(self):
        opener = FakeOpener()
        client(opener)("A")
        self.assertIsNone(opener.calls[0][0].get_header("Authorization"))

    def test_basic_auth_header_when_configured(self):
        opener = FakeOpener()
        client(opener, ApiConfig("https://x.test", "s", "k", basic_user="u", basic_password="p"))("A")
        self.assertEqual(opener.calls[0][0].get_header("Authorization"), "Basic dTpw")

    def test_basic_auth_challenge_message(self):
        opener = FakeOpener(401, b"<html>401 Authorization Required</html>",
                            headers={"WWW-Authenticate": 'Basic realm="Dev Environment"'})
        with self.assertRaises(PermanentError) as ctx:
            client(opener)("A")
        self.assertIn("BASIC_AUTH_USER", str(ctx.exception))

    def test_token_recomputed_each_call(self):
        times = iter([60000, 120000])
        opener = FakeOpener()
        c = client(opener, now=lambda: next(times))
        c("A"); c("A")
        self.assertNotEqual(opener.calls[0][0].get_header("X-app-token"),
                            opener.calls[1][0].get_header("X-app-token"))


if __name__ == "__main__":
    unittest.main()
