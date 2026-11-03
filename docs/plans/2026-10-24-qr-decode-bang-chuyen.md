# Plan cải thiện decode QR trên video băng chuyền

Ngày: 2026-10-24 · Phạm vi: `offline/qr/` (ImprovePipeline) và cấu hình camera MindVision trong `solution/`

## 1. Hiện trạng đo được

Script đánh giá chạy `ImprovePipeline` (detect qrdet imgsz=1280 + cascade zxing/WeChat) trên 5 video trong `videos/`, lấy mẫu 1/5 frame:

| Video | Frame mẫu | Detect được | Decode được | Cạnh QR (px, median) | Laplacian var (median) |
|---|---|---|---|---|---|
| 153834594 | 23 | 7 | 0 | 59 | 396 |
| 153938850 | 35 | 32 | 0 | 56 | 356 |
| 154008196 | 152 | 139 | 0 | 59 | 329 |
| 154152847 | 66 | 51 | 2 | 60 | 181 |
| 154459957 | 122 | 89 | 0 | 66 | 159 |
| **Tổng** | **398** | **318 (80%)** | **2 (0.6%)** | | |

Nội dung QR giải được: `000000585546`, `000000585623` (12 chữ số → QR version 1–2, 21–25 module).

Thời gian cascade decode: ~160–240 ms / QR khi thất bại (chạy hết 5 bước).

## 2. Nguyên nhân gốc (theo thứ tự mức ảnh hưởng)

1. **Motion blur theo hướng băng chuyền.** Năng lượng gradient dọc gấp 1.6–2.0 lần gradient ngang trên ROI của cả 5 video; quan sát ROI thấy vệt mờ ngang ~4–8 px. Mỗi module QR chỉ ~2.3–2.8 px, tức vệt mờ dài **2–3 module**. Theo Yahyanejad & Ström (CVPR-W 2010), không deblur thì chỉ đọc được khi kernel < ½ module; deblur tốt nhất đẩy lên ~4 lần module, với điều kiện ảnh ít nhiễu.
2. **Độ phân giải quá thấp: ~2.5 px/module.** Khuyến nghị công nghiệp là tối thiểu 4 px/module để đọc (machine-vision-shop, MVisionPro), 8–10 px/module để verify (Omron). Finder pattern của zxing-cpp cần tâm ≥ 3 px. Upscale bicubic không tạo thêm thông tin.
3. **Video nén H.264 mạnh.** ~50–60 KB/frame ở 2448×2048 (bitrate rất thấp). Nén khối 8×8 / 16×16 xoá chi tiết cỡ 2–3 px, sinh artefact ở cạnh module. Video trong `videos/` có tên dạng `Video_YYYYMMDD…` (giống phần mềm demo MindVision), không phải luồng ghi không nén của `solution/camera/recording.py`.
4. **Thứ hai: QR version 1 không có alignment pattern**, nên perspective chỉ dựa vào 3 finder; quad từ qrdet là `padded_quad_xy` (có nới) nên warp lệch lưới.

**Thử nghiệm deblur nhanh:** Wiener deconvolution với PSF đường ngang (L = 3–7 px gốc, K ∈ {0.005, 0.02}), sau đó upscale 3x → zxing/WeChat, trên 80 ROI lỗi: **0/80 decode được** (baseline có WeChat CNN: 0/80). Deblur cổ điển không cứu được dữ liệu hiện tại, vì nhiễu nén H.264 bị khuếch đại khi deconvolution ở mức ~2.5 px/module.

Kết luận: đây chủ yếu là **bài toán thu nhận ảnh (acquisition)**. Thuật toán (deblur, gộp nhiều frame) chỉ bù được một phần, vì thông tin đã mất khi chụp và khi nén.

## 3. Kết quả nghiên cứu (web)

| Hướng | Nguồn | Ý chính | Áp dụng được ở đây? |
|---|---|---|---|
| Giới hạn exposure theo tốc độ | TI SSZT704, Opto Engineering, MVisionPro, machine-vision-shop | `t_exp ≤ blur_cho_phép(px) × kích_thước_pixel_trên_vật(mm) / v(mm/s)`; blur ≤ 0.5–1 px | **Có, hiệu quả nhất** |
| Strobe / đèn xung đồng bộ | TI, MVisionPro, Opto-E | Đèn xung ngắn đóng băng chuyển động; ánh sáng nền phải yếu | Có, nếu exposure ngắn làm ảnh quá tối |
| Px/module tối thiểu | machine-vision-shop (4 px), Omron (8–10 px) | Chọn ống kính/khoảng cách để module ≥ 4 px | Có, cần đổi quang học hoặc ROI |
| Deblur mù cho barcode | Yahyanejad CVPR-W 2010; van Gennip IEEE TIP 2015 | Ước lượng PSF từ finder pattern đã biết hoặc histogram 2 mức, rồi deconvolution | Có, PSF ở đây gần như đường ngang cố định → **semi-blind** đơn giản |
| Deblur bằng deep learning | ADNet / EG-Restormer (2025, có code), GAN + attention (Springer 2024), KEN + Transformer (2024) | Tỉ lệ decode 70–90% trên tập blur nặng; 0.3–0.9 s/ảnh | Có thể dùng, nhưng cần GPU và fine-tune theo dữ liệu thật |
| Super-resolution cho 2D code | Mosaic-SR (Datalogic, ICIP 2025, có code); EDSR/ESPCN (PMC 2025) | SR chuyên cho barcode tốt hơn SR ảnh chung (Real-ESRGAN) | Có, cho bài toán px/module thấp |
| Gộp nhiều frame | Patent US8150163; CN121120442A; QR SR max-likelihood (55×55 px, >85%) | Theo dõi QR qua các frame, căn chỉnh sub-pixel, tích luỹ thống kê từng module rồi decode | **Có**: băng chuyền chuyển động đều, QR xuất hiện ở nhiều frame liên tiếp |
| Tinh chỉnh zxing-cpp | Issue zxing-cpp #888, #966 | Unsharp mask bán kính 1 giúp mép module; HybridBinarizer tốt nhất khi ≤ 8 px/module | Có, chi phí thấp |

## 4. Plan

### Giai đoạn 0: Bộ đánh giá chuẩn (0.5 ngày, làm trước)
- Thêm `offline/tests/eval_videos.py`: chạy pipeline trên `videos/*.avi`, xuất CSV (video, frame, detect, decode, cạnh QR, gy/gx, bước cascade thành công, thời gian).
- Gom nhóm theo **vật thể** (một QR đi qua nhiều frame), không theo frame: metric chính là *tỉ lệ vật thể đọc được*, vì băng chuyền chỉ cần đọc mỗi vật một lần.
- Lưu ROI thất bại để làm bộ test hồi quy.

### Giai đoạn 1: Sửa phần thu nhận ảnh (ưu tiên cao nhất, 1–2 ngày thử trên máy)
1. **Tính exposure tối đa** theo công thức ở mục 3. Cần đo: tốc độ băng chuyền v (mm/s), bề rộng FOV theo hướng chạy (mm).
   Ví dụ: FOV 300 mm / 2448 px ≈ 0.12 mm/px; v = 500 mm/s; blur ≤ 0.5 px → `t_exp ≤ 0.5 × 0.12 / 500 ≈ 120 µs`.
   Đặt `AeState=False`, `ExposureTime` cố định (đã có `set_exposure_time` trong `solution/camera/camera_manager.py`).
2. **Bù sáng**: tăng đèn hoặc dùng strobe đồng bộ qua `IOMODE_STROBE_OUTPUT` của MVSDK; giữ analog gain thấp (gain cao làm tăng nhiễu, deblur khó hơn).
3. **Tăng px/module lên ≥ 4**: ống kính tiêu cự dài hơn hoặc đặt camera gần hơn, thu FOV về đúng làn băng chuyền. Có thể dùng ROI phần cứng của sensor để tăng FPS.
4. **Bỏ H.264 khi ghi dữ liệu test**: ghi bằng `NativeRecorder` (không nén) hoặc lưu BMP/PNG theo trigger. Mọi đánh giá thuật toán sau đều phải chạy trên dữ liệu không nén.
5. Tuỳ chọn: **trigger theo cảm biến quang** khi vật vào vùng nhìn, thay vì quay liên tục.

Tiêu chí xong: gy/gx ≈ 1.0–1.2 trên ROI và ≥ 4 px/module. Riêng bước này dự kiến đưa tỉ lệ decode lên > 90% với cascade hiện tại.

### Giai đoạn 2: Deblur có định hướng trong pipeline (2–3 ngày)
Cho dữ liệu cũ và trường hợp blur còn sót lại:
1. Thêm `offline/qr/deblur.py`:
   - PSF là đường thẳng theo hướng băng chuyền (góc cố định, cấu hình được), độ dài L.
   - Wiener (FFT, ~1 ms trên ROI 80×80) và Richardson–Lucy vài vòng lặp.
   - **Ước lượng L tự động**: quét L ∈ [2..12] px, chọn L làm ảnh sau deconvolution "giống QR" nhất (histogram 2 mức rõ nhất, như Yahyanejad 2010), hoặc khớp với finder pattern 7×7 đã biết (van Gennip 2015).
   - L ổn định giữa các frame của cùng băng chuyền: cache L tốt nhất và thử nó trước.
2. Chèn bước `deblur → upscale 3–4x → zxing/WeChat` vào `_CASCADE` sau bước 1 (rẻ nhất), trước các bước WeChat CNN.
3. Thêm unsharp mask bán kính 1 (gợi ý từ zxing-cpp #966) làm một bước rẻ.

### Giai đoạn 3: Gộp nhiều frame theo vật thể (3–5 ngày)
Băng chuyền chạy đều nên mỗi QR xuất hiện ở khoảng 5–15 frame:
1. **Tracker** đơn giản (IoU, hoặc dự đoán vị trí theo vận tốc băng chuyền) gán `track_id` cho mỗi QR qua các frame.
2. **Bỏ phiếu theo thời gian**: khi một frame decode được thì gán kết quả cho cả track và dừng decode track đó (tiết kiệm CPU).
3. **Gộp ROI**: warp ROI của các frame về cùng lưới (ECC `cv2.findTransformECC` hoặc phase correlation, độ chính xác sub-pixel), lấy trung bình hoặc median → giảm nhiễu nén/cảm biến, rồi deblur và decode. Nếu căn chỉnh sub-pixel đủ tốt thì làm multi-frame super-resolution (shift-and-add) để tăng px/module.
4. **Bỏ phiếu theo module** (giống US8150163): lấy mẫu lưới 21×21 hoặc 25×25 trên mỗi frame, cộng dồn xác suất đen/trắng, tạo lại ma trận bit nhị phân sạch rồi đưa vào zxing.

### Giai đoạn 4: Mô hình học sâu (tuỳ chọn, khi các giai đoạn trên chưa đủ)
- Thử **ADNet / EG-Restormer** (có code, chuyên cho QR motion blur) và **Mosaic-SR** (SR cho barcode 2D), export sang ONNX.
- Fine-tune bằng dữ liệu tổng hợp: sinh QR đúng định dạng (12 chữ số, version thực tế) → resize về 2.5 px/module → blur đường ngang L ngẫu nhiên → nhiễu + nén H.264/JPEG. Kết hợp vài trăm ROI thật đã gán nhãn (nhãn lấy từ các frame decode được trong cùng track).
- Chỉ chạy model khi các bước rẻ thất bại, và chỉ chạy một lần cho mỗi track.

### Giai đoạn 5: Hiệu năng & tích hợp
- Cascade hiện tốn 160–240 ms/QR khi thất bại. Với tracking, mỗi track chỉ decode đến khi thành công.
- Chạy detect mỗi frame nhưng decode bất đồng bộ (đã có `DecodeWorker`). Ưu tiên frame có độ nét cao nhất (Laplacian var) trong track.
- Đồng bộ thay đổi sang `solution/qr/` (đang trùng mã với `offline/qr/`).

## 5. Thứ tự đề xuất & kỳ vọng

| Bước | Công sức | Kỳ vọng tỉ lệ đọc theo vật thể |
|---|---|---|
| 0. Bộ đánh giá | 0.5 ngày | đo baseline |
| 1. Exposure ngắn + đèn + ≥ 4 px/module + ghi không nén | 1–2 ngày | lên > 90% (yếu tố quyết định) |
| 2. Deblur PSF đường ngang | 2–3 ngày | 0/80 trên video H.264 hiện tại; chỉ thử lại trên dữ liệu không nén, blur ≤ 1–2 module |
| 3. Tracking + gộp frame | 3–5 ngày | tăng độ ổn định, giảm CPU |
| 4. DL deblur/SR | 1–2 tuần | chỉ khi không đổi được phần cứng |

## 6. Thông tin cần từ bạn
- Tốc độ băng chuyền (m/phút) và kích thước QR thật (mm/cạnh).
- Exposure, gain, FPS đang dùng khi quay các video này; video quay bằng phần mềm nào (có nén H.264 không).
- Có thể thay ống kính, khoảng cách camera, hoặc thêm đèn/strobe không.
