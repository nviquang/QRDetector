"""Offline pixel comparison; frame alignment is explicit, never inferred from FPS."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from camera.color_diagnostics import compare_bgr


def read_png(path):
    image = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"Cannot read PNG: {path}")
    return image


def read_frame(path, index):
    capture = cv2.VideoCapture(str(path))
    try:
        if not capture.isOpened():
            raise ValueError(f"Cannot open AVI: {path}")
        # Sequential decode avoids relying on backend-specific frame seeking.
        for ordinal in range(index + 1):
            ok, image = capture.read()
            if not ok:
                raise ValueError(f"AVI ended or decoding failed at frame {ordinal}.")
        return image
    finally:
        capture.release()


def show_pair(reference, decoded):
    from PyQt5.QtCore import Qt
    from PyQt5.QtGui import QImage, QPixmap
    from PyQt5.QtWidgets import QApplication, QHBoxLayout, QLabel, QVBoxLayout, QWidget

    app = QApplication.instance() or QApplication([])
    window = QWidget()
    window.setWindowTitle("Source / decoded AVI — same RGB renderer")
    layout = QHBoxLayout(window)
    for title, image in (("Source before SDK Push", reference), ("Decoded AVI", decoded)):
        column = QVBoxLayout()
        column.addWidget(QLabel(title))
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        height, width = rgb.shape[:2]
        qimage = QImage(rgb.data, width, height, rgb.strides[0], QImage.Format_RGB888).copy()
        label = QLabel()
        label.setPixmap(QPixmap.fromImage(qimage).scaled(
            600, 500, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        column.addWidget(label)
        layout.addLayout(column)
    window.show()
    app.exec_()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument("sample", type=Path, help="color_diagnostics/sample_0001 directory")
    parser.add_argument("--frame", required=True, type=int, help="Decoded AVI frame index, zero-based")
    parser.add_argument("--matched", action="store_true",
                        help="You independently confirmed the same source/video frame by content or counter")
    parser.add_argument("--view", action="store_true", help="Show both images through the same Qt renderer")
    args = parser.parse_args()
    if args.frame < 0:
        parser.error("--frame must be nonnegative")
    try:
        metadata = json.loads((args.sample / "metadata.json").read_text(encoding="utf-8"))
        reference = read_png(args.sample / "before.png")
        after_path = args.sample / "after.png"
        # Older diagnostics named their post-Push reference preview.png.
        if not after_path.exists() and "preview_source" not in metadata:
            after_path = args.sample / "preview.png"
        after = read_png(after_path)
        decoded = read_frame(args.video, args.frame)
        metrics = compare_bgr(reference, decoded)
        after_metrics = compare_bgr(after, decoded)
        if not args.matched:
            interpretation = "UNALIGNED: metrics only; cannot diagnose color until matching is confirmed."
        elif not metadata.get("push_succeeded"):
            interpretation = "Sample Push failed; not evidence of a successfully recorded matching frame."
        elif metrics["identical"]:
            interpretation = "Matched AVI pixels equal source; investigate player rendering if VLC differs."
        elif after_metrics["identical"] and metadata.get("buffer_changed"):
            interpretation = "AVI equals post-Push but not source; native buffer mutation boundary needs investigation."
        elif max(metrics["swapped_rb_max_abs_bgr"]) == 0:
            interpretation = "Matched pixels fit an exact R/B swap; verify SDK input/output media contract."
        else:
            interpretation = "Matched pixels differ; inspect packing/orientation, SDK conversion and neutral patches."
        report = {
            "video": str(args.video.resolve()),
            "sample": str(args.sample.resolve()),
            "decoded_frame_index": args.frame,
            "alignment_confirmed_by_user": args.matched,
            "push_ordinal_not_frame_index": metadata.get("push_ordinal"),
            "source_timestamp": metadata.get("before_header", {}).get("uiTimeStamp"),
            "native_buffer_changed": metadata.get("buffer_changed"),
            "source_vs_avi": metrics,
            "post_push_vs_avi": after_metrics,
            "interpretation": interpretation,
            "note": "No resizing, channel compensation or color correction applied to metrics.",
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
        if args.view:
            show_pair(reference, decoded)
    except (OSError, ValueError, cv2.error) as exc:
        parser.exit(1, f"Comparison failed: {exc}\n")


if __name__ == "__main__":
    main()
