"""Gói QR: detector, các bước decode, ImprovePipeline và PassReader.

Lưu ý: nạp DLL pyzbar cho Windows TRƯỚC khi import .decoder.
"""

from __future__ import annotations

import os

# --- Fix pyzbar DLL trên Windows (giống demo.py) ---
if os.name == "nt":
    try:
        import pyzbar  # noqa: F401  (import gói không nạp DLL, add_dll_directory mới nạp)
        os.add_dll_directory(os.path.abspath(os.path.dirname(pyzbar.__file__)))
    except (ImportError, FileNotFoundError, OSError, AttributeError):
        pass

from .detector import Detection, QRDetector
from .improved_pipeline import Decoded, ImprovePipeline
from .pass_reader import FrameResult, Overlay, PassReader

__all__ = ["Detection", "QRDetector", "Decoded", "ImprovePipeline",
           "FrameResult", "Overlay", "PassReader"]
