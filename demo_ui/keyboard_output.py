"""Gõ mã QR vào ô đang focus của ứng dụng khác rồi nhấn Enter, như máy quét mã vạch USB.

Dùng SendInput với KEYEVENTF_UNICODE nên không phụ thuộc layout bàn phím hay bộ gõ tiếng Việt.
Windows không cho biết focus có thật sự nằm trong ô nhập hay không (nhất là trên trình duyệt),
nên các lớp chặn ở đây chỉ tránh gõ nhầm cửa sổ. Ứng dụng chạy quyền Administrator chặn phím từ
tiến trình quyền thấp hơn.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass
import logging
import os
import queue
import struct
import threading
import time
import unicodedata

logger = logging.getLogger("solution.keyboard")

REASON_TYPED = "typed"
REASON_OWN_WINDOW = "own_window"
REASON_NO_WINDOW = "no_window"
REASON_MODIFIER = "modifier"
REASON_FOCUS_CHANGED = "focus_changed"
REASON_SEND_FAILED = "send_failed"

DEDUPE_S = 30.0
ENTER_DELAY_S = 0.03         # để ứng dụng đích xử lý xong chữ trước khi nhận Enter
MODIFIER_WAIT_S = 0.3
MODIFIER_POLL_S = 0.02

_SKIP_TEXT = {
    REASON_OWN_WINDOW: "đang chọn cửa sổ app",
    REASON_NO_WINDOW: "không có cửa sổ được chọn",
    REASON_MODIFIER: "đang giữ Ctrl/Alt/Shift/Win",
    REASON_FOCUS_CHANGED: "cửa sổ đổi, chưa nhấn Enter",
    REASON_SEND_FAILED: "Windows từ chối phím",
}


@dataclass(frozen=True)
class KeyStatus:
    text: str
    reason: str

    @property
    def ok(self) -> bool:
        return self.reason == REASON_TYPED

    @property
    def message(self) -> str:
        return "Đã gõ {}".format(self.text) if self.ok else "Chưa gõ {}: {}".format(self.text, _SKIP_TEXT[self.reason])


def sanitize(text: str) -> str:
    """Bỏ ký tự điều khiển: xuống dòng hay tab trong mã sẽ nhấn phím sớm ở ứng dụng đích."""
    return "".join(c for c in text if unicodedata.category(c) != "Cc")


class KeyboardTyper:
    """Hàng đợi và thread nền gõ từng mã. Mặc định tắt; chỉ gõ sau ``set_enabled(True)``."""

    def __init__(self, backend=None, on_status=None, own_pid: int | None = None, dedupe_s: float = DEDUPE_S,
                 enter_delay_s: float = ENTER_DELAY_S, modifier_wait_s: float = MODIFIER_WAIT_S,
                 monotonic=time.monotonic, sleep=time.sleep, autostart: bool = True):
        self._backend = backend if backend is not None else Win32Keyboard()
        self.on_status = on_status
        self._own_pid = os.getpid() if own_pid is None else own_pid
        self._dedupe_s = dedupe_s
        self._enter_delay_s = enter_delay_s
        self._modifier_wait_s = modifier_wait_s
        self._monotonic = monotonic
        self._sleep = sleep
        self._queue: queue.Queue = queue.Queue()
        self._seen: dict[str, float] = {}
        self._lock = threading.Lock()
        self._enabled = False
        self._stopped = False
        self._thread = None
        if autostart:
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()

    def submit(self, text: str | None) -> bool:
        """Đưa mã vào hàng đợi; False nếu bị bỏ qua (rỗng, trùng trong 30 giây, đang tắt, đã dừng)."""
        text = sanitize(text or "")
        if not text:
            return False
        with self._lock:
            if self._stopped or not self._enabled:
                return False
            now = self._monotonic()
            self._seen = {k: t for k, t in self._seen.items() if now - t < self._dedupe_s}
            if text in self._seen:
                return False
            self._seen[text] = now
            self._queue.put(text)
        return True

    def set_enabled(self, enabled: bool):
        """Tắt: bỏ các mã đang chờ; mã đang gõ dở không thu hồi được."""
        with self._lock:
            if self._stopped:
                return
            self._enabled = enabled
            if not enabled:
                self._clear_queue()

    def drain(self):
        """Gõ hết hàng đợi trên thread hiện tại (chế độ autostart=False)."""
        while True:
            try:
                text = self._queue.get_nowait()
            except queue.Empty:
                return
            if text is not None:
                self._process(text)

    def stop(self, timeout: float = 2.0):
        with self._lock:
            if self._stopped:
                return
            self._stopped = True
            self._enabled = False
            self._clear_queue()
            self._queue.put(None)
        if self._thread is not None:
            self._thread.join(timeout)

    def _clear_queue(self):
        while True:
            try:
                text = self._queue.get_nowait()
            except queue.Empty:
                return
            self._seen.pop(text, None)

    def _loop(self):
        while True:
            text = self._queue.get()
            if text is None:
                return
            self._process(text)

    def _process(self, text: str):
        try:
            reason = self._type(text)
        except Exception as exc:                  # lỗi một mã không được làm chết thread
            logger.warning("keyboard_error text=%s error=%s", text, exc)
            reason = REASON_SEND_FAILED
        if reason is None:                        # bị tắt giữa chừng
            with self._lock:
                self._seen.pop(text, None)
            return
        if reason == REASON_TYPED:
            logger.info("keyboard_typed text=%s", text)
        else:
            with self._lock:
                self._seen.pop(text, None)        # chưa gõ xong thì lượt sau được gõ lại
            logger.warning("keyboard_skipped text=%s reason=%s", text, reason)
        if self.on_status is not None:
            self.on_status(KeyStatus(text, reason))

    def _type(self, text: str) -> str | None:
        modifiers_released = self._wait_modifiers_released()
        with self._lock:
            if not self._enabled:
                return None
        if not modifiers_released:
            return REASON_MODIFIER
        # đọc cửa sổ sau khi nhả phím: Alt+Tab đang giữ thì cửa sổ còn đổi
        window, pid = self._backend.foreground()
        if not window:
            return REASON_NO_WINDOW
        if pid == self._own_pid:
            return REASON_OWN_WINDOW
        if not self._backend.type_text(text):
            return REASON_SEND_FAILED
        self._sleep(self._enter_delay_s)
        if self._backend.foreground() != (window, pid):
            return REASON_FOCUS_CHANGED
        return REASON_TYPED if self._backend.press_enter() else REASON_SEND_FAILED

    def _wait_modifiers_released(self) -> bool:
        deadline = self._monotonic() + self._modifier_wait_s
        while self._backend.modifiers_held():
            if self._monotonic() >= deadline:
                return False
            self._sleep(MODIFIER_POLL_S)
        return True


# ── Win32 ─────────────────────────────────────────────────────────────────────

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
VK_RETURN = 0x0D
SCAN_RETURN = 0x1C
MODIFIER_KEYS = (0x10, 0x11, 0x12, 0x5B, 0x5C)      # Shift, Ctrl, Alt, Win trái, Win phải
ULONG_PTR = ctypes.c_size_t


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]


class _InputUnion(ctypes.Union):
    # đủ cả ba thành viên: thiếu thì sizeof(INPUT) sai và SendInput không gõ gì
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _InputUnion)]


def _key(vk: int, scan: int, flags: int) -> INPUT:
    item = INPUT(type=INPUT_KEYBOARD)
    item.ki = KEYBDINPUT(wVk=vk, wScan=scan, dwFlags=flags)
    return item


def text_inputs(text: str):
    """Mỗi đơn vị UTF-16 là một lần nhấn và nhả; ký tự ngoài BMP thành cặp surrogate."""
    data = text.encode("utf-16-le")
    keys = []
    for unit in struct.unpack("<{}H".format(len(data) // 2), data):
        keys.append(_key(0, unit, KEYEVENTF_UNICODE))
        keys.append(_key(0, unit, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP))
    return (INPUT * len(keys))(*keys)


class Win32Keyboard:
    def __init__(self):
        user32 = ctypes.WinDLL("user32", use_last_error=True)     # bản riêng, không đụng argtypes của windll
        user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
        user32.SendInput.restype = wintypes.UINT
        user32.GetForegroundWindow.argtypes = ()
        user32.GetForegroundWindow.restype = wintypes.HWND
        user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        user32.GetAsyncKeyState.argtypes = (ctypes.c_int,)
        user32.GetAsyncKeyState.restype = wintypes.SHORT
        self._user32 = user32

    def foreground(self) -> tuple[int, int]:
        """(hwnd, pid) của cửa sổ đang được chọn; (0, 0) nếu không có."""
        window = self._user32.GetForegroundWindow()
        if not window:
            return 0, 0
        pid = wintypes.DWORD()
        self._user32.GetWindowThreadProcessId(window, ctypes.byref(pid))
        return int(window), pid.value

    def modifiers_held(self) -> bool:
        return any(self._user32.GetAsyncKeyState(key) & 0x8000 for key in MODIFIER_KEYS)

    def _send(self, inputs) -> bool:
        return self._user32.SendInput(len(inputs), inputs, ctypes.sizeof(INPUT)) == len(inputs)

    def type_text(self, text: str) -> bool:
        return self._send(text_inputs(text))

    def press_enter(self) -> bool:
        return self._send((INPUT * 2)(_key(VK_RETURN, SCAN_RETURN, 0),
                                      _key(VK_RETURN, SCAN_RETURN, KEYEVENTF_KEYUP)))
