# CLAUDE.md — solution/

Sản phẩm cuối: ứng dụng PyQt5 tích hợp **camera MindVision (MVSDK `Camera*`)** + **QR pipeline**.

Hướng dẫn cài đặt và sử dụng: xem `solution/README.md`.

## Chạy

```bash
.venv\Scripts\activate
cd solution
python main.py
```

Cần driver/runtime MindVision tương ứng kiến trúc Python (`MVCAMSDK_X64.dll` cho 64-bit). Test pipeline offline không cần camera:
`python tests/test_improve_pipeline.py` và `python tests/test_small_qr.py`

## Kiến trúc

```
main.py                  → entry, khởi tạo MainWindow
mvsdk.py                 → wrapper Python MindVision, vendor từ Demo/Python/Basic
camera/camera_manager.py → lifecycle, tham số, capture thread → latest_frame BGR
qr/                      → copy từ production/ (KHÔNG sửa production/ gốc)
  detector/corrector/preprocessor/decoder.py
  improved_pipeline.py   → ImprovePipeline
ui/main_window.py        → bind UI ↔ CameraManager, panel quay/đóng bất đồng bộ
camera/recording.py      → AVI không nén MVSDK, một file/phiên, trạng thái và disk guard
camera/conveyor.py       → công thức băng chuyền thuần (exposure tối đa theo tốc độ/mm/px, px/ô, căn dải ROI)
```

**Chế độ băng chuyền** (`CameraManager.apply_conveyor_mode(ConveyorSettings)`, nút trong panel Kết quả QR): tắt AE, exposure cố định `t = mờ_px × mm/px ÷ v` (kẹp theo min/max camera), frame speed cao nhất, tùy chọn ROI dải ngang toàn bề rộng (`set_sensor_band`, căn bội 16 — cần kiểm chứng camera thật). `open()` vẫn bật AE như cũ; chế độ băng chuyền phải bấm áp dụng sau khi mở. Nhãn trạng thái hiển thị exposure, vệt mờ ước tính, độ sáng TB và % cháy sáng; khi đang quay/đóng không gọi getter SDK từ GUI thread (dùng cache).

Camera dùng MindVision `mvsdk`: `CameraSdkInit → CameraEnumerateDevice → CameraInit → CameraGetCapability → CameraPlay`. Capture dùng `CameraGetImageBuffer → CameraImageProcess → CameraReleaseImageBuffer`; đóng bằng `CameraStop → CameraUnInit → CameraAlignFree`.

**Luồng:** capture thread → copy frame sở hữu độc lập, RGB/mono chuyển thành BGR 3 kênh → `latest_frame` (frame cũ bị drop) → mỗi N frame decode một lần → vẽ quad và hiển thị text QR.

**Quay video:** `start_recording(RecordingOptions)` / `stop_recording()` chỉ gửi yêu cầu; đọc `recording_status()` để biết kết quả. Capture thread sở hữu InitRecord/PushFrame/StopRecord, dùng RGB8/MONO8 + header sau ISP trước BGR/overlay, không lấy từ latest_frame. Snapshot không giữ SDK lock. Giữ `native_open` độc lập với ERROR: chưa finalize thì không UnInit/free/reopen. Mỗi phiên khởi tạo thành công ghi một `video.avi` trong thư mục timestamp + UUID riêng, không tự chia file/dừng theo dung lượng video; giữ b2GLimit=False (SDK chưa triển khai tự chia). Khả năng AVI >4 GiB phụ thuộc DLL, phải kiểm chứng camera thật; vẫn giữ disk guard và dừng khi có lỗi. Đường dẫn phải encode GBK. Camera configuration bị khóa khi ghi. Test mock không chứng minh không mất frame hoặc AVI thật đúng thời lượng.

**ImprovePipeline** (không dùng SR/Real-ESRGAN, tối ưu cho QR nhỏ ~60px trên frame 2448×2048): detect qrdet với `imgsz=1280` (640 mặc định bỏ sót QR nhỏ) → cascade trên ROI cắt từ ảnh gốc, rẻ trước đắt sau: ROI×4 → zxing; warp 256 + Quiet Zone → zxing; CLAHE×4 → WeChat; stretch×4 → WeChat CNN+SR; ROI×3 → WeChat CNN+SR. Model WeChat ONNX (OpenCV 5 không load caffemodel) ở `qr/models/wechat/`; thiếu model thì bỏ qua bước CNN. Không dùng pyzbar/`decode_parallel` trong pipeline (yếu với QR ~2px/module, chậm). Test: `python tests/test_small_qr.py` (dùng frame mẫu `../images/*.bmp`, kỳ vọng ≥12/14).

## Ràng buộc

- Không thêm `basicsr`/`realesrgan` vào `solution/`.
- Không sửa `production/` và `Demo/`; mọi thay đổi chỉ nằm trong `solution/`.
- Đầu vào QR luôn là BGR `np.ndarray` contiguous (OpenCV).
- `CameraManager` là boundary tương thích của UI; giữ API public khi thay đổi backend.
- `torch`/`qr` phải được import trước PyQt5 để tránh `WinError 1114` trên Windows.
- Wrapper `solution/mvsdk.py` được vendor trong solution; không import động từ `Demo/`.
