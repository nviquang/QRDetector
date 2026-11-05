# CLAUDE.md

Sản phẩm cuối: ứng dụng PyQt5 tích hợp **camera MindVision (MVSDK `Camera*`)** + **QR pipeline**.

Hướng dẫn cài đặt và sử dụng: xem `README.md`. Code và dữ liệu thử nghiệm cũ ở repo `../QRDetector-research` (lịch sử git ở tag `archive/research-2026-11`), không dùng trong sản phẩm.

## Chạy

```bash
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

Cần driver/runtime MindVision tương ứng kiến trúc Python (`MVCAMSDK_X64.dll` cho 64-bit). Test pipeline offline không cần camera:
`python -m unittest discover -s tests -t . -p "test_*.py"` (cả bộ test, phải có `-t .` để `tests/__init__.py` nạp torch trước PyQt5), `python tests/test_improve_pipeline.py <ảnh>`, `python tests/test_small_qr.py`, và `python tools/bench_decode.py [--device cpu] [--band Y H] [--half] [--video …]` để đo tốc độ

## Kiến trúc

```
main.py                  → entry, khởi tạo MainWindow
mvsdk.py                 → wrapper Python MindVision, vendor từ mẫu SDK Python/Basic
camera/camera_manager.py → lifecycle, tham số, capture thread → latest_frame BGR
qr/                      → pipeline QR
  detector/corrector/preprocessor/decoder.py
  improved_pipeline.py   → ImprovePipeline
  tracker.py             → PassTracker: gom detection qua frame thành lượt
  pass_reader.py         → PassReader: detect → ghép lượt → bỏ cascade QR đã đọc chắc (kiểm tra lại mỗi 5 lần) → ms + Overlay
  multiframe.py          → PassDecoder: đọc theo lượt (xếp chồng ROI hỏng, Wiener theo vận tốc)
ui/main_window.py        → bind UI ↔ CameraManager, panel quay/đóng bất đồng bộ
camera/recording.py      → AVI không nén MVSDK, một file/phiên, trạng thái và disk guard
camera/conveyor.py       → công thức băng chuyền thuần (exposure tối đa theo tốc độ/mm/px, px/ô, căn dải ROI)
```

**Chế độ băng chuyền** (`CameraManager.apply_conveyor_mode(ConveyorSettings)`, nút trong panel Kết quả QR): tắt AE, exposure cố định `t = mờ_px × mm/px ÷ v` (kẹp theo min/max camera), frame speed cao nhất, tùy chọn ROI dải ngang toàn bề rộng (`set_sensor_band`, căn bội 16 — cần kiểm chứng camera thật). `open()` vẫn bật AE như cũ; chế độ băng chuyền phải bấm áp dụng sau khi mở. Nhãn trạng thái hiển thị exposure, vệt mờ ước tính, độ sáng TB và % cháy sáng; khi đang quay/đóng không gọi getter SDK từ GUI thread (dùng cache).

Camera dùng MindVision `mvsdk`: `CameraSdkInit → CameraEnumerateDevice → CameraInit → CameraGetCapability → CameraPlay`. Capture dùng `CameraGetImageBuffer → CameraImageProcess → CameraReleaseImageBuffer`; đóng bằng `CameraStop → CameraUnInit → CameraAlignFree`.

**Luồng:** capture thread → copy frame sở hữu độc lập, RGB/mono chuyển thành BGR 3 kênh → `latest_frame` (frame cũ bị drop) → mỗi N frame `DecodeWorker.submit(frame, seq)` (bận thì bỏ; thread worker warm-up GPU trước) → `PassReader.process` → signal `done` (results + Overlay), `stats` (ms detect/cascade), `passes` (đếm lượt, log `pass_finished`). Hiển thị: `draw_overlays` dịch quad theo vận tốc lượt tới seq hiện tại, bỏ quad cũ >100 seq hoặc khác kích thước frame; `frame_to_qimage` resize OpenCV trước khi đổi màu.

**Đọc nhiều frame** (`ImprovePipeline(multi_frame=True)`, mặc định; `False` = cascade từng frame như cũ): YOLO tối đa mỗi 400 ms, xen giữa là job đoán vị trí lượt chưa đọc được từ vận tốc (không detect, không WeChat; `DecodeWorker.decode_every` rút nhịp gửi còn 2 frame). `PassDecoder` thay cascade: zxing 3 binarizer → warp → Wiener → từ 3 ROI hỏng xếp chồng tối đa 8 ảnh → zxing, Wiener, WeChat CNN. WeChat chỉ chạy trên ảnh xếp chồng. Tracker `strict=True` (cổng có trần 900 px, nội dung khác tách lượt), 1 phiếu là đủ, bỏ QR chạm mép hoặc méo; không loại theo kích thước vì tem dài ngắn khác nhau. Độ dài vệt mờ = vận tốc × seq/s (đo được) × exposure (`set_exposure_ms`); chưa biết exposure thì thử 2/3/4,5/6,5 px. Tem không có định dạng cố định nên mặc định không lọc nội dung (`code_pattern=None`); đọc sai vẫn có thể được báo và gửi đi. `tools/bench_decode.py` và `tools/eval_videos.py` giữ `multi_frame=False` vì chạy offline nhanh hơn thời gian thực. Số liệu và giới hạn: `experiments/README.md`.

**GPU:** detect chạy CUDA nếu có (`device="auto"`, torch `2.14.1+cu126`, GTX 1650; không có CUDA → CPU + cảnh báo log). FP16 tắt (trên GTX 1650 chậm hơn và lệch kết quả). Đo 31/10: detect 190 ms GPU so với 980 ms CPU toàn khung; dải 2448×768 tổng 336 ms. Sau khi lên GPU, cascade CPU (~200–300 ms) là phần chậm nhất.

**Quad hiển thị:** mỗi bước cascade trả `Decoded(text, corners)` — 4 góc QR quy về ảnh gốc (trừ viền đệm `UPSCALE_PAD_PER_SCALE × scale`, chia scale, cộng gốc ROI; bước warp đi ngược homography). Vẽ bằng `display_quad()`: góc decoder, chưa đọc được thì `minAreaRect(polygon_xy)`. KHÔNG vẽ `padded_quad_xy` (mask YOLO thô ~8×8 điểm cho QR 60px → quad méo tới 45°); `padded_quad_xy` vẫn dùng cho warp.

**Quay video:** `start_recording(RecordingOptions)` / `stop_recording()` chỉ gửi yêu cầu; đọc `recording_status()` để biết kết quả. Capture thread sở hữu InitRecord/PushFrame/StopRecord, dùng RGB8/MONO8 + header sau ISP trước BGR/overlay, không lấy từ latest_frame. Snapshot không giữ SDK lock. Giữ `native_open` độc lập với ERROR: chưa finalize thì không UnInit/free/reopen. Mỗi phiên khởi tạo thành công ghi một `video.avi` trong thư mục timestamp + UUID riêng, không tự chia file/dừng theo dung lượng video; giữ b2GLimit=False (SDK chưa triển khai tự chia). Khả năng AVI >4 GiB phụ thuộc DLL, phải kiểm chứng camera thật; vẫn giữ disk guard và dừng khi có lỗi. Đường dẫn phải encode GBK. Camera configuration bị khóa khi ghi. Test mock không chứng minh không mất frame hoặc AVI thật đúng thời lượng.

**ImprovePipeline** (không dùng SR/Real-ESRGAN, tối ưu cho QR nhỏ ~60px trên frame 2448×2048): detect qrdet với `imgsz=1280` (640 mặc định bỏ sót QR nhỏ) → `decode_detection`/`scan` (ảnh đơn, và PassReader khi `multi_frame=False`) chạy cascade trên ROI cắt từ ảnh gốc, rẻ trước đắt sau: ROI×4 → zxing; warp 256 + Quiet Zone → zxing; CLAHE×4 → WeChat; stretch×4 → WeChat CNN+SR; ROI×3 → WeChat CNN+SR. Model WeChat ONNX (OpenCV 5 không load caffemodel) ở `qr/models/wechat/`; thiếu model thì bỏ qua bước CNN. Không dùng pyzbar/`decode_parallel` trong pipeline (yếu với QR ~2px/module, chậm). Test: `python tests/test_small_qr.py` (dùng frame mẫu trong `QR_SAMPLES_DIR`, mặc định `../QRDetector-research/data/images`, kỳ vọng ≥12/14).

## Phiên bản demo (`python main_demo.py`, gói `demo_ui/`)

Bản riêng cho khách hàng, không thay app test camera: `main.py` + `ui/` giữ nguyên hành vi. `demo_ui/` chỉ phụ thuộc một chiều vào `ui/` (form `main_window_ui`, `frame_to_qimage`, `draw_overlays`, `DecodeWorker`); `ui/` không biết gì về `demo_ui/`. Sửa `ui/main_window.py` thì chạy cả `test_demo_*` và `test_workspace_ui`.

```
demo_ui/main_window.py     → lắp ráp; DecodeWorker kế thừa ui/ (thêm reads, flushed, ready, request_flush)
demo_ui/workspace.py       → màn hình làm việc, chỉ nhận dữ liệu để hiển thị, không gọi SDK
demo_ui/settings_window.py → cửa sổ Cấu hình 2 tab (non-modal): kết nối camera, băng chuyền
demo_ui/run_controller.py  → máy trạng thái Bắt đầu/Dừng, mở camera trên thread nền
demo_ui/session_stats.py   → số liệu phiên (thuần Python)
demo_ui/app_settings.py    → JSON `config/app_settings.json`, kiểm tra hợp lệ từng trường
demo_ui/theme.py           → bảng màu + QSS
demo_ui/scan_uploader.py   → ScanUploader: hàng đợi + thread nền gửi `PUT {upload_base_url}/{nội dung QR URL-encode}`
```

**Gửi QR lên server:** `on_reads_done` (đọc lần đầu của lượt) gọi `ScanUploader.submit`. Mã chờ hoặc đã gửi trong 30 giây bị bỏ qua; lỗi mạng/5xx thử lại 3 lần (1s, 2s, 4s), 4xx không thử lại, 409 coi như đã nhận; hàng đợi 500 mục, đầy thì bỏ mục cũ nhất. Thất bại không nhớ là đã gửi. Tắt bằng `upload_enabled=false` trong `config/app_settings.json`. `MainWindow(settings_path=None)` không tạo uploader (test không gọi mạng thật); test truyền uploader giả qua tham số `uploader`.

`Ui_MainWindow.setupUi` vẫn tạo widget cũ, `_setup_shell` chuyển `label_image` vào `Workspace`, `frame_camera_list` và `status_bar` vào `SettingsWindow`; phần còn lại của form (`frame_area`…) bị hủy cùng central widget cũ nên không được đụng tới. `MainWindow(settings_path=None)` không đọc/ghi file (dùng trong test); `main_demo.py` truyền `DEFAULT_SETTINGS_PATH`. Bắt đầu: thread nền chạy tìm camera → `open` → trigger liên tục → `apply_run_settings(RunSettings)` (AE tắt, exposure + gain cố định, FPS cao nhất, vùng đọc x/y qua `set_sensor_window`) → `configured` → chờ `worker.ready` → RUNNING. KHÔNG nạp Param khi Bắt đầu: Param A lưu gain 10, nạp ngay sau `open` rồi tắt AE làm ảnh tối đi khoảng 3 lần và không đọc được QR. Mặc định exposure 12,9 ms, gain 40; decode mỗi `DECODE_EVERY_N` = 5 frame. **Mở** ở tab Kết nối cũng áp dụng ngay cấu hình này. Bản demo không có quay video. Ô **Dùng GPU** (tab Băng chuyền, lưu `use_gpu`) gọi `ImprovePipeline.set_device("auto"/"cpu")`, đổi được lúc đang chạy và chỉ ảnh hưởng bước detect; máy không có CUDA thì ô bị vô hiệu hóa và giữ nguyên giá trị đã lưu. CUDA lỗi lúc chạy thì detector tự về CPU trong khi ô vẫn tích (chân màn hình hiện CPU); tắt rồi bật lại ô để thử lại GPU. Khi CONNECTING, GUI không gọi getter SDK. Số liệu: `reads` (từ `FrameResult.first_reads`) thêm dòng ngay, `passes` chốt trạng thái, ghép theo `track_id`. Reset/Dừng dùng `request_flush(purpose)`: chốt lượt trên thread worker rồi phát `flushed`; signal cùng thread đến theo thứ tự nên GUI xóa lúc nhận `flushed` không bị kết quả cũ chen vào. Lượt không nội dung và <2 observation là nhiễu, không tính vào tỉ lệ.

## Ràng buộc

- Không thêm `basicsr`/`realesrgan`.
- Đầu vào QR luôn là BGR `np.ndarray` contiguous (OpenCV).
- `CameraManager` là boundary tương thích của UI; giữ API public khi thay đổi backend.
- `torch`/`qr` phải được import trước PyQt5 để tránh `WinError 1114` trên Windows.
- `mvsdk.py` được vendor trong repo; không import động từ thư mục SDK.
