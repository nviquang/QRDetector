# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Chạy các script chính

```bash
# Kích hoạt virtualenv (Windows)
.venv\Scripts\activate

# Chạy Streamlit demo (upload ảnh/video, giải mã QR)
streamlit run demo.py

# Chạy pipeline production trên một ảnh
python production/main.py

# Chạy script QR detection từ video (qrdet)
python test.py

# Chạy camera IP (cần file .env với thông tin RTSP)
python cam-ip.py
```

## Cài đặt

```bash
python -m pip install -r requirements.txt  # nếu có
# Hoặc cài thủ công:
pip install opencv-python pyzbar qrdet streamlit pillow python-dotenv basicsr realesrgan
```

**Lưu ý pyzbar trên Windows:** pyzbar cần ZBar DLL. Thư viện đã xử lý bằng `os.add_dll_directory()` tự động trong `_eval_common.py` và `demo.py`. Nếu gặp lỗi DLL, cài `zbar` qua `pip install zbar-py` hoặc copy `libzbar-64.dll` vào thư mục pyzbar.

## Cấu hình RTSP camera

Tạo file `.env` từ `.env.example` và điền thông tin:
```
RTSP_USERNAME=admin
RTSP_PASSWORD=<mật_khẩu_thực>
RTSP_IP=192.168.1.19
RTSP_PORT=554
```

## Kiến trúc hệ thống

Dự án có hai luồng xử lý song song:

### 1. Production pipeline (`production/`)
Đây là module chính dùng trong production. Luồng xử lý 6 bước:

```
Ảnh BGR → Detector → Warp perspective → Multi-decoder
                                              ↓ (thất bại)
                                      Upscale 2x + Otsu threshold
                                              ↓ (thất bại)
                                      Super-Resolution (Real-ESRGAN x4)
                                        → SR + Otsu
                                        → SR + Adaptive threshold
```

- **`detector.py`** — Phát hiện QR bằng YOLOv8-based `qrdet`, trả về `Detection` (bbox + quad 4 góc)
- **`corrector.py`** — `warp_qr()`: perspective transform 4 góc → ảnh vuông 512×512; `add_quiet_zone()`: thêm viền trắng 64px
- **`preprocessor.py`** — `upscale_otsu()` và `upscale_adaptive()`: upscale 2x + threshold để tăng độ tương phản
- **`super_resolution.py`** — Lazy-load Real-ESRGAN x4 (`weights/RealESRGAN_x4plus.pth`)
- **`decoder.py`** — `decode_parallel()`: thử nhiều decoder song song (pyzbar + xoay ảnh)
- **`pipeline.py`** — `QRPipeline.decode(image_bgr)`: orchestrator nối toàn bộ 6 bước trên

**Sử dụng production pipeline:**
```python
from production.pipeline import QRPipeline
pipeline = QRPipeline(sr_weight_path="weights/RealESRGAN_x4plus.pth")
results = pipeline.decode(image_bgr)  # list[str]
```

### 2. Demo Streamlit (`demo.py`)
Giao diện web upload ảnh/video, dùng pyzbar trực tiếp (không qua production pipeline), có fallback xoay 90°.

### 3. Công cụ thu thập dữ liệu (`cam-ip.py`)
Kết nối camera IP qua RTSP, cho phép chụp ảnh (Space) và ghi video (s/d), lưu vào `data/images/` và `data/videos/`.

## Thư mục quan trọng

| Thư mục | Mục đích |
|---|---|
| `production/` | Module production: detector, corrector, preprocessor, SR, decoder, pipeline |
| `weights/` | Model weights (Real-ESRGAN, không push git) |
| `tmp/` | Script thực nghiệm và dữ liệu tạm — không dùng trong production |
| `_eval_common.py` | Hàm tiện ích dùng chung cho các script eval: `try_decode()`, `props()` |

## Lưu ý quan trọng

- **`weights/RealESRGAN_x4plus.pth`** (~64MB) không push git — cần tải thủ công hoặc qua script.
- `SuperResolver` lazy-load: chỉ load GPU khi thực sự gặp ảnh khó (4 bước đầu thất bại).
- Tất cả ảnh đầu vào/ra xử lý theo format **BGR** (OpenCV), không phải RGB.
- `wechat_qrcode_models/` hiện rỗng — tính năng WeChat QR chưa triển khai.
