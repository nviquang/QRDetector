"""Tính nhanh thông số camera cho băng chuyền: px/ô, exposure tối đa, số frame mỗi QR.

Chạy:
  python offline/tools/conveyor_calc.py --mm-per-px 0.43
  python offline/tools/conveyor_calc.py --fov-mm 1650 --fov-px 2448 --fps 15 --blur 1 2
  python offline/tools/conveyor_calc.py --mm-per-px 0.43 --exposure-ms 20   # vệt mờ với exposure đang dùng

Công thức dùng chung với app camera: ``solution/camera/conveyor.py``.
"""

from __future__ import annotations

import argparse
import os
import sys

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_REPO, "solution"))

from camera.conveyor import (SPEEDS_MM_S, blur_px, frames_in_view,  # noqa: E402
                             max_exposure_us, px_per_module)


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):   # console Windows mặc định cp1252
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--mm-per-px", type=float, help="mm trên mỗi pixel (đo bằng thước trên băng)")
    p.add_argument("--fov-mm", type=float, help="bề rộng vùng nhìn (mm) — dùng cùng --fov-px nếu chưa có mm/px")
    p.add_argument("--fov-px", type=int, default=2448, help="số pixel ứng với --fov-mm")
    p.add_argument("--along-px", type=int, default=2448, help="số pixel theo hướng băng chạy (độ rộng khung/ROI)")
    p.add_argument("--qr-mm", type=float, default=25.0)
    p.add_argument("--modules", type=int, default=21, help="số ô mỗi cạnh QR (version 1 = 21)")
    p.add_argument("--fps", type=float, default=15.0, help="FPS camera thực tế")
    p.add_argument("--blur", type=float, nargs="+", default=[1.0], help="vệt mờ cho phép (px)")
    p.add_argument("--speeds", type=float, nargs="+", default=list(SPEEDS_MM_S), help="tốc độ băng (mm/s)")
    p.add_argument("--exposure-ms", type=float, help="exposure đang dùng → in vệt mờ tương ứng")
    a = p.parse_args(argv)

    if a.mm_per_px is None:
        if a.fov_mm is None:
            p.error("cần --mm-per-px hoặc --fov-mm")
        a.mm_per_px = a.fov_mm / a.fov_px
    ppm = px_per_module(a.mm_per_px, a.qr_mm, a.modules)
    along_mm = a.along_px * a.mm_per_px
    print(f"mm/px = {a.mm_per_px:.3f}   QR {a.qr_mm:.0f} mm = {a.qr_mm / a.mm_per_px:.0f} px   "
          f"= {ppm:.2f} px/ô ({a.modules}×{a.modules})")
    verdict = ("đủ (≥ 2.4 px/ô)" if ppm >= 2.4 else
               "sát ngưỡng — cần ảnh rất nét + gộp nhiều frame" if ppm >= 1.8 else
               "dưới ngưỡng decode từng frame")
    print(f"Đánh giá độ phân giải: {verdict}")
    print(f"Vùng nhìn theo hướng chạy: {along_mm / 10:.0f} cm ({a.along_px} px) @ {a.fps:g} fps\n")

    head = f"{'tốc độ':>8} {'frame/QR':>9} " + " ".join(f"{'exp≤ (mờ ' + format(b, 'g') + 'px)':>16}" for b in a.blur)
    if a.exposure_ms:
        head += f" {'mờ @ ' + format(a.exposure_ms, 'g') + 'ms':>12}"
    print(head)
    print("-" * len(head))
    for v in a.speeds:
        row = f"{v / 10:>5.0f}cm/s {frames_in_view(along_mm, v, a.fps, a.qr_mm):>9.0f} "
        row += " ".join(f"{max_exposure_us(v, a.mm_per_px, b) / 1000:>14.2f}ms" for b in a.blur)
        if a.exposure_ms:
            row += f" {blur_px(v, a.mm_per_px, a.exposure_ms * 1000):>10.1f}px"
        print(row)
    return 0


if __name__ == "__main__":
    sys.exit(main())
