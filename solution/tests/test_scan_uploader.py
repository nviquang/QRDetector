"""ScanUploader — hàng đợi gửi QR lên API, không cần Qt/mạng.

Chạy (từ solution/):  python -m unittest tests.test_scan_uploader
"""
from pathlib import Path
import sys
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from demo_ui.scan_uploader import (PermanentError, ScanUploader, TransientError,  # noqa: E402
                                   build_url)

BASE = "https://example.test/api/scans"


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def make(send, clock=None, **kw):
    """Uploader chạy đồng bộ: autostart=False, dùng drain() thay thread."""
    return ScanUploader(send=send, base_url=BASE, monotonic=clock or Clock(), sleep=lambda s: None,
                        autostart=False, **kw)


class BuildUrlTests(unittest.TestCase):
    def test_encodes_reserved_and_unicode_characters(self):
        self.assertEqual(build_url(BASE, "A/B?C#D%E"), BASE + "/A%2FB%3FC%23D%25E")
        self.assertEqual(build_url(BASE + "/", "Mã 1"), BASE + "/M%C3%A3%201")


class UploaderTests(unittest.TestCase):
    def test_sends_put_to_encoded_url(self):
        sent = []
        up = make(lambda url: sent.append(url))
        up.submit("A/1")
        up.drain()
        self.assertEqual(sent, [BASE + "/A%2F1"])

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

    def test_full_queue_drops_oldest(self):
        sent = []
        up = make(sent.append, maxsize=2)
        for t in "ABC":
            up.submit(t)
        up.drain()
        self.assertEqual([u.rsplit("/", 1)[1] for u in sent], ["B", "C"])
        self.assertEqual(up.dropped_count, 1)

    def test_status_callback_reports_pending_and_results(self):
        events = []
        up = make(lambda url: None, on_status=lambda s: events.append((s.pending, s.sent, s.failed)))
        up.submit("A"); up.drain()
        self.assertEqual(events[0], (1, 0, 0))
        self.assertEqual(events[-1], (0, 1, 0))

    def test_thread_mode_sends_and_stop_does_not_hang(self):
        done = threading.Event()
        up = ScanUploader(send=lambda url: done.set(), base_url=BASE)
        up.submit("A")
        self.assertTrue(done.wait(2.0))
        up.stop()
        up.submit("B")                            # sau stop: bỏ qua, không lỗi
        self.assertEqual(up.pending, 0)


if __name__ == "__main__":
    unittest.main()
