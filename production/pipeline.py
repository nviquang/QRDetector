"""Orchestrator: kết nối 6 bước của pipeline QR decode."""

from __future__ import annotations

import numpy as np

from .corrector import add_quiet_zone, warp_qr
from .decoder import decode_parallel
from .detector import QRDetector
from .preprocessor import upscale_adaptive, upscale_otsu
from .super_resolution import SuperResolver


class QRPipeline:
    """
    Pipeline QR:
      1. Detect QR (qrdet)
      2. Warp perspective
      3. Multi-decoder lần 1 (ảnh warp & warp + Quiet Zone 64px, có tự động xoay)
      4. Fallback 1: Upscale 2x + Otsu Threshold + Quiet Zone 64px (trên warp)
      5. Fallback 2: Real-ESRGAN (SR)
         → Upscale 2x + Otsu Threshold + Quiet Zone 64px (trên SR)
      6. Fallback 3: Real-ESRGAN (SR)
         → Upscale 2x + Adaptive Threshold (blockSize=101) + Quiet Zone 64px
    """

    def __init__(
        self,
        model_size: str = "s",
        conf_th: float = 0.5,
        sr_weight_path: str = "weights/RealESRGAN_x4plus.pth",
        warp_size: int = 512,
        quiet_zone_pad: int = 64,
    ):
        self._detector = QRDetector(model_size=model_size, conf_th=conf_th)
        self._sr: SuperResolver | None = None          # lazy-load khi cần
        self._sr_weight_path = sr_weight_path
        self._warp_size = warp_size
        self._quiet_zone_pad = quiet_zone_pad

    # ── public ────────────────────────────────────────────────────────────────

    def decode(self, image_bgr: np.ndarray) -> list[str]:
        """
        Nhận ảnh BGR (np.ndarray H×W×3 uint8).
        Trả về danh sách nội dung QR tìm được (có thể rỗng).
        """
        # Bước 1: Detect
        detections = self._detector.detect(image_bgr)
        if not detections:
            return []

        results: list[str] = []
        for det in detections:
            text = self._decode_one(image_bgr, det)
            if text:
                results.append(text)
        return results

    # ── private ───────────────────────────────────────────────────────────────

    def _decode_one(self, image_bgr: np.ndarray, det) -> str | None:
        # Bước 2: Warp perspective
        warped = warp_qr(image_bgr, det, out_size=self._warp_size)

        # Bước 3: Multi-decoder lần 1 (thử ảnh warp gốc, sau đó thử kèm Quiet Zone 64px)
        text = decode_parallel(warped)
        if text:
            return text

        if self._quiet_zone_pad > 0:
            warped_qz = add_quiet_zone(warped, pad_px=self._quiet_zone_pad)
            text = decode_parallel(warped_qz)
            if text:
                return text

        # Luồng fallback 1: Upscale 2x + Otsu Threshold + Quiet Zone 64px (trên warp)
        otsu_img = upscale_otsu(warped, scale=2.0, pad_px=self._quiet_zone_pad)
        text = decode_parallel(otsu_img)
        if text:
            return text

        # Bước 4: Super-Resolution (Real-ESRGAN fallback)
        sr_img = self._get_sr().upscale(warped)

        # Luồng fallback 2: SR + Upscale 2x + Otsu Threshold + Quiet Zone 64px
        sr_otsu = upscale_otsu(sr_img, scale=2.0, pad_px=self._quiet_zone_pad)
        text = decode_parallel(sr_otsu)
        if text:
            return text

        # Luồng cuối: SR + Upscale 2x + Adaptive Threshold (blockSize=101) + Quiet Zone 64px
        sr_adaptive = upscale_adaptive(sr_img, scale=2.0, block_size=101, pad_px=self._quiet_zone_pad)
        return decode_parallel(sr_adaptive)

    def _get_sr(self) -> SuperResolver:
        """Lazy-load SuperResolver — chỉ khởi tạo khi thực sự cần."""
        if self._sr is None:
            self._sr = SuperResolver(weight_path=self._sr_weight_path)
        return self._sr
