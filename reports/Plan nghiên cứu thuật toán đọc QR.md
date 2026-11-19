# Plan nghiên cứu thuật toán đọc QR nhỏ mờ

> **Cấu hình cũ (trước 18/11/2026).** Tài liệu này lập theo thông số đã thay thế (tem 25/36 mm, camera cao 1 m, 0,673 mm/px, băng 100 mm/s, nội dung 12#12 hoặc version 1, một camera, máy CPU). Ràng buộc hiện hành: mục "Bài toán và ràng buộc" trong `README.md`. Kỹ thuật và tài liệu tham khảo vẫn dùng được, nhưng số px/ô và mọi đề xuất đổi tem, nội dung, version/mức sửa lỗi, camera, ống kính, line-scan, đầu đọc thương mại hay vị trí dán tem không còn áp dụng.

Ngày lập: 06/11/2026. Cơ sở: báo cáo `reports/Phương pháp đọc QR nhỏ mờ.md` (nghiên cứu tài liệu), `reports/Độ khả thi thuật toán đọc QR.md` (đo thực tế), chuẩn quay `experiments/benchmark_standard.md`.

## 0. Bài toán sau khi chốt ràng buộc

| Hạng mục | Giá trị | Ghi chú |
|---|---|---|
| Tem | 36 mm phần đen, nội dung 12 số `#` 12 số; quy cách đã chốt: version 1 (21×21 ô) mức M, mã hóa tách đoạn | Không tăng được kích thước. Tem thử ở phòng thí nghiệm lẫn version 1–3, mức L–H |
| Hình học | Basler 2856 px, ống 4 mm, cao 1 m, vùng 1,6 × 0,6 m | Đo được 0,673 mm/px, **2,55 px/ô** |
| Chuyển động | Băng 100 mm/s, exposure 3 ms | Vệt mờ 0,17 ô, gần như không mờ |
| Xử lý | Chỉ CPU | Giai đoạn này đo khả năng đọc, chưa đo tốc độ |

Báo cáo nghiên cứu viết khi còn ở 2 px/ô và vệt mờ 1–2 ô. Từ đó tới nay, hai đòn bẩy vật lý đã được dùng: px/ô tăng lên 2,55 và vệt mờ giảm còn 0,17 ô. Ở mức này, **mờ chuyển động không còn là vấn đề chính**. Vấn đề còn lại là:

- Lấy mẫu sát sàn: 2,55 px/ô, dưới mức 3–4 px/ô mà MVTec khuyến nghị.
- Nhòe sang ô bên cạnh.
- Ngân sách sửa lỗi nhỏ: mức L chỉ 2 codeword theo ISO, mức M (quy cách đã chốt) 4 codeword.
- Chất lượng ở mép vùng đọc.
- Vệt chói.

Plan vì vậy ưu tiên hướng **ước lượng trực tiếp giá trị từng ô + giải mã mềm**. Khử mờ xếp sau.

**Đòn bẩy rẻ nhất còn lại là mức sửa lỗi.** Nội dung 12 số `#` 12 số mã hóa tách đoạn (số, byte, số) vừa đúng version 1 mức M ở cùng cỡ 36 mm, sửa được 4 codeword thay vì 2 của mức L. Mức H không vừa version 1. Đây là quy cách đã chốt (README.md, mục Thông số hiện trường và tem); nên quay thêm đoạn tem in đúng quy cách để đo lợi ích.

## 1. Tổng quan các giai đoạn

| Giai đoạn | Ai làm | Đầu ra | Điều kiện qua |
|---|---|---|---|
| G1. Sửa setup | Bạn | Hết vệt chói, `check_setup.py` ĐẠT ở tâm và hai mép | Mọi dòng ĐẠT |
| G2. Lấy dữ liệu | Bạn | Các đoạn quay + `labels.json` + nhật ký buổi quay | Đủ đoạn theo §2.4, không mất frame |
| G3. Bộ chấm điểm chung | Tôi, trên `main` | `experiments/bench/`, điểm mốc của pipeline hiện tại | Chấm đúng trên dữ liệu thử có đáp án |
| G4. Thử nghiệm song song | 4–5 agent, mỗi agent một worktree | Mỗi hướng một nhánh + báo cáo + điểm trên tập phát triển | Báo cáo đủ số liệu theo §4.3 |
| G5. Chấm trên tập kiểm tra, gộp | Tôi | Bảng so sánh, nhánh tích hợp vào `PassDecoder` | Theo §5 |
| G6. Tối ưu tốc độ | Sau | | |

G3 có thể làm song song với G1–G2.

## 2. Lấy dữ liệu (G1–G2)

### 2.1 Nguyên tắc chống lệch (bias)

1. **Camera và đèn cố định, chỉ di chuyển băng.** Đèn phải chiếu toàn vùng 1,6 × 0,6 m như ở hiện trường, không gắn theo băng. Nếu đèn đi theo băng, tem ở mép sẽ sáng như ở tâm và kết quả ở mép tốt hơn thực tế.
2. **Kịch bản đặt tem được tạo trước bằng máy** (`make_sequence.py`), không do người đặt tự chọn. Người đặt thường vô thức đặt tem ở chỗ "dễ đọc".
3. **Đáp án viết trước khi quay.** Khi quay chỉ ghi lại lượt nào lệch kịch bản.
4. **Tách tập phát triển / tập kiểm tra.** Mỗi vị trí quay ≥ 2 đoạn với kịch bản khác nhau. Agent chỉ thấy đoạn phát triển; đoạn kiểm tra chỉ dùng một lần ở G5.
5. **Một bộ = một setup.** Đổi nét, đèn, độ cao hay exposure thì sang bộ mới và chạy lại kiểm tra.

### 2.2 Vị trí băng trong khung hình

Băng chạy theo chiều 0,6 m của ảnh. Bề ngang 1,6 m được phủ bằng cách dời băng ngang qua nhiều vị trí `belt_x` (mm, tính từ trục camera, trái âm, phải dương).

- Chia sao cho các vị trí phủ kín từ tâm ra sát mép vùng đọc (±800 mm). Ví dụ băng rộng 300 mm: `belt_x` = 0, ±325, ±650.
- Ống kính đối xứng quanh trục, nên nếu thiếu thời gian, ưu tiên tâm, một nửa (ví dụ bên phải: +325, +650), và một vị trí mép đối diện (−650) để kiểm tính đối xứng.
- Mặt băng ở mọi vị trí phải cao đúng 1000 mm (đo hai đầu băng), và chạy song song cạnh dọc ảnh (lệch < 2°).

### 2.3 Định dạng đáp án `labels.json`

`make_sequence.py` tạo sẵn file này trong `experiments/out/runs/<tên>/`:

```json
{"clip": "x+650_a", "belt_x_mm": 650, "mode": "ngau_nhien", "seed": 123,
 "codes": ["000000585545", "..."], "note": "", "deviations": "",
 "passes": [{"i": 1, "code": "000000585545", "lane": "T", "rot": 45, "status": "ok"}, ...]}
```

- `lane`: T/G/P = trái/giữa/phải mặt băng.
- `rot`: 0/45/90°.
- `status`: `ok`, hoặc `bo` nếu lượt đó hỏng khi quay (tem rơi, dính nhau, quên đặt).
- Thứ tự `passes` là thứ tự tem đi qua camera. Bộ chấm điểm ghép mã đọc được với lượt theo thứ tự này, nên phải giữ đúng thứ tự.

### 2.4 Danh sách đoạn cần quay (một bộ)

| Loại | Mỗi vị trí | Lượt | Mục đích |
|---|---|---:|---|
| `a`: kịch bản lưới (`--mode luoi`) | 1 đoạn | 30 | Mọi tổ hợp làn × góc xuất hiện đều nhau |
| `b`: kịch bản ngẫu nhiên (`--mode ngau_nhien`) | 1 đoạn | 30 | Tập kiểm tra |
| `tinh`: băng dừng, 6–9 tem đứng yên, 10 s | 1 đoạn | | Trần đọc khi không chuyển động; làm việc với frame tĩnh nhanh hơn |

Với 5 vị trí: 10 đoạn chạy × 30 lượt = **300 lượt**, sai số tỉ lệ đọc khoảng ±3% toàn bộ và ±8% mỗi vị trí.

Dung lượng: khoảng 3,7 GB/phút. Cả bộ khoảng 40–50 GB; cần ổ trống ≥ 80 GB và một ổ sao lưu.

Đoạn phụ, tùy chọn, quay sau khi xong bộ chính:

| Tên | Thay đổi | Câu hỏi |
|---|---|---|
| `ecH` | Tem in lại mức H, 36 mm | Mức sửa lỗi giúp bao nhiêu |
| `sat` | Từng cặp tem cách nhau 30–50 mm | Tem sát nhau có tách lượt đúng |
| `kho` | Tem nhăn, hơi cong, bẩn nhẹ | Độ bền khi tem không lý tưởng |

Đoạn phụ không dùng để chọn phương pháp, chỉ để mô tả giới hạn.

### 2.5 Phân tập

| Tập | Đoạn | Ai dùng |
|---|---|---|
| Phát triển | Mọi đoạn `a` + `tinh` | Agent ở G4 |
| Kiểm tra | Mọi đoạn `b` | Chỉ tôi, một lần ở G5 |

Đường dẫn đoạn kiểm tra không đưa vào brief của agent. Dữ liệu nằm ngoài repo (`experiments/out/` không commit), bộ chấm điểm đọc qua biến môi trường `QR_BENCH_DATA`.

### 2.6 Hướng dẫn chi tiết từng bước

Xem §7 cuối file.

## 3. Bộ chấm điểm chung (G3, tôi làm trên `main`)

```
experiments/bench/
  manifest.json      → danh sách đoạn phát triển: tên, belt_x, số frame, fps
  data.py            → đọc frames.bin + index.json theo frame, không nạp hết vào RAM
  reader_api.py      → giao diện Reader chung cho mọi phương pháp
  score.py           → ghép mã đọc được với lượt, tính chỉ số
  run.py             → python -m experiments.bench.run <reader> [--clips ...] → JSON + bảng
  readers/baseline.py → PassReader hiện tại (multi_frame=True), mốc so sánh
  readers/soft_proto.py → bộ đọc mềm prototype hiện có (đã đo 3/4 tem tĩnh)
```

**Giao diện `Reader`:** `process(frame_bgr, seq, t) -> list[Read]` và `finish() -> list[Read]`, với `Read = (text, seq, center_xy, confirmed)`.

- Mỗi phương pháp tự quyết định cách gom frame, nhưng mã chỉ được tính khi đã **xác nhận** (2 lần đọc giống nhau, như sản phẩm).
- Chạy offline, đưa đủ mọi frame. Chưa mô phỏng việc bỏ frame do xử lý chậm, vì giai đoạn này chỉ đo khả năng đọc.

**Chỉ số `score.py`** (cho từng đoạn và gộp):

| Chỉ số | Định nghĩa |
|---|---|
| Tỉ lệ đọc theo lượt | Lượt `ok` có mã xác nhận đúng ÷ số lượt `ok` |
| Đọc sai | Số mã xác nhận không thuộc `codes`, hoặc khác mã của lượt tương ứng. **Mục tiêu 0** |
| Tách theo nhóm | `belt_x`, `lane`, `rot`, và vị trí tem tính bằng mm so với trục camera |
| Số frame đến lần đọc đầu | Chỉ báo sớm về tốc độ: đọc sớm thì còn nhiều frame để xác nhận |
| Đọc thêm so với mốc | Lượt phương pháp đọc được mà baseline không đọc được, và ngược lại |

**Ghép mã với lượt:** theo thứ tự thời gian và theo mã. Hai lượt liền nhau luôn khác mã vì kịch bản đảm bảo điều này.

**Kiểm chứng bộ chấm điểm:** chạy trên đoạn có đáp án biết trước (đoạn `tinh` và một đoạn lab cũ), và có unit test cho phần ghép lượt.

## 4. Thử nghiệm song song (G4)

### 4.1 Các hướng (mỗi hướng một agent, một worktree)

| Agent | Hướng | Cơ sở trong báo cáo nghiên cứu | Ưu tiên |
|---|---|---|---|
| **A** | Bộ đọc mềm nhiều frame: khớp lưới 21×21 một lần mỗi lượt, bám theo vận tốc; ngưỡng cục bộ + bù nhòe; cộng log-likelihood từng ô qua các frame; giải RS có erasure (ISO trước, ngân sách tối đa sau); kiểm định độ khớp ô chức năng | Bằng sáng chế Cognex US11151346B2, RS 2E+S ≤ 7, prototype đọc 3/4 tem tĩnh | Cao nhất |
| **B** | Tái tạo nhiều frame trên lưới ô với tiên nghiệm nhị phân: đăng ký dưới pixel giữa các frame, ước lượng một giá trị mỗi ô, ước lượng PSF từ finder/timing | Kato và cộng sự, ICDAR 2011 (+15,7 điểm so với SR thông thường) | Cao |
| **C** | Định vị ở mép và khi YOLO bỏ sót: bù tối góc (flat-field), tinh chỉnh 4 góc theo finder, so recall của detector theo `belt_x` | Rủi ro mép trong báo cáo khả thi | Trung bình (phụ thuộc kết quả mốc ở mép) |
| **D** | Engine thương mại làm mốc trên: Dynamsoft DBR (`BarcodeScaleModes` ngưỡng ~4, đích 6–8; `DeblurModes` gồm DM_DEEP_ANALYSIS, DM_NEURAL_NETWORK), HALCON nếu có license đánh giá | Benchmark nhà cung cấp: nhóm mờ 67,7% so với 46,2% WeChat | Trung bình; **cần bạn cấp key dùng thử** |
| **E** | Mosaic-SR huấn luyện lại trên frame nét của dự án (hạ mẫu), làm bước tiền xử lý cho zxing | ICIP 2025, 1–4 ms/crop CPU, có mã nguồn | Thấp, chỉ chạy nếu A/B chưa đạt |

**Không mở hướng** khử mờ sâu (NAFNet, Restormer): cần GPU và mờ không còn là vấn đề chính ở exposure 3 ms.

**Quét vệt mờ mịn** (Zeng 2026) chỉ cần nếu ở hiện trường phải tăng exposure. Để làm phụ trong agent A nếu số liệu cho thấy cần.

Chạy đồng thời tối đa 4 agent (A, B, C, D), vì máy chỉ có CPU và mỗi agent chạy đánh giá riêng. Mỗi agent đặt `cv2.setNumThreads(2)` và `torch.set_num_threads(2)`.

### 4.2 Quy tắc cho mọi agent

- Làm trong worktree riêng, nhánh `exp/<chữ cái>-<tên>`, tách từ `main` sau G3.
- Chỉ sửa trong `experiments/methods/<tên>/`. **Không sửa** `experiments/bench/`, `qr/`, `camera/` hay giao diện.
- Phương pháp cần dùng lại code trong `qr/` thì import, không chép.
- Chỉ chạy trên tập phát triển trong `manifest.json`. Không tìm, không đọc đoạn khác trong `QR_BENCH_DATA`.
- Mọi kết quả phải sinh lại được bằng một lệnh `python -m experiments.bench.run ...` ghi trong báo cáo.
- Được dùng thư viện pip mới nếu chạy CPU trên Windows. Không thêm `basicsr`/`realesrgan`.
- Không commit dữ liệu, ảnh lớn hay model > 20 MB.

### 4.3 Đầu ra mỗi agent

1. Code phương pháp + lệnh chạy.
2. `experiments/methods/<tên>/REPORT.md`, gồm:
   - Kết quả `score.py` trên tập phát triển, so với mốc.
   - Bảng lượt đọc thêm và lượt bị mất so với mốc, kèm ảnh crop của 5 trường hợp tiêu biểu.
   - Số lần đọc sai.
   - Tham số đã chỉnh và số lần thử. Nhiều lần thử trên cùng tập thì dễ học thuộc tập.
   - Thời gian xử lý tham khảo (không phải tiêu chí).
   - Giới hạn và ý tưởng tiếp theo.
3. `results_dev.json` do `run.py` sinh.

### 4.4 Điều phối

- Tôi giao việc bằng brief riêng cho từng agent, chạy ở chế độ worktree, rồi nhận báo cáo.
- Câu hỏi giữa chừng đi qua tôi.
- Hai agent có ý tưởng dùng chung (ví dụ A cần phần khớp lưới của B) thì tôi quyết định ghép ở G5, không để agent sửa nhánh của nhau.

## 5. Chấm trên tập kiểm tra và gộp (G5)

1. Chạy mốc và mọi phương pháp trên **tập kiểm tra** (các đoạn `b`), một lần, không chỉnh tham số sau đó.
2. Điều kiện để một phương pháp được đưa vào sản phẩm:
   - Tỉ lệ đọc theo lượt cao hơn mốc **≥ 5 điểm** trên tập kiểm tra, hoặc ≥ 10 điểm ở mép.
   - **0 lần đọc sai** trên toàn bộ dữ liệu.
   - Không làm mất lượt mà mốc đã đọc được, hoặc mất ít hơn 1%.
3. Gộp những phương pháp đạt vào một nhánh tích hợp:
   - Cascade hiện tại giữ nguyên làm bước đầu.
   - Phương pháp mới chạy sau, cho lượt chưa đọc được.
   - Chèn vào `PassDecoder`.
   - Chạy lại toàn bộ test hiện có.
4. Chấm lại nhánh tích hợp trên tập kiểm tra, rồi viết báo cáo so sánh cuối.
5. Mốc quyết định:
   - **Mốc đã ≥ 95% ở mọi vị trí:** dừng nghiên cứu thuật toán, chuyển sang tốc độ.
   - **Dynamsoft hơn hẳn mọi phương pháp tự làm:** cân nhắc mua license, có số liệu đi kèm.
   - **Đoạn `ecH` cho lợi ích lớn hơn mọi thuật toán:** đề xuất đổi mức in tem.

## 6. Rủi ro

| Rủi ro | Cách giảm |
|---|---|
| Học thuộc tập phát triển | Tập kiểm tra tách riêng; báo cáo số lần thử |
| Băng lab khác băng hiện trường (nền, rung) | Ghi chú trong báo cáo; xác nhận lần cuối ở hiện trường |
| Đọc sai khi dùng ngân sách sửa lỗi tối đa | 2 lần đọc giống nhau, kiểm ô chức năng, chấm đọc sai trên mọi đoạn |
| Máy CPU quá tải khi 4 agent chạy | Giới hạn luồng, chấp nhận chạy chậm; không đo tốc độ ở G4 |
| Phương pháp tốt nhưng quá chậm | G6 xử lý; cần giữ số frame đến lần đọc đầu trong báo cáo |

## 7. Hướng dẫn lấy dữ liệu từng bước

Mọi lệnh chạy trong venv của dự án (mở terminal ở thư mục `QRDetector`, chạy `.venv\Scripts\activate` trước). Tắt app demo và pylon Viewer trước khi chạy script nào mở camera.

### Bước 1: Chuẩn bị (làm một lần)

1. **Danh sách tem:** tạo `experiments/codes.txt`, mỗi dòng một mã tem đang có. Cần ≥ 20 mã khác nhau, mỗi mã một tem vật lý. Có thể chuẩn bị 2 tem cùng mã để đặt nhanh hơn.
2. **Sửa vệt chói:**
   - Đèn chiếu xiên khoảng 45°, không đặt gần trục camera.
   - Thêm tấm khuếch tán. Nếu vẫn chói, dùng phân cực chéo: một tấm trước đèn, một tấm trước ống kính, xoay tấm ở ống kính tới khi vệt chói tắt.
   - Đèn chiếu toàn vùng 1,6 × 0,6 m và **cố định theo camera**.
3. **Kiểm tra ổ đĩa:** trống ≥ 80 GB, chuẩn bị ổ sao lưu.
4. **Đo tốc độ băng:** dán 2 vạch cách nhau 1 m, bấm giờ, chỉnh cho đúng 10 s ± 0,3 s.

### Bước 2: Kiểm setup cho từng vị trí băng

Với mỗi vị trí:

1. Đặt băng, đo độ cao mặt băng hai đầu = 1000 mm, căn băng chạy song song cạnh ảnh.
2. Đặt một tem đứng yên giữa mặt băng, chạy:
   ```bash
   python experiments/check_setup.py --save experiments/out/check
   ```
3. Mọi dòng phải ĐẠT. Dòng cuối in vị trí tem so với trục camera (mm): đây là `belt_x` của vị trí này.
   - Ở lần đầu, đặt tem lệch hẳn về một phía để kiểm dấu trái/phải khớp với thực tế. Nếu ngược thì đổi dấu khi ghi.
4. Nếu ở vị trí mép, nền trắng < 170: được tăng `analog_gain` tối đa 18 dB. Nhưng như vậy là đổi setup, nên phải ghi `gain` vào ghi chú và áp dụng cho **mọi vị trí** của bộ. Đừng chỉnh riêng từng vị trí.
5. Ghi nhật ký: `belt_x`, kết quả 6 dòng ĐẠT, giờ.

### Bước 3: Tạo kịch bản cho đoạn quay

Đặt tên đoạn theo vị trí và loại: `x+650_a`, `x+650_b`, `x0_a`… (đoạn tĩnh: `x+650_tinh`).

```bash
python experiments/make_sequence.py x+650_a --codes experiments/codes.txt --belt-x 650 --passes 30 --mode luoi
```

```bash
python experiments/make_sequence.py x+650_b --codes experiments/codes.txt --belt-x 650 --passes 30 --mode ngau_nhien
```

In bảng ra giấy, hoặc mở trên điện thoại. Người đặt tem làm đúng theo:
- **Làn** (T/G/P trên mặt băng).
- **Góc** xoay theo chiều kim đồng hồ.
- **Thứ tự** từ trên xuống.

### Bước 4: Quay

1. Băng đang chạy, chưa có tem trong vùng đọc. Chạy:
   ```bash
   python experiments/record_basler.py x+650_a 60 --config experiments/benchmark_basler.json --fps 30 --note "belt_x +650, đèn ..., gain 12"
   ```
2. Đặt tem theo bảng, cách nhau ≥ 100 mm (khoảng 1 giây ở 100 mm/s), đặt tem trước khi nó vào vùng đọc. Đánh dấu ô "đã đặt" từng lượt.
3. 30 lượt cần khoảng 40–50 s. Nếu không đủ thời gian, tăng số giây (ví dụ 90). Tem cuối phải ra khỏi vùng đọc trước khi script dừng.
4. Kiểm tra dòng cuối script: **"bỏ do ghi chậm 0"** và **"mất giữa chừng 0 seq"**. Nếu khác 0, quay lại với tên mới (ví dụ `x+650_a2`), hoặc giảm `--fps 20`.

**Đoạn tĩnh:** dừng băng, đặt 6–9 tem đứng yên trên mặt băng (đủ làn và góc), rồi chạy:
```bash
python experiments/make_sequence.py x+650_tinh --codes experiments/codes.txt --belt-x 650 --passes 9 --mode luoi
```
Đặt tem theo bảng, sau đó quay 10 s:
```bash
python experiments/record_basler.py x+650_tinh 10 --config experiments/benchmark_basler.json --fps 30 --note "tĩnh"
```

### Bước 5: Ghi sai lệch ngay sau mỗi đoạn

Mở `experiments/out/runs/<tên>/labels.json`:
- Lượt nào lệch kịch bản (tem rơi, không kịp đặt, hai tem dính nhau, đặt sai góc): đổi `"status": "ok"` thành `"bo"`.
- Ghi lý do vào `"deviations"`.
- Đặt sai làn hoặc góc nhưng vẫn qua vùng đọc: sửa `lane`/`rot` theo thực tế, giữ `ok`.
- Không xóa lượt, không đổi thứ tự.

### Bước 6: Sao lưu và báo lại

1. Chép cả thư mục `experiments/out/runs/` sang ổ sao lưu.
2. Gửi cho tôi:
   - Danh sách đoạn đã quay.
   - Nhật ký bước 2.
   - Ảnh chụp setup đèn.

   Tôi sẽ chạy bộ chấm điểm với mốc, kiểm tra đáp án khớp với video (số lượt detect được so với số lượt `ok`), rồi khởi động G4.

### Thứ tự gợi ý trong một buổi

1. Vị trí tâm: `tinh`, `a`, `b`.
2. Các vị trí còn lại: mỗi vị trí `tinh`, `a`, `b`.
3. Cuối buổi, nếu còn thời gian: đoạn phụ.

Không chỉnh nét hay đèn giữa các vị trí. Chạy `check_setup.py` mỗi khi dời băng.
