"""Tiền xử lý ảnh cho QR decode: Sharpen, Unsharp Mask, Upscale 2x + Otsu, Upscale 2x + Adaptive Threshold."""

from __future__ import annotations

import cv2
import numpy as np


def sharpen_laplacian(image_bgr: np.ndarray) -> np.ndarray:
    """Làm nét ảnh bằng toán tử Laplacian."""
    kernel = np.array([
        [0, -1, 0],
        [-1, 5, -1],
        [0, -1, 0],
    ], dtype=np.float32)
    return cv2.filter2D(image_bgr, -1, kernel)


def unsharp_masking(image_bgr: np.ndarray) -> np.ndarray:
    """Làm nét ảnh bằng Unsharp Masking (Gaussian blur sigma=3)."""
    gaussian_blur = cv2.GaussianBlur(image_bgr, (0, 0), 3)
    return cv2.addWeighted(image_bgr, 1.5, gaussian_blur, -0.5, 0)


def upscale_otsu(image_bgr: np.ndarray, scale: float = 2.0, pad_px: int = 64) -> np.ndarray:
    """
    Upscale ảnh bằng nội suy bicubic và áp dụng Otsu Threshold.
    Tự động đệm Quiet Zone viền trắng pad_px (mặc định 64) sau khi threshold.
    Trả về ảnh BGR 3 kênh.
    """
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY) if image_bgr.ndim == 3 else image_bgr
    upscaled = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    _, binary = cv2.threshold(upscaled, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    if pad_px > 0:
        binary = cv2.copyMakeBorder(binary, pad_px, pad_px, pad_px, pad_px, cv2.BORDER_CONSTANT, value=255)
    return cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)


def upscale_adaptive(
    image_bgr: np.ndarray,
    scale: float = 2.0,
    block_size: int = 101,
    c: int = 7,
    pad_px: int = 64,
) -> np.ndarray:
    """
    Upscale ảnh bằng nội suy bicubic và áp dụng Adaptive Gaussian Threshold.
    Tự động đệm Quiet Zone viền trắng pad_px (mặc định 64) sau khi threshold.
    Trả về ảnh BGR 3 kênh.
    """
    if block_size % 2 == 0:
        block_size += 1  # blockSize phải là số lẻ > 1

    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY) if image_bgr.ndim == 3 else image_bgr
    upscaled = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    binary = cv2.adaptiveThreshold(
        upscaled, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        blockSize=block_size,
        C=c,
    )
    if pad_px > 0:
        binary = cv2.copyMakeBorder(binary, pad_px, pad_px, pad_px, pad_px, cv2.BORDER_CONSTANT, value=255)
    return cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)
