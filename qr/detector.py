"""Bước 1: Phát hiện QR bằng qrdet (YOLOv8-seg) — chạy GPU NVIDIA nếu torch có CUDA."""

from __future__ import annotations

import logging

import numpy as np

# torch/qrdet là tùy chọn: máy chỉ dùng bộ phát hiện ONNX/OpenVINO (Jetson Nano, docs/jetson-nano.md) không cài
# hai gói này. Khi đó vẫn import được gói qr; chỉ tạo QRDetector (QR_DETECTOR=qrdet) mới báo lỗi.
try:
    import torch
    from qrdet import QRDetector as _QRDetector
    # qrdet.detect() không cho chỉnh imgsz → gọi thẳng model YOLO và dùng lại helper của qrdet
    from qrdet.qrdet import _prepare_input, _yolo_v8_results_to_dict
    _IMPORT_ERROR = None
except (ImportError, OSError) as _e:
    torch = _QRDetector = _prepare_input = _yolo_v8_results_to_dict = None
    _IMPORT_ERROR = _e

from .detection import Detection  # noqa: F401  (giữ đường import cũ qr.detector.Detection)

logger = logging.getLogger("solution.qr")

# Dải hẹp (vùng đọc quanh băng): cạnh dài bị thu về imgsz làm QR quá nhỏ, độ tin cậy tụt dưới ngưỡng. Đo trên
# Basler 2856×400: imgsz 1280 cho 0,21–0,71, 1600 cho ~0,8 và không chậm hơn vì ảnh có ít điểm hơn nhiều.
BAND_ASPECT = 4.0
BAND_MIN_IMGSZ = 1600


def resolve_device(requested: str, cuda_available: bool) -> str:
    """'auto' → 'cuda:0' nếu có CUDA, ngược lại 'cpu'. Yêu cầu cuda mà không có → 'cpu' + cảnh báo."""
    if requested == "auto":
        return "cuda:0" if cuda_available else "cpu"
    if requested.startswith("cuda") and not cuda_available:
        logger.warning("Không có CUDA — detector chạy CPU thay cho %s", requested)
        return "cpu"
    return requested


class QRDetector:
    def __init__(self, model_size: str = "s", conf_th: float = 0.5, imgsz: int = 640,
                 device: str = "auto", half: bool = False):
        """
        imgsz:  cạnh ảnh đưa vào YOLO. Mặc định qrdet là 640 — frame 2448×2048 bị thu nhỏ ~4 lần,
                QR ~60px còn ~15px và bị bỏ sót. imgsz=1280 giữ QR nhỏ đủ lớn để phát hiện.
        device: "auto" (GPU nếu có), "cpu" hoặc "cuda:N".
        half:   FP16 — chỉ có tác dụng trên GPU; tắt mặc định vì GTX 16xx từng lỗi FP16.
        """
        if _IMPORT_ERROR is not None:
            raise ImportError(f"Bộ phát hiện qrdet cần torch và qrdet ({_IMPORT_ERROR}); "
                              "dùng QR_DETECTOR=openvino|onnx hoặc cài requirements.txt")
        self._detector = _QRDetector(model_size=model_size, conf_th=conf_th)
        self._conf_th = conf_th
        self._imgsz = imgsz
        self._want_half = half
        self.set_device(device)

    def set_device(self, device: str):
        """Đổi được lúc đang chạy: frame đang detect chạy nốt trên thiết bị cũ, YOLO tự nạp lại
        model sang thiết bị mới ở lần detect sau. Lần đầu lên GPU mất vài giây (như warmup)."""
        resolved = resolve_device(device, torch.cuda.is_available())
        gpu = "-"
        if resolved.startswith("cuda"):
            try:
                gpu = torch.cuda.get_device_name(resolved)
            except Exception as e:   # driver lỗi dù is_available() → dùng CPU, app vẫn khởi động
                logger.warning("Không đọc được GPU (%s) — detector chạy CPU", e)
                resolved = "cpu"
        self._device, self._half = resolved, self._want_half and resolved.startswith("cuda")
        logger.info("qr_detector device=%s half=%s imgsz=%d gpu=%s",
                    self._device, self._half, self._imgsz, gpu)

    @property
    def device(self) -> str:
        return self._device

    @property
    def gpu_available(self) -> bool:
        return torch.cuda.is_available()

    def warmup(self, shape: tuple[int, int] = (768, 2448)):
        """Detect một lần trên ảnh đen — lần đầu trên GPU mất vài giây (nạp kernel CUDA)."""
        self.detect(np.zeros((shape[0], shape[1], 3), np.uint8))

    def _predict(self, image):
        h, w = image.shape[:2]
        imgsz = max(self._imgsz, BAND_MIN_IMGSZ) if max(h, w) >= BAND_ASPECT * min(h, w) else self._imgsz
        return self._detector.model.predict(
            source=image, conf=self._conf_th, iou=self._detector._nms_iou, imgsz=imgsz,
            device=self._device, half=self._half, max_det=100, agnostic_nms=True, verbose=False,
        )

    @staticmethod
    def _to_dicts(result, image) -> list[dict]:
        """qrdet cắt thử detection đầu bằng padded quad; mask suy biến cho quad rất lớn và cấp phát vài PiB.
        Khi đó xử lý riêng từng detection, bỏ cái lỗi, để không mất các QR khác trong frame."""
        try:
            return _yolo_v8_results_to_dict(results=result, image=image)
        except MemoryError as e:
            logger.warning("Bỏ detection có mask suy biến: %s", e)
        dicts = []
        for i in range(len(result)):
            try:
                dicts += _yolo_v8_results_to_dict(results=result[i:i + 1], image=image)
            except MemoryError:
                continue
        return dicts

    def detect(self, image_bgr: np.ndarray) -> list[Detection]:
        """Nhận ảnh BGR, trả về danh sách Detection (có thể rỗng)."""
        image = _prepare_input(source=image_bgr, is_bgr=True)
        try:
            predictions = self._predict(image)
        except RuntimeError as e:   # CUDA OOM / lỗi driver (GTX 1650 chỉ 4 GB) → chuyển hẳn sang CPU
            if not self._device.startswith("cuda"):
                raise
            logger.warning("Lỗi CUDA khi detect (%s) — chuyển detector sang CPU", e)
            self._device, self._half = "cpu", False
            predictions = self._predict(image)
        raw = self._to_dicts(predictions[0], image)
        results = []
        for d in raw:
            # ưu tiên padded_quad_xy để bao trọn QR khi warp; fallback về quad_xy
            quad = d.get("padded_quad_xy", d.get("quad_xy"))
            if quad is None:
                continue
            polygon = d.get("polygon_xy")
            results.append(Detection(
                bbox_xyxy=d["bbox_xyxy"].astype(np.float32),
                quad_xy=quad.astype(np.float32),
                confidence=float(d["confidence"]),
                polygon_xy=None if polygon is None else np.asarray(polygon, np.float32),
            ))
        return results
