"""Test offline ImprovePipeline — không cần camera.

Chạy:  python tests/test_improve_pipeline.py [đường_dẫn_ảnh]
Mặc định: ảnh adown.jpg ở thư mục gốc repo.
"""

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # gốc repo
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import cv2  # noqa: E402


def main() -> int:
    # Import model dependencies only for this standalone test. This keeps
    # unittest discovery camera-only and avoids loading torch after Qt.
    from qr import ImprovePipeline
    image_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(_ROOT, "adown.jpg")
    image = cv2.imread(image_path)
    if image is None:
        print(f"FAIL: không đọc được ảnh: {image_path}")
        return 1

    pipeline = ImprovePipeline()
    results = pipeline.decode(image)

    print(f"Ảnh: {image_path} ({image.shape[1]}x{image.shape[0]})")
    if results:
        print(f"OK — tìm thấy {len(results)} QR:")
        for i, text in enumerate(results, 1):
            print(f"  [{i}] {text}")
        return 0

    print("FAIL: không decode được QR nào.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
