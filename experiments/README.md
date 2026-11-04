# Thử nghiệm tăng tỉ lệ đọc QR

Mã thử nghiệm độc lập, không sửa `qr/`, `ui/`, `demo_ui/`. Cấu hình tốt nhất **chưa được tích hợp vào app** và **chưa được kiểm chứng trên băng chuyền thật**.

## Kết luận

Cấu hình nên dùng: `H0+H1v1+H2+H3+H4+H6k3+H7k05+SW`.

| Đo trên ảnh camera thật + chuyển động, độ tối, nhiễu mô phỏng (264 lượt, hạt giống mới) | Bản hiện tại | Cấu hình đề xuất |
|---|---:|---:|
| Lượt đọc được | 88 (33,3%) | 202 (76,5%) |
| Lượt đọc sai | 0 | 0 |
| Thời gian TB mỗi lần xử lý, đo tuần tự (gồm 150 ms detect giả định khi có YOLO) | ~250 ms | ~145 ms |

Về tỉ lệ đọc, cấu hình này ngang `H4+H6k3+H7k05+SW` (201/264). Nó được chọn vì không đọc sai (bản kia đọc sai 1 lần) và ít tách lượt hơn (28 so với 35).

## Thành phần của cấu hình

| Tên | Nội dung |
|---|---|
| H0 | Sửa tracker: bỏ cổng ghép quá rộng (`qr/tracker.py:112`, tới 3400 px) khiến lượt sau bị nhập vào lượt trước, mã thứ hai không được gửi |
| H1v1 | Chỉ nhận mã đúng định dạng 12 chữ số, 1 phiếu là đủ. Định dạng này lấy từ tem hiện có, cần xác nhận |
| H2 | Bỏ QR chạm mép ảnh hoặc có kích thước bất thường |
| H3 | Thêm các binarizer của zxing |
| H4 | Giữa hai lần YOLO, đoán vị trí ROI theo vận tốc lượt thay vì detect lại (YOLO mỗi 400 ms) |
| H6k3 | Căn và xếp chồng ROI của các lần đọc hỏng, từ 3 ảnh trở lên, tối đa 8 ảnh |
| H7k05 | Khử vệt mờ Wiener theo hướng chuyển động trên ảnh đã xếp chồng, k=0,05 |
| SW | WeChat chỉ chạy trên ảnh xếp chồng, không chạy trên từng frame |

## Ba loại bằng chứng

**1. Bán thực — đáng tin nhất.** 11 QR cắt từ ảnh BMP camera không nén (tem, in ấn, quang học thật), trượt trên băng ảo; vệt mờ, độ tối, nhiễu là mô phỏng. Mỗi điều kiện 33 lượt, mỗi ảnh 3 lần.

Hạt giống 2 (kiểm tra lại, số trong bảng dưới):

| Điều kiện | Bản hiện tại | Đề xuất |
|---|---:|---:|
| A: 10 cm/s, mờ 1 px, sáng | 31 | 32 |
| B: 10 cm/s, mờ 3 px, sáng | 17 | 30 |
| C: 10 cm/s, mờ 3 px, sáng vừa, nhiễu | 0 | 24 |
| D: 10 cm/s, mờ 1 px, tối | 28 | 32 |
| E: 20 cm/s, mờ 3 px, tối | 4 | 26 |
| F: 30 cm/s, mờ 3 px, rất tối | 0 | 14 |
| G: 20 cm/s, mờ 1 px, rất tối | 8 | 28 |
| H: 20 cm/s, mờ 6 px, sáng | 0 | 16 |

Hạt giống 1 (dò tìm, 15 cấu hình, /264): `H4+H6k3+H7k05+SW` 198, `H4+H6k3+H7k05+H9+SW` 190, `H6k3+H7k05+SW` 188, `H6k3+H7k05+H9+SW` 176, `H6k3+H7k05` 153, H6k3 125, H9 110, H7k05 101, base 92, H4 91, H5e3 85. Cấu hình có H0+H1v1+H2+H3 không chạy ở hạt giống này.

**2. Mô phỏng hoàn toàn — chỉ để hỗ trợ.** Hạt giống 2, 3 và các điều kiện chịu lỗi (/640): `H6k3+H7k05+H9+SW` 632, `H4+H6k3+H7k05+SW` 624, `H0+H1v1+H2+H3+H4+H6k3+H7k05+H9+SW` 623, `H6k3+H7k05+SW` 619, base 322. Mô phỏng này lạc quan quá mức: nó đọc gần hết ở vệt mờ 6 px, còn ảnh camera thì không. Không dùng để so tuyệt đối. Cấu hình đề xuất (không có H9) chưa chạy trên bộ này.

**3. Video cũ — không phân biệt được.** base 4/55, các tổ hợp 5/55, không đọc sai. Tem di chuyển bằng tay và video nén nặng (8–30 KB/frame); các AVI 20/10 không có frame nào đọc được dù thử không giới hạn thời gian.

## Từng hướng riêng lẻ

- **Hiệu quả nhất:** H6 (xếp chồng), H4 và SW, nhưng SW và H4 chủ yếu có tác dụng sau khi đã có H6: chúng giải phóng thời gian để gom được nhiều ảnh hơn.
- **H7 (Wiener):** riêng lẻ chỉ có tác dụng ở mờ 3 px khi ảnh sáng (B: 17 → 25, tổng 92 → 101); mạnh hơn trên ảnh xếp chồng (B: 16 → 29, H6k3 so với H6k3+H7k05). Ở mờ 6 px, quét ảnh tĩnh chỉ đọc được 0–1/11; trong lượt đầy đủ, cấu hình đề xuất đọc được 16/33 (H).
- **H9 (đọc lưới module V1):** riêng lẻ khá trên mô phỏng, nhưng trong tổ hợp bán thực không thêm được gì và làm tăng tách lượt. Không nên dùng lúc này.
- **H8 (tinh chỉnh 4 góc):** không có tác dụng. Không đưa vào bán thực.
- **H5 (WeChat trên frame nét nhất):** giảm tải nhưng giảm tỉ lệ đọc so với giữ nguyên (85 so với 92).
- **H0, H1, H2, H3:** riêng lẻ tăng rất ít; giá trị chính là giảm đọc sai và tách lượt.

## Hệ quả về vận hành

Ở 20 cm/s, cấu hình đề xuất đọc 28/33 khi phơi sáng ngắn dù rất tối (G), 26/33 khi vừa (E), chỉ 16/33 khi phơi sáng dài dù sáng (H). Nếu kết quả này đúng trên thật, nên ưu tiên giảm vệt mờ hơn giữ ảnh sáng. Giả định: nhiễu mô phỏng 3 mức xám; nhiễu thật ở gain cao có thể lớn hơn.

## Giới hạn

- Chỉ có 11 QR, ít mẫu, tất cả cùng một đợt chụp. Lượt lặp cùng một ảnh không độc lập với nhau.
- Chuyển động, vệt mờ và nhiễu là mô phỏng. Chưa biết mức sáng/nhiễu thật ở cấu hình hiện tại (exposure 12,9 ms, gain 40) vì không có ảnh không nén gần đây.
- Thời gian detect giả định cố định (150 ms dải, 200 ms toàn khung); đồng hồ ảo được đo từ thời gian thật của cascade. Các đợt chạy song song bị tranh CPU nên chậm hơn thực tế: base ở E là 4/33 khi song song, 8/33 khi tuần tự; đề xuất là 26/33 và 28/33.
- Bản thử nghiệm dùng `LabReader`, chưa phải code sản phẩm. Khi tích hợp cần giữ cả H1v1 và kiểm tra lại với mọi định dạng mã thực tế.

## Việc cần làm để xác nhận

Quay AVI không nén bằng tính năng quay của app, ở cấu hình và tốc độ băng thật, rồi phát lại qua bộ thử nghiệm này với cả hai bản. Đây là phép đo quyết định trước khi đưa vào sản phẩm.

## Lỗi phát hiện thêm

`qr/detector.py:94` có thể ném `MemoryError` khi `qrdet.crop_qr` gặp mask suy biến (cố cấp phát vài PiB), đã gặp 2 lần trên ảnh nhiễu. App không sập vì `DecodeWorker._process` bắt lỗi, nhưng mất cả frame đó kể cả QR khác trong frame. Chưa sửa; nên bắt lỗi theo từng detection hoặc tự tính crop.

## Chạy lại

Dữ liệu ở `../QRDetector-research/data`, không cần camera. Kết quả ghi vào `experiments/out/` (không commit). Đặt `LAB_PY` trỏ tới Python của `.venv`:

```bash
bash experiments/run_semi.sh
```

```bash
bash experiments/run_semi_holdout.sh
```

```bash
bash experiments/run_timing.sh
```

```bash
python experiments/summarize.py "experiments/out/semi2_*.jsonl"
```

Mô phỏng hoàn toàn: `run_singles.sh`, `run_combos.sh`, `run_holdout.sh`. Quét ảnh tĩnh: `sweep_semi.py`. Video cũ: `summarize_real.py`, `inspect_real.py`.
