# Thiết kế UI demo cho `solution/`

> **Tài liệu lịch sử:** ghi theo cấu hình tại thời điểm viết (camera MindVision 2448 × 2048, tem 25 mm, khoảng 0,43 mm/px). Thông số hiện tại: `README.md`, mục Thông số hiện trường và tem.

Ngày: 2026-11-02

> **Cập nhật:** đây là **phiên bản riêng** (`solution/main_demo.py`, gói `solution/demo_ui/`), không thay app test camera (`main.py`, `ui/`). Các file ghi `ui/...` ở dưới nằm trong `demo_ui/`, `app_settings.py` cũng vậy; `ui/main_window.py` và `main_window_ui.py` không sửa, chỉ được dùng lại.
>
> **Cập nhật sau khi chạy thử:** cửa sổ Cấu hình chỉ còn tab Kết nối camera và Băng chuyền (bật decode, vẽ quad, exposure, gain, dải y, dải x). Bỏ tab Ảnh camera, tab Quay dữ liệu, Param A–D, tốc độ băng, mm/px, mức mờ, N frame và nhãn `● REC`. Bắt đầu không nạp Param nữa vì làm gain tụt và ảnh quá tối. Các mục dưới đây nói về những phần đó không còn áp dụng.

## 1. Mục tiêu

Biến app test camera trong `solution/` thành giao diện demo cho khách hàng:

- Màn hình chính chỉ là giao diện làm việc.
- Cấu hình nằm trong menu riêng, không hiển thị khi không mở.
- Khách nhìn vào hiểu ngay hệ thống đang đọc được gì và tốt đến đâu.
- Người demo không phải chạm vào thông số trong lúc trình bày.

Kịch bản demo: **băng chuyền chạy liên tục**, QR đi qua camera.

### Ràng buộc

- Giữ PyQt5. `CameraManager` giữ API public; chỉ thêm, không đổi các API đang có.
- Không sửa `production/` và `Demo/`. Không thêm `basicsr`/`realesrgan`.
- `torch`/`qr` vẫn phải import trước PyQt5.
- Số liệu trên màn hình là số thật, không giả lập.

### Ngoài phạm vi

Xuất CSV, tra cứu thông tin theo mã, đăng nhập, lưu lịch sử vào CSDL, đóng gói .exe, tự kết nối lại camera, làm mới giao diện form cấu hình.

## 2. Hướng làm

Viết lại phần vỏ PyQt5 với layout co giãn và theme QSS. Form cấu hình hiện có (`main_window_ui.py`, không sửa) được chuyển nguyên vào cửa sổ Cấu hình dạng tab.

Lý do: khách chỉ nhìn màn hình chính, còn logic camera và quay video đã được test và đã chạy với phần cứng. Viết lại khoảng 40 thông số (hướng B) hoặc chuyển sang QML/web (hướng C) tốn công và rủi ro hơn nhiều so với giá trị thu được trong một bản demo.

## 3. Màn hình làm việc

```
┌──────────────────────────────────────────────────────────────────────────┐
│ ▣ QR Conveyor Reader     ● ĐANG CHẠY  00:12:45         [ Reset ] [ ⚙ ]   │
├───────────────────────────────────────────────┬──────────────────────────┤
│                                               │ MÃ VỪA ĐỌC               │
│                                               │ 000000585546             │
│                                               │ 16:02:11 · vừa xong      │
│                 VIDEO LIVE                    ├────────┬────────┬────────┤
│         (khung QR xanh = đã đọc,              │  ĐÃ ĐỌC│TỈ LỆ   │ TỐC ĐỘ │
│               đỏ = chưa đọc)                  │   128  │ 98,5%  │ 42 m/ph│
│                                               ├────────┴────────┴────────┤
│                                               │ MÃ ĐÃ ĐỌC                │
│                                               │ 16:02:11  000000585546 ✓ │
│                                               │ 16:02:09  000000585545 ✓ │
│                                               │ 16:02:07  không đọc được │
│                                               │ 16:02:05  000000585543 ⚠ │
├───────────────────────────────────────────────┴──────────────────────────┤
│ [ ▶ BẮT ĐẦU ]       Camera ● 50 fps    GPU ● 336 ms    Băng 30 cm/s      │
└──────────────────────────────────────────────────────────────────────────┘
```

### Bố cục

- Video chiếm khoảng 65% chiều rộng, cột kết quả chiếm phần còn lại.
- Cửa sổ co giãn được, kích thước tối thiểu 1280×720. F11 bật/tắt toàn màn hình, Esc thoát toàn màn hình.
- Theme tối, chữ đủ lớn để nhìn từ xa. Toàn bộ màu nằm trong `ui/theme.py` để đổi sang theme sáng được nếu phòng demo quá sáng; bản này chỉ làm theme tối.

### Thành phần

| Thành phần     | Hành vi                                                                                                                                                                                       |
| -------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Mã vừa đọc     | Chữ lớn. Nháy viền xanh khoảng 0,3 giây khi có mã mới. Hiện giờ đọc và "x giây trước", cập nhật mỗi giây.                                                                                     |
| Đã đọc         | Số lượt đã kết thúc và có nội dung.                                                                                                                                                           |
| Tỉ lệ          | Số lượt đã kết thúc có nội dung / số lượt đã kết thúc được tính (xem mục 6.2). Hiện `—` khi chưa có lượt nào.                                                                                 |
| Tốc độ         | Số mã/phút, tính trên các lượt kết thúc trong 60 giây gần nhất. Hiện `—` khi chưa có lượt nào.                                                                                                |
| Danh sách mã   | Mới nhất ở trên, hiển thị tối đa 200 dòng (bộ đếm không bị giới hạn). Dòng xuất hiện ngay khi đọc được, trạng thái chốt khi lượt kết thúc: ✓ đọc được, ⚠ mâu thuẫn, dòng đỏ "không đọc được". |
| Dải trạng thái | FPS camera, GPU/CPU kèm thời gian xử lý (detect + cascade), tốc độ băng đang đặt. GPU rơi về CPU thì nhãn chuyển vàng.                                                                        |
| Tiêu đề        | Trạng thái và thời gian chạy của phiên. Thêm `● REC` khi đang quay, `CHỈNH CAMERA` khi camera mở nhưng chưa chạy decode.                                                                      |

Video hiện quad như hiện tại (`draw_overlays`): xanh là đã có nội dung, đỏ là chưa đọc được. Khi chưa chạy, vùng video hiện thông báo trạng thái thay vì ô đen.

### Trạng thái Bắt đầu/Dừng

```
Sẵn sàng → Đang kết nối → Đang chạy → Đang dừng → Sẵn sàng
                ↓
         Lỗi (Thử lại / Mở Cấu hình)
```

- **Dừng** giữ nguyên số liệu trên màn hình. **Bắt đầu** lại chạy tiếp phiên đó.
- **Reset** đưa số liệu về 0, có hỏi xác nhận. Bấm được cả khi đang chạy.
- Lỗi hiện ngay trong vùng video bằng tiếng Việt dễ hiểu, nêu đúng bước bị lỗi, không bật hộp thoại kỹ thuật.

## 4. Menu Cấu hình

Nút ⚙ thả menu: Kết nối camera…, Băng chuyền & nhận diện…, Ảnh camera…, Quay dữ liệu…, Thoát. `Ctrl+,` mở cửa sổ Cấu hình ở tab dùng gần nhất.

Mỗi mục mở cùng một cửa sổ **Cấu hình**, đúng tab tương ứng. Cửa sổ không chặn màn hình chính (non-modal, luôn nằm trên cửa sổ chính). Đóng cửa sổ không làm dừng hệ thống.

| Tab                     | Nội dung, lấy từ UI hiện có                                                                                              |
| ----------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| Kết nối camera          | `frame_camera_list`: danh sách camera, Refresh, Mở/Đóng để chỉnh thử.                                                    |
| Băng chuyền & nhận diện | Tốc độ băng, mm/px, mức mờ, dải ROI, N frame/lần decode, vẽ quad, nút Áp dụng, `lbl_conveyor`, thông số decode chi tiết. |
| Ảnh camera              | Toàn bộ `frame_area`: exposure, gain, ISP, LUT, màu, ROI, Param A–D, Snap, hiệu ứng ảnh.                                 |
| Quay dữ liệu            | Toàn bộ `record_group`.                                                                                                  |

**Chỉnh camera trước khi demo:** bấm Mở trong tab Kết nối thì màn hình chính hiện video, chưa decode, tiêu đề có nhãn `CHỈNH CAMERA`. Bấm Bắt đầu sẽ dùng luôn camera đang mở, không mở lại (`CameraManager.open()` luôn đóng camera trước khi mở).

**Khóa khi đang chạy:**

- Thông số ảnh và băng chuyền vẫn chỉnh được khi đang chạy.
- Không đổi được camera đang dùng: danh sách, Refresh và Mở/Đóng bị khóa khi đang chạy.
- Khi đang quay, cấu hình camera bị khóa như hiện nay (`on_recording_tick`).

## 5. Lưu cấu hình và luồng Bắt đầu

### Hai nơi lưu

**`solution/config/app_settings.json`** (thêm `solution/config/` vào `.gitignore`), tự lưu khi đổi giá trị:

| Khóa                               | Mặc định              |
| ---------------------------------- | --------------------- |
| `camera_serial`                    | rỗng                  |
| `param_slot`                       | 0 (Param A)           |
| `speed_mm_s`                       | 300                   |
| `mm_per_px`                        | 0,43                  |
| `max_blur_px`                      | 1,0                   |
| `band_enabled`, `band_y`, `band_h` | tắt, 640, 768         |
| `decode_every_n`                   | 5                     |
| `draw_quad`                        | bật                   |
| `record_directory`                 | `solution/recordings` |
| `record_fps`                       | 60                    |

File hỏng, thiếu, hoặc giá trị ngoài khoảng cho phép thì dùng giá trị mặc định cho phần đó, ghi log cảnh báo, app vẫn chạy.

**Param A–D trong camera:** gain, gamma, màu và các thông số ảnh khác. Vẫn phải bấm Save như hiện nay; tab Ảnh camera ghi rõ điều này.

### Thứ tự khi bấm Bắt đầu

1. **Tìm camera** qua `list_cameras()`, so `GetSn()` với `camera_serial`. Chưa lưu serial và chỉ có một camera thì dùng camera đó và lưu serial. Không thấy camera, hoặc có nhiều camera mà chưa chọn, thì báo lỗi.
2. **Mở camera** trên thread nền (bỏ qua nếu đang ở `CHỈNH CAMERA`).
3. **Nạp Param slot** đã chọn, rồi đặt lại trigger liên tục vì Param có thể chứa trigger mode khác. Bỏ qua việc nạp khi đi từ `CHỈNH CAMERA`, để không mất thông số vừa chỉnh tay chưa Save.
4. **Áp dụng chế độ băng chuyền** bằng `apply_conveyor_mode()`. Bước này đặt sau cùng vì nó ghi đè exposure và tắt AE. Kết quả `ok=False` là lỗi.
5. **Chờ warm-up GPU xong** rồi bật decode.

Các bước 1–4 chạy trên thread nền, kết quả trả về GUI qua signal. Bấm Dừng khi đang kết nối sẽ hủy sau khi bước đang chạy kết thúc. Khi cần cập nhật widget cấu hình từ camera, `ui_init_param()` được gọi trên GUI thread sau bước 4.

## 6. Thay đổi trong pipeline và worker

### 6.1 Tín hiệu mã vừa đọc

Hiện tại lượt chỉ được báo sau khi QR mất dấu 100 seq (khoảng 2 giây), nên danh sách cần thêm tín hiệu sớm hơn:

- `PassTracker` thêm property đọc các lượt đang mở.
- `FrameResult` thêm `first_reads: list[Track]`: các lượt vừa có nội dung lần đầu. `PassReader` giữ tập `track_id` đã báo và xóa khỏi tập khi lượt đóng.
- `DecodeWorker` thêm signal `reads(list)`.

Dòng trong danh sách và lượt được ghép bằng `track_id`. Khi lượt kết thúc, dòng cập nhật nội dung theo `Track.text` (nội dung được đọc nhiều nhất) và trạng thái. `track_id` tăng liên tục kể cả qua Reset nên không bị trùng.

### 6.2 Lọc nhiễu khi tính tỉ lệ

Lượt **không có nội dung và chỉ có 1 observation** được coi là nhận nhầm của detector: không hiện dòng đỏ, không tính vào tỉ lệ, vẫn ghi log `pass_finished`.

QR thật ở 30 cm/s nằm trong khung khoảng 3,5 giây (khung ~1050 mm theo chiều băng ở 0,43 mm/px) nên được detect nhiều lần. Cần đối chiếu tỉ lệ hiển thị với log khi chạy thử trên băng thật.

### 6.3 Chốt lượt theo phiên

`PassReader.flush()` hiện chỉ chạy khi đóng app. `DecodeWorker` thêm `request_flush()`: thread worker chạy `flush()` giữa hai frame rồi phát signal `flushed(list)`.

- **Dừng:** tắt submit, gọi `request_flush()`, cập nhật các lượt còn mở vào `SessionStats`, sau đó đóng camera.
- **Reset:** gọi `request_flush()`, GUI xóa dữ liệu khi nhận `flushed` và bỏ danh sách lượt đi kèm. Signal từ cùng một thread đến theo thứ tự, nên không có kết quả cũ chen vào sau khi xóa.
- **Warm-up:** `DecodeWorker` thêm signal `ready` sau khi warm-up xong (kể cả warm-up lỗi, vì decode vẫn chạy được).

## 7. Cấu trúc code

| File                                       | Nhiệm vụ                                                                          | Phụ thuộc       |
| ------------------------------------------ | --------------------------------------------------------------------------------- | --------------- |
| `app_settings.py` (mới)                    | Đọc/ghi JSON, giá trị mặc định, kiểm tra hợp lệ.                                  | Không dùng Qt   |
| `ui/session_stats.py` (mới)                | Danh sách lượt, số đã đọc, tỉ lệ, mã/phút.                                        | Không dùng Qt   |
| `ui/run_controller.py` (mới)               | Máy trạng thái Bắt đầu/Dừng, chạy mở camera trên thread nền.                      | `CameraManager` |
| `ui/theme.py` (mới)                        | Bảng màu và QSS.                                                                  | Qt              |
| `ui/workspace.py` (mới)                    | Widget màn hình chính, chỉ nhận dữ liệu để hiển thị, không gọi SDK.               | Qt              |
| `ui/settings_window.py` (mới)              | Cửa sổ Cấu hình dạng tab, chứa các widget cũ.                                     | Qt              |
| `ui/main_window.py` (sửa)                  | Lắp các phần trên lại với nhau. Các slot camera và quay video gần như giữ nguyên. | Tất cả          |
| `qr/tracker.py`, `qr/pass_reader.py` (sửa) | Mục 6.1.                                                                          |                 |

`Ui_MainWindow.setupUi` vẫn tạo widget như cũ, sau đó `MainWindow` chuyển chúng sang vị trí mới: `label_image` vào vùng video của workspace; `frame_camera_list`, `frame_area`, `record_group` và các widget băng chuyền vào tab Cấu hình. `label_image` đặt size policy Ignored để pixmap không làm layout giãn ra.

`status_bar` (tọa độ cũ) chuyển vào tab Băng chuyền & nhận diện làm dòng thông báo kỹ thuật.

### Luồng dữ liệu

```
PassReader → reads (mã vừa đọc)  → SessionStats → Workspace: thêm dòng, nháy "Mã vừa đọc"
           → passes (lượt xong)  → SessionStats → Workspace: cập nhật ✓/⚠/✗ và chỉ số
           → stats (ms)          ───────────────→ dải trạng thái
           → flushed             → SessionStats → Workspace: chốt lượt hoặc xóa khi Reset
```

## 8. Xử lý lỗi khi đang chạy

| Tình huống                            | Hành vi                                                                                                                                                             |
| ------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Không có frame mới quá 3 giây         | Lớp phủ "Mất tín hiệu camera" trên video. Người dùng bấm Dừng rồi Bắt đầu. Không tự kết nối lại. Không áp dụng cho chế độ trigger (bản demo chạy trigger liên tục). |
| Một frame decode lỗi                  | Chạy tiếp, dải trạng thái báo cảnh báo.                                                                                                                             |
| GPU tự chuyển sang CPU                | Nhãn chuyển vàng, số ms vẫn là số thật.                                                                                                                             |
| Đóng app khi đang chạy hoặc đang quay | Giữ nguyên luồng đóng bất đồng bộ trong `closeEvent`, không đóng cưỡng bức khi file chưa hoàn tất.                                                                  |

## 9. Kiểm thử

### Tự động, không cần camera

- Unit test: `SessionStats` (tỉ lệ, mã/phút, lọc nhiễu, ghép dòng theo `track_id`), `AppSettings` (mặc định, file hỏng, giá trị ngoài khoảng), `PassReader.first_reads`, `DecodeWorker.request_flush`.
- Máy trạng thái: thành công, lỗi từng bước, dừng khi đang kết nối, bắt đầu khi đang `CHỈNH CAMERA`.
- Test UI offscreen với SDK giả. Các test đang truy cập `window.ui.*` và `btn_record_*` được giữ. Test của `lbl_latest` và `lst_history` viết lại theo màn hình mới.
- Chụp ảnh màn hình offscreen bằng `QWidget.grab()` ở 1280×720 và 1920×1080 để kiểm tra bố cục.

### Thủ công trên camera thật

Test tự động không chứng minh được các mục này:

- [ ] Bắt đầu/Dừng 10 lần liên tiếp.
- [ ] Rút cáp camera khi đang chạy.
- [ ] Chỉnh thông số ảnh và băng chuyền khi đang chạy.
- [ ] Nạp Param slot không làm hỏng ROI hoặc trigger khi Bắt đầu.
- [ ] Quay video khi đang chạy, kể cả dừng hệ thống khi đang quay.
- [ ] Đối chiếu tỉ lệ trên màn hình với log `pass_finished` trên băng thật.
- [ ] Chạy liên tục 30 phút, theo dõi FPS và bộ nhớ.
- [ ] F11 trên màn hình trình chiếu.

## 10. Tài liệu

Cập nhật `solution/README.md` (mục Sử dụng) và `solution/CLAUDE.md` (kiến trúc UI, cấu hình JSON, các signal mới).
