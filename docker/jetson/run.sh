#!/bin/sh
# Chạy app trong image qrdetector-jetson, mã nguồn lấy từ repo trên máy chủ (gắn vào /app) nên .env, config/ và
# logs/ nằm ngay trong repo. Mặc định main_basler.py; ví dụ khác:
#   docker/jetson/run.sh main_replay.py --data data/field/raw
#   QR_FALLBACK=off QR_DETECT_THREADS=4 docker/jetson/run.sh
#   QR_MAX_FPS=0 docker/jetson/run.sh      # bỏ giới hạn fps camera (mặc định 15 fps, xem docs/jetson-nano.md)
#   QR_DETECTOR=openvino docker/jetson/run.sh   # detect bằng CPU dù đã có engine GPU
# GPU: có qr/models/qrdet_n_detect_fp16.engine (tools/build_trt_engine.sh) và chưa đặt QR_DETECTOR thì dùng
# QR_DETECTOR=tensorrt, tự chạy tools/trt_service.py bằng Python 3.6 của máy chủ (log ở logs/trt_service.log, hoặc
# /tmp/qrdetector-trt_service.log khi logs/ thuộc root do container tạo).
set -e
cd "$(dirname "$0")/../.."
[ $# -eq 0 ] && set -- main_basler.py

ENGINE=qr/models/qrdet_n_detect_fp16.engine
SOCK=/dev/shm/qrdetector-trt.sock
if [ -z "$QR_DETECTOR" ] && [ -f "$ENGINE" ]; then
    QR_DETECTOR=tensorrt
fi
if [ "$QR_DETECTOR" = tensorrt ]; then
    if ! pgrep -f "tools/trt_service.py" >/dev/null; then
        mkdir -p logs 2>/dev/null || true
        LOG=logs/trt_service.log
        { [ -w logs ] && touch "$LOG" 2>/dev/null; } || LOG=/tmp/qrdetector-trt_service.log
        rm -f "$SOCK"                          # socket cũ của lần chạy trước bị tắt ngang
        echo "Khởi động dịch vụ TensorRT ($LOG)..."
        nohup python3 tools/trt_service.py >> "$LOG" 2>&1 &
        i=0
        while [ ! -S "$SOCK" ] && [ $i -lt 60 ]; do sleep 1; i=$((i + 1)); done
        [ -S "$SOCK" ] || echo "Dịch vụ TensorRT chưa sẵn sàng sau 60 s — app sẽ detect bằng CPU"
    fi
fi
export QR_DETECTOR

xhost +local:root >/dev/null 2>&1 || true     # cho container (root) mở cửa sổ trên màn hình Jetson
TTY=-i
[ -t 0 ] && TTY=-it                            # chạy từ biểu tượng desktop (không có terminal) thì bỏ -t
exec docker run --rm $TTY --privileged --network host --ipc host \
    -e DISPLAY="${DISPLAY:-:0}" -e QT_X11_NO_MITSHM=1 \
    -e QR_DETECTOR -e QR_DETECT_SCALE -e QR_DETECT_THREADS -e QR_FALLBACK \
    -e QR_MAX_FPS="${QR_MAX_FPS:-15}" \
    -v /tmp/.X11-unix:/tmp/.X11-unix -v /dev:/dev -v /etc/localtime:/etc/localtime:ro \
    -v "$PWD":/app -w /app \
    qrdetector-jetson python3 "$@"
