# Chạy QRDetector trên Jetson Nano 4GB

Hướng dẫn chạy app quét QR với **camera Basler** (`main_basler.py`) trên Jetson Nano Developer Kit 4GB. App chạy trong Docker và chỉ dùng CPU. Không cần cài pylon hay MindVision SDK.

> **Trạng thái (23/11/2026):** đã làm theo tài liệu trên Jetson Nano 4GB thật (JetPack 4.6.1, L4T R32.7.1):
>
> - image build được, mọi gói cài từ wheel, không phải biên dịch;
> - camera `a2A2840-48umBAS` nhận qua USB 3 trong container;
> - `main_basler.py` mở được và tìm thấy camera, không cần MindVision SDK;
> - OpenVINO chạy được trên Cortex-A57.
>
> **Chưa thử đọc QR trên băng chuyền.** Gặp lỗi thì ghi lại theo mục [Xử lý sự cố](#xử-lý-sự-cố) và cập nhật tài liệu này.

## Vì sao phải dùng Docker

Jetson Nano chỉ được NVIDIA hỗ trợ tới JetPack 4.6.x (Ubuntu 18.04). Máy có Python 3.6 và glibc 2.27, trong khi app cần nhiều hơn:

| Cần | Lý do |
|---|---|
| Python ≥ 3.11 | `numpy==2.4.6`, `scipy==1.17.1`, `onnxruntime==1.32.0` |
| glibc ≥ 2.28 / 2.31 / 2.35 | wheel aarch64 của `onnxruntime` / `pypylon` / `openvino` |
| PyQt5 | PyPI không có wheel aarch64 (chỉ có mã nguồn, build trên Nano mất hàng giờ) |

Image `docker/jetson/Dockerfile` dựa trên Debian bookworm, gồm Python 3.11, glibc 2.36 và PyQt5 lấy từ apt. Nhờ vậy không phải cài lại hệ điều hành hay build Python, Qt từ mã nguồn.

**Không dùng GPU của Jetson.** torch cho Jetson chỉ có bản Python 3.6 của NVIDIA. Từ 20/11/2026 bộ phát hiện mặc định là YOLOv8n ONNX chạy CPU (OpenVINO, thiếu thì tự lùi sang ONNX Runtime), nên image không cài torch hay qrdet. Ô **Dùng GPU** trong app bị khóa là đúng. Đặt `QR_DETECTOR=qrdet` sẽ báo lỗi.

## 1. Chuẩn bị Jetson (máy chủ)

1. Flash **JetPack 4.6.x** (SD card image của Jetson Nano Developer Kit). Đăng nhập vào giao diện desktop: app cần màn hình.
2. Cấp nguồn 5 V 4 A qua jack tròn (cắm jumper J48), rồi bật chế độ hiệu năng tối đa:

   ```bash
   sudo nvpmodel -m 0      # MAXN 10 W, 4 nhân
   sudo jetson_clocks
   ```

   `jetson_clocks` mất tác dụng khi khởi động lại. Muốn giữ, thêm vào `crontab -e` của root dòng `@reboot /usr/bin/jetson_clocks`.
3. Thêm swap 4 GB. RAM 4 GB dùng chung cho CPU, GPU và desktop. Tiến trình đọc nền (B/C) nạp thêm một bản OpenCV/numpy riêng.

   ```bash
   sudo fallocate -l 4G /swapfile && sudo chmod 600 /swapfile
   sudo mkswap /swapfile && sudo swapon /swapfile
   echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
   ```

4. Nâng bộ đệm USB cho camera Basler USB 3. Mặc định 16 MB, pylon khuyến nghị 1000 MB. Sửa `/boot/extlinux/extlinux.conf`: thêm `usbcore.usbfs_memory_mb=1000` vào cuối dòng `APPEND`, rồi khởi động lại. Kiểm tra:

   ```bash
   cat /sys/module/usbcore/parameters/usbfs_memory_mb    # phải ra 1000
   ```

5. Docker có sẵn trong JetPack. Kiểm tra bằng `sudo docker run --rm hello-world`. Thêm người dùng vào nhóm docker để khỏi gõ `sudo`, rồi đăng xuất và đăng nhập lại:

   ```bash
   sudo usermod -aG docker $USER
   ```

## 2. Lấy mã nguồn

```bash
git clone git@github.com:nviquang/QRDetector.git
cd QRDetector
```

**Không cần cài pylon:** wheel `pypylon` đã có sẵn runtime pylon cho aarch64.

**Không cần MindVision SDK khi chỉ dùng camera Basler.** Thiếu `libMVSDK.so` thì `mvsdk.py` vẫn import được (`mvsdk.AVAILABLE = False`); chỉ khi gọi hàm của camera MindVision mới báo lỗi. Nếu sau này cần camera MindVision (`main_dual.py`), chép `libMVSDK.so` bản arm64 của MindVision Linux SDK (`file` phải ra "ARM aarch64") vào `docker/jetson/lib/` rồi build lại image. Thư mục này đã được gitignore.

## 3. Cấu hình gửi mã lên server

Tạo `.env` ở gốc repo giống máy Windows (xem `.env.example` và đoạn **Gửi mã lên server** ở mục "Phiên bản demo cho khách hàng" trong `README.md`):

```bash
cp .env.example .env
nano .env       # điền BASE_URL, APP_TOKEN_SECRET, API_KEY (và BASIC_AUTH_* nếu là host dev)
```

Đồng bộ giờ máy, vì `X-App-Token` tính theo phút và giờ lệch sẽ làm server trả 403:

```bash
timedatectl     # "System clock synchronized: yes"
```

## 4. Build image

Build ngay trên Jetson. Lần đầu tải khoảng 400 MB và mất 10–20 phút:

```bash
docker build -t qrdetector-jetson docker/jetson
```

Sửa `docker/jetson/` (requirements, Dockerfile, thư viện trong `lib/`) thì build lại. Sửa mã Python thì **không** cần build lại, vì `run.sh` gắn thẳng thư mục repo vào container.

## 5. Chạy

Chạy từ terminal trên màn hình của Jetson (cần `DISPLAY`). Khi SSH vào thì đặt `export DISPLAY=:0` trước.

```bash
docker/jetson/run.sh                                     # main_basler.py
docker/jetson/run.sh main_replay.py --data data/field/raw   # phát lại bản ghi, không cần camera
docker/jetson/run.sh main_dual.py                        # MindVision (A) + Basler (B)
```

`run.sh` chạy container với các tùy chọn sau:

- `--privileged -v /dev:/dev`: mở được camera USB;
- `--network host`: camera GigE và gửi API;
- X11 của máy chủ để hiện cửa sổ;
- thư mục repo gắn vào `/app`, nên `config/*.json`, `logs/` và `.env` dùng chung với máy chủ.

Container chạy bằng root, nên file mới tạo trong `config/` và `logs/` thuộc root. Muốn sửa tay thì dùng `sudo chown -R $USER config logs`.

Biến môi trường đặt trước `run.sh` sẽ được chuyển vào container: `QR_DETECTOR`, `QR_DETECT_SCALE`, `QR_DETECT_THREADS`, `QR_FALLBACK`. Ví dụ:

```bash
QR_DETECTOR=onnx QR_DETECT_THREADS=4 docker/jetson/run.sh
```

Cách dùng giao diện (Cấu hình → Kết nối → Mở, tab Băng chuyền, Bắt đầu/Dừng) giống trên Windows: xem `README.md`, mục "Bản demo dùng camera Basler" và "Phiên bản demo cho khách hàng". Nút **Chạy nền** chỉ hiện khi desktop có khay hệ thống (LXDE/Unity của JetPack có).

Kiểm tra camera Basler trong container trước khi mở app:

```bash
docker run --rm --privileged -v /dev:/dev -v "$PWD":/app -w /app qrdetector-jetson \
    python3 tools/test_basler.py --list
```

## 6. Tinh chỉnh tốc độ

Jetson Nano chỉ có 4 nhân Cortex-A57 1,43 GHz. Đo ngày 23/11/2026 ở chế độ MAXN, ảnh dải 2840×1072, ×0,75, p50 của 5 lần:

| Bộ phát hiện | Jetson Nano | Ryzen 5 5500U (`README.md`) |
|---|---:|---:|
| OpenVINO | 1474 ms | 144 ms |
| ONNX Runtime | 1912 ms | 182 ms |

Detect chậm hơn khoảng 10 lần so với máy bàn. Ở chế độ đọc nhiều frame, YOLO chạy tối đa mỗi 400 ms, nên trên Nano thực tế khoảng 1,5 s một lần. Tem đi qua dải 600 mm ở 100 mm/s mất khoảng 6 s, tức được detect khoảng 4 lần. Bước cascade và đọc nền còn tốn thêm CPU, **chưa đo tỉ lệ đọc**. Xem thời gian detect và cascade trên nhãn trạng thái của app. Cách đo không cần băng chuyền là chạy `main_replay.py` với một bản ghi. Các nút chỉnh, theo thứ tự nên thử:

| Chỉnh | Tác dụng | Đánh đổi |
|---|---|---|
| Vùng đọc (dải y, tab Băng chuyền) hẹp sát buồng tối | ảnh nhỏ hơn: detect nhanh hơn và USB nhẹ hơn | đặt sai dải thì mất tem ở mép |
| Ô **N** (decode mỗi N frame) | giảm tải đều | N lớn quá thì lượt ngắn có ít frame để đọc |
| `QR_DETECT_THREADS=4` | dùng đủ 4 nhân cho detect | tranh CPU với cascade và đọc nền |
| `QR_FALLBACK=off` | tắt đọc nền B/C (mỗi lượt khó tốn 2–15 s CPU trên máy bàn, trên Nano lâu hơn) | mất các lượt chỉ B/C đọc được |
| `QR_DETECT_SCALE=0.6` | detect nhanh khoảng 1,5 lần (số trên máy bàn) | recall tụt khoảng 3 điểm (99,7% → 96,6% trên `data/field`) |

**Hai camera trên một Nano:** cả 4 cổng USB 3 của Nano đi chung một đường 5 Gbit/s qua hub nội. Hai camera 8 MP ở fps cao vượt cả băng thông lẫn sức CPU. Nên dùng một Nano cho mỗi camera, trừ khi đo thực tế cho thấy đủ. App hai camera hiện là MindVision + Basler (`main_dual.py`), chưa có bản hai Basler.

## Xử lý sự cố

| Triệu chứng | Nguyên nhân và cách xử lý |
|---|---|
| `Chưa cài MindVision SDK … không gọi được Camera…` | Đang mở camera MindVision (`main.py`, `main_demo.py`, camera A của `main_dual.py`). Với Basler dùng `main_basler.py`. Cần MindVision thì chép `libMVSDK.so` arm64 vào `docker/jetson/lib/` rồi build lại. |
| `qt.qpa.xcb: could not connect to display` | Chưa có `DISPLAY` (khi SSH thì `export DISPLAY=:0`), hoặc `xhost` từ chối. Chạy `xhost +local:root` trên máy chủ, trong phiên desktop. |
| `Could not load the Qt platform plugin "xcb"` | Có ai đó cài `opencv-contrib-python` bản thường vào image. Phải dùng bản `-headless` như `docker/jetson/requirements.txt`. |
| Log `Không dùng được bộ phát hiện openvino … thử phương án kế tiếp` | OpenVINO không chạy trên CPU này. App tự dùng ONNX Runtime, không cần làm gì. Muốn bỏ hẳn lần thử OpenVINO thì đặt `QR_DETECTOR=onnx`. |
| `pip install` trong lúc build đòi biên dịch (`Building wheel for …`) | Không có wheel cho tổ hợp này. Kiểm tra image là Debian bookworm arm64 (`uname -m` trong container ra `aarch64`) và đúng phiên bản trong `requirements.txt`. |
| Camera Basler mất frame, lỗi grab | Chưa nâng `usbfs_memory_mb` (bước 1.4), camera cắm qua hub, hoặc nguồn yếu. Dùng nguồn 4 A qua jack tròn. |
| App bị kill hoặc treo khi chạy lâu | Hết RAM. Kiểm tra swap (`free -h`), tắt đọc nền (`QR_FALLBACK=off`), đóng trình duyệt trên Jetson. |
| Server trả 403 `invalid X-App-Token` | Giờ máy lệch. Kiểm tra `timedatectl`. Container dùng đồng hồ của máy chủ. |
