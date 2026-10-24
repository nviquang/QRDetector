# solution/ — Ứng dụng quét QR bằng camera MindVision

Ứng dụng PyQt5 tích hợp **camera MindVision (MVSDK / `mvsdk`)** và **pipeline QR** (qrdet detect ở imgsz 1280 → chuỗi decode trên vùng QR cắt từ ảnh gốc: zxing → WeChat → WeChat CNN + super-resolution). Tối ưu cho QR nhỏ (~60px) trên frame 2448×2048; khoảng 1s/frame trên CPU. Không dùng Real-ESRGAN.

```
Camera (MindVision Camera* API) → frame BGR độc lập → mỗi N frame → ImprovePipeline → quad + text QR
```

---

## 1. Yêu cầu

| Thành phần | Phiên bản |
| --- | --- |
| Windows | 10/11 64-bit |
| Python | 3.11 (64-bit) |
| SDK camera | MindVision MVSDK/driver tương thích camera |
| Runtime DLL | `MVCAMSDK_X64.dll` với Python 64-bit (`MVCAMSDK.dll` với Python 32-bit) |
| Camera | Camera đã hoạt động với `Demo/Python/Basic` |

`solution/mvsdk.py` là wrapper Python được đóng gói cùng ứng dụng; máy chạy vẫn cần driver và runtime DLL MindVision. Bảo đảm DLL tương ứng kiến trúc Python nằm trong thư mục mà Windows có thể tìm thấy (thường do bộ cài SDK thêm vào `PATH`).

Kiểm tra nhanh trong PowerShell:

```powershell
where.exe MVCAMSDK_X64.dll
python -c "import struct; print(struct.calcsize('P') * 8)"
```

Nếu lệnh đầu không thấy DLL, cài lại MindVision SDK/driver hoặc thêm thư mục chứa DLL vào `PATH` trước khi chạy.

---

## 2. Python environment

```bash
# từ thư mục gốc repo (QRDetector/)
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install PyQt5 numpy opencv-contrib-python pillow pyzbar zxing-cpp qrdet torch torchvision ultralytics
```

> `opencv-contrib-python` cung cấp `WeChatQRCode` và `QRCodeDetector`.
> `qrdet` tự kéo `ultralytics` + `torch`; lần đầu chạy có thể tải model YOLOv8.

**pyzbar trên Windows:** nếu thiếu ZBar DLL, cài `pip install zbar-py` hoặc đặt `libzbar-64.dll` cạnh package `pyzbar`.

### Chạy

```bash
cd solution
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
   - Mở camera, đợi frame đầu tiên; chọn **Thư mục lưu** (mặc định `solution/recordings/`).
   - Chọn **FPS video** cao hơn FPS acquisition/trigger tối đa; gợi ý ít nhất `ceil(1.25 × FPS tối đa)`. Giá trị ban đầu 60 không bảo đảm phù hợp mọi camera. Đây là FPS đầu ra SDK, **không thay đổi FPS camera** và không lấy theo FPS preview.
   - **Bắt đầu quay** / **Dừng quay**. Start chờ frame xử lý hợp lệ tiếp theo để dùng đúng ROI hiện tại; ở chế độ software-trigger có thể cần bấm **Soft trigger** khi trạng thái là STARTING. Stop vẫn hủy được yêu cầu trong lúc chưa có frame. Mỗi phiên khởi tạo thành công ghi một file `video.avi` trong thư mục timestamp + UUID riêng, không tự chia đoạn và không ghi đè phiên trước.
   - Ảnh sau ISP camera ở **độ phân giải ROI hiện tại**, không resize, không overlay QR/âm thanh và không phải RAW cảm biến. Exposure/gain/ISP trước khi quay vẫn ảnh hưởng ảnh.
   - Các control cấu hình camera bị khóa trong phiên ghi; bật/tắt decode hoặc quad vẫn dùng được. Với software-trigger, dùng nút **Soft trigger** trong panel quay (gửi lệnh bất đồng bộ tới capture thread). Stop/đóng camera chạy bất đồng bộ; chỉ coi file hoàn tất khi finalize thành công.
   - Nhãn riêng hiển thị số frame **gửi ghi thành công**, camera lost delta (hoặc “không xác định”), thời gian đã quay, đường dẫn file và lỗi. Số Push thành công không chứng minh số frame thực tế trong AVI.

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
.\.venv\Scripts\python.exe solution/tests/compare_recording_color.py "D:/QRData/session/video.avi" "D:/QRData/session/color_diagnostics/sample_0001" --frame 0 --view
```

`--frame` là chỉ số AVI bắt đầu từ 0, **không** suy ra từ push ordinal/FPS. Chỉ thêm `--matched` sau khi đã xác nhận cùng frame bằng nội dung/counter; nếu chưa xác nhận công cụ chỉ báo số đo, không kết luận lỗi màu. `--view` hiển thị hai ảnh bằng cùng đường QImage RGB888. Công cụ không sửa video, không tự tìm/đổi frame và không bù màu.

Nếu frame đã ghép đúng trùng pixel nguồn nhưng VLC khác màu, cần điều tra filter/output renderer của VLC, không recolor AVI để bù riêng trình phát. Nếu pixel khác, báo sai số từng kênh và giả thuyết R/B swap; không coi giả thuyết đó là bản sửa đã xác nhận.

### Test offline (không cần camera)

```bash
python -m unittest discover -s solution/tests -p "test_*.py"
cd solution
python tests/test_improve_pipeline.py            # ảnh mặc định ../adown.jpg
python tests/test_improve_pipeline.py path\to\qr.jpg
python tests/test_small_qr.py                    # QR nhỏ: QR tổng hợp + frame mẫu ../images/*.bmp (≥12/14)
```

### Log chẩn đoán camera

Ứng dụng ghi console và `solution/logs/camera.log` (UTF-8), xoay vòng ở 2 MB và giữ tối đa 3 bản cũ. Log không chứa ảnh hay nội dung QR.

Các bản ghi chính gồm thao tác SDK và mã trả về dạng hex, snapshot exposure/gain/AE/gamma khi mở camera, lỗi capture được giới hạn tần suất, và thống kê frame mỗi 5 giây (`mean`, `min`, `max`, `near_black_pct`).

- `Capture fps: 0` kèm `operation=capture`: kiểm tra trigger, cáp, driver và mã lỗi SDK.
- FPS lớn hơn 0 nhưng `mean` rất thấp hoặc `near_black_pct` gần 100%: kiểm tra exposure, gain, ánh sáng và cấu hình ISP.

---

## 4. Cấu trúc

```
solution/
├── main.py                 # entry
├── mvsdk.py                # wrapper Python MindVision được vendor từ Demo Basic
├── camera/
│   └── camera_manager.py   # lifecycle SDK, tham số và capture thread → BGR frame
├── qr/                     # pipeline QR (không sửa production/)
│   ├── detector.py
│   ├── corrector.py
│   ├── preprocessor.py
│   ├── decoder.py
│   ├── improved_pipeline.py
│   └── models/wechat/      # detect.onnx + sr.onnx (WeChat QR, ~1 MB, cho OpenCV 5)
├── ui/                     # PyQt5, bind UI ↔ CameraManager
└── tests/                  # test offline
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
- **Không sửa** `production/` và `Demo/`; mọi thay đổi thuộc `solution/`.
- Frame đầu vào QR luôn là **BGR** `np.ndarray`.
- Decode chạy trên thread riêng; nếu pipeline bận thì frame mới bị bỏ qua thay vì xếp hàng.
- Nếu không thấy camera, mở công cụ cấu hình/Viewer của MindVision để xác nhận driver, kết nối và cấu hình mạng của camera GigE.
