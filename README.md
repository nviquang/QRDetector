# QRDetector — Ứng dụng quét QR bằng camera MindVision

Ứng dụng PyQt5 tích hợp **camera MindVision (MVSDK / `mvsdk`)** và **pipeline QR** (qrdet detect ở imgsz 1280 → chuỗi decode trên vùng QR cắt từ ảnh gốc: zxing → WeChat → WeChat CNN + super-resolution). Tối ưu cho QR nhỏ (~60px) trên frame 2448×2048; khoảng 1s/frame trên CPU. Không dùng Real-ESRGAN.

```
Camera (MindVision Camera* API) → frame BGR độc lập → mỗi N frame → ImprovePipeline → quad + text QR
```

---

## 1. Yêu cầu

| Thành phần  | Phiên bản                                                               |
| ----------- | ----------------------------------------------------------------------- |
| Windows     | 10/11 64-bit                                                            |
| Python      | 3.11 (64-bit)                                                           |
| SDK camera  | ChinaVision Camera Platform 2.1.10.196 (bộ cài `ChinaVision Camera Platform Setup(2.1.10.196_20260721)(WIN10)`) |
| Runtime DLL | `MVCAMSDK_X64.dll` với Python 64-bit (`MVCAMSDK.dll` với Python 32-bit) |
| Camera      | Camera đã hoạt động với app ChinaVision đi kèm bộ cài                   |

Tài liệu này gọi SDK là "MindVision" theo API `mvsdk` / `Camera*`, nhưng bản đang dùng được cài từ bộ cài ChinaVision vào `C:\Program Files (x86)\ChinaVision`. DLL có trong `C:\Windows\System32` (64-bit) và `C:\Windows\SysWOW64` (32-bit), trùng với bản trong thư mục `SDK\` của ChinaVision, nên gỡ ChinaVision có thể làm app không mở được camera.

**Không nhầm với MVS của Hikrobot:** MVS là SDK của hãng khác (`MvCameraControl`), không cung cấp `MVCAMSDK_X64.dll` và app này không dùng.

`mvsdk.py` là wrapper Python được đóng gói cùng ứng dụng, giống hệt `Demo\Python\Basic\mvsdk.py` của ChinaVision; máy chạy vẫn cần driver và runtime DLL. Bảo đảm DLL tương ứng kiến trúc Python nằm trong thư mục mà Windows có thể tìm thấy.

Kiểm tra nhanh trong PowerShell:

```powershell
where.exe MVCAMSDK_X64.dll
python -c "import struct; print(struct.calcsize('P') * 8)"
```

Nếu lệnh đầu không thấy DLL, cài lại bộ cài ChinaVision hoặc thêm `C:\Program Files (x86)\ChinaVision\SDK\X64` vào `PATH` trước khi chạy.

---

## 2. Python environment

```bash
# từ thư mục gốc repo (QRDetector/)
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

> `opencv-contrib-python` cung cấp `WeChatQRCode` và `QRCodeDetector`.
> `qrdet` tự kéo `ultralytics` + `torch`; lần đầu chạy có thể tải model YOLOv8.

**pyzbar trên Windows:** nếu thiếu ZBar DLL, cài `pip install zbar-py` hoặc đặt `libzbar-64.dll` cạnh package `pyzbar`.

### GPU NVIDIA (khuyến nghị)

Detect QR (YOLO) chạy trên GPU NVIDIA nếu torch có CUDA; không có CUDA thì tự chạy CPU (chậm hơn nhiều).
Máy lab: GTX 1650 4 GB, driver ≥ 560. `requirements.txt` cài bản CUDA 12.6 (~2,6 GB). Kiểm tra:

```bash
.venv\Scripts\python.exe -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
```

Máy không có GPU: `pip install "torch==2.14.1+cpu" "torchvision==0.29.1+cpu" --index-url https://download.pytorch.org/whl/cpu`.
Thiết bị đang dùng hiện trên nhãn "Decode" (GPU/CPU) và trong log (`qr_detector device=…`).

### Chạy

```bash
python main.py
```

---

## 3. Sử dụng

1. **Refresh** — quét camera MindVision đang kết nối.
2. Chọn camera trong dropdown → **Open camera**. Video live hiển thị bên phải.
3. Panel trái điều khiển Exposure (Auto/Manual), Gain, Trigger, Strobe, mirror/sharpness, gamma/contrast, WB, ROI, Param A–D, Snap và hiệu ứng ảnh.
4. Panel **Kết quả QR**:
   - **Bật decode** — decode mỗi N frame.
   - **Vẽ quad** — xanh khi decode thành công, đỏ khi chỉ phát hiện được QR.
   - Hiển thị QR mới nhất, số lần lặp và lịch sử 50 lần gần nhất.
5. **Snap** — lưu frame hiện tại ra `./output.jpg|bmp|png`.
6. Panel **Quay dữ liệu — AVI không nén**, dưới preview:
   - Mở camera, đợi frame đầu tiên; chọn **Thư mục lưu** (mặc định `recordings/`).
   - Chọn **FPS video** cao hơn FPS acquisition/trigger tối đa; gợi ý ít nhất `ceil(1.25 × FPS tối đa)`. Giá trị ban đầu 60 không bảo đảm phù hợp mọi camera. Đây là FPS đầu ra SDK, **không thay đổi FPS camera** và không lấy theo FPS preview.
   - **Bắt đầu quay** / **Dừng quay**. Start chờ frame xử lý hợp lệ tiếp theo để dùng đúng ROI hiện tại; ở chế độ software-trigger có thể cần bấm **Soft trigger** khi trạng thái là STARTING. Stop vẫn hủy được yêu cầu trong lúc chưa có frame. Mỗi phiên khởi tạo thành công ghi một file `video.avi` trong thư mục timestamp + UUID riêng, không tự chia đoạn và không ghi đè phiên trước.
   - Ảnh sau ISP camera ở **độ phân giải ROI hiện tại**, không resize, không overlay QR/âm thanh và không phải RAW cảm biến. Exposure/gain/ISP trước khi quay vẫn ảnh hưởng ảnh.
   - Các control cấu hình camera bị khóa trong phiên ghi; bật/tắt decode hoặc quad vẫn dùng được. Với software-trigger, dùng nút **Soft trigger** trong panel quay (gửi lệnh bất đồng bộ tới capture thread). Stop/đóng camera chạy bất đồng bộ; chỉ coi file hoàn tất khi finalize thành công.
   - Nhãn riêng hiển thị số frame **gửi ghi thành công**, camera lost delta (hoặc “không xác định”), thời gian đã quay, đường dẫn file và lỗi. Số Push thành công không chứng minh số frame thực tế trong AVI.

## Phiên bản demo cho khách hàng

Bản riêng, chạy song song với app test camera ở trên; hai bản dùng chung camera nên không mở cùng lúc.

```bash
python main_demo.py
```

**Màn hình làm việc**

- **Bắt đầu** — tự tìm camera đã lưu → mở camera → áp dụng exposure, gain và dải đọc trong Cấu hình → chờ warm-up → decode (khi **Bật decode** đang bật). Lỗi ở bước nào thì báo đúng bước đó trong vùng video, kèm **Thử lại** và **Mở Cấu hình**.
- **Dừng** — đóng camera, giữ nguyên số liệu; **Bắt đầu** lại sẽ chạy tiếp phiên đó. **Reset phiên** đưa số liệu về 0 (có hỏi xác nhận).
- **Mã vừa đọc** và danh sách mã cập nhật ngay khi đọc được. Trạng thái dòng chốt khi lượt kết thúc (mất dấu khoảng 2 giây): `…` đang chờ, `✓` đọc được, `⚠` có mâu thuẫn, dòng đỏ là không đọc được.
- **Đã đọc / Tỉ lệ đọc / Mã/phút** chỉ tính trên lượt đã kết thúc. Lượt không đọc được và chỉ có 1 detection coi là nhận nhầm: không hiện, không tính vào tỉ lệ, vẫn có trong log `pass_finished`. Vì vậy tỉ lệ này có thể khác nhãn "Lượt QR" của app test camera.
- Không có frame mới quá 3 giây khi đang chạy → hiện "Mất tín hiệu camera". Không tự kết nối lại.
- **F11** bật/tắt toàn màn hình, **Esc** thoát toàn màn hình.

**Cấu hình** (nút ⚙ hoặc `Ctrl+,`): cửa sổ riêng, không chặn màn hình chính, đóng lại không làm dừng hệ thống.

- **Kết nối camera:** chọn camera, quét lại, **Mở** / **Đóng**. Bấm **Mở** để xem trước với đúng exposure và gain sẽ dùng khi chạy mà chưa decode (nhãn `CHỈNH CAMERA`).
- **Băng chuyền:** **Bật decode**, **Vẽ quad**, **Exposure (ms)**, **Gain**, **Chỉ đọc dải y** (y, cao), **Chỉ đọc dải x** (x, rộng), nút **Áp dụng** để đổi ngay khi camera đang mở. Dải đọc được căn bội 16.
- Exposure dài hơn thì ảnh sáng hơn nhưng QR trên băng nhòe hơn; gain cao hơn thì ảnh sáng hơn nhưng nhiễu hơn. Giá trị vượt giới hạn camera sẽ bị kẹp (camera hiện tại: gain 10–640). Băng chạy theo trục x nên dải x hẹp làm QR ở trong khung ít frame hơn.

**Lưu cấu hình**

`config/app_settings.json` (không đưa lên git, tự lưu khi đổi giá trị): serial camera và toàn bộ thông số tab Băng chuyền. File hỏng hoặc giá trị sai → dùng mặc định cho phần đó và ghi cảnh báo vào log. Bản demo không nạp Param A–D của camera và không quay video; các việc đó vẫn làm ở app test camera.

**Kiểm chứng trên camera thật trước khi demo:** đọc QR khi băng chạy; Bắt đầu/Dừng nhiều lần; rút cáp khi đang chạy; đối chiếu tỉ lệ đọc với log `pass_finished`; chạy liên tục 30 phút; F11 trên màn hình trình chiếu. Test offline không xác nhận được các mục này.

### Dung lượng và giới hạn quay video

- Dùng `CameraInitRecord(format=0)` / `CameraPushFrame` / `CameraStopRecord` từ SDK hiện có, không cần encoder package mới. Ghi trực tiếp trong capture thread, không dùng ảnh preview có thể bỏ frame.
- AVI không nén rất lớn: RGB 1920×1080 ở 30 FPS khoảng **187 MB/s, 11,2 GB/phút**, chưa tính overhead hoặc frame lặp do SDK. Khuyến nghị SSD nhanh và đo throughput thực tế.
- Mỗi phiên ghi **một file AVI liên tục**, không có ngưỡng tự chia file hoặc tự dừng theo dung lượng video trong Python. Giữ `b2GLimit=False`; SDK ghi tính năng tự chia trên 2 GiB chưa triển khai. Tài liệu đi kèm **chưa bảo đảm AVI >4 GiB hợp lệ**: cần kiểm chứng với camera/DLL thực tế trước khi dùng quay dài. Dùng ổ hỗ trợ file lớn như NTFS/exFAT, không FAT32. Đây không phải cam kết dung lượng không giới hạn hoặc không mất frame.
- Kiểm tra dung lượng trống lúc bắt đầu/mỗi giây và dừng nếu thấp hơn `max(256 MiB, 2 × footprint frame)`. Ổ đầy hoặc mất kết nối vẫn có thể khiến file chưa finalize; không báo “đã lưu” khi SDK lỗi.
- Wrapper encode đường dẫn bằng **GBK**. Nếu đường dẫn tiếng Việt/ký tự khác không biểu diễn được, chọn đường dẫn ASCII (ví dụ `D:\\QRData`); ứng dụng báo lỗi thay vì đổi ký tự hoặc chuyển thư mục ngầm.
- Không chủ động bỏ frame trong nhánh ghi Python, nhưng Push có thể chặn capture và gây mất frame tại SDK. So sánh counter camera và kiểm tra video giải mã lại; không suy diễn “lossless” từ test mock.
- Nếu finalize lỗi, **Dừng quay / Thử đóng lại** gửi một yêu cầu retry rõ ràng. Khi SDK còn chạy/treo, giữ handle/buffer; không mở camera mới đè lên tài nguyên cũ. Cửa sổ không xác nhận thoát khi chưa đóng được camera.

**Kiểm chứng phần cứng trước khi thu thập quan trọng:** xác nhận codec không nén, RGB/mono đúng màu/hướng, kích thước ROI, thời lượng/FPS, missing/duplicate frame với cảnh có số thứ tự, trigger thưa, nhiều phiên riêng biệt và đóng khi đang ghi. Quay thực tế vượt 4 GiB, xác nhận chỉ một AVI, finalize thành công, giải mã toàn bộ và seek/phát gần cuối bằng công cụ độc lập (ví dụ ffprobe/ffmpeg, chỉ dùng kiểm chứng, không phải dependency runtime). Đối chiếu nội dung/counter sau các mốc 1/2/4 GiB, không chỉ metadata thời lượng. Nếu DLL cắt/hỏng file lớn thì chưa đạt yêu cầu quay dài; không ngầm chia file hoặc đổi backend. So sánh FPS/lost khi có/không ghi, bật/tắt QR. Test offline không xác nhận những đặc tính này.

### Đối chiếu màu video và preview

- Preview lấy bản sao ảnh sau ISP **trước** khi gọi SDK ghi, không phụ thuộc buffer sau `CameraPushFrame`. Giữ RGB8 → BGR nội bộ → RGB888 khi hiển thị; không tự đổi WB/gamma hoặc bù vàng. Đây là cách ly buffer, **chưa phải kết luận nguyên nhân ngả vàng**.
- Trước Start, bật **Lưu mẫu đối chiếu màu** nếu cần điều tra. Mặc định tắt. Tối đa 3 mẫu, ngân sách bộ nhớ 256 MiB; ảnh lớn có thể chỉ lấy được ít mẫu hơn. Khi tắt không có bản copy chẩn đoán bổ sung.
- Mẫu nằm cạnh `video.avi`, dưới `color_diagnostics/sample_0001/`: `before.bin`, `after.bin`, `before.png`, `preview.png` (nguồn trước Push), `after.png`, `metadata.json`. PNG chưa overlay/resize, không phải screenshot Qt. Metadata gồm timestamp, push ordinal, header trước/sau, thông số SDK đọc được; giá trị không đọc được là null.
- UI báo số mẫu đã lưu, đang lưu hoặc lỗi riêng. Finalize AVI thành công không đồng nghĩa mẫu đã lưu xong. Worker lưu mẫu không chặn UI/capture bằng join; khi thoát Python bình thường sẽ đợi các worker hữu hạn. Không tắt cưỡng bức nếu còn đang lưu.
- Ảnh có thể chứa nội dung cảnh camera; chỉ lưu cục bộ khi bật tùy chọn, không đưa ảnh vào log hay dịch vụ bên ngoài. Bật chẩn đoán làm tăng chi phí copy/ghi đĩa.

Công cụ offline (chạy từ gốc repo, chỉ khi cần đối chiếu):

```powershell
.\.venv\Scripts\python.exe tools/compare_recording_color.py "D:/QRData/session/video.avi" "D:/QRData/session/color_diagnostics/sample_0001" --frame 0 --view
```

`--frame` là chỉ số AVI bắt đầu từ 0, **không** suy ra từ push ordinal/FPS. Chỉ thêm `--matched` sau khi đã xác nhận cùng frame bằng nội dung/counter; nếu chưa xác nhận công cụ chỉ báo số đo, không kết luận lỗi màu. `--view` hiển thị hai ảnh bằng cùng đường QImage RGB888. Công cụ không sửa video, không tự tìm/đổi frame và không bù màu.

Nếu frame đã ghép đúng trùng pixel nguồn nhưng VLC khác màu, cần điều tra filter/output renderer của VLC, không recolor AVI để bù riêng trình phát. Nếu pixel khác, báo sai số từng kênh và giả thuyết R/B swap; không coi giả thuyết đó là bản sửa đã xác nhận.

### Test offline (không cần camera)

```bash
python -m unittest discover -s tests -t . -p "test_*.py"   # torch được nạp trước PyQt5 trong tests/__init__.py
python tests/test_improve_pipeline.py path\to\qr.jpg
python tests/test_small_qr.py                              # QR nhỏ: QR tổng hợp + frame mẫu (≥12/14)
```

Ảnh mẫu đọc từ biến môi trường `QR_SAMPLES_DIR`, mặc định `../QRDetector-research/data/images`. Thiếu ảnh thì các test liên quan được bỏ qua.

Công cụ trong `tools/` (chạy từ gốc repo, xem cách dùng ở đầu mỗi file): `bench_decode.py`, `eval_videos.py`, `sim_qr.py`, `conveyor_calc.py`, `compare_recording_color.py`, `conveyor_camera_3d.html`.

Code và dữ liệu thử nghiệm cũ nằm ở repo `../QRDetector-research`; lịch sử git của chúng ở tag `archive/research-2026-11`.

### Log chẩn đoán camera

Ứng dụng ghi console và `logs/camera.log` (UTF-8), xoay vòng ở 2 MB và giữ tối đa 3 bản cũ. Log không chứa ảnh hay nội dung QR.

Các bản ghi chính gồm thao tác SDK và mã trả về dạng hex, snapshot exposure/gain/AE/gamma khi mở camera, lỗi capture được giới hạn tần suất, và thống kê frame mỗi 5 giây (`mean`, `min`, `max`, `near_black_pct`).

- `Capture fps: 0` kèm `operation=capture`: kiểm tra trigger, cáp, driver và mã lỗi SDK.
- FPS lớn hơn 0 nhưng `mean` rất thấp hoặc `near_black_pct` gần 100%: kiểm tra exposure, gain, ánh sáng và cấu hình ISP.

---

## 4. Cấu trúc

```
QRDetector/
├── main.py                 # entry app test camera
├── main_demo.py            # entry phiên bản demo cho khách hàng
├── logging_setup.py
├── mvsdk.py                # wrapper Python MindVision được vendor từ mẫu SDK Python/Basic
├── requirements.txt
├── camera/                 # lifecycle SDK, tham số, capture thread, quay video, công thức băng chuyền
├── qr/                     # pipeline QR
│   ├── detector.py, corrector.py, preprocessor.py, decoder.py
│   ├── improved_pipeline.py, tracker.py, pass_reader.py
│   └── models/wechat/      # detect.onnx + sr.onnx (WeChat QR, ~1 MB, cho OpenCV 5)
├── ui/                     # PyQt5, app test camera: bind UI ↔ CameraManager
├── demo_ui/                # PyQt5, phiên bản demo (dùng lại form và DecodeWorker của ui/)
├── tests/                  # test offline, không cần camera
├── tools/                  # đo tốc độ, đánh giá video, mô phỏng, đối chiếu màu, tính băng chuyền
└── docs/                   # plan, spec, đề xuất khắc phục
```

Lifecycle camera:

```
CameraSdkInit → CameraEnumerateDevice → CameraInit → CameraGetCapability
→ CameraSetIspOutFormat → CameraAlignMalloc → CameraPlay
→ CameraGetImageBuffer / CameraImageProcess / CameraReleaseImageBuffer
→ CameraStop → CameraUnInit → CameraAlignFree
```

Mỗi frame được xử lý theo kích thước thật trong `FrameHead`, chuyển RGB→BGR (hoặc mono→BGR 3 kênh), rồi copy sang `np.ndarray uint8` contiguous riêng trước khi publish. UI và QR worker không giữ con trỏ vào buffer native tái sử dụng.

---

## 5. Ghi chú kỹ thuật

- **Import order:** `torch` phải được import trước PyQt5 để tránh `WinError 1114` (`c10.dll`).
- Frame đầu vào QR luôn là **BGR** `np.ndarray`.
- Decode chạy trên thread riêng; nếu pipeline bận thì frame mới bị bỏ qua thay vì xếp hàng.
- Nếu không thấy camera, mở công cụ cấu hình/Viewer của MindVision để xác nhận driver, kết nối và cấu hình mạng của camera GigE.
