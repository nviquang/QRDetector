# -*- coding: utf-8 -*-
"""Chung: nạp pyzbar với đúng đường dẫn DLL, cung cấp try_decode + hàm đếm."""
import os
import sys

# --- Fix pyzbar DLL loading trên Windows ---
try:
    pkgdir = os.path.join(os.path.dirname(__file__), ".venv", "Lib", "site-packages", "pyzbar")
    if os.path.isdir(pkgdir):
        os.add_dll_directory(os.path.abspath(pkgdir))
except Exception:
    pass

import cv2
import numpy as np
from pyzbar import pyzbar


def decode_gray(gray):
    """pyzbar.decode() kèm fallback grayscale/contiguous."""
    return pyzbar.decode(gray)


def try_decode(gray_roi):
    """Pipeline-h style: upscale x4 + otsu + border, trả payload hoặc 'FAIL'."""
    big = cv2.resize(gray_roi, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
    attempts = [big]
    _, otsu = cv2.threshold(big, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    attempts.append(otsu)
    attempts.append(cv2.copyMakeBorder(otsu, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=255))
    for a in attempts:
        d = decode_gray(a)
        if d:
            return d[0].data.decode("utf-8", errors="replace")
    return "FAIL"


def props(gray):
    """Độ nét (Laplacian) + mean/std độ sáng."""
    lap = cv2.Laplacian(gray, cv2.CV_64F).var()
    return lap, float(gray.mean()), float(gray.std())