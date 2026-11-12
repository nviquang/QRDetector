"""Bộ gõ mã vào ô đang focus, với backend giả; không gửi phím thật.

Chạy (từ gốc repo):  python -m unittest tests.test_keyboard_output
"""
import ctypes
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from demo_ui.keyboard_output import (  # noqa: E402
    REASON_FOCUS_CHANGED, REASON_MODIFIER, REASON_NO_WINDOW, REASON_OWN_WINDOW, REASON_SEND_FAILED,
    REASON_TYPED, INPUT, KeyboardTyper, sanitize, text_inputs)

OWN_PID = 111
OTHER_PID = 222
OTHER_WINDOW = (5000, OTHER_PID)


class FakeBackend:
    """Ghi lại chuỗi phím như một ô nhập: mọi thứ nhận được nằm trong ``events``."""

    def __init__(self):
        self.window = OTHER_WINDOW
        self.windows_after_text = None
        self.modifier_polls = []       # giá trị lần lượt trả về; hết thì False
        self.text_ok = True
        self.events = []

    def foreground(self):
        return self.window

    def modifiers_held(self):
        return self.modifier_polls.pop(0) if self.modifier_polls else False

    def type_text(self, text):
        self.events.append(("text", text))
        if self.windows_after_text is not None:
            self.window = self.windows_after_text
        return self.text_ok

    def press_enter(self):
        self.events.append(("enter",))
        return True


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class TyperCase(unittest.TestCase):
    def setUp(self):
        self.backend = FakeBackend()
        self.clock = Clock()
        self.statuses = []
        self.typer = KeyboardTyper(backend=self.backend, on_status=self.statuses.append, own_pid=OWN_PID,
                                   monotonic=self.clock, sleep=self.clock.sleep, autostart=False)
        self.typer.set_enabled(True)

    def type_code(self, text):
        accepted = self.typer.submit(text)
        self.typer.drain()
        return accepted

    @property
    def reasons(self):
        return [s.reason for s in self.statuses]


class TypingTests(TyperCase):
    def test_types_code_then_presses_enter(self):
        self.assertTrue(self.type_code("ABC-123"))
        self.assertEqual(self.backend.events, [("text", "ABC-123"), ("enter",)])
        self.assertEqual(self.reasons, [REASON_TYPED])
        self.assertTrue(self.statuses[0].ok)

    def test_waits_before_enter_so_target_can_process_text(self):
        self.type_code("A")
        self.assertGreater(self.clock.now, 1000.0)

    def test_codes_are_typed_in_read_order(self):
        self.typer.submit("A")
        self.typer.submit("B")
        self.typer.drain()
        self.assertEqual(self.backend.events, [("text", "A"), ("enter",), ("text", "B"), ("enter",)])

    def test_disabled_by_default(self):
        typer = KeyboardTyper(backend=self.backend, own_pid=OWN_PID, autostart=False)
        self.assertFalse(typer.submit("A"))
        typer.drain()
        self.assertEqual(self.backend.events, [])

    def test_empty_code_is_ignored(self):
        self.assertFalse(self.type_code(""))
        self.assertFalse(self.type_code(None))
        self.assertEqual(self.backend.events, [])

    def test_control_characters_cannot_press_enter_early(self):
        self.type_code("AB\r\nC\tD\x00")
        self.assertEqual(self.backend.events, [("text", "ABCD"), ("enter",)])

    def test_code_of_only_control_characters_is_ignored(self):
        self.assertFalse(self.type_code("\r\n"))
        self.assertEqual(self.backend.events, [])

    def test_sanitize_keeps_unicode(self):
        self.assertEqual(sanitize("Mã Số 😀"), "Mã Số 😀")


class DuplicateTests(TyperCase):
    def test_same_code_within_30_seconds_is_typed_once(self):
        self.type_code("A")
        self.clock.now += 29
        self.assertFalse(self.type_code("A"))
        self.assertEqual(self.backend.events.count(("text", "A")), 1)

    def test_same_code_after_30_seconds_is_typed_again(self):
        self.type_code("A")
        self.clock.now += 31
        self.assertTrue(self.type_code("A"))
        self.assertEqual(self.backend.events.count(("text", "A")), 2)

    def test_skipped_code_is_not_remembered_as_typed(self):
        self.backend.window = (6000, OWN_PID)
        self.type_code("A")
        self.backend.window = OTHER_WINDOW
        self.assertTrue(self.type_code("A"))
        self.assertEqual(self.backend.events, [("text", "A"), ("enter",)])


class GuardTests(TyperCase):
    def assert_skipped(self, reason):
        self.assertEqual(self.reasons, [reason])
        self.assertFalse(self.statuses[0].ok)

    def test_own_window_gets_no_keys(self):
        self.backend.window = (6000, OWN_PID)
        self.type_code("A")
        self.assertEqual(self.backend.events, [])
        self.assert_skipped(REASON_OWN_WINDOW)

    def test_no_foreground_window_gets_no_keys(self):
        self.backend.window = (0, 0)
        self.type_code("A")
        self.assertEqual(self.backend.events, [])
        self.assert_skipped(REASON_NO_WINDOW)

    def test_waits_for_short_modifier_press(self):
        self.backend.modifier_polls = [True, True, False]
        self.type_code("A")
        self.assertEqual(self.backend.events, [("text", "A"), ("enter",)])

    def test_held_modifier_skips_code(self):
        self.backend.modifier_polls = [True] * 1000
        self.type_code("A")
        self.assertEqual(self.backend.events, [])
        self.assert_skipped(REASON_MODIFIER)

    def test_window_change_while_typing_blocks_enter(self):
        self.backend.windows_after_text = (7000, OTHER_PID)
        self.type_code("A")
        self.assertEqual(self.backend.events, [("text", "A")])
        self.assert_skipped(REASON_FOCUS_CHANGED)

    def test_failed_send_blocks_enter(self):
        self.backend.text_ok = False
        self.type_code("A")
        self.assertEqual(self.backend.events, [("text", "A")])
        self.assert_skipped(REASON_SEND_FAILED)

    def test_backend_exception_does_not_stop_typer(self):
        def boom(_text):
            raise OSError("user32")
        original, self.backend.type_text = self.backend.type_text, boom
        self.type_code("A")
        self.assert_skipped(REASON_SEND_FAILED)
        self.backend.type_text = original
        self.type_code("B")
        self.assertEqual(self.backend.events, [("text", "B"), ("enter",)])


class SwitchTests(TyperCase):
    def test_turning_off_drops_queued_codes(self):
        self.typer.submit("A")
        self.typer.set_enabled(False)
        self.typer.drain()
        self.assertEqual(self.backend.events, [])

    def test_turning_off_during_modifier_wait_types_nothing(self):
        typer = self.typer

        class Backend(FakeBackend):
            def modifiers_held(self):
                typer.set_enabled(False)
                return False

        typer._backend = Backend()
        typer.submit("A")
        typer.drain()
        self.assertEqual(typer._backend.events, [])

    def test_dropped_code_can_be_typed_after_turning_on_again(self):
        self.typer.submit("A")
        self.typer.set_enabled(False)
        self.typer.drain()
        self.typer.set_enabled(True)
        self.assertTrue(self.type_code("A"))
        self.assertEqual(self.backend.events, [("text", "A"), ("enter",)])

    def test_stopped_typer_refuses_codes(self):
        self.typer.stop()
        self.assertFalse(self.type_code("A"))
        self.assertEqual(self.backend.events, [])

    def test_background_thread_types_and_stops(self):
        statuses = []
        import threading
        finished = threading.Event()

        def on_status(status):
            statuses.append(status)
            finished.set()

        typer = KeyboardTyper(backend=self.backend, on_status=on_status, own_pid=OWN_PID, enter_delay_s=0)
        typer.set_enabled(True)
        typer.submit("A")
        self.assertTrue(finished.wait(2))
        typer.stop()
        self.assertFalse(typer._thread.is_alive())
        self.assertEqual(self.backend.events, [("text", "A"), ("enter",)])


class Win32StructTests(unittest.TestCase):
    def test_input_struct_has_size_windows_expects(self):
        # sai kích thước thì SendInput trả 0 và không gõ gì, không báo lỗi rõ ràng
        expected = 40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28
        self.assertEqual(ctypes.sizeof(INPUT), expected)

    def units(self, text):
        return [(item.ki.wScan, item.ki.dwFlags) for item in text_inputs(text)]

    def test_each_character_is_unicode_key_down_then_up(self):
        self.assertEqual(self.units("Aé"), [(0x41, 4), (0x41, 6), (0xE9, 4), (0xE9, 6)])

    def test_character_outside_bmp_is_sent_as_surrogate_pair(self):
        self.assertEqual([scan for scan, flags in self.units("😀") if flags == 4], [0xD83D, 0xDE00])


if __name__ == "__main__":
    unittest.main()
