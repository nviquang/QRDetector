# Độ khả thi thuật toán đọc QR ở hình học hiện trường

> **Cấu hình cũ (trước 18/11/2026).** Tài liệu này lập theo thông số đã thay thế (tem 25/36 mm, camera cao 1 m, 0,673 mm/px, băng 100 mm/s, nội dung 12#12 hoặc version 1, một camera, máy CPU). Ràng buộc hiện hành: mục "Bài toán và ràng buộc" trong `README.md`. Kỹ thuật và tài liệu tham khảo vẫn dùng được, nhưng số px/ô và mọi đề xuất đổi tem, nội dung, version/mức sửa lỗi, camera, ống kính, line-scan, đầu đọc thương mại hay vị trí dán tem không còn áp dụng.

Ngày đo: 06/11/2026. Dữ liệu: 30 frame tĩnh, cấu hình chuẩn `experiments/benchmark_basler.json`, lưu tại `experiments/out/static_20261106/` (kèm script thử nghiệm trong `proto/`).

## Kết luận

**Khả thi có điều kiện.** Với ràng buộc hiện tại (chỉ CPU, camera 8 MP, ống 4 mm, cao 1 m, tem 36 mm; các tem đo ở đây là version 1), hình học đo được đạt đúng tính toán: **2,55 px/ô**. Ở mức này:

> **Đính chính (12/11):** khi viết báo cáo này tôi coi mọi tem là version 1 mức L. Đo sau đó cho thấy tem phòng thí nghiệm lẫn version 1–3, mức L–H. Quy cách đã chốt cho hiện trường là version 1 mức M (README.md, mục Thông số hiện trường và tem).

- Pipeline hiện tại đọc được **2/4 tem** trong vùng đọc.
- Bộ đọc mềm thử nghiệm (lấy mẫu theo lưới ô + giải mã Reed–Solomon có erasure) đọc được **3/4 tem**. Trong đó có một tem mà pipeline hiện tại không đọc được ở frame nào.
- Tem còn lại hỏng vì **vệt chói phản xạ**, không phải vì thuật toán. Đây là lỗi phải sửa ở đèn.

Chưa chứng minh được ba điều: hiệu quả khi băng chạy 10 cm/s, tỉ lệ đọc sai trên số lượng lớn, và chất lượng ở mép vùng đọc. Video chuẩn sẽ trả lời cả ba.

## 1. Điều kiện đo

| Đại lượng | Tính toán | Đo được | Đánh giá |
|---|---:|---:|---|
| mm/px | 0,686 | 0,673 | Đạt |
| px/ô | 2,5 | 2,55 | Đạt |
| Nền trắng tem (p95) | 170–225 | 174 | Đạt (sau khi chỉnh; lần đầu 255, cháy 7,9%) |
| Ô đen (p5) | ≤ 70 | 11 | Đạt |
| Vệt mờ ở 100 mm/s, exposure 3 ms | ≤ 0,25 ô | 0,17 ô | Đạt |

So với phòng thí nghiệm trước đó (~1,9 px/ô), hình học hiện trường tăng khoảng 35% số px mỗi ô.

## 2. Kết quả trên 4 tem (30 frame tĩnh)

| Tem | Tình trạng | Pipeline hiện tại | Bộ đọc mềm, giới hạn ISO | Bộ đọc mềm, ngân sách tối đa |
|---|---|---:|---:|---:|
| 0 | Nghiêng, nằm chồng lên tem 1 | 30/30 | 30/30 | 30/30 |
| 1 | Nghiêng, bị tem 0 đè một phần | **0/30** | 13/30 | **30/30** (`000000585623`) |
| 2 | Thẳng, vệt chói ở góc trên phải | 0/30 | 0/30 | 0/30 |
| 3 | Thẳng, sạch | 30/30 | 30/30 | 30/30 |

- **Giới hạn ISO:** chỉ sửa tối đa 2 byte lỗi, giữ 3 byte sửa lỗi để phát hiện đọc sai, đúng như các bộ giải mã thông thường.
- **Ngân sách tối đa:** dùng hết 7 byte sửa lỗi (lỗi tính 2, erasure tính 1). Đọc được nhiều hơn nhưng tăng nguy cơ đọc sai.
- Tem 1 cho cùng một nội dung ở cả 30 frame, và nội dung này trùng một mã tem đã gặp trước đó. Đây là bằng chứng tốt rằng nó đọc đúng, nhưng chưa phải phép đo tỉ lệ đọc sai.

## 3. Vì sao bộ đọc mềm đọc được nhiều hơn

Cùng một lưới ô trên tem 0, thay đổi cách quyết định đen/trắng:

| Cách quyết định | Ô sai | Byte sai | Giải được? |
|---|---:|---:|---|
| Ngưỡng chung cho cả tem | 25 | 14 | Không |
| Ngưỡng cục bộ | 11 | 3 | Chỉ với ngân sách tối đa |
| Ngưỡng cục bộ + bù nhòe từ 4 ô bên cạnh | 9 | 2 | Có, kể cả giới hạn ISO |

Ở 2,5 px/ô, mỗi ô bị lẫn sáng từ ô bên cạnh. Bù phần lẫn này trước khi quyết định, rồi đánh dấu các byte kém chắc chắn nhất là erasure, đẩy số byte sai xuống trong ngân sách sửa lỗi của mức L. Đây đúng là hướng mà báo cáo nghiên cứu xếp vào nhóm có triển vọng (Kato 2011; bằng sáng chế Cognex US11151346B2), nhưng chưa có mã nguồn công khai.

Gộp 5 hoặc 30 frame tĩnh không giúp thêm, vì frame tĩnh chỉ giảm nhiễu mà nhiễu không phải vấn đề. Khi băng chạy, các frame lệch nhau một phần ô, nên gộp nhiều frame có thể có ích hơn. Điều này cần kiểm trên video chuẩn.

## 4. Tem 2: vệt chói là giới hạn vật lý

Vệt phản xạ chạy dọc qua cột phải của finder trên phải và hai cột dữ liệu sát mép, làm các ô đó thành trắng. Do mất một finder, lưới khớp lệch khoảng một ô; và ngay cả khi khớp đúng, số ô bị xóa trắng vẫn vượt ngân sách sửa lỗi của mức L. Không thuật toán nào lấy lại được thông tin bị xóa.

Cách xử lý:
- Đổi góc đèn để phản xạ gương không đi vào ống kính (đèn xiên, không đặt gần trục camera).
- Dùng tấm khuếch tán, hoặc kính phân cực chéo (một tấm trước đèn, một tấm trước ống kính).
- Nếu tem có lớp phủ bóng, dùng tem mờ (matte).

## 5. Rủi ro và điều chưa biết

| Hạng mục | Mức | Ghi chú |
|---|---|---|
| Băng chạy 10 cm/s | Chưa đo | Vệt mờ tính ra 0,17 ô, nhỏ; lưới cần bám theo tem giữa các frame |
| Đọc sai khi dùng ngân sách tối đa | Trung bình | Giảm bằng: thử giới hạn ISO trước, cần 2 lần đọc giống nhau, kiểm định dạng nội dung nếu có |
| Vệt chói | Cao nếu không sửa | Sửa ở đèn, xem §4 |
| Tem chồng nhau | Thấp | Tem 0 và 1 vẫn đọc được; ở hiện trường nên dán cách nhau |
| Mép vùng đọc | Chưa đo | Ống 4 mm thường kém nét và tối ở mép |
| Tốc độ xử lý | Chưa tối ưu | Khớp lưới mất 1,4–7 s/tem bằng Python thuần; giải mã sau khi khớp chỉ vài ms. Cần khớp một lần mỗi lượt rồi bám theo vận tốc. Theo yêu cầu, phần tốc độ để sau |

## 6. Bước tiếp theo

1. **Sửa vệt chói** (góc đèn, khuếch tán, phân cực), rồi chạy lại `check_setup.py` với tem đặt ở tâm và hai mép.
2. **Quay video chuẩn** theo `experiments/benchmark_standard.md`, ≥ 100 lượt tem, có `labels.json`.
3. **Đưa bộ đọc mềm vào `PassDecoder`** như một bước sau cascade: khớp lưới một lần mỗi lượt, cộng dồn giá trị ô qua các frame, giải RS có erasure, giữ quy tắc 2 lần đọc giống nhau.
4. **Đo trên video chuẩn**: tỉ lệ đọc theo lượt và số lần đọc sai, so pipeline hiện tại với pipeline có bộ đọc mềm.
5. Sau khi chốt được tỉ lệ đọc mới tối ưu tốc độ khớp lưới.
