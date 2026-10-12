"""Bước 4: Super-Resolution bằng spandrel + Real-ESRGAN weight."""

from __future__ import annotations

import cv2
import numpy as np
import torch
from spandrel import ImageModelDescriptor, ModelLoader

# Đường dẫn mặc định đến weight — người dùng tự chỉnh
DEFAULT_WEIGHT_PATH = "weights/RealESRGAN_x4plus.pth"


class SuperResolver:
    """Wrapper cho Real-ESRGAN qua spandrel. Load model một lần, dùng nhiều lần."""

    def __init__(self, weight_path: str = DEFAULT_WEIGHT_PATH):
        self._device = "cuda" if torch.cuda.is_available() else "cpu"
        model = ModelLoader().load_from_file(weight_path)
        assert isinstance(model, ImageModelDescriptor), (
            f"Model tại {weight_path} không phải ImageModelDescriptor"
        )
        self._model = model.to(self._device).eval()

    def upscale(self, image_bgr: np.ndarray) -> np.ndarray:
        """Nâng độ phân giải ảnh BGR, trả về BGR uint8."""
        rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        x = (
            torch.from_numpy(rgb)
            .float()
            .div(255.0)
            .permute(2, 0, 1)
            .unsqueeze(0)
            .to(self._device)
        )
        with torch.no_grad():
            y = self._model(x)  # [1, 3, H*scale, W*scale], range 0..1

        out_rgb = (
            y.squeeze(0)
            .permute(1, 2, 0)
            .clamp(0, 1)
            .cpu()
            .numpy()
            * 255
        ).astype(np.uint8)
        return cv2.cvtColor(out_rgb, cv2.COLOR_RGB2BGR)
