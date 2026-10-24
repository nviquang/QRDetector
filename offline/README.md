# offline/ — App quét QR từ ảnh / video (không cần camera)

App PyQt5 dùng **cùng thuật toán với `solution/`** (`ImprovePipeline`, không Real-ESRGAN):

```
Ảnh/frame BGR → qrdet (YOLOv8) detect → warp 512 + Quiet Zone 64 → decode_parallel
              → fallback [Gốc, Laplacian, Unsharp] → upscale 2x + Otsu + Quiet Zone → decode lại
```

Gói `offline/qr/` là **bản copy nguyên** của `solution/qr/` để app độc lập, không import gì từ
`solution/` và không cần MindVision SDK. Khi thuật toán trong `solution/qr/` thay đổi, copy lại thư mục.

## Chạy

```bash
# từ gốc repo
.venv\Scripts\activate
python offline/app.py
python offline/app.py images/            # mở sẵn thư mục ảnh
python offline/app.py video/10.mp4       # mở sẵn video
```

Phụ thuộc giống `solution/` trừ MindVision: `PyQt5 numpy opencv-contrib-python pyzbar zxing-cpp qrdet torch`.
Lần chạy đầu `qrdet` có thể tải model YOLOv8.

## Sử dụng

- **Mở ảnh… / Mở thư mục ảnh… / Mở video…** hoặc kéo thả file/thư mục vào cửa sổ.
- **Ảnh:** chọn trong danh sách hoặc ⏮/⏭; mỗi ảnh được decode đầy đủ. Quad **xanh** = decode được, **đỏ** = chỉ phát hiện.
- **Video:** ▶/⏸ (phím Space), kéo thanh tua, ⏮/⏭ lùi/tiến 1 frame. Khi phát, cứ **mỗi N frame** gửi decode một lần;
  pipeline bận thì frame bị bỏ (giống app camera) — kết quả khi phát là *lấy mẫu*, không đầy đủ.
  Khi dừng/tua, frame hiện tại luôn được decode.
- **Quét toàn bộ:** decode tuần tự mọi ảnh trong danh sách, hoặc mọi frame thứ N của video (không bỏ frame,
  không theo thời gian thực), có thanh tiến độ và **Huỷ quét**. Đặt N = 1 để quét từng frame.
- **Bảng kết quả** gộp theo (file, nội dung QR): frame/thời điểm đầu tiên, số lần đọc được.
  Double-click một dòng để nhảy tới ảnh/frame đó.
- **Xuất CSV…** (UTF-8 BOM, mở được bằng Excel): `file, qr_text, first_frame, first_time, last_frame, last_time, hits`.
- **Lưu ảnh kết quả…** lưu frame hiện tại kèm quad (PNG/JPG, chịu được đường dẫn tiếng Việt).

## Cấu trúc

```
offline/
├── app.py            # entry — import qr (torch) TRƯỚC PyQt5 để tránh WinError 1114
├── main_window.py    # UI: ảnh/video, phát, tua, quét toàn bộ, bảng kết quả, xuất
├── workers.py        # DecodeWorker (1 frame, bỏ frame khi bận), ScanWorker (quét toàn bộ), SharedPipeline (khoá model)
├── media_source.py   # đọc ảnh (Unicode path), VideoSource (cv2.VideoCapture), ensure_bgr
├── results.py        # ResultLog: gộp kết quả, xuất CSV
├── qr/               # copy nguyên từ solution/qr/
└── tests/            # test offline, không cần model
```

## Test

```bash
python -m unittest discover -s offline/tests -p "test_*.py"
```

## Giới hạn

- Video mở bằng `cv2.VideoCapture`: đường dẫn video có ký tự ngoài ASCII có thể không mở được trên Windows —
  đổi sang đường dẫn ASCII. (Ảnh không bị giới hạn này.)
- Số frame / FPS lấy từ metadata container; một số file (AVI không chuẩn) có thể báo sai → thời điểm lệch.
  Không biết số frame thì thanh tua bị tắt, quét toàn bộ vẫn chạy đến hết file.
- Màu quad theo cả frame (có ít nhất 1 QR decode được → tất cả quad xanh), giống app camera, vì
  `ImprovePipeline.scan()` không trả về cặp detection ↔ nội dung.
