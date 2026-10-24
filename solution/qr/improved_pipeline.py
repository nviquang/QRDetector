"""ImprovePipeline: luồng QR tối ưu cho QR nhỏ trên frame lớn — KHÔNG dùng Real-ESRGAN.

Thứ tự:
  1. Detect (qrdet / YOLOv8) với imgsz=1280 — imgsz 640 mặc định bỏ sót QR ~60px trên frame 2448×2048
  2. Cascade decode trên ROI cắt từ ảnh gốc, bước rẻ chạy trước, dừng ở bước đầu tiên thành công:
     a. ROI xám × upscale 4x → zxing                   (~1ms)
     b. Warp perspective 256 + Quiet Zone → zxing       (~5ms)
     c. ROI CLAHE × upscale 4x → WeChat                 (~50ms)
     d. ROI stretch × upscale 4x → WeChat CNN + SR      (~55ms)
     e. ROI xám × upscale 3x → WeChat CNN + SR          (~40ms)

Thứ tự cascade chọn từ benchmark trên frame camera thật (images/*.bmp): bỏ pyzbar (yếu với QR
~2px/module) và fallback warp 512 + decode_parallel cũ (~3.6s/frame, gần như không thêm kết quả).
"""

from __future__ import annotations

from typing import Callable

import cv2
import numpy as np

from .corrector import add_quiet_zone, warp_qr
from .decoder import decode_wechat_gray, decode_zxing_gray
from .detector import Detection, QRDetector
from .preprocessor import clahe, crop_roi_gray, stretch_contrast, upscale_gray


def _roi_step(preprocess: Callable[[np.ndarray], np.ndarray], scale: int,
              decode: Callable[[np.ndarray], str | None]):
    def step(image_bgr: np.ndarray, det: Detection, roi_gray: np.ndarray) -> str | None:
        return decode(upscale_gray(preprocess(roi_gray), scale))
    return step


def _warp_zxing_step(image_bgr: np.ndarray, det: Detection, roi_gray: np.ndarray) -> str | None:
    warped = cv2.cvtColor(warp_qr(image_bgr, det, out_size=256), cv2.COLOR_BGR2GRAY)
    return decode_zxing_gray(add_quiet_zone(warped, pad_px=32))


def _identity(gray: np.ndarray) -> np.ndarray:
    return gray


_CASCADE = (
    _roi_step(_identity, 4, decode_zxing_gray),
    _warp_zxing_step,
    _roi_step(clahe, 4, decode_wechat_gray),
    _roi_step(stretch_contrast, 4, lambda g: decode_wechat_gray(g, use_cnn=True)),
    _roi_step(_identity, 3, lambda g: decode_wechat_gray(g, use_cnn=True)),
)


class ImprovePipeline:
    def __init__(
        self,
        model_size: str = "s",
        conf_th: float = 0.3,
        imgsz: int = 1280,
        roi_margin: float = 0.25,
    ):
        self._detector = QRDetector(model_size=model_size, conf_th=conf_th, imgsz=imgsz)
        self._roi_margin = roi_margin

    # ── public ────────────────────────────────────────────────────────────────

    def detect(self, image_bgr: np.ndarray) -> list[Detection]:
        """Chỉ chạy bước detect — dùng để vẽ quad không cần decode."""
        return self._detector.detect(image_bgr)

    def decode(self, image_bgr: np.ndarray) -> list[str]:
        """
        Nhận ảnh BGR (np.ndarray H×W×3 uint8), trả về list nội dung QR (có thể rỗng).
        """
        results, _ = self.scan(image_bgr)
        return results

    def scan(self, image_bgr: np.ndarray) -> tuple[list[str], list[Detection]]:
        """Detect 1 lần, trả về (list nội dung QR, list Detection TẤT CẢ — dùng để vẽ quad)."""
        detections = self._detector.detect(image_bgr)
        if not detections:
            return [], []

        results: list[str] = []
        for det in detections:
            text = self._decode_one(image_bgr, det)
            if text:
                results.append(text)
        return results, detections

    # ── private ───────────────────────────────────────────────────────────────

    def _decode_one(self, image_bgr: np.ndarray, det: Detection) -> str | None:
        roi_gray = crop_roi_gray(image_bgr, det.bbox_xyxy, margin=self._roi_margin)
        if roi_gray.size == 0:
            return None
        for step in _CASCADE:
            text = step(image_bgr, det, roi_gray)
            if text:
                return text
        return None
