# Kết quả thử nghiệm thuật toán đọc QR

Ngày chạy: 09–10/11/2026. Dữ liệu: 3 đoạn quay Basler `gan`, `xa`, `cheo` (78 lượt tem). Tóm tắt phương pháp trong `reports/Plan nghiên cứu thuật toán đọc QR.md`.

## Kết luận

**Hướng tốt nhất là ước lượng trực tiếp giá trị từng ô trên lưới với mô hình mờ đã biết.** Ba hướng dùng ý này đều vượt pipeline hiện tại khoảng 15–18 điểm trên tập kiểm tra, còn thêm bộ giải mã mã nguồn mở chỉ được 1,5 điểm.

| Hạng | Phương pháp | Điểm tập phát triển | **Điểm tập kiểm tra** | Báo sai (test) | Đọc thêm / mất so với mốc | p95 mỗi lượt |
|---|---|---:|---:|---:|---:|---:|
| 1 | **C `preproc_sweep`**: giải ô trên lưới + vẽ lại mã sạch cho zxing/WeChat | 96,58 | **96,14** | 1 (*) | +205 / 0 | 10,9 s |
| 2 | **B `grid_sr`**: bài toán ngược chung trên lưới, tiên nghiệm nhị phân | 96,67 | **95,18** | 0 | +194 / 0 | 14,1 s |
| 3 | A `soft_reader`: bộ đọc mềm + Reed–Solomon erasure | 98,50 | **93,25** | 0 | +172 / 0 | 18,7 s |
| 4 | D `engines`: thêm BoofCV, zxing Lanczos | 80,83 | 79,65 | 0 | +17 / 0 | 3,0 s |
| Mốc | Pipeline hiện tại (`PassDecoder`) | 79,25 | 78,16 | 0 | | 1,9 s |
| Ghép | **B rồi C** | 99,25 | **98,51** | 1 (*) | +232 / 0 | 14,6 s |
| Ghép | A rồi B rồi C | 99,83 | 98,95 | 1 (*) | +237 / 0 | 25,2 s |

(*) Lần báo sai duy nhất **không phải đọc sai**. Ở frame 1148 của lượt `gan_17`, hai tem đè lên nhau và bộ theo dõi gom nhầm thành một lượt. Phương pháp đọc đúng tem nằm trên (`444…`), nhưng đáp án của lượt là tem kia (`333…`). Bỏ lượt này thì mọi phương pháp đều 0 báo sai.

**Đề xuất:** tích hợp **C** trước (điểm kiểm tra cao nhất, ổn định giữa hai tập, vẫn giải mã bằng zxing/WeChat nên rủi ro đọc sai thấp). Nếu cần thêm thì nối **B** phía sau. Không chọn A làm trụ cột: A đứng đầu tập phát triển nhưng tụt 5,3 điểm ở tập kiểm tra, dấu hiệu khớp theo dữ liệu đã thấy.

**Điều phải biết trước khi dùng các con số:** trên **ảnh thật không suy giảm**, pipeline hiện tại đã đọc 100% khi có từ 3 frame trở lên, và cả ba phương pháp mới cũng vậy. Phần chênh lệch chủ yếu đến từ các điều kiện **giả lập** (ảnh nhỏ hơn, thêm vệt mờ, thêm nhiễu). Lợi ích trên ảnh thật mới thấy ở lượt khó `xa_04` (tem nghiêng/cong, xem §4). Muốn biết có đáng đưa vào sản phẩm, cần một đoạn quay thật ở điều kiện khó (§6).

## 1. Cách chấm

- **Dữ liệu:** detect mọi frame (5037 frame), gom thành 79 lượt, gán đáp án theo đa số cascade (không có nhãn tay). Chia xen kẽ: 40 lượt phát triển, 38 lượt kiểm tra (bỏ 1 mảnh lượt ngắn). Agent không được dùng tập kiểm tra.
- **Điều kiện thử:** `goc` (ảnh thật), `nho80`, `nho65` (thu nhỏ ×0,8 và ×0,65 ảnh, tương đương 2,05 và 1,65 px/ô với QR V1), `mo` (vệt mờ 4 px ≈ 1,6 ô), `nhieu` (tối đi ×0,6, nhiễu σ = 5).
- **k** = số frame của lượt được dùng (1, 3, 5), mô phỏng việc CPU chỉ xử lý được vài frame mỗi lượt.
- **Điểm tổng:** trung bình 15 ô × 2 seed.

Phát hiện khi chấm: tem **không phải tất cả V1-L** như tôi đã báo trước đó. Trong 78 lượt có V1-L 29, V1-M 3, V2-L 3, V2-M 12, V2-Q 15, V2-H 3, V3-H 11, 2 lượt chưa xác định. Nhãn in trên tem (L/M/Q/H) đúng là mức sửa lỗi. Lần kiểm tra trước của tôi chỉ xem một tem cho mỗi nội dung nên kết luận sai. Cùng cỡ 36 mm, V2 chỉ còn khoảng 2,16 px/ô, V3 khoảng 1,86 px/ô.

## 2. Kết quả trên tập kiểm tra (%, k = 1 / 3 / 5)

| Điều kiện | Mốc | C | B | A | B rồi C |
|---|---|---|---|---|---|
| `goc` (thật) | 98,7 / 100 / 100 | 98,7 / 100 / 100 | 98,7 / 100 / 100 | 98,7 / 100 / 100 | 98,7 / 100 / 100 |
| `nho80` | 97,4 / 97,4 / 98,7 | 98,7 / 100 / 100 | 97,4 / 98,7 / 100 | 100 / 98,7 / 98,7 | 98,7 / 100 / 100 |
| `nho65` | 77,6 / 78,9 / 82,9 | 98,7 / 100 / 100 | 96,1 / 92,1 / 88,2 | 89,5 / 93,4 / 96,1 | 98,7 / 100 / 100 |
| `mo` | 36,8 / 39,5 / 53,9 | 92,1 / 96,1 / 97,4 | 89,5 / 89,5 / 93,4 | 80,3 / 78,9 / 78,9 | 97,4 / 98,7 / 100 |
| `nhieu` | 61,8 / 63,2 / 85,5 | 78,9 / 89,5 / 92,1 | 88,2 / 97,4 / 98,7 | 88,2 / 97,4 / 100 | 88,2 / 98,7 / 98,7 |

Theo đoạn trên tập kiểm tra:

| | Mốc | C | B | A | B rồi C |
|---|---:|---:|---:|---:|---:|
| `gan` | 91,1 | 98,9 | 97,5 | 99,4 | 99,4 |
| `xa` | 58,2 | 90,0 | 90,8 | 84,1 | 96,4 |
| `cheo` | 86,2 | 99,7 | 97,4 | 96,7 | 99,7 |

Tất cả phương pháp mới không làm mất lần đọc nào mà mốc đọc được, vì đều chạy `PassDecoder` trước.

## 3. Vì sao chọn C và hướng lưới ô

Đo lợi ích từng bước của C (600 lần chấm, tập phát triển):

| Cấu hình | Điểm | `mo` | `nhieu` |
|---|---:|---:|---:|
| Chỉ cascade | 79,17 | 41,7 | 69,2 |
| Chỉ giải ô trên lưới (`lsq`) | 92,67 | 88,3 | 84,2 |
| `lsq` + gộp nhiều frame + khớp lại lưới | 95,17 | 93,3 | 90,8 |
| Đủ các bước | 96,17 | 95,8 | 91,7 |
| Chỉ quét vệt mờ (Wiener) | 87,83 | 85,0 | 69,2 |
| Chỉ phần ánh sáng/khử nhiễu | 81,83 | 44,2 | 76,7 |

Khoảng 80% phần tăng đến từ giải giá trị ô. Khử nhiễu, gộp frame thông thường hay quét vệt mờ đóng góp ít hơn nhiều. Điều này đúng với hướng mà báo cáo nghiên cứu đề xuất (Kato, Cognex): ước lượng từng ô thay vì làm ảnh đẹp rồi mới giải mã.

Mỗi hướng có điểm mạnh riêng: C mạnh ở `nho65`, `mo`; B và A mạnh ở `nhieu`; ghép B rồi C bù nhau và lên 98,5.

**Engine mã nguồn mở (D):** không engine riêng lẻ nào thắng mốc (tốt nhất zxing nhiều tỉ lệ 66,3%, BoofCV 65,4%). Ghép thêm chỉ +1,5 điểm, BoofCV lại cần JVM. Không đáng đưa vào sản phẩm.

## 4. Lượt khó trên ảnh thật: `xa_04`

Đây là tem nghiêng/cong ở vị trí xa, thuộc tập phát triển. Cascade chỉ đọc được 3/25 frame:

| Phương pháp | Số lần đọc đúng (trên 30 lần chấm, 5 điều kiện) |
|---|---:|
| Mốc | 2 |
| C | 4 |
| B | 25 |
| A | 30 |

Trường hợp này C yếu vì không mô hình hóa tem cong. A và B có trường biến dạng nên đọc được. Đây là lý do nối B phía sau C có giá trị.

## 5. Giới hạn của kết quả

1. **Suy giảm là giả lập.** `mo` đặc biệt lạc quan: vệt mờ có độ dài và hướng đúng như mô hình được báo. Vệt mờ thật có thể cho kết quả thấp hơn đáng kể. `nho*` thu nhỏ từ ảnh đã lấy mẫu một lần.
2. **Detection giữ nguyên** từ ảnh gốc, nên tỉ lệ bỏ sót của detector ở ảnh khó chưa được tính.
3. **Mẫu nhỏ.** 78 lượt, chỉ 8 nội dung, 0 báo sai chỉ nói lên được cận trên khoảng 0,3% và các lần chấm không độc lập. Biên an toàn của cổng chống báo sai ở A và B khá hẹp. Trước khi dùng thật cần tập lớn với nhiều nội dung khác nhau.
4. **Đáp án lấy theo đa số cascade**, không phải nhãn tay. Lượt có tem đè nhau bị gom nhầm (như `gan_17`).
5. **Các tổ hợp** B→C và A→B→C được chọn sau khi đã thấy điểm kiểm tra của từng phương pháp riêng, nên điểm của chúng hơi lạc quan.
6. **Tốc độ chưa xử lý.** p95 10–25 s cho lượt mà cascade không đọc được, chưa dùng được thời gian thực. Trên ảnh thật đa số lượt do cascade đọc xong trong vài chục ms nên bước chậm ít khi phải chạy.
7. **Dynamsoft và HALCON chưa được đo** vì cần license của bạn.
8. Vùng cắt ảnh chưa biết Offset, nên chưa quy được `xa` ra số mm so với trục camera.

## 6. Bước tiếp theo đề xuất

1. **Quay thêm đoạn thật ở điều kiện khó** để kiểm chứng phần giả lập: băng chạy nhanh hơn hoặc exposure dài hơn để vệt mờ 1–2 ô thật, ánh sáng yếu hơn, tem bẩn/cong, thêm vị trí mép. Ghi đáp án theo từng lượt. Đặt tem cách nhau đủ xa để không đè lên nhau.
2. **Tăng sáng:** nền trắng tem chỉ 53–73/255, mục tiêu 170–225.
3. Nếu đoạn khó cho thấy lợi ích thật: **tích hợp lõi giải ô của C** vào `PassDecoder` như một bước sau cascade, sau đó nối B cho tem cong.
4. **Tối ưu tốc độ** sau khi chốt: khớp lưới một lần mỗi lượt rồi bám theo vận tốc; viết lại phần giải ô bằng NumPy/Numba.
5. Mức sửa lỗi: tem hiện có V1 đến V3 với 4 mức. Nên chọn một quy cách in cố định; V1 mức cao nhất mà nội dung vừa thì có ô to nhất.
6. Nếu muốn so sánh Dynamsoft, HALCON: cấp license dùng thử, tôi chạy cùng bộ chấm.

## 7. Nơi lưu kết quả

- Bộ chấm điểm: `experiments/bench/` (chưa commit).
- Dữ liệu và kết quả: `experiments/out/bench/` (`tracks_dev`, `tracks_test_holdout`, `results/`), không commit.
- Mã từng phương pháp: `experiments/out/methods/{soft_reader,grid_sr,preproc_sweep,engines}/`, không commit. Bản làm việc ở các worktree `.claude/worktrees/agent-*`.
- Các agent không ghi được `REPORT.md` (bị chặn quyền ghi file), nên nội dung báo cáo của chúng được tóm tắt trong file này.
- Code sản phẩm (`qr/`, `camera/`, `ui/`, `demo_ui/`) không thay đổi.
