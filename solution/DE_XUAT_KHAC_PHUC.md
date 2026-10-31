# Đề xuất khắc phục — QR trên băng chuyền (`solution/`)

Ngày: 31/10/2026 · Căn cứ: `logs/camera.log` (phiên 20/10 và 27/10), kết quả test ngày 31/10, code tại commit `510e294`.

Mục tiêu: **tỷ lệ đọc đúng mỗi QR đi qua camera** (read rate theo lượt) ở tốc độ băng 10–30 cm/s.
Các giải pháp dưới đây được **xếp theo mức tác động lên kết quả đọc**, từ lớn nhất đến nhỏ nhất.

---

## Bảng xếp hạng

| # | Vấn đề | Loại giải pháp chính | Tác động | Chi phí / công sức |
|---|---|---|---|---|
| 1 | Ảnh quá tối khi phơi sáng ngắn (thiếu ánh sáng khoảng 100 lần) | **Phần cứng**: đèn chiếu mạnh, nháy theo camera (strobe) | Rất cao, đây là điều kiện bắt buộc | Trung bình |
| 2 | QR quá ít pixel (khoảng 2,8 px/ô) | **Phần cứng**: ống kính/khoảng cách, QR lớn hơn | Rất cao | Thấp đến trung bình |
| 3 | Đọc QR chậm (khoảng 1 giây/frame) | **Phần mềm**: tách luồng decode, tracker, tăng tốc detect | Cao | Trung bình |
| 4 | Chưa có số liệu đọc trên băng thật | **Phần mềm và quy trình**: bộ dữ liệu và công cụ đo | Cao (không đo thì không biết đã sửa đúng chưa) | Thấp |
| 5 | Chụp không đồng bộ với vật (chạy tự do) | **Phần cứng và phần mềm**: cảm biến quang + trigger ngoài | Trung bình | Thấp đến trung bình |
| 6 | Lỗi SDK khi đổi cấu hình lúc đang chụp | **Phần mềm**: tạm dừng luồng chụp khi cấu hình | Trung bình (ổn định vận hành) | Thấp |
| 7 | Test hỏng, thiếu pytest, quay video chưa kiểm chứng | **Phần mềm** | Thấp (không ảnh hưởng trực tiếp tới kết quả đọc) | Thấp |

---

## 1. Ánh sáng — nguyên nhân số 1 khiến không đọc được

### Bằng chứng trong log (27/10)
| Chế độ | Exposure | Độ sáng TB (0–255) | % điểm gần đen |
|---|---|---|---|
| AE bật, toàn khung | AE tự chỉnh, ước tính ~200 ms (chỉ khoảng **5 fps**) | 105–125 | 3–7% |
| Băng chuyền, dải 2448×768 | 12,9 ms | 8–10 | khoảng 60% |
| Băng chuyền | 6,45 ms | 4–5 | 75–90% |
| Băng chuyền | 4,3 ms | 3–12 | 58–96% |

Độ sáng tăng gần như **tuyến tính theo thời gian phơi sáng**, khoảng 0,7 mức xám mỗi ms. Ở 30 cm/s, nếu muốn nhòe ≤1 px thì exposure chỉ được **1,43 ms**, khi đó độ sáng TB chỉ khoảng 1. Như vậy cần khoảng **100 lần ánh sáng** so với hiện tại. Không thuật toán nào bù được khoảng thiếu này: ở mức xám 3–10, chỉ còn vài mức xám để phân biệt ô đen với ô trắng, và nhiễu lấn át tín hiệu.

Ngoài ra, khi bật AE, camera chỉ đạt khoảng 5 fps và nhòe chuyển động rất lớn. Vì vậy ánh sáng yếu cũng đang làm hỏng cả chế độ thường.

### Phần cứng (giải pháp chính)
1. **Đèn LED công nghiệp dạng thanh (bar light), chiếu xiên 30–45°** lên dải băng nằm trong vùng ROI. Chiếu xiên giúp tránh lóa gương trên tem in bóng. Nên chọn đèn có cường độ cao và dài hơn bề rộng ROI.
2. **Cho đèn nháy đồng bộ với camera (strobe)**: nối cổng output của camera vào driver đèn. SDK đã có sẵn `CameraSetStrobeMode`, `CameraSetStrobePulseWidth`, `CameraSetStrobeDelayTime`, `CameraSetStrobePolarity` và `CameraSetOutPutIOMode` trong `mvsdk.py`. Khi đèn chỉ nháy trong lúc phơi sáng:
   - LED được phép chạy dòng quá định mức (overdrive), sáng hơn chế độ liên tục nhiều lần và ít nóng.
   - Thời gian xung đèn (ví dụ 100–500 µs) mới là thời gian phơi sáng thực tế, nên **vệt mờ giảm xuống dưới 1 px ngay cả ở 30 cm/s**, không phải đánh đổi với độ sáng nữa.
3. **Che ánh sáng môi trường** (chụp che, rèm) để chỉ còn ánh sáng từ đèn strobe. Ảnh sẽ ổn định, không phụ thuộc đèn trần hay ánh sáng ban ngày.
4. **Ống kính**: mở khẩu (số f nhỏ hơn, ví dụ f/2.8 thay vì f/8) sẽ thêm ánh sáng, nhưng độ sâu trường ảnh giảm. Chỉ nên làm vậy khi khoảng cách tới băng cố định.
5. **Nếu camera đang dùng là bản màu (Bayer)**: bản mono cùng độ phân giải nhận nhiều ánh sáng hơn khoảng 2–3 lần và cho độ nét thật cao hơn, vì không phải nội suy Bayer. Cần kiểm tra lại model. `CameraManager` đã đọc `bMonoSensor` từ capability.

### Phần mềm (hỗ trợ, không thay được phần cứng)
- Thêm điều khiển **gain** (`set_analog_gain` đã có) vào chế độ băng chuyền, ví dụ tự tăng gain tới khi độ sáng TB vượt ngưỡng 80 thì dừng. Cách này chỉ tạm thời: gain cao thì nhiễu cao.
- Thêm cấu hình strobe vào `apply_conveyor_mode` (chế độ, độ rộng xung, độ trễ, cực tính) và hiển thị trên UI.
- Cảnh báo ngay trên nhãn trạng thái khi độ sáng TB < 40 hoặc tỷ lệ điểm gần đen > 30%, ví dụ: "Thiếu sáng — không đủ để đọc QR".
- Khi đo, dùng khung tối ưu ánh sáng trên QR (độ tương phản trong ROI) thay vì độ sáng TB của cả dải.

**Tiêu chí đạt:** ở exposure (hoặc xung strobe) ≤1,4 ms, độ sáng TB trong vùng QR đạt 80–150 và tỷ lệ cháy sáng < 1%.

---

## 2. Độ phân giải trên QR — ~2,8 px/ô là quá sát giới hạn

Hiện tại: 0,43 mm/px, QR 25 mm version 1 (21 ô), tức **25 ÷ 0,43 ÷ 21 ≈ 2,8 px/ô**. Thực tế cascade decode phải upscale ×3–×4 và dùng tới WeChat CNN+SR mới đạt 12/14 ảnh mẫu. Đó là ảnh tĩnh và đủ sáng; khi có nhòe và nhiễu, tỷ lệ sẽ còn giảm. Để đọc ổn định nên đạt **≥4 px/ô**, tốt nhất là 5 px/ô trở lên.

### Phần cứng
Có ba cách, chọn một hoặc kết hợp:

| Cách | Kết quả px/ô | Đánh đổi |
|---|---|---|
| In QR to hơn: 35 mm / 40 mm (vẫn version 1) | 3,9 / 4,4 | Rẻ nhất, nếu được phép đổi tem |
| Ống kính tiêu cự dài hơn hoặc đưa camera lại gần để đạt 0,25 mm/px | 4,8 (QR 25 mm) | Vùng nhìn (FOV) hẹp lại: 612 × 512 mm |
| Đạt 0,20 mm/px | 6,0 | FOV 490 × 410 mm, cần bề rộng băng nhỏ hơn mức này |

- Kiểm tra lại FOV dọc theo hướng băng: với 0,25 mm/px, chiều dài vùng nhìn là 612 mm. Ở 30 cm/s và 50 fps, một QR nằm trong khung khoảng **(612 − 25) ÷ 300 × 50 ≈ 98 frame**, vẫn dư rất nhiều cơ hội đọc. `frames_in_view()` trong `conveyor.py` tính đúng con số này.
- Lấy nét đúng tại mặt băng, khóa vòng nét và vòng khẩu bằng vít.
- Lắp camera vuông góc với băng để QR không bị méo phối cảnh. Nếu bắt buộc phải lắp xiên thì giữ góc < 15°.

### Phần mềm
- Thêm mục "px/ô" vào nhãn trạng thái (đã có `px_per_module()`), báo đỏ khi < 3,5.
- Giữ `mm_per_px` trong UI đồng bộ với hiệu chuẩn thật: đo bằng thước hoặc bảng caro, không đoán.
- Khi px/ô đã ≥4, có thể bỏ bước upscale ×4 và giảm `imgsz` của detector để tăng tốc (liên quan mục 3).

---

## 3. Tốc độ xử lý — ~1,01 giây/frame

Hiện tại `ImprovePipeline` chạy YOLO (qrdet) với `imgsz=1280` trên toàn frame, rồi chạy cascade 5 bước. Ở 30 cm/s với FOV hiện tại (khoảng 1050 mm dọc băng), mỗi QR chỉ được thử khoảng 3 lần. Nếu sau mục 2 FOV thu hẹp còn khoảng 600 mm thì chỉ còn khoảng 2 lần thử. Nhiều QR cùng lúc trong khung còn làm chậm thêm.

### Phần mềm (theo thứ tự nên làm)
1. **Tách decode khỏi luồng UI và luồng chụp**: dùng một worker riêng (thread, hoặc process nếu bị GIL chặn) và hàng đợi dài 1 để luôn xử lý frame mới nhất. UI chỉ vẽ kết quả.
2. **Tracker theo lượt** (đã có trong `offline/qr/tracker.py`, chưa commit): mỗi QR thật là một "track", đã đọc được thì không decode lại; ở cuối lượt thì bỏ phiếu chọn nội dung. Cách này vừa nhanh hơn, vừa tránh đếm trùng và cho ra con số read rate theo lượt.
3. **Detect trên dải nhỏ hơn**: chỉ đưa vùng băng (đã cắt bằng sensor band 2448×768) vào YOLO với `imgsz` phù hợp tỷ lệ dải, không resize cả khung vuông. Nếu px/ô tăng, có thể hạ `imgsz` về 640–960.
4. **Tăng tốc suy luận**: dùng GPU (CUDA) nếu máy có, hoặc xuất model sang ONNX/OpenVINO cho CPU Intel. Cần đo lại xem thời gian nằm ở detect hay ở cascade trước khi tối ưu.
5. **Thử đường tắt "không cần YOLO"**: chạy zxing-cpp trực tiếp trên dải băng (đa QR, rất nhanh khi ảnh đủ sáng và đủ px/ô), YOLO chỉ dùng làm phương án dự phòng.

### Phần cứng
- Nếu không có GPU: một GPU tầm trung, hoặc một PC công nghiệp có CPU nhiều nhân để chạy nhiều worker decode.

**Tiêu chí đạt:** ≥5 lần thử decode cho mỗi QR trong một lượt đi qua ở 30 cm/s, và UI không bị giật.

### Kết quả đo sau khi sửa (bench_decode.py, GTX 1650, 31/10/2026)

| Cấu hình | Thiết bị | detect mean | cascade mean | tổng mean / p95 | frame đọc được |
|---|---|---|---|---|---|
| Toàn khung 2448×2048 | CPU | 980 ms | 363 ms | 1344 / 3271 ms | 12/14 |
| Toàn khung 2448×2048 | GPU | 190 ms | 230 ms | 420 / 798 ms | 12/14 |
| Dải 2448×768 (y=1024) | CPU | 487 ms | 318 ms | 805 / 2378 ms | 9/14* |
| Dải 2448×768 (y=1024) | GPU | 131 ms | 205 ms | 336 / 584 ms | 9/14* |
| Dải, FP16 | GPU | 259 ms | 168 ms | 428 / 692 ms | 11/14 |
| Video 20/10 (cảnh tĩnh, every 10, 6 frame) | GPU | 188 ms | 307 ms | 495 / 551 ms | 0 (bỏ cascade 0) |

\* Dải y=1024..1792 không chứa các QR ở y≈1914–1940.

- Detect trên GPU nhanh hơn CPU **5,2 lần** (toàn khung) và giữ nguyên số QR đọc được. Chế độ dải trên GPU đạt **336 ms/frame**, tức khoảng 10 lần thử/lượt với FOV hiện tại (3,4 s) và khoảng 5–6 lần với 0,25 mm/px (1,96 s). Đạt mục tiêu ≥5.
- **FP16 không giữ**: trên GTX 1650 chậm hơn FP32 (259 ms so với 131 ms) và cho kết quả khác (21 so với 22 detection).
- Sau khi detect lên GPU, **cascade trên CPU (~200–300 ms) là phần chậm nhất**. Phần bỏ cascade cho QR đã đọc chắc (PassReader) chỉ phát huy khi QR nằm trong khung qua nhiều frame; chưa đo được vì hai video 20/10 là cảnh tĩnh không đọc được QR. Cần quay video băng chạy (mục 4).
- Quad hiển thị: lấy từ góc decoder, hoặc minAreaRect của mask, và bù vận tốc lượt. Quad dùng cho warp chưa đổi.

---

## 4. Đo lường trên băng thật — điều kiện để biết các mục trên có hiệu quả

Hiện chỉ có 14 ảnh tĩnh làm chuẩn. Chưa có con số nào cho QR đang chạy trên băng.

- Quay video thật (chức năng quay đã có) ở 10/20/30 cm/s, mỗi tốc độ ≥100 lượt QR, ghi lại danh sách mã thật để làm đáp án.
- Dùng `offline/tests/eval_videos.py` và `offline/tools/` (chưa commit) kết hợp tracker để tính:
  - **read rate theo lượt** = số lượt đọc đúng ÷ tổng số lượt
  - tỷ lệ đọc sai (sai nội dung)
  - thời gian xử lý trung bình và p95
- Đo mỗi lần thay đổi phần cứng (đèn, ống kính) để so sánh trước và sau.

**Tiêu chí đạt (đề xuất):** read rate ≥99% ở 30 cm/s và 0 lần đọc sai nội dung.

---

## 5. Đồng bộ chụp với vật — trigger ngoài

### Phần cứng
- **Cảm biến quang (photoelectric)** đặt trước vùng chụp, nối vào cổng trigger của camera. Khi vật tới, camera chụp đúng lúc QR ở giữa khung, và đèn strobe nháy cùng lúc (kết hợp với mục 1).
- Nếu băng có tốc độ thay đổi: dùng encoder trên trục băng để biết tốc độ thật, từ đó đặt exposure hoặc độ trễ trigger.

### Phần mềm
- Thêm chế độ trigger vào `CameraManager` qua `CameraSetTriggerMode`, `CameraSetExtTrigSignalType`, `CameraSetExtTrigDelayTime` và `CameraSetExtTrigJitterTime` (lọc nhiễu tín hiệu).
- Với mỗi lần trigger, chụp một chuỗi ngắn (`CameraSetTriggerCount`) gồm vài frame, đọc lần lượt cho tới khi được.
- Lợi ích: ít frame vô ích hơn, CPU chỉ xử lý frame có QR, và kết quả gắn được với từng vật.

---

## 6. Ổn định SDK khi đổi cấu hình

Log 27/10 lúc 10:37: ngay sau khi áp dụng chế độ băng chuyền có lỗi chụp hết thời gian chờ (`0xFFFFFFF4`) và lỗi đọc `ExposureTime` lặp lại trong khoảng 20 giây.

### Phần mềm
- Trong `apply_conveyor_mode` và `set_sensor_band`: **tạm dừng luồng chụp** (`CameraPause` hoặc `CameraStop`) → đổi độ phân giải, frame speed, exposure → `CameraPlay`. Không đổi độ phân giải khi đang lấy buffer.
- Bỏ qua các frame đầu sau khi đổi cấu hình (ví dụ 2–3 frame) vì frame cũ vẫn còn trong hàng đợi.
- Trong lúc đổi cấu hình, nhãn trạng thái chỉ đọc giá trị cache, không gọi getter SDK lên camera (hiện đã làm vậy khi đang quay; cần làm tương tự khi đang cấu hình).
- Thêm retry có giới hạn cho lỗi hết thời gian chờ (timeout). Nếu lỗi lặp lại quá N lần thì đóng và mở lại camera, có ghi log.

### Phần cứng
- Cáp USB3 hoặc GigE ngắn, có chống nhiễu. Cắm vào cổng riêng, không qua hub. Với camera GigE: bật jumbo frame và tắt tiết kiệm điện trên card mạng. Lỗi "ip error" ngày 20/10 cho thấy kết nối mạng cần được cố định (IP tĩnh).

---

## 7. Hạng mục phụ (không ảnh hưởng trực tiếp tới kết quả đọc)

- `tests/test_improve_pipeline.py` đang lỗi vì thiếu `adown.jpg` ở thư mục gốc. Nên đổi sang dùng ảnh trong `images/`.
- Cài `pytest` vào `.venv` hoặc ghi rõ trong README là chạy test bằng `python -m unittest`.
- Quay video: cần kiểm chứng trên camera thật rằng không mất frame (đếm frame so với thời lượng) và rằng file AVI lớn hơn 4 GiB đọc được.
- Commit các file còn treo trong `offline/` (tracker, eval, tools) vì mục 3 và mục 4 cần dùng tới.

---

## Lộ trình đề xuất

| Giai đoạn | Việc | Mục |
|---|---|---|
| Tuần 1 | Mượn hoặc mua đèn bar LED + driver strobe, che sáng; thêm cấu hình strobe và gain vào phần mềm | 1 |
| Tuần 1 | Tạm dừng luồng chụp khi cấu hình; sửa test | 6, 7 |
| Tuần 2 | Quyết định in QR to hơn hay đổi ống kính; hiệu chuẩn mm/px; quay bộ video đo | 2, 4 |
| Tuần 2–3 | Worker decode riêng + tracker + detect trên dải | 3 |
| Tuần 3 | Cảm biến quang + trigger ngoài; đo read rate cuối ở 10/20/30 cm/s | 5, 4 |

> Các con số độ sáng, FPS và exposure ở trên được rút từ log; exposure AE khoảng 200 ms là **ước tính** từ tốc độ khoảng 5 fps khi bật AE. Mức tăng sáng cần thiết (khoảng 100 lần) cần được xác nhận lại khi lắp đèn thử.
