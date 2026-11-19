"""Chuyển qrdet-n (YOLOv8n-seg đã train cho QR) thành YOLOv8n detect 1 lớp và xuất ONNX — không train lại.

Head ``Segment`` của ultralytics kế thừa ``Detect``: nhánh hộp/lớp (cv2, cv3, dfl) cùng tên và cùng kích thước, seg chỉ
có thêm nhánh mask (proto, cv4). Chép mọi tham số trùng tên sang ``yolov8n.yaml`` (nc=1) cho ra cùng hộp, bỏ phần mask.

    python tools/export_qrdet_detect.py                     # tạo qr/models/qrdet_n_detect.{pt,onnx} và kiểm tra trùng khớp
    python tools/export_qrdet_detect.py --check-dir <thư mục ảnh> --check-n 20

ONNX xuất ở kích thước động (một file cho mọi tỉ lệ thu); OpenVINO đọc thẳng file ONNX này (qr/detector_onnx.py).
"""
from __future__ import annotations

import argparse
import datetime
import glob
import os
import sys
from copy import deepcopy

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import torch  # noqa: E402  (torch trước cv2/PyQt5)
import cv2  # noqa: E402
import numpy as np  # noqa: E402
import qrdet  # noqa: E402
from ultralytics import YOLO  # noqa: E402
from ultralytics.nn.tasks import DetectionModel  # noqa: E402

MODELS = os.path.join(ROOT, "qr", "models")
OUT_PT = os.path.join(MODELS, "qrdet_n_detect.pt")
OUT_ONNX = os.path.join(MODELS, "qrdet_n_detect.onnx")
DEFAULT_CHECK_DIR = os.path.join(os.path.dirname(ROOT), "..", "..", "data", "field", "raw")


def qrdet_weights(size: str = "n") -> str:
    folder = os.path.join(os.path.dirname(qrdet.__file__), ".model")
    path = os.path.join(folder, f"qrdet-{size}.pt")
    if not os.path.isfile(path):
        qrdet.QRDetector(model_size=size)       # tự tải về .model
    return path


def convert(seg_path: str) -> DetectionModel:
    seg = YOLO(seg_path).model
    det = DetectionModel(cfg="yolov8n.yaml", nc=1, verbose=False)
    src = seg.float().state_dict()
    dst = det.state_dict()
    copied = {k: v for k, v in src.items() if k in dst and dst[k].shape == v.shape}
    missing = [k for k in dst if k not in copied]
    if missing:
        raise RuntimeError(f"thiếu {len(missing)} tham số khi chép từ seg sang detect, ví dụ {missing[:5]}")
    det.load_state_dict(copied, strict=True)
    skipped = sorted({k.split(".")[2] for k in src if k not in copied and k.startswith("model.22.")})
    print(f"chép {len(copied)}/{len(src)} tham số; bỏ nhánh head: {skipped}")
    det.names = {0: "QR"}
    det.stride = seg.stride
    det.args = {"task": "detect", "imgsz": 640}
    det.eval()
    return det


def save(det: DetectionModel, path: str):
    ckpt = {"model": deepcopy(det).half(), "date": datetime.datetime.now().isoformat(),
            "version": "qrdet-n seg -> detect", "train_args": {"task": "detect", "imgsz": 640}}
    torch.save(ckpt, path)
    print("lưu", path)


def boxes(model: YOLO, image, imgsz):
    r = model.predict(image, imgsz=imgsz, conf=0.3, iou=0.3, agnostic_nms=True, verbose=False, device="cpu")[0]
    return r.boxes.xyxy.cpu().numpy(), r.boxes.conf.cpu().numpy()


def iou(a, b):
    x1, y1 = np.maximum(a[:2], b[:2])
    x2, y2 = np.minimum(a[2:], b[2:])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    return inter / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter + 1e-9)


def check(seg_path: str, det_path: str, files: list[str], imgsz: int = 1280) -> bool:
    seg, det = YOLO(seg_path), YOLO(det_path, task="detect")
    worst, n_boxes = 1.0, 0
    for f in files:
        img = cv2.imread(f)
        if img is None:
            continue
        bs, cs = boxes(seg, img, imgsz)
        bd, cd = boxes(det, img, imgsz)
        if len(bs) != len(bd):
            print(f"  khác số hộp {len(bs)} vs {len(bd)}: {f}")
            worst = 0.0
            continue
        for b, c in zip(bs, cs):
            j = int(np.argmax([iou(b, x) for x in bd])) if len(bd) else -1
            score = iou(b, bd[j]) if j >= 0 else 0.0
            worst = min(worst, score)
            n_boxes += 1
            if abs(c - cd[j]) > 0.02:
                print(f"  lệch độ tin {c:.3f} vs {cd[j]:.3f}: {f}")
    ok = worst >= 0.99
    print(f"trùng khớp seg ↔ detect trên {len(files)} ảnh, {n_boxes} hộp: IoU nhỏ nhất {worst:.4f} → {'ĐẠT' if ok else 'KHÔNG ĐẠT'}")
    return ok


def export_onnx(det_path: str, opset: int = 12) -> str:
    out = YOLO(det_path, task="detect").export(format="onnx", opset=opset, dynamic=True, simplify=True,
                                                imgsz=640, device="cpu")
    if os.path.abspath(out) != os.path.abspath(OUT_ONNX):
        os.replace(out, OUT_ONNX)
    print("xuất", OUT_ONNX)
    return OUT_ONNX


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check-dir", default=DEFAULT_CHECK_DIR, help="thư mục chứa frame_*.tiff (tìm đệ quy)")
    ap.add_argument("--check-n", type=int, default=20)
    ap.add_argument("--opset", type=int, default=12)
    args = ap.parse_args()
    seg_path = qrdet_weights("n")
    save(convert(seg_path), OUT_PT)
    files = sorted(glob.glob(os.path.join(args.check_dir, "**", "frame_*.tiff"), recursive=True))
    if files:
        step = max(1, len(files) // args.check_n)
        if not check(seg_path, OUT_PT, files[::step][:args.check_n]):
            sys.exit(1)
    else:
        print("không có ảnh để kiểm tra trùng khớp:", args.check_dir)
    export_onnx(OUT_PT, args.opset)


if __name__ == "__main__":
    main()
