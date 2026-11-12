# Plan sửa tài liệu theo thông số thực tế

Ngày lập: 12/11/2026. Mục tiêu: mọi tài liệu đang dùng (README, CLAUDE.md, tài liệu thử nghiệm, kịch bản hiện trường) nói cùng một bộ thông số đúng với thực tế. Tài liệu lịch sử giữ nguyên nội dung, chỉ thêm ghi chú để người đọc không lấy số cũ.

## 1. Bộ thông số chuẩn (nguồn duy nhất)

Đặt thành một mục mới trong `README.md` ("Thông số hiện trường và tem"). Các tài liệu khác dẫn tới mục này thay vì chép lại số.

| Hạng mục | Giá trị | Trạng thái | Nguồn |
|---|---|---|---|
| Tem | **36 × 36 mm** phần đen (không phải 25 mm), không tăng được | Đã chốt | Người dùng |
| Nội dung | **12 chữ số + `#` + 12 chữ số**, 25 ký tự, ví dụ `111111111111#111111111111` | Đã chốt | Người dùng |
| Quy cách mã đề xuất | **V1-M**, mã hóa tách đoạn số / byte / số (128 bit) | **Chờ chốt** | Đã kiểm bằng `segno` + zxing |
| Phương án thay thế | Bỏ `#` (24 chữ số) → **V1-Q**, phía đọc tự chèn `#` | **Chờ chốt** | Như trên |
| Tem đang có ở phòng thí nghiệm | Lẫn V1–V3, mức L/M/Q/H (in mặc định ở chế độ byte) | Đo được | Bộ chấm 78 lượt |
| Camera hiện trường | Basler a2A2840-48umBAS, 2856 × 2848 px, 2,74 µm | Đã chốt | |
| Ống kính, độ cao, vùng đọc | 4 mm f/4, cao 1 m, vùng 1,6 × 0,6 m | Đã chốt | |
| Độ phân giải | 0,673 mm/px; V1 2,57 px/ô, V2 2,16, V3 1,86 | Đo được | `check_setup.py`, bộ chấm |
| Băng, exposure, gain | 100 mm/s; exposure 3 ms; gain 6 dB (nền trắng tem còn tối, 53–73/255) | Đo được | Video 06/11 |
| Máy xử lý | Chỉ CPU ở hiện trường (GPU chỉ có ở máy phát triển) | Đã chốt | Người dùng |
| Đọc nền lượt khó | B rồi C (`qr/solvers`), chỉ trong `main_basler.py` | Đã merge `f5e6123` | |

Cấu hình MindVision 2448 × 2048 với tem 25 mm và khoảng 0,43 mm/px là **phòng thí nghiệm cũ**. Giữ trong tài liệu lịch sử, không dùng làm số hiện tại.

## 2. Phân loại tài liệu

### A. Tài liệu đang dùng: sửa nội dung

| File | Chỗ sai / thiếu | Sửa |
|---|---|---|
| `README.md` | Tiêu đề và giới thiệu chỉ nói MindVision; không có thông số tem; bản Basler ghi "exposure mặc định 12,9 ms" (đúng với code nhưng khác cấu hình chuẩn 3 ms); chưa có đọc nền | Thêm mục bộ thông số chuẩn (§1); giới thiệu cả Basler; ghi rõ exposure khuyến nghị 3 ms ở 100 mm/s; thêm đoạn ngắn về đọc nền và `QR_FALLBACK=off`; thêm `experiments/live_methods.py` vào công cụ nếu commit |
| `CLAUDE.md` | "tối ưu cho QR nhỏ ~60px trên frame 2448×2048"; "Tem không có định dạng cố định nên không lọc nội dung" | Cập nhật QR ~54 px trên dải Basler, 1,9–2,6 px/ô tùy version; ghi định dạng nội dung đã biết; quyết định về lọc nội dung theo §3 |
| `experiments/README.md` | Số đo cũ (MindVision, tem 25 mm, exposure 12,9 ms) không có ghi chú phạm vi | Thêm đoạn đầu: số liệu thuộc phòng thí nghiệm cũ, dẫn tới `reports/So sánh chất lượng các hướng đọc QR.md` cho cấu hình hiện tại |
| `experiments/benchmark_standard.md` | "Tem: version 1, mức L" | Đổi thành quy cách mã ở §1 và ghi rõ phải ép mã hóa tách đoạn khi in |
| `experiments/bench/BRIEF.md` | "QR version 1 mức L (21×21 ô, một số mã version 2)" | Đổi thành V1–V3, mức L–H, kèm px/ô từng version |
| `reports/Plan nghiên cứu thuật toán đọc QR.md` | §0 "QR version 1 mức L, nội dung 12 chữ số"; đòn bẩy "12 chữ số vừa V1-H" | Sửa theo nội dung 12#12: V1-M (tách đoạn) hoặc V1-Q (bỏ `#`); V1-H không vừa |
| `reports/Độ khả thi thuật toán đọc QR.md` | "QR 36 mm version 1 mức L" ở kết luận | Thêm một dòng đính chính về loại tem và nội dung |
| `reports/Kịch bản kiểm thử hiện trường.docx` | Bảng 2 tính cho "QR 25 mm, version 1": 1,4 px/ô, cần ≥ 71 mm cho 4 px/ô; đường chéo QR 25 mm | Tính lại với tem 36 mm và V1-M; kiểm tra các bảng exposure theo mm/px đúng của camera dùng. **File được tạo ngày 12/11, có thể đang được sửa ở chỗ khác: xác nhận trước khi sửa** |

### B. Tài liệu lịch sử: giữ nguyên, thêm ghi chú đầu file

Một dòng: *"Tài liệu ghi theo cấu hình tại thời điểm viết (MindVision, tem 25 mm). Thông số hiện tại: README.md, mục Thông số hiện trường và tem."*

- `docs/DE_XUAT_KHAC_PHUC.md`
- `docs/plans/2026-10-24-qr-decode-bang-chuyen.md`
- `docs/plans/2026-10-26-plan-thi-nghiem-lab.md`
- `docs/plans/2026-10-26-sua-thuat-toan-decode-bang-chuyen.md`
- `docs/plans/2026-10-31-tang-toc-decode.md`
- `docs/specs/2026-10-19-solution-camera-qr-design.md`
- `docs/specs/2026-11-02-solution-demo-ui-design.md` (nếu có số tem/camera cũ)
- `reports/Phương pháp đọc QR nhỏ mờ.md` (tiêu đề "tem 25 mm chỉ được 2 px/ô"; phần nghiên cứu vẫn đúng, chỉ phần hình học là của cấu hình cũ)
- `research_notes/Phương pháp đọc QR nhỏ mờ/` (ghi chú nguồn, không sửa)

### C. Đã đúng, không sửa

- `reports/Kết quả thử nghiệm thuật toán đọc QR.md` (đã có đính chính về loại tem)
- `reports/So sánh chất lượng các hướng đọc QR.md`
- `reports/Lệnh chạy app theo thuật toán.md`: chỉ cần ghi chú rằng `main_basler.py` ở thư mục gốc nay đã là B+C, muốn chạy mốc phải đặt `QR_FALLBACK=off`

## 3. Quyết định cần người dùng chốt trước khi sửa

1. **Quy cách in tem:** V1-M giữ `#` (tách đoạn), hay V1-Q bỏ `#` và phía đọc tự chèn. Quyết định này đổi nội dung §1, benchmark và kịch bản hiện trường.
2. **Exposure mặc định của bản Basler:** code đang là 12,9 ms (thừa kế từ bản MindVision). Hoặc đổi mặc định code sang 3 ms, hoặc chỉ ghi khuyến nghị trong tài liệu. Đổi code là thay đổi riêng, ngoài plan này.
3. **Lọc nội dung:** định dạng đã biết là `^\d{12}#\d{12}$`. Bật `code_pattern` sẽ loại phần lớn mã đọc sai (code, ngoài plan này) và tài liệu cần đổi theo. Nếu chưa bật thì tài liệu chỉ ghi định dạng.
4. **Các file chưa commit** (`reports/`, `experiments/bench/`, `experiments/live_methods.py`, benchmark, plan này): có commit cùng đợt sửa tài liệu không.

## 4. Thứ tự làm và kiểm tra

1. Chốt §3.
2. Viết mục bộ thông số chuẩn trong `README.md`.
3. Sửa nhóm A theo bảng, bắt đầu từ `CLAUDE.md` và `README.md`.
4. Thêm ghi chú nhóm B.
5. Sửa `Kịch bản kiểm thử hiện trường.docx` sau khi xác nhận không ai đang sửa file này.
6. Kiểm tra:
   - Tìm lại các cụm `25 mm`, `25 × 25`, `version 1, mức L`, `V1-L`, `~60px`, `12,9 ms`, `định dạng cố định` trong tài liệu nhóm A. Mỗi kết quả còn lại phải là số lịch sử có ghi rõ.
   - Đường dẫn và lệnh trong tài liệu chạy được.
   - Chạy lại bộ test (tài liệu không ảnh hưởng code, chỉ để chắc không đụng nhầm file).
7. Commit tài liệu nếu được đồng ý (một commit riêng, không lẫn code).
