# Image chạy QRDetector trên Jetson Nano 4GB (JetPack 4.6 / Ubuntu 18.04 trên máy chủ).
#
# Vì sao Docker: máy chủ chỉ có Python 3.6 và glibc 2.27, trong khi app cần Python >= 3.11 (numpy 2.4, scipy 1.17)
# và các wheel aarch64 cần glibc mới hơn (onnxruntime 2.28, pypylon 2.31, openvino 2.35). Debian bookworm có
# Python 3.11, glibc 2.36 và PyQt5 qua apt. Chạy CPU (không dùng GPU của Jetson).
#
# Build (trên Jetson, từ gốc repo):  docker build -t qrdetector-jetson docker/jetson
# Chạy:                              docker/jetson/run.sh [main_basler.py | main_replay.py ... | main_dual.py]
FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-venv python3-pip python3-pyqt5 \
        libzbar0 libgl1 libglib2.0-0 libusb-1.0-0 \
        fonts-dejavu-core fonts-noto-core ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# --system-site-packages để thấy PyQt5 của apt
RUN python3 -m venv --system-site-packages /opt/venv
ENV PATH=/opt/venv/bin:$PATH
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Tùy chọn: libMVSDK.so arm64 nếu dùng camera MindVision; chỉ dùng Basler thì thư mục lib/ để trống
COPY lib/ /usr/local/lib/
RUN ldconfig

ENV QR_DETECTOR=openvino \
    QT_X11_NO_MITSHM=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app
CMD ["python3", "main_basler.py"]
