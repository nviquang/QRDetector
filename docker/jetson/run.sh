#!/bin/sh
# Chạy app trong image qrdetector-jetson, mã nguồn lấy từ repo trên máy chủ (gắn vào /app) nên .env, config/ và
# logs/ nằm ngay trong repo. Mặc định main_basler.py; ví dụ khác:
#   docker/jetson/run.sh main_replay.py --data data/field/raw
#   QR_FALLBACK=off QR_DETECT_THREADS=4 docker/jetson/run.sh
set -e
cd "$(dirname "$0")/../.."
[ $# -eq 0 ] && set -- main_basler.py
xhost +local:root >/dev/null 2>&1 || true     # cho container (root) mở cửa sổ trên màn hình Jetson
exec docker run --rm -it --privileged --network host --ipc host \
    -e DISPLAY="${DISPLAY:-:0}" -e QT_X11_NO_MITSHM=1 \
    -e QR_DETECTOR -e QR_DETECT_SCALE -e QR_DETECT_THREADS -e QR_FALLBACK \
    -v /tmp/.X11-unix:/tmp/.X11-unix -v /dev:/dev -v /etc/localtime:/etc/localtime:ro \
    -v "$PWD":/app -w /app \
    qrdetector-jetson python3 "$@"
