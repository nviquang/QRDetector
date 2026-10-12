"""Chạy thử pipeline QR decode trên một ảnh."""

import sys, os
# Thêm thư mục cha vào path để Python nhận ra 'production' là package
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2
from production.pipeline import QRPipeline

# Thư mục gốc project (QRDetector/), không phụ thuộc cwd
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── Đổi đường dẫn ảnh tại đây ────────────────────────────────────────────────
IMAGE_PATH = os.path.join(_ROOT, "adown.jpg")
SR_WEIGHT  = os.path.join(_ROOT, "weights", "RealESRGAN_x4plus.pth")
# ─────────────────────────────────────────────────────────────────────────────

image = cv2.imread(IMAGE_PATH)
if image is None:
    raise FileNotFoundError(f"Không đọc được ảnh: {IMAGE_PATH}")

pipeline = QRPipeline(sr_weight_path=SR_WEIGHT)
results = pipeline.decode(image)

if results:
    print(f"Tìm thấy {len(results)} QR:")
    for i, text in enumerate(results, 1):
        print(f"  [{i}] {text}")
else:
    print("Không decode được QR nào.")
