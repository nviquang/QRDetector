"""Bước 3 & 6: Multi-decoder song song — pyzbar, zxing-cpp, OpenCV."""

from __future__ import annotations

import concurrent.futures

import cv2
import numpy as np
import zxingcpp
from pyzbar.pyzbar import decode as _pyzbar_decode


# ── Decoder riêng lẻ ─────────────────────────────────────────────────────────

def _decode_pyzbar(image_bgr: np.ndarray) -> str | None:
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY) if image_bgr.ndim == 3 else image_bgr
    results = _pyzbar_decode(gray)
    for r in results:
        if r.type == "QRCODE":
            return r.data.decode("utf-8", errors="replace")

    # Tự động xoay 90, 180, 270 độ nếu hướng ban đầu chưa decode được
    for rot in (cv2.ROTATE_90_CLOCKWISE, cv2.ROTATE_180, cv2.ROTATE_90_COUNTERCLOCKWISE):
        rotated = cv2.rotate(gray, rot)
        results = _pyzbar_decode(rotated)
        for r in results:
            if r.type == "QRCODE":
                return r.data.decode("utf-8", errors="replace")
    return None


def _decode_zxing(image_bgr: np.ndarray) -> str | None:
    # zxingcpp với cờ tự động xoay và downscale
    try:
        barcodes = zxingcpp.read_barcodes(
            image_bgr,
            formats=zxingcpp.BarcodeFormat.QRCode,
            try_rotate=True,
            try_downscale=True,
        )
        for b in barcodes:
            if b.valid and b.text:
                return b.text
    except Exception:
        try:
            barcodes = zxingcpp.read_barcodes(
                image_bgr,
                formats=zxingcpp.BarcodeFormat.QRCode,
            )
            for b in barcodes:
                if b.valid and b.text:
                    return b.text
        except Exception:
            pass
    return None


def _decode_opencv(image_bgr: np.ndarray) -> str | None:
    detector = cv2.QRCodeDetector()
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    ok, texts, *_ = detector.detectAndDecodeMulti(gray)
    if ok:
        for t in texts:
            if t:
                return t
    return None


_wechat_detector = None


def _get_wechat_detector():
    global _wechat_detector
    if _wechat_detector is None and hasattr(cv2, "wechat_qrcode_WeChatQRCode"):
        try:
            _wechat_detector = cv2.wechat_qrcode_WeChatQRCode()
        except Exception:
            pass
    return _wechat_detector


def _decode_wechat(image_bgr: np.ndarray) -> str | None:
    detector = _get_wechat_detector()
    if detector is None:
        return None
    try:
        texts, _ = detector.detectAndDecode(image_bgr)
        if texts:
            for t in texts:
                if t:
                    return t

        # Tự động xoay 90, 180, 270 độ nếu hướng ban đầu chưa decode được
        for rot in (cv2.ROTATE_90_CLOCKWISE, cv2.ROTATE_180, cv2.ROTATE_90_COUNTERCLOCKWISE):
            rotated = cv2.rotate(image_bgr, rot)
            texts, _ = detector.detectAndDecode(rotated)
            if texts:
                for t in texts:
                    if t:
                        return t
    except Exception:
        pass
    return None


# ── Multi-decoder ─────────────────────────────────────────────────────────────

_DECODERS = [_decode_pyzbar, _decode_zxing, _decode_opencv, _decode_wechat]


def decode_parallel(image_bgr: np.ndarray) -> str | None:
    """Chạy 4 decoder song song, trả về kết quả đầu tiên thành công."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(fn, image_bgr): fn for fn in _DECODERS}
        for fut in concurrent.futures.as_completed(futures):
            try:
                result = fut.result()
                if result:
                    # Huỷ các future còn lại (best-effort)
                    for f in futures:
                        f.cancel()
                    return result
            except Exception:
                pass
    return None
