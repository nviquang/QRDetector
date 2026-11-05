"""Bước 3 & 6: Multi-decoder song song — pyzbar, zxing-cpp, OpenCV."""

from __future__ import annotations

import concurrent.futures
import os

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


# ── Decoder cho ROI QR nhỏ (dùng trong cascade của ImprovePipeline) ─────────

_WECHAT_MODEL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models", "wechat")
_wechat_cnn_detector = None
_wechat_cnn_loaded = False


def _zxing_corners(barcode) -> np.ndarray:
    p = barcode.position
    return np.array([[p.top_left.x, p.top_left.y], [p.top_right.x, p.top_right.y],
                     [p.bottom_right.x, p.bottom_right.y], [p.bottom_left.x, p.bottom_left.y]],
                    np.float32)


def read_zxing_gray(gray: np.ndarray, binarizer=None) -> tuple[str, np.ndarray] | None:
    """zxing-cpp, mặc định binarizer LocalAverage — rất nhanh (~1ms) trên ROI đã upscale.

    Trả (nội dung, 4 góc QR (4, 2) trong tọa độ ``gray``) hoặc None.
    """
    options = {} if binarizer is None else {"binarizer": binarizer}
    for b in zxingcpp.read_barcodes(gray, formats=zxingcpp.BarcodeFormat.QRCode, try_rotate=True, **options):
        if b.valid and b.text:
            return b.text, _zxing_corners(b)
    return None


def decode_zxing_gray(gray: np.ndarray) -> str | None:
    hit = read_zxing_gray(gray)
    return hit[0] if hit else None


def _get_wechat_cnn_detector():
    """WeChatQRCode có CNN detector + super-resolution (model ONNX cho OpenCV 5).

    Load 1 lần; nếu thiếu model hoặc lỗi load thì trả về None (cascade bỏ qua bước CNN).
    """
    global _wechat_cnn_detector, _wechat_cnn_loaded
    if not _wechat_cnn_loaded:
        _wechat_cnn_loaded = True
        detect_path = os.path.join(_WECHAT_MODEL_DIR, "detect.onnx")
        sr_path = os.path.join(_WECHAT_MODEL_DIR, "sr.onnx")
        if hasattr(cv2, "wechat_qrcode_WeChatQRCode") and os.path.isfile(detect_path) and os.path.isfile(sr_path):
            try:
                # Model ONNX in WARN "Shape mismatch ... Clamping" mỗi lần chạy (vô hại) → chỉ log ERROR
                cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_ERROR)
                _wechat_cnn_detector = cv2.wechat_qrcode_WeChatQRCode(detect_path, sr_path)
            except Exception:
                _wechat_cnn_detector = None
    return _wechat_cnn_detector


def read_wechat_gray(gray: np.ndarray, use_cnn: bool = False) -> tuple[str, np.ndarray] | None:
    """WeChatQRCode một lần (không xoay — WeChat tự xử lý hướng). use_cnn=True dùng CNN + SR.

    Trả (nội dung, 4 góc QR (4, 2) trong tọa độ ``gray``) hoặc None.
    """
    detector = _get_wechat_cnn_detector() if use_cnn else _get_wechat_detector()
    if detector is None:
        return None
    try:
        texts, points = detector.detectAndDecode(gray)
    except Exception:
        return None
    for text, pts in zip(texts, points):
        if text:
            return text, np.asarray(pts, np.float32).reshape(4, 2)
    return None


def decode_wechat_gray(gray: np.ndarray, use_cnn: bool = False) -> str | None:
    hit = read_wechat_gray(gray, use_cnn)
    return hit[0] if hit else None


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
