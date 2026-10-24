"""Test offline ImprovePipeline cho QR nhỏ trên frame lớn — không cần camera.

Chạy:  python tests/test_small_qr.py [thư_mục_frame_mẫu]
Mặc định thư mục frame mẫu: ../images (frame camera 2448×2048, QR ~60px). Thiếu thư mục thì bỏ qua phần đó.

Kiểm tra:
  1. Model WeChat CNN (ONNX) load được.
  2. QR tổng hợp ~2px/module đặt trong frame 2448×2048 → detect + decode được.
  3. Cascade decode trên Detection dựng tay (không phụ thuộc YOLO).
  4. Frame mẫu thật: decode được >= MIN_SAMPLE_OK ảnh, nội dung đúng định dạng.
"""

import glob
import os
import re
import sys
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # solution/
_REPO = os.path.dirname(_ROOT)                                        # QRDetector/
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import cv2  # noqa: E402
import numpy as np  # noqa: E402

FRAME_W, FRAME_H = 2448, 2048
SYNTH_TEXT = "000000585545"
MIN_SAMPLE_OK = 12          # benchmark: 12/14 (2 ảnh còn lại bị nhòe chuyển động / lóa sáng)
SAMPLE_TEXT_RE = re.compile(r"^\d{12}$")


def _synthetic_frame(px_per_module: int = 2) -> tuple[np.ndarray, np.ndarray]:
    """QR in nhãn trắng trên nền băng chuyền tối, nhỏ ~2px/module, hơi mờ + nhiễu. Trả về (frame, bbox)."""
    qr = cv2.QRCodeEncoder.create().encode(SYNTH_TEXT)                 # 1 px/module, có quiet zone
    qr = cv2.resize(qr, None, fx=px_per_module, fy=px_per_module, interpolation=cv2.INTER_NEAREST)
    rng = np.random.default_rng(0)
    frame = np.full((FRAME_H, FRAME_W), 40, np.uint8)                  # nền tối
    frame[1100:1300, 900:1400] = 210                                   # nhãn trắng
    y, x = 1150, 1200
    frame[y:y + qr.shape[0], x:x + qr.shape[1]] = np.where(qr > 0, 210, 30)
    frame = cv2.GaussianBlur(frame, (3, 3), 0.8)
    frame = np.clip(frame.astype(np.int16) + rng.normal(0, 4, frame.shape), 0, 255).astype(np.uint8)
    bbox = np.array([x, y, x + qr.shape[1], y + qr.shape[0]], np.float32)
    return np.ascontiguousarray(cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)), bbox


def check(name: str, ok: bool, detail: str = "") -> bool:
    print(f"[{'PASS' if ok else 'FAIL'}] {name}{' — ' + detail if detail else ''}")
    return ok


def main() -> int:
    # Import model dependencies only for this standalone test (giống test_improve_pipeline.py).
    from qr import Detection, ImprovePipeline
    from qr.decoder import _get_wechat_cnn_detector

    results = [check("WeChat CNN model (ONNX) load được", _get_wechat_cnn_detector() is not None)]

    pipeline = ImprovePipeline()
    frame, bbox = _synthetic_frame()

    t = time.perf_counter()
    texts, dets = pipeline.scan(frame)
    results.append(check("QR tổng hợp 2px/module trong frame 2448×2048",
                         SYNTH_TEXT in texts,
                         f"{len(dets)} detection, kết quả={texts}, {time.perf_counter() - t:.2f}s"))

    quad = np.array([[bbox[0], bbox[1]], [bbox[2], bbox[1]], [bbox[2], bbox[3]], [bbox[0], bbox[3]]], np.float32)
    text = pipeline._decode_one(frame, Detection(bbox_xyxy=bbox, quad_xy=quad, confidence=1.0))
    results.append(check("Cascade decode trên Detection dựng tay", text == SYNTH_TEXT, f"kết quả={text}"))

    sample_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(_REPO, "images")
    paths = sorted(glob.glob(os.path.join(sample_dir, "*.bmp")) + glob.glob(os.path.join(sample_dir, "*.png")))
    if not paths:
        print(f"[SKIP] Không có frame mẫu trong {sample_dir}")
    else:
        ok_count, bad_texts, t = 0, [], time.perf_counter()
        for p in paths:
            found = pipeline.decode(cv2.imread(p))
            ok_count += bool(found)
            bad_texts += [s for s in found if not SAMPLE_TEXT_RE.match(s)]
            print(f"       {os.path.basename(p)}: {found}")
        avg = (time.perf_counter() - t) / len(paths)
        need = min(MIN_SAMPLE_OK, len(paths))
        results.append(check(f"Frame mẫu: decode được >= {need}/{len(paths)}", ok_count >= need,
                             f"{ok_count}/{len(paths)}, trung bình {avg:.2f}s/frame"))
        results.append(check("Frame mẫu: nội dung đúng định dạng 12 chữ số", not bad_texts, f"sai={bad_texts}"))

    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
