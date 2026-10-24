"""Bounded, opt-in copies at the native recorder boundary; no color correction."""
from __future__ import annotations

import ctypes
import json
import logging
from pathlib import Path
import threading
import time

import cv2
import numpy as np

logger = logging.getLogger("solution.camera.color_diagnostics")
HEADER_FIELDS = (
    "uiMediaType", "uBytes", "iWidth", "iHeight", "iWidthZoomSw", "iHeightZoomSw",
    "bIsTrigger", "uiTimeStamp", "uiExpTime", "fAnalogGain", "iGamma", "iContrast",
    "iSaturation", "fRgain", "fGgain", "fBgain",
)


def header_values(info):
    return {name: getattr(info, name, None) for name in HEADER_FIELDS}


def reference_bgr(data, width, height, interpretation):
    if interpretation not in ("RGB8", "MONO8"):
        raise ValueError("Unsupported diagnostic interpretation: " + interpretation)
    channels = 1 if interpretation == "MONO8" else 3
    if width <= 0 or height <= 0 or len(data) != width * height * channels:
        raise ValueError("Diagnostic payload does not match tightly packed dimensions.")
    image = np.frombuffer(data, dtype=np.uint8)
    if channels == 1:
        return cv2.cvtColor(image.reshape(height, width), cv2.COLOR_GRAY2BGR)
    return cv2.cvtColor(image.reshape(height, width, 3), cv2.COLOR_RGB2BGR)


def compare_bgr(reference, decoded):
    if (reference.shape != decoded.shape or reference.ndim != 3
            or reference.shape[2] != 3 or reference.dtype != np.uint8
            or decoded.dtype != np.uint8 or not reference.size):
        raise ValueError("Expected equally sized, nonempty uint8 BGR images.")
    delta = np.abs(reference.astype(np.int16) - decoded.astype(np.int16))
    swapped = np.abs(reference.astype(np.int16) - decoded[:, :, ::-1].astype(np.int16))
    return {
        "identical": bool(not delta.any()),
        "mean_abs_bgr": delta.mean(axis=(0, 1)).tolist(),
        "max_abs_bgr": delta.max(axis=(0, 1)).tolist(),
        "swapped_rb_mean_abs_bgr": swapped.mean(axis=(0, 1)).tolist(),
        "swapped_rb_max_abs_bgr": swapped.max(axis=(0, 1)).tolist(),
    }


class ColorDiagnostics:
    """At most three owned samples/writers, bounded total memory, never native pointers."""

    def __init__(self, directory, *, max_samples=3, max_bytes=256 * 1024 ** 2):
        if not 1 <= max_samples <= 3 or max_bytes <= 0:
            raise ValueError("Diagnostic limits must allow 1–3 samples and positive memory.")
        self.directory = Path(directory)
        self.max_samples = max_samples
        self.max_bytes = max_bytes
        self._count = 0
        self._reserved = 0
        self._closed = False
        self._threads = []
        self._errors = []
        self._saved = 0
        self._lock = threading.Lock()

    @property
    def errors(self):
        with self._lock:
            return tuple(self._errors)

    def status_text(self):
        with self._lock:
            saved, errors = self._saved, tuple(self._errors)
        text = f"Mẫu màu đã lưu: {saved}/{self._count} | {self.directory}"
        if any(worker.is_alive() for worker in tuple(self._threads)):
            text += " | đang lưu mẫu (độc lập với finalize video)"
        if errors:
            text += " | Lỗi chẩn đoán: " + errors[-1]
        return text

    def report_error(self, exc):
        message = str(exc) or type(exc).__name__
        with self._lock:
            self._errors.append(message)
        logger.warning("color_diagnostic_error: %s", message)

    def before(self, pointer, byte_count, info, interpretation, ordinal, context):
        if self._closed or self._count >= self.max_samples:
            return None
        # Two byte copies, converted PNG inputs and encoder workspace; no unbounded queue.
        budget = byte_count * 8
        if byte_count <= 0 or self._reserved + budget > self.max_bytes:
            self._closed = True
            self.report_error(ValueError("Diagnostic memory budget exceeded; recording unchanged."))
            return None
        self._count += 1
        self._reserved += budget
        return {
            "sample": self._count,
            "push_ordinal": ordinal,
            "interpretation": interpretation,
            "layout_assumption": "tightly packed, top-down; same interpretation as current preview",
            "copied_bytes": byte_count,
            "before_header": header_values(info),
            "context": context,
            "before": ctypes.string_at(pointer, byte_count),
        }

    def after(self, sample, pointer, byte_count, info, succeeded):
        if sample is None:
            return
        sample["after"] = ctypes.string_at(pointer, byte_count)
        sample["after_header"] = header_values(info)
        sample["push_succeeded"] = bool(succeeded)
        # Threads own only copies. No filesystem access or joins on the capture owner.
        worker = threading.Thread(target=self._write, args=(sample,), daemon=False)
        self._threads.append(worker)
        worker.start()

    def finish(self):
        self._closed = True

    def wait(self, timeout=None):
        deadline = None if timeout is None else time.monotonic() + timeout
        for worker in self._threads:
            remaining = None if deadline is None else max(0, deadline - time.monotonic())
            worker.join(remaining)
        return all(not worker.is_alive() for worker in self._threads)

    def _write(self, sample):
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            target = self.directory / f"sample_{sample['sample']:04d}"
            target.mkdir(exist_ok=False)
            before = sample.pop("before")
            after = sample.pop("after")
            sample["buffer_changed"] = before != after
            for name, data in (("before", before), ("after", after)):
                (target / f"{name}.bin").write_bytes(data)
            width = sample["before_header"]["iWidth"]
            height = sample["before_header"]["iHeight"]
            sample["preview_source"] = "before Push; source copy used by live preview"
            for name, data in (("before", before), ("preview", before), ("after", after)):
                image = reference_bgr(data, width, height, sample["interpretation"])
                ok, encoded = cv2.imencode(".png", image)
                if not ok:
                    raise OSError("PNG diagnostic encoding failed.")
                (target / f"{name}.png").write_bytes(encoded.tobytes())
            (target / "metadata.json").write_text(
                json.dumps(sample, ensure_ascii=False, indent=2), encoding="utf-8")
            with self._lock:
                self._saved += 1
            logger.info("color_diagnostic_saved path=%s", target)
        except Exception as exc:
            self.report_error(exc)
