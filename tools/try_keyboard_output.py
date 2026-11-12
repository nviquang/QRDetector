"""Gõ thử mã mẫu vào ô đang focus, không cần camera hay model.

    python tools/try_keyboard_output.py [--delay 3] [mã ...]

Chạy lệnh, chuyển sang Notepad/Excel/form web và đặt con trỏ vào ô nhập trong lúc đếm ngược.
"""
import argparse
from pathlib import Path
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from demo_ui.keyboard_output import KeyboardTyper  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("codes", nargs="*", default=["TEST-QR-001", "Mã thử 002"])
    parser.add_argument("--delay", type=float, default=3.0, help="số giây chờ trước khi gõ")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    remaining = len(set(args.codes))
    finished = threading.Event()

    def on_status(status):
        nonlocal remaining
        print(status.message)
        remaining -= 1
        if remaining == 0:
            finished.set()

    print("Đặt con trỏ vào ô nhập, sẽ gõ sau {:g} giây…".format(args.delay))
    time.sleep(args.delay)
    typer = KeyboardTyper(on_status=on_status)
    typer.set_enabled(True)
    for code in args.codes:
        typer.submit(code)
    finished.wait(5)
    typer.stop()


if __name__ == "__main__":
    main()
