# Video chuẩn để so sánh thuật toán đọc QR

Mục đích: một bộ dữ liệu quay một lần, đúng hình học hiện trường, để mọi giải pháp (pipeline hiện tại, bộ đọc mềm, quét vệt mờ mịn, SDK thương mại…) được chấm trên cùng các frame.

Cấu hình máy: `experiments/benchmark_basler.json`. Kiểm tra: `experiments/check_setup.py`. Quay: `experiments/record_basler.py`.

## 1. Thông số chuẩn

### Cơ khí và quang học (chỉnh tay)

| Thông số | Giá trị chuẩn | Ghi chú |
|---|---|---|
| Camera | Basler a2A2840-48umBAS (2856×2848, pixel 2,74 µm) | |
| Ống kính | 4 mm, cho cảm biến 2/3", độ phân giải ≥ 5 MP | Ống 8 mm không phủ được 1,6 m ở độ cao 1 m |
| Khẩu độ | f/4 | Ở f/4, độ sâu trường ảnh rất rộng; khép hơn f/5,6 bắt đầu mất nét do nhiễu xạ |
| Lấy nét | Nét nhất trên mặt băng tại tâm, rồi khóa vít | Kiểm bằng tem đứng yên ở tâm và ở mép |
| Độ cao | 1000 mm từ mặt kính đến mặt băng | |
| Hướng camera | Vuông góc mặt băng; chiều ngang ảnh theo cạnh 1,6 m | Dải đọc (band) cắt theo chiều 0,6 m |
| Vùng đọc | 1600 × 600 mm, camera ở giữa | |

### Băng chuyền, đèn, tem

| Thông số | Giá trị chuẩn | Ghi chú |
|---|---|---|
| Tốc độ băng | 100 mm/s | Đo lại bằng vạch dấu: 1 m trong 10 s |
| Đèn | Nguồn DC, không dùng dimmer PWM; ánh sáng khuếch tán, chiếu xiên ~45° để tránh phản xạ gương vào camera | Tắt hoặc giữ cố định đèn phòng (đèn 50 Hz làm sáng tối theo frame khi exposure ngắn) |
| Đồng đều sáng | Tem ở mép vùng đọc sáng ≥ 60% so với tem ở tâm | Ống 4 mm tối dần ra góc |
| Tem | 36 × 36 mm phần đen, nội dung 12 số `#` 12 số, **version 1 mức M, mã hóa tách đoạn** (xem `README.md`, mục Thông số hiện trường và tem) | Mỗi tem một nội dung khác nhau, ghi lại danh sách. Tem in mặc định bị đẩy lên version 2–4: ghi rõ loại tem nếu dùng |
| Số tem | ≥ 20 nội dung khác nhau, tổng ≥ 100 lượt đi qua | Đủ để sai số tỉ lệ đọc khoảng ±5% |
| Khoảng cách tem | ≥ 100 mm theo chiều chạy | Tránh hai tem dính thành một khung detect |
| Vị trí | Trải đều bề ngang: giữa, 1/4, sát mép (cách mép vùng đọc ~50 mm) | Mép là nơi ống góc rộng kém nhất |
| Góc xoay | 0°, 45°, 90° (mỗi loại ~1/3) | |

### Camera (đã có trong `benchmark_basler.json`, script tự đặt)

| Thông số | Giá trị chuẩn | Lý do |
|---|---|---|
| PixelFormat | Mono8 | |
| ExposureAuto / GainAuto | Off | Thông số cố định để các lần quay so sánh được |
| ExposureTime | **3,0 ms** | Ở 100 mm/s vệt mờ 0,3 mm ≈ 0,44 px ≈ 0,18 ô: gần như không mờ |
| Gain | 12 dB (chỉnh theo §2) | Giữ ≤ 18 dB; cần hơn thì tăng đèn, đừng tăng gain |
| Vùng đọc (band) | x = 256, rộng 2336; y = 984, cao 880 | ≈ 1602 × 604 mm ở 0,686 mm/px |
| Tốc độ khung | **30 fps cố định** (`--fps 30`) | 3,3 mm ≈ 4,9 px dịch chuyển mỗi frame; tem nằm trong vùng ~170 frame nếu chạy theo chiều 0,6 m |
| Gamma, Black level | Mặc định (Gamma 1, Black level 0) | Không bật xử lý ảnh trong camera |

### Kết quả mong đợi theo tính toán (kiểm bằng §2)

| Đại lượng | Tính toán | Ngưỡng chấp nhận |
|---|---:|---|
| mm/px ở mặt băng | 0,686 | |
| Cạnh QR | 52,5 px | |
| px/ô | 2,5 | 2,3–2,8 |
| Vệt mờ | 0,18 ô | ≤ 0,25 ô |
| Nền trắng tem (p95) | | 170–225 |
| Ô đen (p5) | | ≤ 70 |
| Cháy sáng trong tem | | < 0,5% |
| Dung lượng ghi | 2,06 MB/frame, 62 MB/s, 3,7 GB/phút | |

## 2. Kiểm tra trước khi quay

1. Tắt app demo và pylon Viewer (camera chỉ mở được bởi một chương trình).
2. Đặt 1 tem đứng yên ở tâm vùng đọc, chạy:

   ```bash
   python experiments/check_setup.py --save experiments/out/check
   ```

3. Chỉnh cho tới khi mọi dòng ĐẠT:
   - Nền trắng < 170: tăng đèn, hoặc tăng `analog_gain` trong `benchmark_basler.json` (tối đa 18).
   - Nền trắng > 225 hoặc cháy sáng: giảm gain hoặc đèn. Không đổi exposure.
   - px/ô ngoài 2,3–2,8: kiểm độ cao và tiêu cự ống kính.
   - Không đọc được: chỉnh nét lại.
4. Đặt tem ở mép trái, mép phải, chạy lại; mép phải đọc được hoặc ít nhất có tương phản ≥ 110.
5. Ghi kết quả cả ba lần chạy vào ghi chú của buổi quay.

## 3. Quay

Mỗi đoạn tối đa khoảng 60 s (≈ 3,7 GB). Quay đoạn chuẩn trước, đặt tên theo ngày:

```bash
python experiments/record_basler.py chuan_20261106_a 60 --config experiments/benchmark_basler.json --fps 30 --note "100 mm/s, 4 mm f/4, cao 1 m, đèn ..."
```

Script in ra fps thật của camera, số frame bỏ do ghi đĩa chậm và số frame mất giữa chừng. **Hai số sau phải bằng 0**; nếu không, giảm `--fps` (ví dụ 20) và quay lại.

Đáp án `labels.json` (thứ tự mã, làn, góc từng lượt) được tạo **trước khi quay** bằng `experiments/make_sequence.py`; sau đoạn quay chỉ đánh dấu lượt lệch kịch bản. Định dạng và quy trình đầy đủ: `reports/Plan nghiên cứu thuật toán đọc QR.md` §2.3 và §7. Mẫu số của tỉ lệ đọc là số lượt `"status": "ok"`; mã đọc ra không có trong `codes` hoặc khác mã của lượt là đọc sai.

## 4. Đoạn phụ (tùy chọn, cùng setup, chỉ đổi một thông số)

| Tên | Thay đổi | Để trả lời |
|---|---|---|
| `exp1` | exposure 1,0 ms, gain bù (+9,5 dB) hoặc tăng đèn | Exposure ngắn hơn có còn lợi khi nhiễu tăng |
| `exp8` | exposure 8,0 ms, gain −8,5 dB | Mức hiện tại của app (vệt mờ ≈ 0,47 ô) |
| `ecH` | Tem in lại mức H, cùng 36 mm | Lợi ích của mức sửa lỗi (nếu in được) |
| `tinh` | Băng dừng, 20 tem đứng yên, 10 s | Trần đọc khi không có chuyển động |

## 5. Lưu ý

- Đoạn ghi nằm trong `experiments/out/runs/` (không commit). Sao lưu ra ổ khác vì đây là thước đo cho mọi thử nghiệm sau.
- Không chỉnh nét, đèn, độ cao giữa các đoạn của cùng một bộ. Đổi bất kỳ thứ nào thì đặt tên bộ mới và chạy lại §2.
- Phát lại: `python experiments/replay_run.py <tên> <số lượt thật>`.
