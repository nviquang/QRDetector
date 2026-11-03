# Plan cải thiện decode QR trên băng chuyền

Ngày: 2026-10-26 · Thay thế bản nháp trước. Nghiên cứu gốc: [2026-10-24-qr-decode-bang-chuyen.md](2026-10-24-qr-decode-bang-chuyen.md)

## 0. Tóm tắt

- Pipeline hiện tại **detect tốt (80–100%) nhưng decode gần 0%**. Nguyên nhân nằm ở ảnh đầu vào, không phải ở bộ decoder:
  - motion blur 4–8 px do auto exposure để phơi sáng lâu;
  - nén H.264;
  - cháy sáng;
  - chỉ ~2.8 px cho mỗi ô QR.
- Mô phỏng cho thấy ngưỡng thực tế: cần **≥ 2.4 px/ô** và **motion blur ≤ 1 ô**. Ở **≤ 1.8 px/ô** thì hỏng.
- **Một camera 5MP không phủ được 1.6 m** (chỉ đạt 1.5–1.8 px/ô). Đề xuất dùng **2 camera, mỗi camera phủ ~0.85 m → 3.4 px/ô**.
- Thứ tự: sửa cấu hình camera và đèn trước → thu dữ liệu chuẩn → sửa thuật toán (theo dõi từng vật, chọn frame nét, lấy mẫu lưới ô, gộp nhiều frame).

## 1. Điều kiện bài toán (đã xác nhận)

| Mục | Giá trị |
|---|---|
| Hướng chạy băng chuyền | theo **chiều ngang của ảnh** (trục 2448 px ở cách lắp hiện tại) |
| Tốc độ | 10 / 20 / 30 cm/s |
| Bề ngang băng chuyền | thử nghiệm **1.0 m**, thực tế **1.6 m**. Phải phủ toàn bộ bề ngang, QR có thể nằm ở bất kỳ đâu |
| Chiều dọc theo băng chuyền | chỉ cần một dải |
| QR | 25 × 25 mm, 12 chữ số → version 1, 21 × 21 ô, mỗi ô 1.19 mm |
| Camera | MindVision 2448 × 2048, nhà sản xuất ghi 24 fps (thực tế quay 13–14.7 fps) |
| Đèn | có thể lắp thêm |

## 2. Bằng chứng đo được

### 2.1 Pipeline hiện tại trên dữ liệu thật

| Dữ liệu | Frame | Detect | Decode | Ghi chú |
|---|---|---|---|---|
| `videos/*.avi` (H.264, băng chuyền chạy) | 398 | 80% | **0.6%** (2 frame) | motion blur ngang (gradient dọc/ngang 1.6–2.0), ~50 KB/frame |
| `solution/recordings/*` (không nén, QR đứng yên) | 112 | 100% | **0%** | không blur (gy/gx 1.03) nhưng **cháy sáng** (trung vị 254) + nhãn nghiêng mạnh |
| Wiener deblur trên 80 ROI lỗi (H.264) | 80 | | **0%** | deblur không cứu được dữ liệu nén |

Nguyên nhân gốc ở code: `solution/camera/camera_manager.py:295` luôn bật **auto exposure** khi mở camera. Khi thiếu sáng, AE kéo exposure lên vài chục ms → mờ, và FPS bị giới hạn ở ~13–14.

### 2.2 Mô phỏng: tỉ lệ decode theo px/ô
QR v1 ngẫu nhiên, góc xoay ngẫu nhiên, tương phản 40–220, nhiễu, decoder hiện tại (zxing + WeChat), 40 mẫu mỗi ô:

| px/ô | mờ quang σ1.2 | motion 3 px | motion 5 px | motion 8 px | JPEG30 + motion 3 px |
|---|---|---|---|---|---|
| 1.5 | 0% | 0% | 0% | 0% | 0% |
| 1.8 | 0% | 65% | 0% | 0% | 12% |
| 2.4 | 95% | 100% | 27% | 0% | 100% |
| 2.8 | 100% | 100% | 62% | 0% | 100% |
| 3.6 | 100% | 100% | 100% | 15% | 100% |

Mô phỏng lạc quan hơn thực tế, vì bản in hoàn hảo và nhãn phẳng. Vì vậy chọn **mục tiêu thiết kế ≥ 3 px/ô, motion blur ≤ 1 px**.

## 3. Hình học & phần cứng

### 3.1 Phương án phủ bề ngang 1.6 m

| Phương án | mm/px | px/ô | Đánh giá |
|---|---|---|---|
| 1 camera, 2048 px ngang băng chuyền (lắp như hiện nay) | 0.78 | 1.5 | ❌ |
| 1 camera xoay 90°, 2448 px ngang băng chuyền | 0.65 | 1.8 | ❌ |
| 1 camera + QR to hơn 50 mm | 0.65 | 3.6 | ✅ nếu được đổi nhãn |
| **2 camera hiện tại, xoay 90°, mỗi camera ~0.85 m (chồng 5 cm)** | **0.35** | **3.4** | ✅ **đề xuất**: cùng model, cùng SDK |
| 1 camera 20MP (5472 px) | 0.29 | 4.1 | ✅ chi phí cao hơn |
| Camera line-scan 8K + encoder | 0.20 | 6.1 | ✅ chuẩn công nghiệp, nhưng tích hợp nhiều hơn (repo đã có SDK `Python/BasicLineScan`) |

Vùng chồng giữa 2 camera phải ≥ đường chéo QR (35 mm) + lề → **5 cm**, để QR luôn nằm trọn trong ít nhất 1 camera.

### 3.2 Giàn thử nghiệm 1 m
Lắp camera **xoay 90°**: trục 2448 px nằm ngang băng chuyền, băng chuyền chạy dọc theo trục 2048 px. Phủ **~0.85 m** để có đúng hình học của 1 camera trong phương án 2 camera (3.4 px/ô). Kết quả đo trên giàn thử áp dụng thẳng cho thực tế. Mép băng chuyền 1 m bị khuất khoảng 7.5 cm mỗi bên; chấp nhận khi thử, hoặc đặt QR trong vùng nhìn thấy.

### 3.3 Exposure và đèn (0.35 mm/px)

| Tốc độ | blur ≤ 0.5 px | blur ≤ 1 px | blur khi đặt **1.0 ms** |
|---|---|---|---|
| 10 cm/s | 1.73 ms | 3.47 ms | 0.29 px |
| 20 cm/s | 0.87 ms | 1.73 ms | 0.58 px |
| 30 cm/s | 0.58 ms | 1.16 ms | 0.86 px |

- Đặt **exposure cố định 1.0 ms, tắt AE**. Gain chỉ tăng tối đa 2–4× (gain cao làm tăng nhiễu).
- Đèn: LED chiếu đều, khuếch tán, rộng hơn vùng nhìn. Nên dùng đèn chớp đồng bộ qua `IOMODE_STROBE_OUTPUT`. Tránh chói phản xạ trên nhãn bóng.
- Chỉnh sáng sao cho nền trắng của nhãn ≈ 180–220, **không chạm 255**.
- Lấy nét ở khoảng cách làm việc. Khép khẩu (f/4–f/5.6) để vật có độ cao khác nhau vẫn nét.

### 3.4 Dải ROI dọc băng chuyền & FPS
- Chỉ cần một dải: dùng ROI cảm biến **2448 × ~768 px** (dải ~0.27 m dọc băng chuyền). Ở 30 cm/s và 24 fps, vật đi ~36 px mỗi frame → mỗi QR xuất hiện trong **~19 frame**. Ít điểm ảnh hơn cũng giúp FPS tăng và detect nhanh hơn ~2.7 lần.
- Tìm nguyên nhân 13 fps:
  - exposure do AE đặt (đổi sang 1 ms);
  - `CameraSetFrameSpeed` mức cao;
  - cổng USB 3.0;
  - định dạng ra (MONO8 nếu sensor mono);
  - tốc độ ghi đĩa khi quay không nén.

## 4. Kế hoạch thực hiện

Ký hiệu: **[Tôi]** viết code · **[Bạn]** làm tại hiện trường.

### Giai đoạn 0: Công cụ đo (1 ngày) [Tôi]
- `offline/tests/eval_videos.py`: chạy pipeline trên video/thư mục ảnh, xuất CSV:
  - theo frame: detect, decode, bước nào thành công, độ nét, gy/gx, độ sáng, thời gian;
  - theo vật: tỉ lệ vật đọc được, độ trễ.
- `offline/tests/sim_qr.py`: chuyển mô phỏng mục 2.2 thành test, tham số hoá px/ô, blur, nén. Dùng để kiểm tra từng cải tiến thuật toán mà không cần camera.
- `offline/tools/conveyor_calc.py`: nhập tốc độ, mm/px, kích thước QR → trả về exposure tối đa, px/ô, số frame mỗi QR.
- **Xong khi:** có baseline trên dữ liệu cũ và trên mô phỏng.

### Giai đoạn 1: Chế độ camera "Băng chuyền" (1–2 ngày) [Tôi]
Sửa trong `solution/camera/camera_manager.py` và `solution/ui/main_window.py`:
1. Bỏ `set_ae_state(True)` cứng trong `open()`. Thêm preset "Băng chuyền": AE tắt, exposure theo bảng 3.3, gain giới hạn.
2. UI chọn tốc độ 10/20/30 cm/s và mm/px → tự đặt exposure, hiển thị blur dự kiến.
3. Đặt `CameraSetFrameSpeed` mức cao. Tuỳ chọn ROI cảm biến (dải 2448 × 768).
4. Status bar hiển thị FPS thực, exposure thực, % điểm ảnh cháy sáng (cảnh báo khi > 1%).
5. Khi ghi video không nén, lưu metadata JSON kèm theo (exposure, gain, tốc độ, mm/px) để bộ đánh giá đọc.
- **Xong khi:** trên camera thật FPS ≥ 20 (hoặc ≥ 24 khi bật ROI), exposure = giá trị đặt.

### Giai đoạn 2: Lắp đặt & thu dữ liệu chuẩn (1–2 ngày) [Bạn], tôi viết kịch bản
1. Xoay camera và chỉnh độ cao để phủ ~0.85 m bề ngang (mục 3.2). Lắp đèn, lấy nét.
2. **Kiểm tra tĩnh:** đặt 5 QR rải khắp bề ngang, băng chuyền dừng, chụp không nén. Phải decode được 100%. Nếu không đạt thì vấn đề nằm ở quang học/đèn/bản in, chưa sang bước tiếp.
3. **Quay động:** mỗi tốc độ 10/20/30 cm/s, khoảng 30 vật, QR ở nhiều vị trí và góc xoay, ghi **không nén** ở chế độ Băng chuyền.
4. Ghi lại danh sách mã thật theo thứ tự để chấm điểm (hoặc tôi lấy nhãn từ các frame đã decode được).

### Giai đoạn 3: Cải tiến decode từng frame (2–3 ngày) [Tôi], trong `offline/qr/`
1. **Lọc chất lượng ROI** (`quality.py`): độ nét, gy/gx, % cháy sáng, cạnh QR (px), bị cắt ở mép. ROI kém không chạy các bước đắt.
2. **Tinh chỉnh 4 góc** (`corrector.py`): `padded_quad_xy` của qrdet bị nới rộng. Tìm 3 ô định vị (tỉ lệ 1:1:3:1:1) trong ROI → 4 góc chính xác.
3. **Lấy mẫu lưới ô** (`grid_sampler.py`, mới):
   - warp chính xác về lưới 21 × 21, lấy mẫu tâm mỗi ô;
   - ngưỡng thích nghi → ma trận bit → vẽ lại QR sạch (10 px/ô + quiet zone) → zxing `is_pure=True`.
   - Đây là bước quan trọng nhất cho mức 2.5–3.5 px/ô, vì binarizer của zxing yếu ở mức này.
4. **Làm nét rẻ:** unsharp mask bán kính 1 trước zxing; thử thêm binarizer `GlobalHistogram`.
5. **Deblur với PSF đã biết:** độ dài blur `L = v × t_exp ÷ mm/px` lấy từ cấu hình camera. Chỉ chạy khi L > 0.7 px.
6. Sắp lại cascade: rẻ → đắt. WeChat CNN + SR chuyển xuống cuối.
- **Xong khi:** mô phỏng 2.4 px/ô + motion 5 px tăng từ 27% lên ≥ 80%; `test_small_qr.py` vẫn ≥ 12/14; mỗi frame < 30 ms trên ROI tốt.

### Giai đoạn 4: Theo dõi từng vật & kết quả một lần (2–3 ngày) [Tôi]
1. `tracker.py`: gán `track_id` theo IoU + dự đoán dịch chuyển dọc băng chuyền (tốc độ × mm/px). Trạng thái `pending → decoded → gone`.
2. Đã decode thì **dừng decode track đó**. Chỉ chạy cascade đầy đủ trên **top-3 frame nét nhất** của track.
3. Bỏ phiếu theo text trong track để chống đọc sai. Phát **1 sự kiện mỗi vật** (text, thời điểm, vị trí ngang). Track kết thúc mà chưa đọc được thì báo "không đọc được".
4. `ImprovePipeline.process_frame(frame, t) -> list[TrackEvent]`, giữ nguyên `scan()` / `decode()`.
5. **Hai camera:** loại trùng giữa 2 camera theo (text, thời gian ±0.5 s) vì QR trong vùng chồng có thể được cả hai đọc.
- **Xong khi:** trên video Giai đoạn 2, mỗi vật báo đúng 1 lần, không trùng.

### Giai đoạn 5: Gộp nhiều frame (2–4 ngày, chỉ làm nếu tỉ lệ < 95%) [Tôi]
1. Lấy N = 5–10 ROI tốt nhất của track, warp về cùng lưới bằng 4 góc đã tinh chỉnh, căn sub-pixel bằng `cv2.findTransformECC`.
2. **Bỏ phiếu theo ô:** cộng dồn mức xám tâm từng ô qua N frame → ma trận bit → zxing `is_pure`.
3. Trung bình ảnh đã căn → đưa vào cascade. Nếu vẫn thiếu: shift-and-add super-resolution ×2.

### Giai đoạn 6: Hiệu năng & tích hợp (2 ngày) [Tôi]
- Đo detect qrdet `imgsz=1280` trên dải 2448 × 768 × 2 camera. Nếu không kịp: detect mỗi 2 frame, frame giữa dùng vị trí tracker dự đoán.
- Decode chạy ở luồng riêng theo hàng đợi track (không bỏ frame một cách mù quáng như `DecodeWorker` hiện tại).
- Đồng bộ `offline/qr/` → `solution/qr/`. Cập nhật test và `solution/CLAUDE.md`.

## 5. Tiêu chí nghiệm thu

| Chỉ số | Mục tiêu |
|---|---|
| Tỉ lệ vật đọc được ở 10 / 20 / 30 cm/s | ≥ 99% / ≥ 98% / ≥ 95% |
| Đọc sai (text khác mã thật) | 0 |
| Báo trùng một vật | 0 |
| Độ trễ từ khi QR vào khung hình đến khi có kết quả | < 0.5 s |
| FPS camera trong chế độ Băng chuyền | ≥ 20 |

## 6. Lịch dự kiến

| Tuần | Tôi | Bạn |
|---|---|---|
| 1 | Giai đoạn 0 + 1 | Lắp đèn, xoay camera, lấy nét |
| 2 | Giai đoạn 3 (trên mô phỏng + dữ liệu mới) | Giai đoạn 2: kiểm tra tĩnh, quay động |
| 3 | Giai đoạn 4, đánh giá trên dữ liệu thật | Chạy thử, báo lỗi |
| 4 | Giai đoạn 5 (nếu cần) + 6 | Quyết định phần cứng cho 1.6 m |

## 7. Quyết định còn mở (không chặn việc bắt đầu)
1. **Phần cứng cho 1.6 m:** 2 camera (đề xuất), QR 50 mm, camera 20MP, hay line-scan. Giàn thử 0.85 m mô phỏng đúng phương án 2 camera, nên có thể quyết định sau tuần 2.
2. Cấu hình máy tính chạy thực tế (CPU/GPU) để chốt ngân sách thời gian cho detect.
3. Nhãn có thể bị nghiêng/cong không (như trong `solution/recordings`), và khoảng cách tối thiểu giữa 2 vật.
