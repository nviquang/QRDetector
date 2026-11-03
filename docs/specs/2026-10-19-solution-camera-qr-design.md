# Spec: solution/ — Tích hợp Camera SDK + QR Pipeline

**Ngày:** 2026-10-19
**Trạng thái:** Design đã duyệt (3 phần: kiến trúc, ImprovePipeline, camera/UI)

## Mục tiêu

Sản phẩm cuối trong `solution/`: ứng dụng PyQt5 dùng Hikvision MV SDK (`mvsdk`) để kết nối camera và chỉnh thông số, nhận frame trực tiếp, decode QR bằng luồng cải tiến (không Real-ESRGAN) lấy từ `improve_main.ipynb`.

**Ràng buộc từ user:**

- Dùng luồng `production/main.py` (entry) + `improve_main.ipynb` (thuật toán); **không** dùng luồng `main.ipynb` (SR).
- Approach A: package nhiều lớp; `solution/` **tự chứa** (copy `mvsdk.py` + copy `production/` → `qr/`), không sửa `production/` hay `Demo/`.
- Giao diện PyQt5 kiểu `Demo/python/Advanced`.
- Decode theo **interval N frame** (mỗi N frame gọi pipeline 1 lần).
- `CLAUDE.md` cho `solution/` — ngắn gọn.

## Kiến trúc

```
solution/
├── CLAUDE.md
├── main.py                  # entry: python main.py
├── qr/                      # copy production/ (bỏ super_resolution.py)
│   ├── __init__.py
│   ├── detector.py
│   ├── corrector.py
│   ├── preprocessor.py
│   ├── decoder.py
│   └── improved_pipeline.py # ImprovePipeline — MỚI
├── camera/
│   ├── __init__.py
│   ├── hik_sdk.py           # nạp Hikrobot SDK MỚI (MV_CC_* / MvCameraControl.dll)
│   └── camera_manager.py    # wrap SDK mới, không Qt
├── ui/
│   ├── __init__.py
│   ├── main_window.py       # port từ Advanced/MainWindow.py
│   └── main_window_ui.py    # UI form (port từ Advanced/MainWindowUI.py)
└── tests/
    └── test_improve_pipeline.py   # offline, 1 ảnh
```

**Cập nhật (2026-10-19, sau cài MVS 5.1.0):** SDK cũ (`mvsdk.py`, `MVCAMSDK_X64.dll`) ngừng phát hành — `mvsdk.py` đã **xóa**; `camera/` chuyển sang SDK mới `MvCameraControl` (MV_CC_*, API GenICam) lấy wrapper từ `Development\Samples\Python\MvImport`. Public API `CameraManager` giữ nguyên nên UI không đổi. Lưu ý: **torch phải import trước PyQt5** (WinError 1114 c10.dll) — xử lý trong `ui/main_window.py` và `main.py`.

### Luồng dữ liệu

1. **Capture** (thread trong `CameraManager`): `CameraGetImageBuffer` → `CameraImageProcess` → RGB888/MONO8 → `cvtColor` → **BGR np.ndarray** → ghi `latest_frame` (ghi đè = drop frame cũ, có lock).
2. **Decode** (UI đếm frame, cứ mỗi **N frame capture được** thì gọi 1 lần — N là số nguyên do user cấu hình): lấy `latest_frame` → nếu pipeline đang busy thì **bỏ qua** (không xếp hàng) → `ImprovePipeline.decode()` → `list[str]`.
3. **Hiển thị**: frame ~30fps (poll `latest_frame`), vẽ quad 4 góc + text QR; bảng kết quả QR mới nhất + lịch sử; FPS capture/decode; N configurable + Start/Stop decode.

### ImprovePipeline (`qr/improved_pipeline.py`)

```
decode(image_bgr) → list[str]
  1. QRDetector(model_size="s", conf_th=0.5).detect()   # [] nếu không detection
  2. mỗi detection:
     warp_qr(512) → add_quiet_zone(64)
     3. decode_parallel(warp); fail → decode_parallel(warp+QZ)
     4. FALLBACK (chỉ khi fail): [Gốc, sharpen_laplacian, unsharp_masking]
        → upscale_otsu(scale=2, pad=64) → decode_parallel
     trả text đầu tiên thành công
```

- API: `ImprovePipeline(conf_th=0.5, warp_size=512, quiet_zone_pad=64).decode(frame_bgr) -> list[str]`
- Không matplotlib, không `FORCE_RUN_ALL`, không SR (`super_resolution.py` không copy → không cần basicsr/realesrgan/weight).
- 4 decoder như `decoder.py` hiện tại: pyzbar / zxing-cpp / OpenCV / WeChat, auto-rotate.

### CameraManager (`camera/camera_manager.py`)

```python
mgr.init_sdk(); mgr.list_cameras(); mgr.open(index); mgr.close()
mgr.set_ae_state(auto) / set_ae_target(v) / set_exposure_time(us) / set_analog_gain(g)
mgr.set_trigger_mode(mode) / soft_trigger() / set_strobe_mode/polarity(...)
mgr.set_roi(index); set_mirror(h, v); set_gamma/contrast/sharpness/saturation...
mgr.set_gain(r, g, b) / set_once_wb(); get_* corresponding getters
mgr.save_param(slot) / load_param(slot) / reset_param()
mgr.latest_frame() -> (np.ndarray BGR | None, seq:int); mgr.frame_statistic()
```

Không import Qt — test được độc lập. Capture thread port từ `CaptureThread` của Advanced (threading, không Qt). Buffer output có lock riêng khi đổi ROI (`set_roi`) để không free khi capture thread đang dùng.

### UI (`ui/main_window.py`)

- **Trái:** panel thông số camera (giữ logic của `Advanced/MainWindow.py`, chuyển sang gọi `CameraManager`).
- **Phải:** video + quad + bảng kết quả QR + FPS; ô cấu hình N; Start/Stop decode; checkbox hiển thị quad.

## Xử lý lỗi

- Không có camera → message, disable nút, app vẫn mở.
- Camera rút giữa chừng → bắt `CameraException` → status bar + đóng sạch (stop thread → `CameraStop`/`CameraUnInit`).
- Decode exception → log, frame kế tiếp chạy tiếp.
- pyzbar DLL Windows → giữ cách xử lý `os.add_dll_directory()` như repo hiện có.

## Testing

- **Offline:** `tests/test_improve_pipeline.py` chạy `ImprovePipeline.decode()` trên 1 ảnh QR có sẵn trong repo (không cần camera).
- **Smoke:** `python main.py` với camera thật — mở camera, chỉnh exposure, decode ra text.

## Không nằm trong scope

- Sửa `production/` hay `Demo/`.
- Real-ESRGAN / `main.ipynb` flow.
- CLI/headless.
- Trigger hardware nâng cao beyond what Advanced demo có.
