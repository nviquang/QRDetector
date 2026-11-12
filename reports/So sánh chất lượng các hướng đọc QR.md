# So sánh chất lượng các hướng đọc QR trong worktree

Ngày đo: 10/11/2026. Máy đo: AMD Ryzen 5 5500U (6 lõi, 12 luồng), không dùng GPU cho bộ giải. Dữ liệu: 3 đoạn quay `gan`, `xa`, `cheo`. Xem cách chấm trong `reports/Kết quả thử nghiệm thuật toán đọc QR.md`.

## Kết luận

| Tiêu chí | Tốt nhất | Ghi chú |
|---|---|---|
| Khả năng đọc tổng | **C** (96,3%) | Ghép B rồi C đạt 98,6% |
| Ổn định giữa hai tập dữ liệu | **C** (chênh 0,3 điểm) | A chênh 5,3 điểm, dấu hiệu khớp theo dữ liệu đã thấy |
| Tem cong, nghiêng trên ảnh thật (`xa_04`) | **A** (30/30), **B** (25/30) | C chỉ 4/30, chỉ có một lượt khó này để đánh giá |
| Ảnh tối, nhiễu | **B** và **A** (khoảng 95%) | C 86,9% |
| Tốc độ lượt khó | **B** (p95 12,9 s) | C p95 18,9 s, A 16,5 s |
| Độ đơn giản | **C** trong ba hướng mạnh | 683 dòng, giải mã bằng zxing/WeChat có sẵn |
| Không đáng tích hợp | **D** | Chỉ +1,4 điểm, thêm JVM |

**Đề xuất: đưa B rồi C (B trước, C sau) vào sản phẩm** nếu ảnh thật ở điều kiện khó xác nhận lợi ích. B cứu được tem cong, C cứu được các trường hợp B bỏ sót, nên tổng hợp đạt 98,6% trên tập kiểm tra. Nếu chỉ chọn một: chọn **C** khi tem phẳng, chọn **B** khi tem cong hoặc nghiêng thường gặp ở hiện trường.

**Giới hạn lớn nhất:** trên ảnh thật không suy giảm, cả mốc và mọi hướng đều đọc 100%. Phần chênh lệch đến từ các điều kiện giả lập và một lượt khó thật. Chưa hướng nào được chạy trên camera thật.

## 1. Chất lượng đọc

Tập kiểm tra giữ riêng, 37 lượt, 1110 lần chấm (5 điều kiện × k = 1, 3, 5 × 2 seed). Đã bỏ lượt `gan_17` vì gán nhãn nhầm (hai tem đè nhau), nên số hơi khác báo cáo trước.

| Hướng | Tập phát triển | **Tập kiểm tra** | Chênh | Lần hỏng | Lượt từng hỏng (/37) | Báo sai |
|---|---:|---:|---:|---:|---:|---:|
| Mốc (`PassDecoder`) | 79,2 | **78,6** | 0,6 | 237 | 28 | 0 |
| D `engines` | 80,8 | **80,0** | 0,8 | 222 | 28 | 0 |
| A `soft_reader` | 98,5 | **93,2** | 5,3 | 75 | 12 | 0 |
| B `grid_sr` | 96,7 | **95,6** | 1,1 | 49 | 18 | 0 |
| C `preproc_sweep` | 96,6 | **96,3** | 0,3 | 41 | 11 | 0 |
| Ghép B rồi C | 99,2 | **98,6** | 0,6 | 15 | 9 | 0 |

Không hướng nào làm mất lần đọc nào mà mốc đọc được.

### Theo điều kiện (tập kiểm tra, %)

| Điều kiện | Loại | Mốc | D | A | B | C | B rồi C |
|---|---|---:|---:|---:|---:|---:|---:|
| `goc` | Ảnh thật | 100 | 100 | 100 | 100 | 100 | 100 |
| `nho80` | Giả lập, khoảng 2,05 px/ô | 97,7 | 98,6 | 99,1 | 98,6 | 99,5 | 99,5 |
| `nho65` | Giả lập, khoảng 1,65 px/ô | 81,1 | 82,4 | 92,8 | 92,8 | 99,5 | 99,5 |
| `mo` | Giả lập, vệt mờ 1,6 ô | 44,1 | 45,0 | 79,3 | 91,9 | 95,5 | 99,1 |
| `nhieu` | Giả lập, tối + nhiễu | 70,3 | 73,9 | 95,0 | 94,6 | 86,9 | 95,0 |

### Theo đoạn quay (tập kiểm tra, %)

| Đoạn | Mốc | D | A | B | C | B rồi C |
|---|---:|---:|---:|---:|---:|---:|
| `gan` | 93,9 | 93,9 | 100 | 99,1 | 99,7 | 100 |
| `cheo` | 86,2 | 87,7 | 96,7 | 97,4 | 99,7 | 99,7 |
| `xa` | 58,2 | 60,5 | 84,1 | 90,8 | 90,0 | 96,4 |

### Theo loại tem (tập kiểm tra, %)

Cùng cỡ 36 mm: V1 khoảng 2,57 px/ô, V2 khoảng 2,16 px/ô, V3 khoảng 1,86 px/ô.

| Loại tem | Mốc | D | A | B | C | B rồi C |
|---|---:|---:|---:|---:|---:|---:|
| V1-L | 85,8 | 88,2 | 95,8 | 97,3 | 95,8 | 99,4 |
| V1-M | 93,3 | 94,4 | 100 | 98,9 | 100 | 100 |
| V2-M | 76,2 | 77,1 | 98,6 | 97,1 | 97,6 | 98,1 |
| V2-Q | 88,3 | 88,3 | 100 | 99,2 | 100 | 100 |
| V2-H | 91,1 | 92,2 | 93,3 | 100 | 100 | 100 |
| V3-H | 58,5 | 59,6 | 80,7 | 88,1 | 91,9 | 96,7 |

V3-H khó nhất ở mọi hướng vì ô nhỏ nhất, dù sửa lỗi mạnh nhất. Với 36 mm, tem càng ít ô càng dễ đọc.

### Lượt khó trên ảnh thật: `xa_04`

Tem nghiêng hoặc cong ở vị trí xa, thuộc tập phát triển. Số lần đọc đúng trên 30 lần chấm:

| Mốc | D | C | B | A |
|---:|---:|---:|---:|---:|
| 2 | 2 | 4 | 25 | 30 |

## 2. Tốc độ

Đo riêng trên tập kiểm tra: 152 lần chấm, k = 5, 4 điều kiện, mỗi hướng một tiến trình, một luồng. Các hướng chạy cùng lúc (5 tiến trình trên 12 luồng). Máy hiện trường cần đo lại.

**Thời gian giải một lượt (giây):**

| Hướng | Lượt mốc đọc được, p50 / p95 | **Lượt mốc không đọc được**, p50 / p95 / lâu nhất | Đọc thêm (trên 30 lượt mốc hỏng) |
|---|---:|---:|---:|
| Mốc | 0,04 / 1,7 | 1,6 / 2,6 / 2,9 | |
| D | 0,04 / 1,9 | 1,9 / 2,8 / 3,2 | 1 |
| C | 0,03 / 1,4 | **6,0 / 18,9 / 26,0** | 26 |
| B | 0,03 / 1,3 | **8,3 / 12,9 / 15,4** | 23 |
| A | 0,03 / 1,7 | **10,6 / 16,5 / 18,5** | 21 |

- Khi mốc đọc được, bước mới không chạy nên không tốn thêm thời gian.
- Bước mới chỉ mở với lượt mốc hỏng. Hàng đợi có một tiến trình, nên thông lượng khoảng **10 lượt khó/phút với C**, 7 với B, 6 với A (tính theo p50).
- Trên `xa_04` (5 frame, máy rảnh hơn): B 3,7 s, A 5,2 s đều đọc được; C 9,4 s và D 1,7 s không đọc được.

## 3. Tài nguyên

| Hướng | RAM đỉnh tiến trình nền | Mã (dòng) | Phụ thuộc thêm |
|---|---:|---:|---|
| A | 617 MB | 1136 | `scipy` |
| B | 620 MB | 1343 | `scipy` |
| C | 650 MB | 683 | `scipy`, `zxingcpp`, WeChat (đã có) |
| D | 618 MB (chưa tính JVM) | 168 | Java, `pyboof`, `pyzbar`, 26 MB `.deps` |

- Khoảng 570 MB trong số đó là nạp `torch` và `qr`, vì tiến trình nền đang nạp lại app. Có thể giảm nhiều khi đưa vào sản phẩm thật.
- `scipy` đang có trong `.venv` nhưng **chưa có trong `requirements.txt`**. Phải thêm trước khi triển khai A, B, C.
- Bộ giải chạy ở tiến trình riêng nên không làm chậm giao diện hay luồng decode.

## 4. An toàn: rủi ro báo sai

0 báo sai trên 2310 lần chấm mỗi hướng (tập phát triển + kiểm tra, trừ `gan_17`). Các lần chấm không độc lập và chỉ có 8 nội dung, nên con số này mới là chỉ báo tốt, chưa phải bảo đảm.

| Hướng | Cơ chế chống báo sai | Điểm yếu |
|---|---|---|
| C | zxing phải kiểm tra sửa lỗi (UEC ≥ 0,25); k ≥ 2 cần 2 lần đọc giống nhau | Đọc WeChat ở bước thêm không có UEC; phụ thuộc trường `UEC` của zxing-cpp |
| B | Cổng theo sai số mô hình, độ lật bit, khoảng cách ứng viên, điểm format | Ngưỡng chỉnh trên tập phát triển. Kiểm tra độc lập 120 ca ảnh xáo trộn: 0 báo sai |
| A | Parse chặt, độ khớp ô ≥ 0,91–0,97, đồng thuận với cascade | Biên hẹp: ứng viên sai cao nhất 0,888, ngưỡng 0,91 |
| D | Chỉ nhận mã các engine đã kiểm tra | Càng nhiều engine càng tăng cơ hội đọc sai |

## 5. Độ sẵn sàng

| Hạng mục | Trạng thái |
|---|---|
| Có trong `main_basler.py` của worktree | Cả 4 hướng |
| Test tự động (365 test mỗi worktree) | Đạt, 4 test bỏ qua do thiếu ảnh mẫu |
| Giải lượt khó qua tiến trình nền | Đã thử, cả 4 hướng trả kết quả, A và B đọc đúng cả 3 cụm frame |
| App khởi động | Đã thử chế độ không màn hình, chưa có camera thật |
| Chạy với camera thật | **Chưa** |
| Commit, merge vào `main` | **Chưa** |
| Lượt khó thật có vệt mờ thật | **Chưa có dữ liệu** |

Hướng dẫn chạy: `reports/Lệnh chạy app theo thuật toán.md`.

## 6. Đánh giá từng hướng

**A `soft_reader`: đọc tem cong tốt nhất, nhưng dễ khớp theo dữ liệu.** Đọc `xa_04` 30/30 và mạnh ở `nhieu`. Điểm tụt 5,3 điểm khi sang tập kiểm tra, `mo` chỉ 79%, biên chống báo sai hẹp.

**B `grid_sr`: cân bằng nhất giữa độ bền và tốc độ.** Tốt ở `nhieu` và tem cong, p95 thấp nhất trong ba hướng mạnh, có kiểm tra ảnh xáo trộn. Hỗ trợ version 1–3, mã phức tạp nhất. Yếu ở `nho65` khi k lớn (88% ở k = 5).

**C `preproc_sweep`: điểm cao nhất và đơn giản nhất.** Ổn định nhất giữa hai tập. Giải mã bằng thư viện có sẵn nên ít rủi ro. Yếu ở ảnh tối nhiều nhiễu (86,9%) và tem cong (`xa_04` 4/30); p95 lượt khó lâu nhất.

**D `engines`: không đáng tích hợp.** Rẻ nhưng chỉ thêm 1,4 điểm, đọc thêm 1/30 lượt mốc hỏng ở phép đo tốc độ, lại kèm JVM.

**Ghép B rồi C: điểm cao nhất**, nhưng chưa được tích hợp vào app dưới dạng một worktree. Tổ hợp này được chọn sau khi đã thấy điểm kiểm tra từng hướng nên hơi lạc quan.

## 7. Giới hạn của báo cáo

1. Bốn điều kiện suy giảm là giả lập. `mo` đặc biệt lạc quan vì mô hình biết đúng vệt mờ.
2. Ít mẫu: 78 lượt, 8 nội dung, một lượt khó thật. Đáp án lấy theo đa số cascade, không phải nhãn tay.
3. Detection giữ nguyên từ ảnh gốc, chưa tính detector bỏ sót khi ảnh xấu.
4. Tốc độ đo trên máy phát triển, 5 tiến trình chạy cùng lúc, chưa phải máy hiện trường.
5. Dynamsoft và HALCON chưa được đo vì cần license.

## 8. Việc nên làm tiếp

1. Chạy từng app theo `reports/Lệnh chạy app theo thuật toán.md` trên camera thật, ở điều kiện khó.
2. Thu đoạn có vệt mờ thật, tem cong, tem bẩn, kèm đáp án theo từng lượt.
3. Tích hợp B rồi C vào một nhánh mới từ `main`, thêm `scipy` vào `requirements.txt`.
4. Tối ưu tốc độ: khớp lưới một lần mỗi lượt, tách phần nạp `torch` khỏi tiến trình nền.
5. Thống nhất quy cách in tem. Ưu tiên V1 với mức sửa lỗi cao nhất mà nội dung vừa.
