"""ImprovePipeline: luồng QR cải tiến theo production/improve_main.ipynb — KHÔNG dùng Real-ESRGAN.

Thứ tự:
  1. Detect (qrdet / YOLOv8)
  2. Warp perspective 512 + Quiet Zone 64px
  3. Multi-decoder lần 1 (ảnh warp, sau đó warp + QZ)
  4. Fallback (chỉ khi lần 1 fail): 3 biến thể [Gốc, Laplacian, Unsharp]
     → Upscale 2x + Otsu + Quiet Zone → multi-decoder
"""

from __future__ import annotations

import numpy as np

from .corrector import add_quiet_zone, warp_qr
from .decoder import decode_parallel
from .detector import Detection, QRDetector
from .preprocessor import sharpen_laplacian, unsharp_masking, upscale_otsu


class ImprovePipeline:
    def __init__(
        self,
        model_size: str = "s",
        conf_th: float = 0.5,
        warp_size: int = 512,
        quiet_zone_pad: int = 64,
    ):
        self._detector = QRDetector(model_size=model_size, conf_th=conf_th)
        self._warp_size = warp_size
        self._quiet_zone_pad = quiet_zone_pad

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
        # Bước 2: Warp perspective
        warped = warp_qr(image_bgr, det, out_size=self._warp_size)

        # Bước 3: Multi-decoder lần 1 — ảnh warp, sau đó warp + Quiet Zone 64px
        text = decode_parallel(warped)
        if text:
            return text

        if self._quiet_zone_pad > 0:
            warped_qz = add_quiet_zone(warped, pad_px=self._quiet_zone_pad)
            text = decode_parallel(warped_qz)
            if text:
                return text

        # Bước 4: Fallback 3 biến thể [Gốc, Laplacian, Unsharp] → Otsu + QZ
        variants = (
            warped,
            sharpen_laplacian(warped),
            unsharp_masking(warped),
        )
        for variant in variants:
            otsu = upscale_otsu(variant, scale=2.0, pad_px=self._quiet_zone_pad)
            text = decode_parallel(otsu)
            if text:
                return text
        return None
