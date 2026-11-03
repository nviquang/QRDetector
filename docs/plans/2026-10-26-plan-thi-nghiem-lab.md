# Plan: làm tốt decode QR trong phòng thí nghiệm (băng chuyền 1 m)

Ngày: 2026-10-26 · Phạm vi: **chỉ phase phòng thí nghiệm**. Bài toán thực tế (3.2 m, 2 camera × 1.6 m) để sau, khi lab đạt nghiệm thu.

Cố định: camera MindVision 5MP 2448×2048, chỉnh qua MVSDK (`solution/camera/camera_manager.py`). QR 25×25 mm, nội dung 12 chữ số (`000000585545`, `…546`, `…623`) → QR version 1 (21×21 ô). Băng chạy theo chiều ngang khung hình, tốc độ 10 / 20 / 30 cm/s.

---

## 1. Hiện trạng đo được trên dữ liệu có sẵn

Pipeline hiện tại: `offline/qr/improved_pipeline.py`, qrdet imgsz 1280 + cascade zxing/WeChat.

| Dữ liệu | Định dạng | FPS | QR (px) | Detect | Decode | Ghi chú |
|---|---|---|---|---|---|---|
| `images/` 14 ảnh BMP, QR **đứng yên** | không nén | – | 55–62 | 14/14 ảnh | **12/14 QR chính** | QR phụ cầm tay/nghiêng/lóa: 1/11 |
| `video/` 5 mp4 (09/10) | H.264 | 15.9 | 73–117 | 97% frame | 0–53% frame (TB ~32%) | camera gần hơn, ít mờ (gy/gx ≈ 1.0–1.1) |
| `videos/` 5 avi (20/10, băng chạy) | H.264 | **7.5–14.8** | ~59 | 80% frame | **0.6% frame** | mờ chuyển động mạnh (gy/gx 1.6–2.0) |
| `solution/recordings/` | không nén | – | – | 100% | 0% | cháy sáng (trung vị 254), nhãn nghiêng |

Ảnh toàn cảnh (`images/`): khung hình rất tối (độ sáng TB ~50/255), có đốm phản xạ đèn trên sàn và trên nhãn bóng.

**Kết luận:**

1. **Với setup lab hiện tại, độ phân giải đủ.** QR ~58 px ≈ **2.7 px/ô**. Khi QR đứng yên và nét, ảnh BMP decode được 12/14 lần dù chưa có thuật toán gì đặc biệt.
2. **Thất bại khi băng chạy là do chất lượng ảnh**, không do độ phân giải:
   - exposure dài → mờ ngang 5–8 px,
   - nén H.264,
   - FPS thấp,
   - lóa và cháy sáng.

   Mô phỏng trước đó cho cùng kết luận: ở 2.8 px/ô, mờ 3 px vẫn đọc 100%, mờ 5 px còn 62%, mờ 8 px còn 0%.
3. **Đang đo sai chỉ số.** Tỉ lệ theo frame không phải mục tiêu. Mục tiêu là **mỗi lượt QR đi qua phải đọc được ít nhất 1 lần**. Ở lab, mỗi QR nằm trong khung khoảng 3 s ở 30 cm/s, tức ~40 frame, nên chỉ cần vài frame tốt là đủ.

## 2. Mục tiêu nghiệm thu lab

Đo trên **video thô không nén**, QR đặt trên băng (không cầm tay), mỗi tốc độ ≥ 50 lượt.

| Chỉ số | 10 cm/s | 20 cm/s | 30 cm/s |
|---|---|---|---|
| Tỉ lệ lượt đọc được | ≥ 99% | ≥ 99% | ≥ 98% |
| Đọc sai (sai nội dung) | 0 | 0 | 0 |
| Báo trùng (1 lượt báo > 1 lần) | 0 | 0 | 0 |
| Trễ từ lúc QR rời khung đến khi có kết quả | < 0.5 s | < 0.5 s | < 0.5 s |
| FPS camera thực tế | ≥ 20 | ≥ 20 | ≥ 20 |

Thêm một bài **stress**: nhãn nghiêng ±30° trên mặt băng, 2–3 nhãn cùng lúc trong khung. Mục tiêu ≥ 95%.

---

## 3. Các bước

### Bước 0 — Công cụ đo và bộ dữ liệu chuẩn (Claude, ~2 ngày)

- `offline/tests/eval_videos.py`: chạy pipeline trên video hoặc thư mục ảnh và xuất JSON:
  - detect/decode theo frame,
  - **decode theo lượt** (gom bằng tracker đơn giản theo trục x),
  - kích thước QR, độ nét (Laplacian), gy/gx, độ sáng p5/p95, thời gian xử lý.
- So với ground truth: file `labels.json` cho mỗi video, gồm danh sách mã và số lượt.
- `offline/tests/sim_qr.py`: mô phỏng (đã có bản nháp) để thử nhanh thuật toán mà không cần quay.
- Baseline: chạy trên toàn bộ `images/`, `video/`, `videos/` và lưu số liệu làm mốc.

### Bước 1 — Chế độ camera "Băng chuyền" trong `solution/` (Claude, ~2 ngày)

Thay đổi trong `camera_manager.py`, giữ nguyên public API:

- **Tắt AE.** Hiện code luôn gọi `set_ae_state(True)` (dòng ~295), nên exposure tự kéo dài, gây mờ và tụt FPS.
- **Exposure cố định theo tốc độ**, công thức `t ≤ mờ_cho_phép × mm/px ÷ v`. Ở lab ~0.43 mm/px, mờ ≤ 1 px:

  | Tốc độ | Exposure |
  |---|---|
  | 10 cm/s | ≤ 4.3 ms |
  | 20 cm/s | ≤ 2.1 ms |
  | 30 cm/s | ≤ 1.4 ms |

- **Analog gain** chỉnh để bù sáng, nhưng ưu tiên tăng đèn trước.
- **`CameraSetFrameSpeed` mức cao.**
- **Sensor ROI tùy chọn:** chỉ đọc dải ngang chứa băng, ví dụ 2448×640. Tăng FPS và giảm tải xử lý.
- **Ghi video không nén:** chuỗi BMP/PNG hoặc AVI raw kèm timestamp mỗi frame, không dùng H.264.
- **Hiển thị trên UI:**
  - FPS thực,
  - exposure/gain hiện tại,
  - % pixel cháy sáng trong vùng băng,
  - độ nét của QR mới nhất.
- **Tìm nguyên nhân FPS chỉ 7.5–14.8.** Đo lần lượt:
  - exposure (AE),
  - băng thông USB/GigE,
  - mã hóa H.264 trên CPU,
  - decode chạy cùng luồng.

  Ghi rõ nguyên nhân vào plan.

### Bước 2 — Ánh sáng và bố trí (Bạn, ~1 ngày, song song bước 1)

- **Đèn khuếch tán chiếu đều vùng băng**, ví dụ LED bar có tấm tán hoặc 2 đèn chéo 45° hai bên. Tránh đèn rọi thẳng vì nhãn bóng gây lóa (đã thấy trong ảnh). Có thể thêm phim phân cực nếu vẫn lóa.
- **Mục tiêu độ sáng** khi exposure ≤ 1.4 ms:
  - nền trắng của nhãn 170–220,
  - ô đen < 60,
  - không pixel nào ≥ 250 trên nhãn.
- **Lấy nét ở khẩu độ hơi khép** (f/4–f/5.6) để có độ sâu trường ảnh.
- **Đo mm/px thật:** đặt thước 30 cm lên băng, chụp 1 ảnh BMP. Con số này dùng cho mọi phép tính exposure.
- Giữ camera **cố định tuyệt đối** sau khi chỉnh, có đánh dấu vị trí.

### Bước 3 — Quay bộ dữ liệu lab chuẩn (Bạn, ~1 ngày)

Dùng chế độ camera mới, ghi không nén. Mỗi lần quay ghi kèm tốc độ, exposure, gain, ánh sáng.

| Bộ | Nội dung | Số lượng |
|---|---|---|
| S (static) | nhãn đứng yên ở 5 vị trí ngang băng × 4 góc xoay | 20 ảnh |
| A | 1 nhãn thẳng, 10 / 20 / 30 cm/s | 20 lượt mỗi tốc độ |
| B | nhãn nghiêng ±15–30° | 10 lượt mỗi tốc độ |
| C | 2–3 nhãn cùng lúc, cách nhau 5–10 cm | 10 lượt mỗi tốc độ |
| D (sweep) | 30 cm/s, exposure 0.5 / 1 / 1.5 / 2 / 3 ms | 5 lượt mỗi mức |

Bộ D cho đường cong "exposure ↔ tỉ lệ đọc" thật, thay cho mô phỏng. Một nửa dữ liệu dùng để phát triển, nửa còn lại giữ để nghiệm thu.

### Bước 4 — Cải tiến decode từng frame (Claude, ~3–4 ngày)

Đo trên bộ A/B sau mỗi thay đổi, chỉ giữ thay đổi nào tăng tỉ lệ đọc.

1. **Chấm điểm chất lượng ROI:** độ nét, tương phản, cháy sáng. Chỉ đưa vào cascade các frame tốt nhất của mỗi lượt để tiết kiệm CPU.
2. **Tinh chỉnh 4 góc QR:** tìm 3 finder pattern và dùng hình học ô để có quad chính xác hơn bbox của qrdet.
3. **Đọc lưới trực tiếp (`grid_sampler.py`):**
   - warp về lưới 21×21,
   - lấy mẫu tâm mỗi ô,
   - ngưỡng thích nghi cục bộ,
   - dựng QR sạch rồi đưa zxing (`is_pure`).

   Đây là bước quan trọng nhất cho 2–3 px/ô.
4. **Khử mờ ngang với PSF đã biết** (độ dài = v × t ÷ mm/px), cộng unsharp nhẹ. Chỉ áp dụng khi mờ > 1 px.
5. **Sắp lại cascade** theo thống kê bước nào thường thành công, cắt các bước không bao giờ thành công để giảm thời gian.

### Bước 5 — Theo dõi theo lượt và gộp nhiều frame (Claude, ~3 ngày)

- **`tracker.py`:** gán ID cho mỗi QR theo vị trí x/y và tốc độ băng. Mỗi lượt:
  - gom các frame,
  - thử decode theo thứ tự chất lượng,
  - dừng khi đọc được,
  - báo **đúng 1 sự kiện** cho mỗi lượt.
- **Đầu ra mới:** `process_frame(frame, t) -> list[TrackEvent]`, mỗi `TrackEvent` gồm mã, thời điểm, vị trí, số frame đã thử.
- **Gộp nhiều frame** khi không frame đơn nào đọc được:
  - căn chỉnh các ROI (ECC hoặc từ quad),
  - trung bình hoặc bầu chọn từng ô trên lưới 21×21.

  Bước này sẽ là chìa khóa khi chuyển sang thực tế (1.5–1.8 px/ô), nên làm và kiểm chứng ngay ở lab.
- **Chống đọc sai:**
  - kiểm tra định dạng mã (12 chữ số),
  - nếu frame đầu tiên đọc được có độ tin thấp, chờ ít nhất 2 frame cho cùng kết quả.

### Bước 6 — Tích hợp, hiệu năng, nghiệm thu (Claude + Bạn, ~2 ngày)

- **Đồng bộ code** sang `solution/qr/`. Tuân thủ `solution/CLAUDE.md`: không basicsr/realesrgan, import torch/qr trước PyQt5.
- **Hiệu năng:**
  - detect trên ảnh thu nhỏ hoặc chỉ trên dải băng,
  - decode trong worker riêng,
  - không bỏ frame của QR đang theo dõi.

  Hiện `DecodeWorker.submit` bỏ frame khi đang bận, phải sửa.
- **Chạy nghiệm thu** trên nửa dữ liệu giữ riêng và chạy live 3 tốc độ. Ghi kết quả vào plan.

### Bước 7 — Cầu nối sang thực nghiệm (sau khi đạt bước 6)

Nâng camera lên cao để khung hình phủ **1.6 m** (~0.67–0.8 mm/px, 1.5–1.8 px/ô) và chạy lại bộ A với đúng thuật toán đã đạt ở lab. Kết quả này quyết định bài toán thực tế cần thêm gì (gộp nhiều frame, đổi ống kính, QR lớn hơn…), và mở plan thực nghiệm.

---

## 4. Lịch dự kiến (~2.5 tuần)

| Tuần | Claude | Bạn |
|---|---|---|
| 1 | Bước 0, Bước 1 | Bước 2 (đèn, lấy nét, đo mm/px) → test chế độ camera mới |
| 2 | Bước 4, bắt đầu Bước 5 | Bước 3: quay bộ S/A/B/C/D không nén |
| 3 (nửa đầu) | Bước 5, Bước 6 | chạy live nghiệm thu |

## 5. Rủi ro và cách xử lý

| Rủi ro | Dấu hiệu | Xử lý |
|---|---|---|
| Không đủ sáng ở exposure ≤ 1.4 ms | nền nhãn < 120 | thêm đèn; tăng gain ≤ 6 dB; ở 30 cm/s chấp nhận mờ 2 px (2.8 ms) |
| Nhãn bóng gây lóa | vệt ≥ 250 trên nhãn | đèn chéo/khuếch tán, phim phân cực |
| FPS vẫn thấp do băng thông | FPS < 20 dù exposure ngắn | sensor ROI dải băng, bỏ H.264 lúc chạy |
| CPU không kịp | hàng đợi decode tăng | lọc frame theo chất lượng, detect trên dải băng |
| mm/px thật khác ước tính | thước đo | cập nhật công thức exposure trong UI |

## 6. Tiến độ

### Bước 0 — xong (2026-10-26)

| File | Dùng để |
|---|---|
| `offline/tests/eval_videos.py` | đo detect/decode theo frame **và theo lượt** (tracker), so với `labels.json`, xuất JSON, lưu ROI `_ok/_fail` |
| `offline/qr/tracker.py` | `PassTracker`: gom detection thành lượt, chọn mã đa số, đánh dấu lượt có mã mâu thuẫn |
| `offline/tests/sim_qr.py` | mô phỏng tỉ lệ decode theo px/ô × vệt mờ × nén, dùng đúng cascade của pipeline |
| `offline/tools/conveyor_calc.py` | tính px/ô, exposure tối đa, số frame/QR (công thức chung `solution/camera/conveyor.py`) |
| `offline/tests/test_tracker.py` | unit test tracker + chỉ số mờ |

```bash
python offline/tests/eval_videos.py "videos/*.avi" --labels labels.json --out report.json
python offline/tools/conveyor_calc.py --mm-per-px 0.43 --fps 15 --exposure-ms 20
python offline/tests/sim_qr.py --ppm 1.8 2.8 --motion 0 1 3 5
```

**Baseline (pipeline hiện tại, step 1, 2026-10-26).** Chạy trên mọi frame; mã hợp lệ là 3 mã `…585545/546/623`.

| Nguồn | Frame | Detect | Decode frame | Lượt đọc / lượt tracker | QR px | gy/gx | ms/det |
|---|---|---|---|---|---|---|---|
| `images/` (tĩnh) | 14 | 100% | 86% | – | 60 | 1.08 | 141 |
| `video/` 5 mp4 (09/10) | 1033 | 94–100% | 5–56% | 6/12 | 73–115 | 0.91–0.99 | 178–454 |
| `videos/` 5 avi (20/10, băng chạy) | 1978 | 32–93% | **0–1%** | **3/59** | 56–97 | **1.41–2.05** | 189–485 |

- **0 đọc sai** trên toàn bộ dữ liệu: cascade hiện tại không trả mã rác.
- Ở `videos/`, cả 5 file chỉ đọc được **4 frame** (2 ở `…154152847`, 1 ở `…154459957`, 1 khác). Các track dài 150–180 frame (QR nằm trong khung ~10 s) vẫn không đọc được lần nào. gy/gx 1.4–2.0 xác nhận nguyên nhân chính là mờ chuyển động.
- **Tracker tách nhiều lượt ngắn** (2–15 frame) do detect chập chờn hoặc detect nhầm. Vì vậy số "lượt tracker" lớn hơn số lượt thật, và **phải ghi `passes` trong labels.json** khi quay bộ dữ liệu mới.
- **Chi phí:** ROI thất bại mất ~1 s qua cả cascade (tới WeChat CNN). Toàn bộ baseline chạy ~70 phút, nên Bước 4 cần lọc ROI theo chất lượng trước khi decode.

### Bước 1 — xong phần code, CHƯA kiểm chứng trên camera thật

- `CameraManager.apply_conveyor_mode()`: tắt AE, đặt exposure theo công thức, chọn frame speed cao nhất, tùy chọn chỉ đọc dải sensor (`set_sensor_band`).
- UI, trong panel "Kết quả QR":
  - chọn tốc độ băng, mm/px, mờ tối đa, dải y/cao;
  - nút "Áp dụng chế độ băng chuyền";
  - nhãn hiển thị exposure, vệt mờ ước tính, độ sáng TB, % cháy sáng.
- Quay AVI không nén đã có sẵn (`camera/recording.py`). Video H.264 trong `videos/` không phải từ app này.
- Test: `python -m unittest tests.test_conveyor_mode` (fake SDK). Toàn bộ 59 test camera/UI pass.

**Bạn kiểm tra trên camera thật — tìm nguyên nhân FPS thấp:**

1. Mở camera, ghi lại "Capture fps" khi AE bật (mặc định). Kỳ vọng ~13–15.
2. Bấm "Áp dụng chế độ băng chuyền" (30 cm/s), ghi lại Capture fps.
   - Tăng lên ~20+ → nguyên nhân là AE/exposure dài.
   - Không đổi → chuyển sang bước 3.
3. Bật "Chỉ đọc dải" (ví dụ y = 640, cao = 768), áp dụng lại.
   - FPS tăng mạnh → nguyên nhân là băng thông (USB/GigE) hoặc xử lý toàn khung.
   - SDK báo lỗi ImageResolution → gửi tôi file log `solution/logs`.
4. Tắt "Bật decode" và so FPS. Nếu decode làm tụt FPS capture → tranh chấp CPU/GIL, xử lý ở Bước 6.
5. Ghi lại port camera (USB3/GigE) và kết quả 4 bước trên vào plan này.

**Kết quả Phần A, app hãng (2026-10-26):**

- Camera **MV-500GC-GE**: GigE, màu, Bayer BG 8-bit, cắm cổng LAN.
- Frame rate High, Frame freq 0 (không giới hạn).

| Bước | Cài đặt | FPS |
|---|---|---|
| A2 | AE bật | 12–14 |
| A3/A4 | AE tắt, 1.4 ms, gain 40×, Frame rate High | 17–20 |
| A5 | ROI 2448×768 | ~50 |
| A6 | thước trên băng | 0.23 mm/px (**cần xác minh**, xem dưới) |

**Kết luận nguyên nhân FPS thấp:**

1. **AE kéo exposure dài**, làm mất ~5 fps.
2. **Băng thông GigE 1 Gbps** (~110 MB/s): toàn khung 5 MB/frame thì tối đa ~22 fps. ROI 768 dòng (1.9 MB/frame) lên được 50 fps.

→ Dùng chế độ băng chuyền **kèm dải ROI**.

**Mâu thuẫn cần xác minh:** 0.23 mm/px nghĩa là QR 25 mm phải rộng ~109 px, nhưng trên ảnh QR chỉ ~58 px (≈ 13 mm). Cần kiểm tra lại một trong hai: kích thước thật của ô QR in trên nhãn (cạnh ngoài 3 ô vuông định vị), hoặc phép đo thước.

## 7. Bạn cần xác nhận / cung cấp

1. **mm/px thật** (ảnh BMP có thước 30 cm trên băng). Ước tính hiện tại ~0.43 mm/px, suy từ QR 25 mm ≈ 58 px.
2. **Đèn có sẵn:** loại và số lượng, có tấm tán hay không.
3. **Cách nối camera** (USB3 hay GigE) và cấu hình máy tính đang chạy thử.
