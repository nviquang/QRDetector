# QRDetector — Ứng dụng quét QR bằng camera MindVision

Ứng dụng PyQt5 tích hợp **camera MindVision (MVSDK / `mvsdk`)** và **pipeline QR** (qrdet detect ở imgsz 1280 → chuỗi decode trên vùng QR cắt từ ảnh gốc: zxing → WeChat → WeChat CNN + super-resolution). Tối ưu cho QR rất nhỏ (khoảng 2–2,6 px mỗi ô); khoảng 1s/frame trên CPU. Không dùng Real-ESRGAN. Có thêm bản demo cho camera Basler (`main_basler.py`), là cấu hình dùng ở hiện trường.

```
Camera (MindVision Camera* API) → frame BGR độc lập → mỗi N frame → ImprovePipeline → quad + text QR
```

## Bài toán và ràng buộc

Đây là nguồn chuẩn duy nhất cho thông số hiện trường (chốt 18/11/2026); mọi tài liệu, báo cáo và nghiên cứu khác phải theo mục này. Bài toán: **tối ưu việc đọc QR trên phần cứng sẵn có**. Các mục ở bảng "Bất biến" không được đề xuất thay đổi; chỉ cải tiến những thứ ở bảng "Được phép thay đổi".

### Bất biến (không đề xuất thay đổi)

| Hạng mục | Giá trị |
|---|---|
| Camera | Basler a2A2840-48umBAS, đơn sắc, 8 MP (2856 × 2848 px, điểm ảnh 2,74 µm, cảm biến Sony IMX546 2/3" global shutter), USB 3 |
| Ống kính | 4 mm |
| Số camera | 2, đặt cạnh nhau phủ bề rộng băng |
| QR | **32 × 32 mm**, **version 2 (25 × 25 ô), mức sửa lỗi M** → ô rộng 1,28 mm |
| Nội dung | `dãy số` + `#` + `dãy số`; độ dài từng dãy **không cố định** (regex `^\d+#\d+$`) |
| Vị trí dán tem | Bất kỳ trên tấm kính (vị trí và góc xoay tùy ý) |
| Băng chuyền | Rộng 3,25 m (ngang), dài 1,7 m (theo chiều chạy), tốc độ **80–120 mm/s** |
| Máy xử lý | **Jetson Nano** hoặc **máy tính chỉ có CPU**; thuật toán phải chạy được trên cả hai |

### Được phép thay đổi

| Hạng mục | Phạm vi |
|---|---|
| Độ cao camera | Chỉnh sao cho mỗi camera phủ 1,5–1,6 m bề ngang, hai camera xấp xỉ 3,25 m |
| Buồng tối và chiếu sáng | Buồng tối dài 60 cm theo chiều chạy, đèn bên trong: loại đèn, vị trí, góc, khuếch tán, strobe đồng bộ exposure, tấm che |
| Thông số camera | Exposure, gain, ROI dải (theo vùng buồng tối), fps, trigger, định dạng ảnh |
| Phần mềm | Toàn bộ thuật toán phát hiện, theo dõi, giải mã, lịch chạy, tối ưu suy luận cho Jetson Nano/CPU |

Chưa xác nhận (hỏi trước khi đưa vào đề xuất): góc nghiêng camera, việc lắp thêm cảm biến quang/encoder, bản Jetson (Jetson Nano đời đầu Maxwell, JetPack 4.6, Ubuntu 18.04, Python 3.6, hay Jetson Orin Nano), cấu hình máy CPU.

### Số suy ra

Mô hình lỗ kim, ống 4 mm, chưa tính méo ống kính (ống góc rộng thường méo thùng, px/ô ở mép ảnh thấp hơn ở giữa: phải đo lại ở mép).

| Bề ngang mỗi camera | 1,50 m | 1,60 m | 1,66 m* |
|---|---:|---:|---:|
| Độ cao camera xấp xỉ | 0,77 m | 0,82 m | 0,85 m |
| mm/px | 0,525 | 0,560 | 0,581 |
| Cạnh QR 32 mm | 61 px | 57 px | 55 px |
| **px/ô (V2)** | **2,44** | **2,29** | **2,20** |

\* Hai camera 1,6 m chỉ phủ 3,2 m, hụt 5 cm so với băng 3,25 m. Muốn mọi tem nằm trọn trong ít nhất một camera thì vùng chồng phải ≥ đường chéo QR (~45 mm) cộng biên, tức mỗi camera khoảng 1,66 m. Cần xác nhận tấm kính có phủ tới sát mép băng không.

- **Theo chiều chạy:** buồng tối 60 cm ≈ 1070 hàng ảnh ở 0,56 mm/px (ROI dải khoảng 2856 × 1072, khoảng 3 MP). Tem nằm trong buồng **5–7,5 s** (120–80 mm/s).
- **Vệt mờ:** `vệt = v × t`. Giữ vệt ≤ 0,25 ô (0,32 mm) cần exposure ≤ 2,7 ms ở 120 mm/s, ≤ 4 ms ở 80 mm/s. Khuyến nghị **≤ 2,5 ms** ở mọi tốc độ (vệt ≤ 0,3 mm ≈ 0,54 px), bù độ sáng bằng đèn trong buồng tối trước rồi mới tăng gain. Không bật AE.
- **Dung lượng V2-M** (28 byte dữ liệu = 224 bit): mã hóa tách đoạn (số, `#` ở chế độ byte, số) chứa được tổng khoảng **52 chữ số**; mã hóa cả chuỗi ở chế độ byte chỉ được **26 ký tự** (25 chữ số + `#`). Ví dụ 14#12 (27 ký tự) chỉ vừa V2-M khi tách đoạn (135 bit); phần mềm in mặc định dùng chế độ byte sẽ tự đẩy lên version 3. Khi in phải ép version 2, mức M và tách đoạn:

```python
import segno
from segno import consts

qr = segno.make([("18000090001000", consts.MODE_NUMERIC), ("#", consts.MODE_BYTE), ("000000001612", consts.MODE_NUMERIC)],
                version=2, error="m", boost_error=False, micro=False)
qr.save("tem.png", scale=10, border=4)
```

### Hệ quả cho nghiên cứu

- Mức px/ô (2,2–2,44) đã cố định, thấp hơn mức 3–3,5 px/ô mà tài liệu thường khuyến nghị: phần mềm phải đọc được ở mức này. Không đề xuất tem lớn hơn, đổi nội dung/version/mức sửa lỗi, thêm hay đổi camera/ống kính, line-scan, đầu đọc thương mại, cố định vị trí dán tem.
- Đòn bẩy phần cứng còn lại: **buồng tối + đèn** (exposure ngắn, ánh sáng đều, giảm phản xạ kính) và độ cao/ROI camera.
- Nội dung có độ dài thay đổi: được lọc bằng `^\d+#\d+$`, không được giả định độ dài cố định. Bộ giải mã nhận mọi version và mức sửa lỗi (từ 20/11/2026), tem in sai quy cách vẫn đọc được; muốn chỉ nhận V2-M thì truyền `expected_symbol=content_filter.EXPECTED_SYMBOL`. Có thể ghim bit cấu trúc (chỉ thị mode, trường đếm, `#` = 0x23, byte đệm 0xEC/0x11) theo từng giả thiết độ dài khi giải, nhưng bit đã dùng để ghim thì không được tính lại làm bằng chứng kiểm tra.
- Phải chạy trên Jetson Nano (ARM, GPU Maxwell 128 nhân, RAM 4 GB chung) hoặc CPU: tính đến TensorRT/ONNX Runtime, bộ nhớ, và hai luồng camera cùng lúc. Phần riêng Windows (MVSDK, gõ phím `SendInput`, khay hệ thống) không có trên Jetson.
- **Dữ liệu hiện có chưa đúng cấu hình này:** `data/field/raw` quay ngày 06/11 và 13/11 ở camera cao 1 m (0,673 mm/px), tem 36 mm in lẫn version, không có buồng tối, ngày 13/11 có AE (vệt mờ 10–20 px). Dùng được để thử luồng và phát hiện, không dùng để kết luận tỉ lệ đọc. Thông số cũ của phòng thí nghiệm (MindVision 2448 × 2048, tem 25 mm, 0,43 mm/px) trong `docs/` và các báo cáo trước 18/11/2026 chỉ để tham khảo lịch sử.

---

## 1. Yêu cầu

| Thành phần  | Phiên bản                                                               |
| ----------- | ----------------------------------------------------------------------- |
| Windows     | 10/11 64-bit                                                            |
| Python      | 3.11 (64-bit)                                                           |
| SDK camera  | ChinaVision Camera Platform 2.1.10.196 (bộ cài `ChinaVision Camera Platform Setup(2.1.10.196_20260721)(WIN10)`) |
| Runtime DLL | `MVCAMSDK_X64.dll` với Python 64-bit (`MVCAMSDK.dll` với Python 32-bit) |
| Camera      | Camera đã hoạt động với app ChinaVision đi kèm bộ cài                   |

**Jetson Nano 4GB:** chạy trong Docker, chỉ CPU, không cần torch — xem [docs/jetson-nano.md](docs/jetson-nano.md).

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

## App hai camera

MindVision (A) và Basler (B) chạy song song, cùng đọc QR, kết quả gộp một danh sách. Đóng các app camera khác trước khi chạy vì mỗi camera chỉ mở được ở một chương trình.

```bash
python main_dual.py
```

Cùng một mã trong 30 giây chỉ hiện một dòng (ghi `A`, `B` hoặc `A+B`) và chỉ gửi server một lần. Tỉ lệ đọc hiện riêng từng camera. Một camera lỗi thì camera kia vẫn chạy, bấm **Thử lại** trên khung của camera lỗi. Cấu hình lưu ở `config/dual_settings.json`, lần đầu lấy từ cấu hình của hai bản một camera; N, exposure, gain, vùng đọc đặt riêng từng camera.

## Bản demo dùng camera Basler

Cùng giao diện với bản demo bên dưới, dùng camera Basler (viết cho `a2A2840-48umBAS`) qua `pypylon`. Cần cài pylon của Basler (có driver USB) và cắm camera vào cổng USB 3, không qua hub. Không cần MindVision SDK: thiếu DLL thì `mvsdk` vẫn import được, chỉ camera MindVision không dùng được.

```bash
python main_basler.py
```

Cấu hình lưu riêng ở `config/basler_settings.json`. Mặc định Basler: exposure **2 ms** (vệt mờ ≤ 0,43 px ở 120 mm/s), gain 6 dB, chỉ đọc dải y 880–1952 (1072 hàng, ứng với buồng tối 60 cm ở ~0,56 mm/px) — chỉnh dải theo vị trí buồng tối thật khi lắp đặt. File cấu hình đã lưu từ trước vẫn giữ giá trị cũ (ví dụ 12,9 ms): xóa file hoặc sửa trong tab Băng chuyền. Kiểm tra nhanh camera: `python tools/test_basler.py --list`.

**Bộ phát hiện** chọn bằng biến môi trường `QR_DETECTOR` (PowerShell: `$env:QR_DETECTOR="openvino"`):

| `QR_DETECTOR` | Model | Cần |
|---|---|---|
| `openvino` (mặc định) | YOLOv8n detect chuyển từ qrdet-n (`qr/models/qrdet_n_detect.onnx`), OpenVINO, CPU | `openvino`, không cần torch lúc chạy |
| `onnx` | cùng model, ONNX Runtime | `onnxruntime` |
| `tensorrt` | cùng model, TensorRT FP16 trên GPU Jetson qua dịch vụ `tools/trt_service.py` (`docs/jetson-nano.md`) | engine `tools/build_trt_engine.sh`; thiếu dịch vụ thì lùi về OpenVINO |
| `qrdet` | qrdet YOLOv8s-seg, torch, imgsz 1280 (bộ phát hiện cũ) | torch (GPU nếu có) |

Thiếu `openvino` thì tự lùi sang ONNX Runtime, rồi qrdet, và ghi cảnh báo. Bộ phát hiện ONNX/OpenVINO chỉ chạy CPU nên ô **Dùng GPU** bị vô hiệu hóa; muốn dùng GPU của máy phát triển thì đặt `QR_DETECTOR=qrdet`. `QR_DETECT_SCALE` (mặc định 0,75) là tỉ lệ thu ảnh trước khi đưa vào mạng, `QR_DETECT_THREADS` giới hạn số luồng. Tạo lại model: `python tools/export_qrdet_detect.py` (chép trọng số qrdet-n seg sang YOLOv8n detect, không train, kiểm tra hộp trùng bản seg; `--seg` xuất thêm chính bản seg sang ONNX để so). Tiền xử lý giống LetterBox của ultralytics (INTER_LINEAR, đệm chia đều hai phía). So độ nhạy và tốc độ trên `data/field`: `python tools/bench_detector.py`.

Đo 19/11/2026, Ryzen 5 5500U, cùng model nano (qrdet-n) ở ba cách chạy, tỉ lệ thu áp cho cạnh dài của từng ảnh; 363 frame có tem (638 hộp, không tính tem chạm mép vì sản phẩm bỏ qua), 224 frame không tem; recall so với qrdet-s:

| Tỉ lệ | Cách chạy | recall | nhầm | ms p50 / p95 |
|---|---|---:|---:|---:|
| — | qrdet-s seg torch imgsz 1280 (hiện tại) | 100% | 0 | 305 / 681 |
| ×0,45 | qrdet-n seg torch | 92,9% | 5 | 135 / 230 |
| | n-detect torch | 92,9% | 5 | 74 / 78 |
| | qrdet-n seg / n-detect ONNX Runtime | 91,5% | 3 | 86 / 64 |
| | qrdet-n seg / n-detect OpenVINO | 91,5% | 3 | 68 / 52 |
| ×0,6 | qrdet-n seg torch | 98,3% | 7 | 205 / 293 |
| | n-detect torch | 98,3% | 7 | 133 / 142 |
| | qrdet-n seg / n-detect ONNX Runtime | 96,6% | 8 | 154 / 115 |
| | qrdet-n seg / n-detect OpenVINO | 96,6% | 8 | 120 / 93 |
| ×0,75 | qrdet-n seg torch | 99,7% | 5 | 281 / 364 |
| | n-detect torch | 99,7% | 5 | 203 / 212 |
| | qrdet-n seg / n-detect ONNX Runtime | 99,7% | 5 | 242 / 182 |
| | qrdet-n seg / n-detect OpenVINO | 99,7% | 5 | 185 / 144 |

Ở các dòng "seg / detect" hai số ms là p50 của bản seg / bản detect (cùng recall). Kết luận: bỏ nhánh mask không đổi kết quả (seg và detect trùng nhau ở mọi tỉ lệ) và nhanh hơn 25–45%; ONNX/OpenVINO hụt 1–2 điểm recall so với torch ở ×0,45–0,6 vì tỉ lệ thu thực của ultralytics lệch chút ít (ví dụ ×0,607 thay vì ×0,6), làm vài tem sát ngưỡng độ tin rơi xuống dưới 0,3; ở ×0,75 bằng nhau. OpenVINO nhanh nhất. Mọi phương án bắt được 10/10 lượt. Cột "nhầm" (hộp trên đoạn không có tem) chưa xem lại bằng mắt: nhãn đoạn là heuristic và EDA ghi nhận có tem trắng YOLO bỏ sót trong đoạn `glass_no_det`. Dữ liệu là cấu hình cũ (QR 55–75 px, gần cỡ QR mới ~57 px), chỉ dùng để so bộ phát hiện. Từ 20/11/2026 mặc định là n-detect OpenVINO ×0,75. Bộ phát hiện này không có mask: quad lấy cạnh từ hộp và góc xoay từ hướng gradient (`qr/quad_estimate.py`), đệm 1,15 lần để bước warp bao trọn mã; với đệm này `tests/test_small_qr.py` đọc 12/14 frame mẫu, bằng qrdet-s (đệm 1,06 chỉ đọc 11/14). Vẫn cần đo lại trên bản ghi buồng tối và máy hiện trường (Jetson/CPU).

**Lọc chống đọc sai** (`qr/content_filter.py`, luôn bật): nội dung phải là dãy số, có thể kèm `#` và dãy số thứ hai (`[0-9]+(?:#[0-9]+)?`, toàn chuỗi; từ 20/11/2026 nhận cả mã chỉ có số như tem thử `000000585545`); nhận mọi version và mức sửa lỗi (mặc định `expected_symbol=None`; truyền `content_filter.EXPECTED_SYMBOL` để chỉ nhận V2-M: zxing kiểm tra version/mức, WeChat đếm ô qua đường timing); tâm mã phải nằm trong vùng đang đọc, nới 15% (chặn đọc nhầm tem bên cạnh). Mã bị loại ghi log `code_rejected` kèm lý do và không tính phiếu. Kết quả bộ đọc nền cũng qua lọc nội dung.

**Đọc nền cho QR khó:** lượt mà bộ đọc thường không đọc được được gửi sang một tiến trình riêng chạy bộ giải trong `qr/solvers` (tái tạo trên lưới ô `grid_sr`, rồi `preproc_sweep`), nhận mọi version (B: lưới V1–V3, C: 21/25/29/33 ô) và mọi mức sửa lỗi. Lượt đó báo mã trễ khoảng 4 s chờ đóng lượt cộng thời gian giải; lượt đọc được bình thường không bị trễ. Đo trên 8 lượt V2-M tổng hợp khó (2,0–2,3 px/ô, σ 0,8–1,6 px), Ryzen 5 5500U: B đọc 6/8, p50 6,4 s (bản cũ 5/8, 10,2 s; khi ép chỉ V2-M là 4,1 s); C đọc 6/8, p50 3,3 s (bản cũ 6/8, 6,9 s); lượt không có mã: B 5,9 s, C 12 s. Test: `python -m unittest tests.test_solvers_v2m` (chậm, khoảng 40 s). Muốn chạy pipeline cũ để đối chiếu: đặt biến môi trường `QR_FALLBACK=off` trước khi chạy (PowerShell: `$env:QR_FALLBACK="off"`).

## Bản phát lại dữ liệu đã ghi

Chạy đúng luồng của `main_basler.py` (giao diện, đọc nhiều frame, đọc nền B/C, bảng kết quả) trên các lần ghi trong `data/field/raw` thay cho camera. Không cần camera, pylon hay MindVision SDK.

```bash
python main_replay.py
```

Tùy chọn: `--data <thư mục>` (mặc định `data/field/raw`, mỗi thư mục con chứa `frame_NNNN.tiff` + `meta.json`) và `--speed 0.5` (hệ số tốc độ, 1 = thời gian thật).

- Chọn lần ghi trong **Cấu hình → Kết nối** (danh sách camera là danh sách lần ghi), rồi bấm **Bắt đầu**. Frame phát theo nhịp ghi gốc từ lúc nhận diện sẵn sàng; decode bận thì bỏ frame như camera thật.
- Hết frame thì app tự **Dừng**, giữ số liệu phiên và hiện "Hết dữ liệu". Bấm Bắt đầu để phát lại từ đầu. Lượt khó cuối video vẫn được đọc nền xong rồi mới chốt (chờ tối đa 3 phút).
- **Mở** ở tab Kết nối chỉ hiện frame đầu, để chỉnh vùng đọc.
- Exposure dùng để tính vệt mờ lấy từ `meta.json` (`exposure_ms`) nếu đã điền, nếu không thì lấy ô exposure ở tab Băng chuyền. Vùng đọc được áp bằng cách cắt frame.
- Cấu hình lưu ở `config/replay_settings.json`. **Gửi mã lên server mặc định tắt**, để mã từ dữ liệu cũ không lẫn vào dữ liệu thật.

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
- **Chạy nền** (cạnh nút ⚙, hoặc `Ctrl+H`, có ở `main_demo.py` và `main_basler.py`) — ẩn cửa sổ xuống khay hệ thống (vùng ^ cạnh đồng hồ); camera, decode và gửi server vẫn chạy. Màu icon theo trạng thái (xanh: đang chạy, vàng: đang kết nối/dừng, đỏ: lỗi), di chuột lên icon xem số mã đã đọc. Bấm icon để mở lại; chuột phải có **Bắt đầu/Dừng** và **Thoát**. Lỗi camera hoặc mất tín hiệu lúc chạy nền sẽ hiện thông báo của Windows. Nút X vẫn thoát app như cũ. Chưa chặn mở app lần thứ hai: icon đang ở khay nghĩa là app vẫn giữ camera.

**Cấu hình** (nút ⚙ hoặc `Ctrl+,`): cửa sổ riêng, không chặn màn hình chính, đóng lại không làm dừng hệ thống.

- **Kết nối camera:** chọn camera, quét lại, **Mở** / **Đóng**. Bấm **Mở** để xem trước với đúng exposure và gain sẽ dùng khi chạy mà chưa decode (nhãn `CHỈNH CAMERA`).
- **Băng chuyền:** **N (frame / lần decode)** (1–1000, mặc định 5, có hiệu lực ngay kể cả khi đang chạy), **Bật decode**, **Vẽ quad**, **Gửi mã lên server** (tắt thì mã vẫn hiện trong danh sách nhưng không gửi đi, các mã đang chờ bị bỏ và không gửi bù khi bật lại), **Exposure (ms)**, **Gain**, **Chỉ đọc dải y** (y, cao), **Chỉ đọc dải x** (x, rộng), nút **Áp dụng** để đổi ngay khi camera đang mở. Dải đọc được căn bội 16.

**Gửi mã lên server** dùng API báo cáo tấm (`docs/camera-integration.md`). Tem dạng `<số>#<mã tấm>` chỉ gửi phần sau dấu `#` (ví dụ `10000100000500#000000001634` gửi `000000001634`); mã không có `#` gửi nguyên chuỗi. Chép `.env.example` thành `.env` ở thư mục gốc rồi điền `BASE_URL`, `APP_TOKEN_SECRET`, `API_KEY` do quản trị viên cấp (server dev đặt sau đăng nhập HTTP Basic thì điền thêm `BASIC_AUTH_USER`, `BASIC_AUTH_PASSWORD`). Thiếu biến thì ô **Gửi mã lên server** bị khóa và thanh trạng thái báo biến còn thiếu. Lỗi gửi hiện ở thanh trạng thái kèm câu server trả về; gặp `invalid X-App-Token — kiểm tra giờ máy` thì bật đồng bộ giờ tự động của Windows. Thử kết nối không cần camera: `python tools/try_report_api.py <mã>` (mã không tồn tại trả về "Không tìm thấy tấm" là chữ ký và key đã đúng; mã có thật sẽ được ghi nhận như vừa quét).
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

Công cụ trong `tools/` (chạy từ gốc repo, xem cách dùng ở đầu mỗi file): `bench_decode.py`, `test_basler.py`, `eval_videos.py`, `sim_qr.py`, `conveyor_calc.py`, `compare_recording_color.py`, `conveyor_camera_3d.html`.

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
├── main_basler.py          # entry bản demo dùng camera Basler
├── main_replay.py          # entry bản phát lại data/field/raw qua luồng main_basler
├── main_dual.py            # entry app hai camera (MindVision + Basler)
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
