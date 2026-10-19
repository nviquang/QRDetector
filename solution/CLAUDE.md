# CLAUDE.md — solution/

Sản phẩm cuối: ứng dụng PyQt5 tích hợp **camera Hikvision (mvsdk)** + **QR pipeline**.

## Chạy

```bash
.venv\Scripts\activate
python main.py
```

Cần camera thật cài driver MV SDK. Test offline (không cần camera):
`python tests/test_improve_pipeline.py`

## Kiến trúc

```
main.py            → entry, khởi tạo MainWindow
mvsdk.py           → copy từ Demo/python/Advanced/ (SDK binding, KHÔNG sửa ở đây)
camera/camera_manager.py  → wrap mvsdk: enumerate/open/set param/capture thread → latest_frame (BGR)
qr/                → copy từ production/ (KHÔNG sửa production/ gốc)
  detector/corrector/preprocessor/decoder.py  → giữ nguyên
  improved_pipeline.py  → ImprovePipeline: luồng QR chính
ui/main_window.py  → port từ Advanced/MainWindow.py, bind UI ↔ CameraManager
```

**Luồng:** capture thread → `latest_frame` (BGR, frame cũ bị drop) → mỗi N frame decode 1 lần (busy thì bỏ qua) → vẽ quad + hiển thị text QR.

**ImprovePipeline** (theo `production/improve_main.ipynb`, **không dùng SR/Real-ESRGAN**):
detect (qrdet) → warp 512 + Quiet Zone 64 → `decode_parallel` (4 decoder) → fallback: 3 biến thể [Gốc, Laplacian, Unsharp] → upscale_otsu + QZ → `decode_parallel`.

## Ràng buộc

- **Không dùng** luồng `production/main.ipynb` (SR) — `qr/` không có `super_resolution.py`, không cần basicsr/realesrgan.
- **Không sửa** `production/` và `Demo/` — mọi thay đổi chỉ nằm trong `solution/`.
- Đầu vào QR luôn **BGR** np.ndarray (OpenCV); camera RGB888 cần `cvtColor` trước.
- Spec: `docs/superpowers/specs/2026-10-19-solution-camera-qr-design.md`.
