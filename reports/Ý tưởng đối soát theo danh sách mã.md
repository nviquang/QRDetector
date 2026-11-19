# Đề xuất: đối soát tem khó đọc theo danh sách mã còn hiệu lực

**Trạng thái:** đã có bản thử nghiệm trên nhánh `feat/doi-soat-danh-sach-ma` (`qr/candidate_match.py`, `experiments/candidate_match_sim.py`) và kết quả thử offline trên QR tổng hợp (mục 11). Chưa nối vào app, chưa chạy trên video thật. Các con số về dự án lấy từ `README.md` và `reports/`; các nhận định chưa đo được ghi rõ là ước tính.

## Tóm tắt

Hệ thống biết trước tem nào có thể xuất hiện: mỗi mã QR chỉ có hiệu lực **1 giờ** kể từ lúc tạo. Vì vậy, khi camera không giải mã được một tem, ta không cần đoán nội dung từ đầu mà chỉ cần **chọn mã khớp nhất trong số vài trăm mã đang còn hiệu lực**.

Cách này:

- **Đọc thêm được tem khó** (mờ, chói một phần, cong) mà bộ đọc hiện tại bỏ.
- **Làm tầng đọc nền nhanh hơn nhiều**, hợp với máy hiện trường chỉ có CPU.
- **Chặn được mã đọc sai** trước khi gửi lên server.
- **Tự phát hiện và sửa** phần lớn các lần đoán nhầm nhờ sổ đối chiếu 1 giờ.

Đề xuất làm theo từng bước, bắt đầu từ bước rẻ nhất (kiểm tra mọi lần đọc với danh sách mã), và chỉ triển khai phần đoán sau khi đã đo được tỉ lệ nhầm bằng mã mồi.

## 1. Vướng mắc hiện tại

| Vướng mắc | Số liệu |
|---|---|
| QR rất nhỏ | Tem 36 mm ở 0,673 mm/px: version 1 khoảng 2,57 px/ô; tem in mặc định lên version 2–3 chỉ còn 1,86–2,16 px/ô |
| Ảnh tối | Đoạn quay 09–10/11: nền trắng tem chỉ 53–73/255, mục tiêu 170–225 |
| Tem bị chói | Báo cáo khả thi: tem có vệt chói đọc **0/30** frame với mọi phương pháp |
| Tầng đọc nền chậm | Bộ giải B/C mất p95 10–25 giây mỗi lượt khó; hàng đợi tối đa 8 lượt, đầy thì tính là không đọc được; máy hiện trường chỉ có CPU |
| Đọc sai có thể bị gửi đi | Code chưa lọc nội dung (`code_pattern=None`) |
| Lượt chỉ đọc được 1 lần bị bỏ | Phải có 2 lần đọc giống nhau mới báo mã; lượt kết thúc với 1 lần đọc chỉ ghi log `pass_unconfirmed` |

## 2. Ý tưởng

1. Server gửi xuống camera danh sách các mã còn hiệu lực (tạo trong 1 giờ gần nhất).
2. Lượt nào đọc thường thành công thì giữ nguyên như hiện nay, và **kiểm tra mã đó có trong danh sách không**.
3. Lượt nào không đọc được thì **so tem với từng mã trong danh sách**, chọn mã khớp nhất nếu qua được bộ ngưỡng ở mục 6.
4. Kết quả đối soát được ghi riêng là **"suy luận"**, và được chốt hoặc sửa ở cuối khung giờ (mục 8).

## 3. Vì sao ý tưởng này hợp lý

### 3.1 Thu hẹp bài toán rất nhiều

- Đọc thường phải tìm đúng 1 trong khoảng 10²⁴ mã có thể có, nên cần nhìn rõ gần như mọi ô của QR.
- Đối soát chỉ chọn 1 trong vài trăm mã, nên **nhìn rõ một phần các ô là đủ**.

### 3.2 Có cơ sở toán học: mã sửa lỗi của QR

QR dùng mã sửa lỗi Reed–Solomon. Nội dung chia thành các byte (mỗi byte là 8 ô đen/trắng), cộng thêm các byte sửa lỗi tính từ toàn bộ dữ liệu.

- Tem theo quy cách (QR version 1 mức M) có **26 byte = 16 byte dữ liệu + 10 byte sửa lỗi**. Nội dung `12 số#12 số` mã hóa tách đoạn chiếm đúng 16 byte, vừa khít.
- Vì byte sửa lỗi tính từ toàn bộ dữ liệu, chỉ đổi một chữ số (001 → 002) là gần như cả 10 byte sửa lỗi đổi theo. Toán học bảo đảm **hai mã hợp lệ bất kỳ khác nhau ít nhất 11/26 byte**, ước tính khoảng vài chục ô.
- Nghĩa là hai mã liền số **trông gần giống nhau về chữ nhưng khác nhau rất nhiều trên hình QR**. Đây là cơ sở để phân biệt chúng.

### 3.3 Chịu hỏng tốt hơn đọc thường

- Đọc thường với mức M chỉ thành công khi hỏng **tối đa 4 byte** (theo chuẩn ISO).
- Đối soát không cần sửa hết lỗi, chỉ cần đủ ô nhìn rõ để mã đúng **vượt hẳn** mã đứng thứ hai. Tem hỏng quá 4 byte vẫn có thể đối soát được: trong thử nghiệm ở mục 11, tem bị chói 20% (zxing đọc 0%) vẫn đối soát đúng khoảng 87%.

### 3.4 Mức M là lựa chọn hợp nhất

| Version 1 | Byte dữ liệu / sửa lỗi | Hai mã khác nhau ít nhất | Vừa nội dung tem |
|---|---|---|---|
| L | 19 / 7 | 8 byte | Có |
| **M** | **16 / 10** | **11 byte** | **Có, vừa khít** |
| Q, H | 13 / 13, 9 / 17 | 14, 18 byte | Không, phải lên version 2–3 (ô nhỏ đi) |

Mức M cho ô to nhất (version 1) mà các mã vẫn cách nhau xa.

### 3.5 Tận dụng cái đã có

- Bộ giải B (`grid_sr`) và C (`preproc_sweep`) trong `qr/solvers` đã **ước lượng giá trị từng ô** trên lưới. Đây là phần khó nhất của ý tưởng.
- `grid_sr` đã có cơ chế sinh và chấm điểm ứng viên; chỉ cần thay nguồn ứng viên bằng danh sách mã của hệ thống.
- Danh sách mã và thời điểm tạo vốn đã có ở server, không phải thu thập thêm.

### 3.6 Chưa có trong dự án

Các tài liệu hiện có chỉ dùng danh sách mã để **chấm điểm** sau khi chạy, hoặc chỉ lọc theo định dạng. Chưa có tài liệu nào dùng danh sách mã còn hiệu lực để **quyết định** tem khó là mã nào.

## 4. Khắc phục được vướng mắc nào

| Vướng mắc | Cải thiện | Mức tác động (ước tính) |
|---|---|---|
| Tầng đọc nền chậm, hàng đợi dễ đầy | Chấm vài trăm mã trên các ô đã ước lượng chỉ tốn cỡ mili giây; phần tốn thời gian còn lại là khớp lưới | **Lớn** |
| Đọc sai có thể bị gửi đi | Mã đọc ra không có trong danh sách thì cảnh báo, không gửi | **Lớn, rẻ, làm được ngay** |
| Lượt chỉ đọc được 1 lần bị bỏ | Nhận nếu mã có trong danh sách và chưa quét: đọc sai mà rơi đúng vào một mã đang hiệu lực là gần như không xảy ra | **Lớn, rẻ** |
| Tem bị chói hoặc bẩn một phần | Vùng hỏng coi như không biết, phần ô còn lại thường đủ để phân biệt | Lớn |
| Tem in mặc định version 2–3 | Ô nhỏ khó đọc thường, nhưng nhìn được một phần ô là đủ đối soát | Vừa |
| Phát hiện nhầm của YOLO | Cho phép bắt nhạy hơn: phát hiện nhầm không khớp mã nào nên bị loại | Vừa |

## 5. Không giải quyết được gì

Nêu rõ để không kỳ vọng sai:

- **Tem không được phát hiện:** YOLO không thấy tem thì không có gì để đối soát.
- **Hai tem đè nhau bị gom thành một lượt** (như lượt `gan_17`): lỗi của bộ theo dõi, không phải của bước đọc.
- **Tem mờ hoặc hỏng gần hết:** không đủ ô rõ để phân biệt thì hệ thống trả "không xác định". Đây là hành vi đúng.
- **Ảnh tối và in sai quy cách:** vẫn là nguyên nhân gốc. Sửa đèn và in đúng version 1 mức M rẻ hơn và có lợi hơn mọi thuật toán, nên phải làm trước.

## 6. Cách so sánh và bộ ngưỡng quyết định

### 6.1 So theo ô, không so chuỗi

Không dùng ngưỡng kiểu "giống 90%" trên chuỗi ký tự:

- Mã khó đọc thì bộ giải hoặc trả đủ nội dung, hoặc không trả gì; không có chuỗi nào để so.
- Mã liền số giống nhau 24/25 ký tự (96%), nên ngưỡng 90% sẽ nhận nhầm đúng kiểu nguy hiểm nhất.

Thay vào đó: dựng hình QR của từng mã ứng viên **đúng như khi in**, rồi so với giá trị từng ô ước lượng được. Ô nhìn rõ tính nặng, ô bị mờ hoặc chói tính nhẹ.

### 6.2 Sáu cổng, phải qua tất cả mới được nhận

| # | Cổng | Kiểm tra | Chặn lỗi |
|---|---|---|---|
| 1 | Hình học | Thấy đủ 3 ô định vị, khớp lưới tốt; ô thông tin định dạng (version, mức sửa lỗi, mask) đúng quy cách | Tem không phải QR của hệ thống, khớp lưới sai |
| 2 | Đủ bằng chứng | Số ô nhìn rõ đạt tối thiểu; vùng chói/che không quá giới hạn | Đoán trên ảnh quá ít thông tin |
| 3 | Khớp tuyệt đối | Tỉ lệ ô lệch với mã tốt nhất dưới mức cho phép | Tem lạ, tem in lỗi bị ép vào một mã |
| 4 | Chênh lệch | Mã tốt nhất vượt mã thứ hai ít nhất Δ; danh sách càng dài thì Δ càng lớn | Nhầm mã liền số (001 ↔ 002) |
| 5 | Theo byte | Gọi e là số byte bị che, t là số byte nhìn rõ mà lệch; chỉ nhận khi e + 2t ≤ 8 | Mã **không có trong danh sách** bị nhận nhầm vì vùng chói che đúng chỗ khác biệt |
| 6 | Nhất quán | Mã chưa được dùng, thời gian in hợp lý, không mâu thuẫn với lượt đã đọc chắc | Trùng, tem đi lại, tem hết hạn |

Cổng 5 được thêm sau khi thử nghiệm cho thấy lỗ hổng (mục 11). Nó dựa đúng vào tính chất mã sửa lỗi: hai mã hợp lệ khác nhau ít nhất 11 byte, nên nếu chỉ một ít byte bị che thì **mọi mã khác, kể cả mã ngoài danh sách**, buộc phải lệch ở các byte nhìn rõ và bị phát hiện. Đây cũng là điều kiện mà bộ giải mã Reed–Solomon dùng khi sửa lỗi có vị trí xóa, chừa 2 byte dự trữ.

Giá trị cụ thể của từng ngưỡng **không chọn bằng cảm giác** mà hiệu chỉnh trên dữ liệu thật với mã mồi (mục 10).

## 7. Yêu cầu hai bên phải đạt

### 7.1 Phía camera

| Yêu cầu | Mức đề xuất |
|---|---|
| Độ phân giải | ≥ 2,5 px/ô: tem in đúng version 1 (khoảng 2,57 px/ô) |
| Vệt mờ | ≤ khoảng 0,25 ô: exposure 3 ms ở 100 mm/s |
| Độ sáng | Nền trắng 170–225/255, ô đen ≤ 70, không cháy sáng |
| Chói phản xạ | Chỉ che một phần nhỏ của tem (chỉnh góc đèn) |
| Số frame mỗi tem | ≥ 3 frame rõ |
| Tách tem | Tem cách nhau ≥ 100 mm theo chiều chạy, không đè nhau |
| Đồng hồ | Đồng bộ thời gian với server (NTP) |

### 7.2 Phía server sinh QR

| Yêu cầu | Lý do |
|---|---|
| **Quy cách mã hóa cố định và có ghi lại:** version 1, mức M, tách đoạn; mask cố định hoặc lưu mask cho từng mã; cố định phiên bản thư viện tạo mã | Camera phải dựng lại đúng từng ô của hình đã in; lệch quy cách là đối soát vô nghĩa |
| Mã không bao giờ dùng lại | Một mã hai tem thì không phân biệt được |
| API danh sách mã còn hiệu lực, kèm thời điểm tạo/in, dây chuyền, trạng thái | Là nguồn ứng viên; thiếu hoặc trễ thì đối soát sai |
| Báo các sự kiện in lại, hủy, hết hạn | Không đối soát với mã đã hủy; tem in lại phải được biết |
| Giữ danh sách nhỏ: tách theo dây chuyền hoặc trạm | Ít ứng viên thì ngưỡng chênh lệch dễ đạt và chạy nhanh hơn |
| Nhận kết quả "suy luận" kèm điểm khớp và ảnh crop; cho phép sửa hoặc hủy về sau | Để bước đối chiếu cuối giờ chỉnh lại được |
| Đối chiếu cuối khung giờ: báo mã chưa quét và mã bị quét hai lần | Phát hiện lần đoán nhầm |

Để camera không phụ thuộc hoàn toàn vào việc server giữ đúng mask: ô thông tin định dạng trên tem có mã sửa lỗi riêng nên rất dễ đọc; camera có thể đọc mask từ chính tem, hoặc thử cả 8 mask.

## 8. Rủi ro đoán nhầm và cách khắc phục

Đoán nhầm không bao giờ về 0. Mục tiêu là làm cho nó **hiếm, phát hiện được và sửa được**.

### 8.1 Khi nhầm thì sao

Tem thật là X nhưng bị nhận là Y gây hai lỗi cùng lúc: X bị ghi sai thành Y, và Y bị đánh dấu "đã quét" dù tem Y thật có thể chưa đi qua.

### 8.2 Ba lớp bảo vệ

**Lớp 1, ngăn ngừa:** sáu cổng ở mục 6.2. Điểm sát nhau thì trả "không xác định", không đoán. Mã liền số luôn có trong danh sách nên luôn được chấm cùng, cổng chênh lệch chặn đúng trường hợp này.

**Lớp 2, tự phát hiện nhờ sổ 1 giờ:** mỗi mã chỉ được dán và quét đúng một lần, nên lần nhầm thường để lại dấu vết:

- Tem Y thật đi qua sau đó và được đọc chắc → Y bị quét hai lần, mâu thuẫn → biết lần đối soát trước sai.
- Hết 1 giờ mà X vẫn "chưa quét" → có tem bị thiếu, đối chiếu với lần đối soát đáng ngờ.

**Lớp 3, sửa sai:** kết quả đối soát không chốt ngay mà đi qua ba trạng thái:

| Trạng thái | Khi nào |
|---|---|
| Đọc chắc | Giải mã bình thường thành công |
| Tạm nhận (suy luận) | Qua đủ sáu cổng; gửi server kèm cờ, điểm khớp và ảnh crop |
| Chốt | Hết khung giờ mà không có mâu thuẫn |

Khi phát hiện mâu thuẫn:

- Chuyển tem bị nhận nhầm sang **mã khớp thứ hai** nếu mã đó còn trống; rất thường đó chính là mã đúng.
- Cuối khung giờ, **ghép cặp toàn cục** các tem chưa chốt với các mã chưa quét sao cho tổng điểm khớp cao nhất, mỗi mã dùng một lần (thuật toán Hungarian). Ví dụ: tem A khớp 001 hơi hơn 002, tem B chỉ khớp được 001 → phép ghép cho B = 001, A = 002, đúng hơn quyết định từng tem lúc nó đi qua.
- Nếu tem lên băng theo đúng thứ tự in, có thể dùng thứ tự làm thêm căn cứ, còn chặt hơn nữa.

### 8.3 Lựa chọn an toàn nhất: người xác nhận

Nếu nhầm gây hậu quả nặng (ví dụ truy xuất nguồn gốc kính cho khách hàng): với tem khó, màn hình hiện **ảnh tem và 2 mã khớp nhất**, công nhân bấm một lần để chọn hoặc bỏ qua. Máy thu hẹp vài trăm mã xuống còn 2; người chọn chắc chắn. Không còn lỗi nhầm âm thầm mà vẫn nhanh hơn nhiều so với gõ tay.

## 9. Hai chế độ vận hành

| | Ưu tiên chính xác | Ưu tiên đọc được nhiều (recall) |
|---|---|---|
| Ngưỡng chênh lệch | Chặt | Nới |
| Lượt chỉ đọc được 1 lần | Nhận nếu mã có trong danh sách | Nhận nếu mã có trong danh sách |
| Ca điểm sát nhau | Từ chối hoặc cho người xác nhận | Tạm nhận, để bước ghép cặp cuối giờ sửa |
| Phát hiện của YOLO | Như hiện nay | Bắt nhạy hơn; phát hiện nhầm không khớp mã nào |
| Ngưỡng khớp tuyệt đối | Giữ chặt | **Vẫn giữ chặt**: ép tem lạ vào một mã không làm tăng recall thật, chỉ thêm lỗi |

Việc chọn chế độ là quyết định nghiệp vụ: **nhầm 1 tem gây hậu quả gì, so với bỏ sót 1 tem?**

## 10. Độ tin cậy và cách chứng minh

Độ tin cậy được đo bằng hai con số: **tỉ lệ gán nhầm** và **tỉ lệ từ chối**. Ngưỡng chỉ đổi qua lại giữa hai lỗi này, không có ngưỡng nào cho 0 lỗi cả hai phía.

Cách chứng minh:

1. Thu video thật, có cả lượt khó, kèm đáp án từng lượt.
2. Chấm mỗi lượt với mã đúng và hàng nghìn **mã mồi**, nhất là các mã liền số ±1…±10; mô phỏng danh sách đúng cỡ thực tế.
3. Chọn ngưỡng sao cho tỉ lệ gán nhầm thấp hơn mục tiêu, rồi đo tỉ lệ đọc được.
4. Theo quy tắc ba: thử n lần không nhầm lần nào chỉ chứng minh tỉ lệ nhầm dưới khoảng **3/n** (độ tin cậy 95%). Muốn khẳng định dưới 1/1.000 cần khoảng 3.000 lần thử sạch; dưới 1/10.000 cần khoảng 30.000. Dữ liệu hiện có mới 78 lượt.
5. Khi chạy thật, đếm số lần nhầm bị phát hiện qua mâu thuẫn mỗi khung giờ để biết ngưỡng có còn đúng không.

Lưu ý: bộ chấm điểm của dự án có quy tắc "không chép đáp án vào code" (`experiments/bench/BRIEF.md`). Nếu danh sách ứng viên chỉ có mã đúng thì kết quả sẽ đẹp giả, nên bắt buộc phải có mã mồi.

## 11. Kết quả thử nghiệm offline (19/11/2026)

**Cách thử** (`experiments/candidate_match_sim.py`): dựng tem đúng quy cách (version 1 mức M, tách đoạn, mask ngẫu nhiên), làm xấu ảnh rồi thu nhỏ về 2,57 px/ô như hiện trường, lưới lệch dưới 1 px ngẫu nhiên. Danh sách ứng viên gồm **300 mã mồi ngẫu nhiên + 20 mã liền số ±1…±10 + mã đúng**. Mỗi điều kiện 300 lượt × 2 hạt giống × k = 1 và 3 frame. Song song, mỗi lượt được chấm thêm một lần với danh sách **bỏ mã đúng ra**: lần nhận nào khi đó đều là gán nhầm.

**Kiểm tra phần dựng mã:** zxing đọc lại đúng hình QR do code tự dựng với cả 8 mask, nên camera dựng lại được đúng từng ô của tem in theo quy cách.

**Khoảng cách giữa mã liền số (±1), đo trên 600 cặp:** khác nhau 42–60 trong 208 ô dữ liệu, trung bình khoảng 22%.

| Điều kiện | zxing 1 frame | Đối soát đúng (k = 1) | Đối soát đúng (k = 3) | Nhận nhầm khi mã có trong danh sách | Gán nhầm khi mã không có trong danh sách |
|---|---:|---:|---:|---:|---:|
| Sạch | 100% | 100% | 100% | 0 | 0 |
| Vệt mờ 1 ô | 100% | 100% | 100% | 0 | 0 |
| Vệt mờ 1,6 ô | 46% | 89% | 90% | 0 | 0 |
| Tối (nền trắng 70) + nhiễu | 99% | 100% | 100% | 0 | 0 |
| Chói 20% diện tích tem | 0% | 87% | 87% | 0 | 0 |
| Chói 35% diện tích tem | 0% | 40% | 43% | 0 | 1 |
| Nhỏ 2,0 px/ô | 100% | 88% | 92% | 0 | 0 |
| Khó tổng hợp (mờ 1 ô, tối, chói 20%) | 0% | 45% | 32% | 0 | 0 |

Hai cột cuối cộng trên 1.200 lượt mỗi điều kiện (2 hạt giống × 2 giá trị k), tổng cộng 9.600 lượt mỗi cột.

**Kết luận từ số liệu:**

- **Nhận nhầm khi mã có trong danh sách: 0/9.600 lượt**, kể cả với 20 mã liền số luôn có mặt. Theo quy tắc ba, tỉ lệ nhầm trong điều kiện thử dưới khoảng 3/9.600 ≈ 1/3.200.
- **Cứu được tem mà zxing bỏ:** chói 20% từ 0% lên 87%; vệt mờ 1,6 ô từ 46% lên khoảng 90%. Tem hỏng quá 4 byte vẫn đối soát được.
- **Nên dùng sau bước đọc thường, không thay thế nó:** ở 2,0 px/ô zxing đọc 100% còn đối soát 88–92%. Chạy đọc thường trước, chỉ đối soát khi đọc thường thất bại, thì tổng hợp không mất lượt nào.
- **Lỗ hổng tìm ra và đã vá:** bản đầu (chưa có cổng 5) gán nhầm 3/80 lượt khi tem bị chói 20–35% và mã đúng không có trong danh sách, vì vùng chói che đúng chỗ khác biệt. Sau khi thêm cổng 5, con số còn **1/9.600**, xảy ra ở mức chói nặng nhất. Ngưỡng `max_mismatch` cũng phải hạ từ 20% xuống 10% vì mã liền số chỉ lệch nhau khoảng 22% số ô.
- **Gộp 3 frame chưa giúp** vì cách ước lượng ô hiện tại chỉ lấy trung bình; các frame có cùng vệt mờ và vùng chói nên không thêm thông tin.

**Giới hạn của thử nghiệm:**

- **Lạc quan:** vị trí lưới được coi là biết trước; trên ảnh thật phải khớp lưới (bộ giải B/C đã làm), và lỗi khớp lưới chưa được tính.
- **Bi quan:** ước lượng ô bằng lấy mẫu tâm ô, không khử mờ; ước lượng của bộ giải B/C tốt hơn.
- Ảnh tổng hợp, vùng chói mô hình hóa là ô vuông cháy trắng, mốc so sánh zxing 1 frame yếu hơn `PassDecoder` thật.
- 9.600 lượt mỗi cột không độc lập hoàn toàn (cùng cách sinh ảnh). Cần lặp lại trên video thật.

## 12. Lộ trình đề xuất

| Bước | Việc | Chi phí | Điều kiện sang bước sau |
|---|---|---|---|
| 0 | Sửa đèn, in đúng version 1 mức M, đặt exposure 3 ms | Thấp | Ảnh đạt yêu cầu mục 7.1 |
| 1 | Kiểm tra mọi lần đọc với danh sách mã; nhận lượt 1 lần đọc nếu mã có trong danh sách | Thấp | Có API danh sách mã từ server |
| 2 | Thử nghiệm offline trên QR tổng hợp (**đã làm**, mục 11) và trên video thật, có mã mồi | Thấp | Đo được tỉ lệ nhầm và tỉ lệ đọc thêm trên video thật |
| 3 | Đối soát theo ô trong tầng đọc nền, trạng thái tạm nhận | Trung bình | Tỉ lệ nhầm đạt mục tiêu trên dữ liệu thử |
| 4 | Đối chiếu và ghép cặp cuối khung giờ, phía server nhận/sửa kết quả suy luận | Trung bình | Hai bên thống nhất API |
| 5 | Chạy thử hiện trường, theo dõi mâu thuẫn mỗi khung giờ | Trung bình | Đạt mục tiêu đã chốt |

Bước 1 có lợi ngay cả khi các bước sau không làm: nó chặn đọc sai và cứu các lượt chỉ đọc được 1 lần.

## 13. Cần team quyết định

1. Ưu tiên chính xác hay ưu tiên đọc được nhiều? Nhầm 1 tem hậu quả ra sao?
2. Mục tiêu cụ thể, ví dụ: tỉ lệ gán nhầm dưới 1/10.000 lượt, tỉ lệ đọc được ≥ 99,5%.
3. Mã được sinh tuần tự hay ngẫu nhiên? Có bao nhiêu mã còn hiệu lực cùng lúc (số tấm/phút, số tem/tấm, số dây chuyền dùng chung)?
4. Tem có lên băng theo đúng thứ tự in không?
5. Phần mềm in tem có cố định được version 1, mức M, tách đoạn và mask không?
6. App lấy danh sách mã từ server bằng cách nào, xử lý ra sao khi mất mạng?
7. Có dùng người xác nhận cho tem khó không?

## Những điểm chưa kiểm chứng

- Tỉ lệ nhầm và tỉ lệ đọc thêm mới đo trên QR tổng hợp với vị trí lưới biết trước (mục 11), chưa đo trên video thật.
- Tốc độ chưa đo riêng: cả thử nghiệm 16 điều kiện × 300 lượt, mỗi lượt chấm 321 ứng viên hai lần, chạy trong vài phút trên CPU, nhưng chưa tính thời gian khớp lưới trên ảnh thật.
- Cơ chế tự phát hiện nhầm chỉ đúng nếu danh sách mã đầy đủ và mỗi mã chỉ được dán một lần.
