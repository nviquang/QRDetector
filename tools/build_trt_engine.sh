#!/bin/sh
# Tạo engine TensorRT FP16 cho bộ phát hiện QR trên Jetson (máy chủ JetPack, không trong Docker). Chạy một lần sau khi
# cài máy hoặc khi đổi model/JetPack; engine gắn với GPU và phiên bản TensorRT nên không commit (gitignore *.engine).
#   tools/build_trt_engine.sh            # khoảng 10–20 phút trên Jetson Nano
# Đầu vào float32 (app ghi float16 vào /dev/shm, tools/trt_service.py đổi sang float32), kích thước động: cạnh tối đa 2144 = 2856 × 0,75 làm tròn bội 32,
# tối ưu cho dải 2856×1072 (letterbox 2144×832). Đổi QR_DETECT_SCALE lớn hơn 0,75 thì phải sửa --maxShapes và
# MAX_SIDE trong tools/trt_service.py, TRT_MAX_SIDE trong qr/detector_onnx.py.
set -e
cd "$(dirname "$0")/.."
OUT=qr/models/qrdet_n_detect_fp16.engine
/usr/src/tensorrt/bin/trtexec --onnx=qr/models/qrdet_n_detect.onnx --fp16 \
    --workspace=1024 --minShapes=images:1x3x256x256 --optShapes=images:1x3x832x2144 \
    --maxShapes=images:1x3x2144x2144 --shapes=images:1x3x832x2144 --saveEngine="$OUT.tmp"
mv "$OUT.tmp" "$OUT"
echo "Đã tạo $OUT"
