# CLAUDE.md

Sản phẩm cuối: ứng dụng PyQt5 tích hợp **camera MindVision (MVSDK `Camera*`)** + **QR pipeline**.

Hướng dẫn cài đặt và sử dụng: xem `README.md`. **Bài toán là tối ưu trên phần cứng sẵn có**; ràng buộc chuẩn ở mục "Bài toán và ràng buộc" trong `README.md` (chốt 18/11/2026). Bất biến, không đề xuất đổi: 2 camera Basler a2A2840 đơn sắc 8 MP, ống 4 mm; QR 32 mm version 2 (25 × 25 ô) mức M; nội dung `^\d+#\d+$` độ dài thay đổi; tem dán bất kỳ đâu trên kính; băng rộng 3,25 m, 80–120 mm/s; máy xử lý Jetson Nano hoặc chỉ CPU. Được đổi: độ cao camera (mỗi camera phủ 1,5–1,6 m, ~2,2–2,44 px/ô), buồng tối 60 cm có đèn, thông số camera, phần mềm. Số trong `docs/` và các báo cáo trước 18/11/2026 (tem 25/36 mm, cao 1 m, 0,673 mm/px, 100 mm/s, 12#12 version 1) là cấu hình cũ, chỉ tham khảo lịch sử; dữ liệu `data/field` quay ở cấu hình cũ, không dùng để kết luận tỉ lệ đọc. Code và dữ liệu thử nghiệm cũ ở repo `../QRDetector-research` (lịch sử git ở tag `archive/research-2026-11`), không dùng trong sản phẩm.

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

**Đọc nhiều frame** (`ImprovePipeline(multi_frame=True)`, mặc định; `False` = cascade từng frame như cũ): YOLO tối đa mỗi 400 ms, xen giữa là job đoán vị trí lượt chưa đọc chắc từ vận tốc (không detect; `DecodeWorker.decode_every` rút nhịp gửi còn 2 frame). `PassDecoder` thay cascade: zxing 3 binarizer → warp → WeChat từng frame (stretch, CLAHE, ×3) → Wiener → từ 3 ROI hỏng xếp chồng tối đa 8 ảnh → zxing, Wiener, WeChat CNN. Tracker `strict=True` (cổng có trần 900 px, nội dung khác tách lượt); 2 lần đọc giống nhau mới báo mã, lượt kết thúc với 1 lần đọc thì coi như không đọc được và chỉ ghi log `pass_unconfirmed`; bỏ QR chạm mép hoặc méo; không loại theo kích thước vì tem dài ngắn khác nhau. Độ dài vệt mờ = vận tốc × seq/s (đo được) × exposure (`set_exposure_ms`); chưa biết exposure thì thử 2/3/4,5/6,5 px. Lọc chống đọc sai (`qr/content_filter.py`, mặc định của `ImprovePipeline`: `code_pattern=CODE_PATTERN` = `[0-9]+(?:#[0-9]+)?` fullmatch, tức dãy số có thể kèm `#` + dãy số; nhận cả mã chỉ số, `expected_symbol=ACCEPT_SYMBOL` = None, tức nhận mọi version và mức sửa lỗi): `PassDecoder` loại mã sai định dạng và mã có tâm ngoài bbox đang đọc nới 15% (tem bên cạnh); log `code_rejected`. Truyền `expected_symbol=EXPECTED_SYMBOL` (V2-M) thì thêm: kết quả zxing phải đúng version/mức (`result.extra`), kết quả WeChat phải đủ số ô (`module_count` đếm qua đường timing, vì WeChat không báo version). `PassReader._resolve` lọc nội dung kết quả đọc nền. Test: `tests/test_content_filter.py`. Mọi app (`main.py`, `main_demo.py`, `main_basler.py`, `main_replay.py`, `main_dual.py`) đều dùng chế độ này; bản 2 camera có `decode_every`/`set_exposure_ms` theo từng camera trong `DualDecodeWorker`. `tools/bench_decode.py` và `tools/eval_videos.py` giữ `multi_frame=False` vì chạy offline nhanh hơn thời gian thực. Số liệu và giới hạn: `experiments/README.md`.

**Đọc nền cho lượt khó** (`main_basler.py` và `main_replay.py`, gọi `qr.pass_fallback.enable()`; tắt bằng `QR_FALLBACK=off`): lượt kết thúc mà `PassDecoder` không đọc được và có ≥2 crop từ YOLO thì `PassReader` giữ lại, gửi 5 crop trải đều + vận tốc/exposure sang MỘT tiến trình spawn chạy bộ giải trong `qr/solvers` (mặc định `combo_bc.py:ComboBC`: `grid_sr` tái tạo trên lưới ô trước, `preproc_sweep` giải ô rồi vẽ lại mã cho zxing/WeChat sau), rồi báo lượt (đọc được thì `first_reads` + `finished`) khi có kết quả. B và C nhận mọi version và mức sửa lỗi (đặt `grid_sr.VERSIONS = (2,)`, `LEVELS = (LEVEL_M,)`, `preproc_sweep.SIZES = (25,)`, `ACCEPT_SYMBOL` để ép V2-M): B (`grid_sr`) tìm và giải lưới V1–V3, xếp hạng 32 mã format, (σx, σy) ước lượng liên tục (`estimate_sigma`, `SIGMA_MODE="fit"`), bỏ quét góc khi có ô alignment, Chase xóa ≤10 byte và 2×lỗi+xóa ≤12, cổng lọc nội dung, byte đệm đã ghim không làm bằng chứng, lưới phải nằm trong bbox; C (`preproc_sweep`) thử lưới 21/25/29/33 ô, bước mặc định `photo,sweep,warp`, bước photo chỉ nhận mã trong bbox. Lượt V2-M tổng hợp: `tests/v2m_synth.py`, test `tests/test_solvers_v2m.py` (chậm). Lượt khó báo trễ khoảng 4 s chờ đóng lượt + 2–15 s giải; hàng đợi tối đa 8 lượt, đầy thì coi như không đọc được; Dừng/Reset chờ tối đa 5 s (`take_late_reads` cho lượt đọc xong lúc chốt; trong lúc chờ `flush(on_fallback=…)` vẫn báo giai đoạn B → C vì không có frame nào đi qua `process`). Tiến trình nền tự thoát khi app đóng hoặc bị tắt đột ngột. Cần `scipy`. Trạng thái hiển thị: bộ giải có tham số `progress` (ComboBC báo "B" rồi "C") gửi giai đoạn qua queue kết quả → `PassFallback.stage(key)`/`revision` → `FrameResult.fallback` (list `FallbackStatus`, chỉ khi đổi) → `DecodeWorker.fallback` (`demo_ui`) → dòng `RowState.SOLVING` trong bảng ("chờ đọc lại (thứ n)", "đang đọc lại · B/C n s", cập nhật mỗi giây) + nhãn chân "Đọc nền ● n lượt"; không tính vào chỉ số tới khi lượt chốt qua `passes`. `main_dual.py` chưa hiển thị. Số liệu so sánh: `reports/So sánh chất lượng các hướng đọc QR.md`.

**Chọn bộ phát hiện** (`improved_pipeline.make_detector`, biến môi trường `QR_DETECTOR`, từ 20/11/2026 mặc định `openvino`): `openvino`/`onnx` = `qr/detector_onnx.py:OnnxQRDetector` chạy `qr/models/qrdet_n_detect.onnx` (YOLOv8n detect, chép trọng số từ qrdet-n seg bằng `tools/export_qrdet_detect.py`, không train), CPU, không cần torch; thu ảnh theo tỉ lệ cố định `QR_DETECT_SCALE` (mặc định 0,75) rồi đệm bội 32 chia đều hai phía như LetterBox ultralytics; thiếu thư viện thì lùi openvino → onnxruntime → qrdet. `qrdet` = qrdet-s seg trên torch như dưới (GPU). Không có mask nên quad lấy từ `qr/quad_estimate.py:estimate_quad`: cạnh từ hộp, góc từ hướng gradient (tổng m²·e^{4iφ}), đệm `PAD` 1,15 (1,06 làm `test_small_qr` tụt 12 → 11/14). Bộ ONNX chỉ CPU nên ô Dùng GPU bị vô hiệu hóa. `Detection` nằm ở `qr/detection.py` (không nạp torch), `qr.detector` re-export. Đo: `tools/bench_detector.py`, số trong README mục Bản demo dùng camera Basler. Test: `tests/test_detector_onnx.py`.

**GPU:** detect chạy CUDA nếu có (`device="auto"`, torch `2.14.1+cu126`, GTX 1650; không có CUDA → CPU + cảnh báo log). FP16 tắt (trên GTX 1650 chậm hơn và lệch kết quả). Đo 31/10: detect 190 ms GPU so với 980 ms CPU toàn khung; dải 2448×768 tổng 336 ms. Sau khi lên GPU, cascade CPU (~200–300 ms) là phần chậm nhất.

**Quad hiển thị:** mỗi bước cascade trả `Decoded(text, corners)` — 4 góc QR quy về ảnh gốc (trừ viền đệm `UPSCALE_PAD_PER_SCALE × scale`, chia scale, cộng gốc ROI; bước warp đi ngược homography). Vẽ bằng `display_quad()`: góc decoder, chưa đọc được thì `minAreaRect(polygon_xy)`. KHÔNG vẽ `padded_quad_xy` (mask YOLO thô ~8×8 điểm cho QR 60px → quad méo tới 45°); `padded_quad_xy` vẫn dùng cho warp.

**Quay video:** `start_recording(RecordingOptions)` / `stop_recording()` chỉ gửi yêu cầu; đọc `recording_status()` để biết kết quả. Capture thread sở hữu InitRecord/PushFrame/StopRecord, dùng RGB8/MONO8 + header sau ISP trước BGR/overlay, không lấy từ latest_frame. Snapshot không giữ SDK lock. Giữ `native_open` độc lập với ERROR: chưa finalize thì không UnInit/free/reopen. Mỗi phiên khởi tạo thành công ghi một `video.avi` trong thư mục timestamp + UUID riêng, không tự chia file/dừng theo dung lượng video; giữ b2GLimit=False (SDK chưa triển khai tự chia). Khả năng AVI >4 GiB phụ thuộc DLL, phải kiểm chứng camera thật; vẫn giữ disk guard và dừng khi có lỗi. Đường dẫn phải encode GBK. Camera configuration bị khóa khi ghi. Test mock không chứng minh không mất frame hoặc AVI thật đúng thời lượng.

**ImprovePipeline** (không dùng SR/Real-ESRGAN, tối ưu cho QR nhỏ: QR 32 mm version 2 rộng ~55–61 px, 2,2–2,44 px/ô ở cấu hình hiện trường; phòng thí nghiệm cũ ~60 px trên frame MindVision 2448×2048): detect qrdet với `imgsz=1280` (640 mặc định bỏ sót QR nhỏ; dải có cạnh dài ≥4 lần cạnh ngắn tự dùng 1600) → `decode_detection`/`scan` (ảnh đơn, và PassReader khi `multi_frame=False`) chạy cascade trên ROI cắt từ ảnh gốc, rẻ trước đắt sau: ROI×4 → zxing; warp 256 + Quiet Zone → zxing; CLAHE×4 → WeChat; stretch×4 → WeChat CNN+SR; ROI×3 → WeChat CNN+SR. Model WeChat ONNX (OpenCV 5 không load caffemodel) ở `qr/models/wechat/`; thiếu model thì bỏ qua bước CNN. Không dùng pyzbar/`decode_parallel` trong pipeline (yếu với QR ~2px/module, chậm). Test: `python tests/test_small_qr.py` (dùng frame mẫu trong `QR_SAMPLES_DIR`, mặc định `../QRDetector-research/data/images`, kỳ vọng ≥12/14).

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
demo_ui/tray.py            → TrayController: chạy nền ở khay hệ thống (icon, menu, thông báo)
demo_ui/api_config.py      → ApiConfig: đọc BASE_URL, APP_TOKEN_SECRET, API_KEY (+ BASIC_AUTH_USER/PASSWORD tùy chọn) từ `.env`
demo_ui/scan_uploader.py   → ScanUploader (hàng đợi + thread nền) + ReportClient: `POST /api/v1/production/camera/product-item-reports`
```

**Gửi QR lên server** (API báo cáo tấm, `docs/camera-integration.md`): `on_reads_done` (đọc lần đầu của lượt) gọi `ScanUploader.submit`; thread nền gọi `ReportClient(mã)`: `POST {BASE_URL}/api/v1/production/camera/product-item-reports`, body `{"productItemCode": mã nguyên văn}`, header `X-App-Token` = hex HMAC-SHA256(`APP_TOKEN_SECRET`, `"{ts}
POST
{path}"`, ts làm tròn xuống đầu phút, tính lại mỗi lần gửi), `X-Api-Key`, `User-Agent: QRDetector-camera/1.0` (Cloudflare chặn UA mặc định Python-urllib, error 1010) và `Authorization: Basic` nếu có `BASIC_AUTH_USER`/`BASIC_AUTH_PASSWORD` (host dev đặt sau nginx Basic auth `realm="Dev Environment"`). Cấu hình đọc từ `.env` ở gốc repo (`demo_ui/api_config.py`, mẫu `.env.example`, biến môi trường ghi đè); thiếu biến thì không tạo uploader, ô **Gửi mã lên server** bị khóa (giữ giá trị đã lưu), tooltip và status bar nêu biến thiếu (`api_missing`). 200 là thành công, `warning` khác rỗng chỉ ghi log `upload_ok`; 400/401/403/404 không thử lại (403 `invalid X-App-Token` thêm "kiểm tra giờ máy"), mạng/408/429/5xx/body không phải JSON thử lại 3 lần (1s, 2s, 4s); lỗi hiện ở status bar kèm câu `error` server trả về và ở chân màn hình chính (`Workspace.set_upload_error`, giữ tới lần gửi thành công kế tiếp, vì status bar nằm trong cửa sổ Cấu hình và bị trạng thái camera/fps ghi đè). Mã chờ hoặc đã gửi trong 30 giây bị bỏ qua; hàng đợi 500 mục, đầy thì bỏ mục cũ nhất. Thất bại không nhớ là đã gửi (gửi lại chỉ tăng số lần quét trên server). Không log secret/API key. Thử thật: `python tools/try_report_api.py <mã>` (mã có thật sẽ được ghi nhận như vừa quét; mã không tồn tại → 404 để chỉ kiểm chữ ký/key). `main.py` không gửi server. Bật/tắt bằng ô **Gửi mã lên server** (tab Băng chuyền, lưu `upload_enabled`), có hiệu lực ngay qua `ScanUploader.set_enabled`: tắt thì bỏ hàng đợi, ngừng thử lại, mã đọc trong lúc tắt không được gửi bù. `MainWindow(settings_path=None)` không tạo uploader (test không gọi mạng thật); test truyền uploader giả qua tham số `uploader`.

**Chạy nền ở khay hệ thống:** `main_demo.py`/`main_basler.py` truyền `tray=True` và đặt `app.setQuitOnLastWindowClosed(False)` (nếu không, đóng cửa sổ Cấu hình lúc cửa sổ chính đang ẩn sẽ thoát app); `closeEvent` khi accept tự `QApplication.quit()`. Máy không có khay thì `tray` là None và nút **Chạy nền** ẩn; test không truyền `tray` (hoặc truyền bản giả). Nút/`Ctrl+H` gọi `TrayController.hide_window` (ẩn cả cửa sổ Cấu hình, nhớ fullscreen/maximize); icon chỉ hiện khi đang chạy nền, bấm icon thì `restore`. Khi ẩn, `on_display_tick` vẫn gửi decode nhưng bỏ phần vẽ — không được dừng `display_timer`. Màu icon/tooltip theo `RunState` và số mã đã đọc; thông báo Windows khi ERROR hoặc mất tín hiệu lúc đang ẩn. `main_dual.py` chưa có. Test: `tests/test_demo_tray.py`.

`Ui_MainWindow.setupUi` vẫn tạo widget cũ, `_setup_shell` chuyển `label_image` vào `Workspace`, `frame_camera_list` và `status_bar` vào `SettingsWindow`; phần còn lại của form (`frame_area`…) bị hủy cùng central widget cũ nên không được đụng tới. `MainWindow(settings_path=None)` không đọc/ghi file (dùng trong test); `main_demo.py` truyền `DEFAULT_SETTINGS_PATH`. Bắt đầu: thread nền chạy tìm camera → `open` → trigger liên tục → `apply_run_settings(RunSettings)` (AE tắt, exposure + gain cố định, FPS cao nhất, vùng đọc x/y qua `set_sensor_window`) → `configured` → chờ `worker.ready` → RUNNING. KHÔNG nạp Param khi Bắt đầu: Param A lưu gain 10, nạp ngay sau `open` rồi tắt AE làm ảnh tối đi khoảng 3 lần và không đọc được QR. Mặc định exposure 12,9 ms, gain 40 (MindVision); `BaslerSettings` mặc định 2 ms, gain 6 dB, dải y 880 cao 1072 (buồng tối 60 cm), `ReplaySettings` giữ toàn khung; decode mỗi N frame (ô **N** tab Băng chuyền, lưu `decode_every_n`, mặc định 5, đổi được lúc đang chạy). **Mở** ở tab Kết nối cũng áp dụng ngay cấu hình này. Bản demo không có quay video. Ô **Dùng GPU** (tab Băng chuyền, lưu `use_gpu`) gọi `ImprovePipeline.set_device("auto"/"cpu")`, đổi được lúc đang chạy và chỉ ảnh hưởng bước detect; máy không có CUDA thì ô bị vô hiệu hóa và giữ nguyên giá trị đã lưu. CUDA lỗi lúc chạy thì detector tự về CPU trong khi ô vẫn tích (chân màn hình hiện CPU); tắt rồi bật lại ô để thử lại GPU. Khi CONNECTING, GUI không gọi getter SDK. Số liệu: `reads` (từ `FrameResult.first_reads`) thêm dòng ngay, `passes` chốt trạng thái, ghép theo `track_id`. Reset/Dừng dùng `request_flush(purpose)`: chốt lượt trên thread worker rồi phát `flushed`; signal cùng thread đến theo thứ tự nên GUI xóa lúc nhận `flushed` không bị kết quả cũ chen vào. Lượt không nội dung và <2 observation là nhiễu, không tính vào tỉ lệ.

## Bản demo Basler (`python main_basler.py`)

Dùng lại toàn bộ `demo_ui`: `MainWindow(camera=BaslerCameraManager(), settings_cls=BaslerSettings)`; không truyền thì vẫn là MindVision. `camera/basler_manager.py` chỉ có phần API `CameraManager` mà demo dùng (`list_cameras`, `open`, `close`, `latest_frame`, `frame_statistic`, `apply_run_settings`, getter exposure/gain, `set_trigger_mode(0)`), thiết bị bọc trong `BaslerDevice` (`GetSn`, `GetFriendlyName`, `GetPortType`). Sửa API demo gọi từ camera thì sửa cả ba backend (MindVision, Basler, phát lại). Capture: `GrabStrategy_LatestImageOnly`, Mono8 → BGR. Đổi vùng đọc hoặc tắt giới hạn fps phải dừng grab rồi chạy lại (camera khóa tham số khi grab); exposure/gain đổi được ngay. Getter trả giá trị cache, không gọi SDK từ GUI thread. Gain tính bằng dB (`RunSettings.analog_gain`), kẹp theo camera. Cấu hình: `config/basler_settings.json`. Vẫn nạp `mvsdk` qua `demo_ui.main_window` nên máy cần DLL MindVision. Test: `tests/test_basler_manager.py` (pylon giả); chạy không camera bằng `PYLON_CAMEMU=1` và chọn serial `0815-0000` — camera thật xếp trước nên phải chọn theo serial.

## Bản phát lại (`python main_replay.py [--data data/field/raw] [--speed 1.0]`)

Luồng như `main_basler.py` (đọc nền ComboBC bật, `ReplaySettings` ở `config/replay_settings.json`, `tray=False`) nhưng camera là `camera/replay_manager.py:ReplayCameraManager`: mỗi thư mục con của `--data` có `frame_NNNN.tiff` là một `ReplayDevice` (`GetSn` = tên thư mục = `rec_id` của `tools/clean_field_data.py`). Không sửa `demo_ui.MainWindow`.
- `open` chỉ hiện frame đầu (xem trước, vẽ lại khi đổi vùng đọc). Đồng hồ phát chạy từ `start_playback()`, do `demo_ui/replay_end.py:ReplayEndWatcher` gọi khi vào RUNNING; nếu phát ngay lúc mở thì warm-up GPU ~3,5 s làm lần ghi ngắn hết trước khi decode.
- Hai thread: thread đọc trước 8 frame, thread phát đúng mốc mtime (hard link giữ mtime pylon) ÷ `speed`; mtime hỏng thì dùng `write_fps` của `meta.json`, rồi 25 fps. Đọc chậm thì phát trễ chứ không nhảy frame. `seq` = số thứ tự frame + 1, khớp `frames.csv`.
- Hết frame: `finished`, watcher gọi `window.on_stop()` rồi hiện "Hết dữ liệu". `main_replay` đặt `pass_fallback.FLUSH_WAIT_S = 180`: lượt cuối chỉ đóng khi Dừng chốt lượt, và B/C mất 8–110 s, trong khi bản camera chỉ chờ 5 s.
- `apply_run_settings`: exposure lấy `meta.json["exposure_ms"]` nếu có, không thì lấy ô Cấu hình (chỉ để tính vệt mờ). Vùng đọc cắt từ frame.
- `ReplaySettings.upload_enabled = False` mặc định.

Test: `tests/test_replay_manager.py` (TIFF tạm + `os.utime`), `tests/test_replay_end.py`.

## App hai camera (`python main_dual.py`)

`demo_ui/dual_window.py`: mỗi camera một `_Channel` (manager, `RunController`, `CameraPanel`, luồng đóng riêng); trạng thái chung `overall_state` chỉ để hiển thị, camera lỗi không dừng camera kia. `demo_ui/dual_worker.py`: MỘT thread decode luân phiên, `PassReader` riêng từng camera — không chạy hai thread vì chung GPU và `qr/decoder.py` giữ detector WeChat toàn cục không khóa. `demo_ui/merged_stats.py` (thuần Python): cùng mã trong 30 giây kể từ lần đầu là một dòng (`A`/`B`/`A+B`); lượt không đọc được không ghép được với camera kia nên tỉ lệ đọc chỉ theo từng camera; khóa lượt là `(camera, track_id)` vì track_id hai camera trùng nhau. `demo_ui/dual_workspace.py` kế thừa `Workspace` qua `_build_video_area`. Cấu hình `DualSettings` (`config/dual_settings.json`): bản ghi `a`, `b`, phần dùng chung lưu ở `a`. Test: `tests/test_dual_app.py`.

## Jetson Nano (`docs/jetson-nano.md`)

Chạy trong Docker (`docker/jetson/Dockerfile`, Debian bookworm: Python 3.11, glibc 2.36, PyQt5 từ apt vì PyPI không có wheel aarch64; JetPack 4.6 chỉ có Python 3.6/glibc 2.27), chỉ CPU với bộ phát hiện ONNX/OpenVINO, không cài torch/qrdet: `qr/detector.py` nạp torch/qrdet trong try, thiếu thì chỉ `QRDetector()` báo ImportError (`tests/test_no_torch.py`). OpenCV bản headless (bản thường xung đột plugin xcb với PyQt5). `libMVSDK.so` arm64 chép vào `docker/jetson/lib/` (gitignore) vì `mvsdk` luôn được nạp. `docker/jetson/run.sh` gắn repo vào `/app`, `--privileged --network host`, X11. Chưa chạy thử trên Jetson thật.

## Ràng buộc

- Không thêm `basicsr`/`realesrgan`.
- Đầu vào QR luôn là BGR `np.ndarray` contiguous (OpenCV).
- `CameraManager` là boundary tương thích của UI; giữ API public khi thay đổi backend.
- `torch`/`qr` phải được import trước PyQt5 để tránh `WinError 1114` trên Windows.
- `mvsdk.py` được vendor trong repo; không import động từ thư mục SDK.
