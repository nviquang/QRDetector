# Giải thích thuật toán B và C qua một lượt tem thật

> **Cấu hình cũ (trước 18/11/2026).** Tài liệu này lập theo thông số đã thay thế (tem 25/36 mm, camera cao 1 m, 0,673 mm/px, băng 100 mm/s, nội dung 12#12 hoặc version 1, một camera, máy CPU). Ràng buộc hiện hành: mục "Bài toán và ràng buộc" trong `README.md`. Kỹ thuật và tài liệu tham khảo vẫn dùng được, nhưng số px/ô và mọi đề xuất đổi tem, nội dung, version/mức sửa lỗi, camera, ống kính, line-scan, đầu đọc thương mại hay vị trí dán tem không còn áp dụng.

Tài liệu này chạy hai bộ đọc nền trên **một lượt tem thật**, lưu ảnh sau mỗi bước, rồi giải thích từng bước:

- **B**: `qr/solvers/grid_sr`, tái tạo mã trên lưới ô.
- **C**: `qr/solvers/preproc_sweep`, làm sạch ảnh rồi đọc bằng zxing/WeChat.

Trong sản phẩm (`combo_bc.py:ComboBC`), B chạy trước. Nếu B không chốt được mã thì mới chạy C.

Tạo lại toàn bộ ảnh và `summary.json` (khoảng 1 phút, chỉ dùng CPU):

```bash
python tools/explain_solvers.py --track xa_04 --cond goc --k 5 --seed 0 --out reports/giai_thich_BC
```

> **Lưu ý khi đọc ảnh.** `read_pass` thật dừng ngay ở bước đầu tiên chốt được mã. Script này cố ý chạy **mọi bước** để
> có ảnh của từng bước. Bước nào thật sự trả kết quả được ghi ở mục "Kết quả".

## Lượt mẫu

|                 |                                                                                                                                                       |
| --------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| Lượt            | `xa_04` trong tập phát triển của bộ chấm điểm (đoạn `xa`, băng lệch ra mép). Bộ chấm điểm gọi đây là "lượt khó thật": cascade chỉ đọc được 3/25 frame |
| Điều kiện       | `goc` (ảnh thật, không thêm mờ hay nhiễu), k = 5 crop, seed 0 → frame 467, 469, 477, 544, 555                                                         |
| Đáp án          | `000000585623` (QR version 1, 21×21 ô, mức sửa lỗi L)                                                                                                 |
| Crop            | khoảng 170×180 px, tem rộng khoảng 45 px, **2,16 px/ô**                                                                                               |
| Vận tốc         | (−0,11; −6,92) px/frame, tức tem chạy dọc lên trên                                                                                                    |
| Vệt mờ ước tính | 0,52 px (exposure 3 ms). Dưới 1 px nên bước khử mờ của C (sweep) bị bỏ qua                                                                            |

## Kết quả

|                                 | Kết quả                                               | Thời gian `read_pass` | Bước chốt mã                            |
| ------------------------------- | ----------------------------------------------------- | --------------------- | --------------------------------------- |
| Cách đọc thường (`PassDecoder`) | chỉ crop 0 đọc được → 1 phiếu, cần 2 → **không chốt** | —                     | —                                       |
| **B**                           | `000000585623` ✓                                      | 4,1 s                 | tái tạo + RS, qua cổng chống báo sai    |
| **C**                           | `000000585623` ✓                                      | 1,5 s                 | bước **warp** trên crop 1 → phiếu thứ 2 |

Trong `ComboBC`, lượt này được chốt sau B, khoảng 4 s. C không cần chạy.

---

## Bước 0 — Cách đọc thường (chung cho B và C)

![Bước 0](giai_thich_BC/00_crops_baseline.png)

**Cách làm:**

- Chạy `PassDecoder.read` trên từng crop: zxing 3 binarizer → warp → WeChat → Wiener → xếp chồng ROI.
- Cần 2 crop ra cùng nội dung mới chốt.

**Thấy gì trong ảnh:**

- Hàng dưới là vùng tem phóng to. Mỗi ô rộng chỉ khoảng 2 px, cạnh ô nhòe vào nhau.
- Ánh sáng không đều: góc trái-trên sáng, góc phải-dưới tối.
- Chỉ crop 0 đọc được. Crop 1–4 trông gần giống nhưng đều thất bại.

**Kết quả:** 1 phiếu chưa đủ để chốt. Nội dung `000000585623` được giữ làm `hint`. B dùng `hint` này để nới cổng chống báo sai; C không dùng.

---

## B — Tái tạo nhiều frame trên lưới ô

Ý tưởng: coi mã là một bảng N×N số `x` (1 = trắng, 0 = đen). Mô hình hóa vật lý từ `x` ra pixel: vị trí, nhòe quang học, vệt chuyển động, ánh sáng. Sau đó tìm `x` sao cho **mọi frame cùng khớp**, kèm điều kiện mỗi ô phải gần 0 hoặc 1. Cuối cùng B tự giải format và Reed–Solomon.

### B1a. Tìm finder, ghép bộ ba thành lưới

![B1a](giai_thich_BC/B1a_finders.png)

**Cách làm:**

- Dựng **mẫu finder** (khung 7×7 ô kèm 1 ô trắng quanh), đã làm mờ theo Gauss σ và vệt mờ, xoay theo cạnh `quad` của YOLO (−22°).
- Trượt mẫu trên crop, tính NCC. Ảnh 2: vùng sáng là chỗ giống finder.
- Lấy 8 đỉnh, xét mọi bộ ba. Bộ ba hợp lệ khi gần vuông góc, hai cạnh gần bằng nhau, đúng chiều quay, và khoảng cách khớp với 21/25/29 ô.

**Kết quả:**

- Ba bộ ba điểm cao nhất gần như trùng chỗ nhau.
- Hai bộ ba hiểu mã là V1, một bộ ba hiểu là V2, với điểm 2,06 / 2,04 / 2,04.
- Chỉ nhìn điểm finder thì **không phân biệt được version**.

### B1b. Tinh chỉnh góc, chọn giả thiết bằng độ chênh format, chọn σ

![B1b](giai_thich_BC/B1b_hypotheses_sigma.png)

**Cách làm:**

- Mỗi giả thiết (version + 4 góc) được tinh chỉnh 8 tọa độ góc bằng Levenberg–Marquardt. Mục tiêu là tối đa NCC giữa ảnh và mẫu các ô chức năng.
- Sau đó `quick_margin` giải nhanh x trên một frame và đo **độ chênh điểm giữa mã format tốt nhất và nhì**.

**Vì sao chọn theo độ chênh format:**

| giả thiết  | NCC hình học | độ chênh format   |
| ---------- | ------------:| -----------------:|
| V1, crop 2 | 0,524        | **1707,7** ← chọn |
| V2, crop 2 | 0,515        | 4,0               |
| V2, crop 1 | 0,510        | 1,1               |
| V2, crop 0 | 0,507        | 3,6               |
| V1, crop 1 | 0,487        | 1286,9            |
| V1, crop 0 | 0,410        | 61,7              |

- NCC của V1 và V2 chỉ chênh khoảng 0,01, không đủ để tin.
- Độ chênh format chênh tới **hàng trăm lần**. Lưới đúng làm 15 bit format khớp hẳn một mã hợp lệ; lưới sai cho format lộn xộn.

**Chọn σ (cột phải):**

- Thử σ ∈ {0,45 … 1,2 px}. NCC giảm dần theo σ, nên chọn **σ = 0,45 px**.
- Ảnh nét hơn dự đoán mặc định 0,75, khớp với việc vệt mờ ở mẫu này nhỏ (0,52 px).

### B1c. Căn lưới cho từng crop

![B1c](giai_thich_BC/B1c_align_frames.png)

**Cách làm:**

- Hàng trên (cam): chuyển lưới của crop 2 sang crop khác theo tâm bbox, dò lại 3 finder trong bán kính 14 px, dựng affine từ 3 điểm.
- Hàng dưới (xanh): tinh chỉnh LM như trên.

**Kết quả:**

- NCC sau tinh chỉnh từ 0,486 đến 0,524, đều cao hơn ngưỡng loại frame (cao nhất − 0,25).
- Cả 5 crop được đưa vào bài toán chung.

### B1d. Quét vị trí góc phải-dưới

![B1d](giai_thich_BC/B1d_search_corner.png)

**Vì sao cần:** 3 finder chỉ neo 3 góc. Góc phải-dưới phải suy ra, và tem nghiêng nhẹ (phối cảnh) làm góc này lệch.

**Cách làm:**

- Thử dịch góc thứ 3 một đoạn δ: lưới 5×5 bước 1,2 px, rồi 3×3 bước 0,5 px quanh điểm tốt nhất.
- Với mỗi δ, giải x trên 3 frame tốt nhất, chỉ dùng pixel vùng phải-dưới, rồi đo sai số mô hình.

**Kết quả:**

- Bản đồ sai số có đáy rõ ở giữa: **δ = (0; 0)**.
- Ở mẫu này góc từ bước trước đã đúng, nên lưới không đổi. Ở tem nghiêng nhiều hơn, bước này dịch góc vài pixel.

### B2. Mô hình quan sát

![B2](giai_thich_BC/B2_model.png)

Mỗi frame đóng góp các phương trình:

```
y(p) = b(p) + g(p) · (A·x)(p)
```

| ô trong ảnh | nghĩa                                                                                                  |
| ----------- | ------------------------------------------------------------------------------------------------------ |
| y           | khoảng 2650 pixel trong vùng mã (cộng ~2 ô viền) của mỗi frame                                         |
| x ban đầu   | ô chức năng (finder, timing, phân cách) biết trước, **cố định** (tô xanh); ô dữ liệu = 0,5 (chưa biết) |
| A·x         | ma trận thưa `A[p, m]` = phần PSF của pixel p rơi vào ô m. PSF = hộp pixel 1×1 ⊛ Gauss σ ⊛ vệt mờ      |
| b(p)        | nền/lóa, nội suy từ 3×3 nút: **3…9** mức xám                                                           |
| g(p)        | độ tương phản, nội suy từ 4×4 nút: **15…35** mức xám, sáng ở góc trái-trên, tối ở góc phải-dưới        |
| dự đoán     | b + g·A·x: finder và timing đã khớp ảnh, vùng dữ liệu còn xám vì chưa giải                             |

b và g được ước **chỉ từ pixel gần như chỉ phụ thuộc ô đã biết**, vì lúc này chưa biết ô dữ liệu.

Hai trường b, g cho thấy vì sao ngưỡng cố định thất bại ở tem này: nền trắng chỉ khoảng 40 mức xám, và độ tương phản giảm hơn một nửa từ góc này sang góc kia.

### B3. Giải x trên 5 frame

![B3](giai_thich_BC/B3_solve.png)

Bài toán:

```
min  Σ_frame ‖y − b − g·A·x‖² / σ²  +  μ · Σ x(1 − x),   0 ≤ x ≤ 1
```

Gộp 5 frame thành một bài toán toàn phương, giải bằng gradient chiếu có gia tốc Nesterov.

**Hàng trên — μ tăng dần.** Số hạng `x(1−x)` phạt ô có giá trị lưng chừng:

| μ (× trung vị đường chéo Q)                | 0   | 0,1 | 0,3 | 0,6 | 1,0 | 1,6 |
| ------------------------------------------ | ---:| ---:| ---:| ---:| ---:| ---:|
| ô dữ liệu còn lưỡng lự (\|x − 0,5\| < 0,3) | 27% | 12% | 3%  | 0%  | 0%  | 0%  |

- Với μ = 0 (bình phương tối thiểu thuần), nhiều ô xám, nhất là cột phải và hàng dưới, đúng vùng tối nhất.
- Tăng μ đẩy từng ô về 0 hoặc 1 **theo hướng dữ liệu nghiêng**. Đây là "tiên nghiệm nhị phân": biết trước mã chỉ có đen và trắng.

**Hàng dưới — 3 vòng ngoài:**

- Mỗi vòng khớp lại 4 góc, lần này dùng **toàn bộ x vừa giải** làm mẫu chứ không chỉ ô chức năng, nên nhiều ràng buộc hơn.
- Từ vòng 2 thêm **trường biến dạng 4×4 nút** cho tem cong hoặc nhăn. Mũi tên trong ảnh đã phóng ×10; dịch lớn nhất 0,33 ô, ở mép trên và góc phải.
- Phần dư y − dự đoán còn RMS 2,6 mức xám, nhỏ so với độ tương phản 15–35. Mô hình giải thích được gần hết ảnh.
- Ô "đối chứng: chỉ 1 frame" dùng cùng bộ giải. Ở mẫu này nó trông gần giống kết quả 5 frame. Lượt này đủ nét để một frame cũng gần đúng; lợi ích của nhiều frame lộ rõ hơn khi ảnh mờ hoặc nhiễu.

### B4. Chốt format

![B4](giai_thich_BC/B4_format.png)

**Cách làm:**

- `llr` của mỗi ô = chênh chi phí khi đặt ô đó đen so với trắng (các ô khác giữ nguyên). Trong ảnh trái, màu nhạt là ô không chắc.
- Chấm điểm 32 mã format hợp lệ trên **cả hai bản sao** (ảnh giữa).

**Kết quả:**

- **L0** (mức L, mask 0) được 9240,9. Mã nhì Q3 được 1745,7, tức thấp hơn 5,3 lần.
- H7 âm rất sâu vì là mã gần như đảo bit hoàn toàn của L0.

### B5. Nhị phân hóa và giải Reed–Solomon kiểu Chase

![B5](giai_thich_BC/B5_decode.png)

**Hàng trên:**

- Cố định 30 ô format theo L0, giải lại với μ lớn hơn.
- Ngưỡng 0,5, rồi chạy ICM (lật từng ô chừng nào còn giảm chi phí). Ở mẫu này ICM lật **0 ô**: kết quả giải đã ở cực tiểu cục bộ.
- Mask 0 (bàn cờ) được bỏ khỏi bit dữ liệu.

**Hàng dưới:**

- Đọc 208 bit theo thứ tự đặt bit của chuẩn QR, gom thành **26 codeword** (V1-L: 19 byte dữ liệu + 7 byte EC). Độ tin của byte = |LLR| nhỏ nhất trong byte.
- 8 byte yếu nhất (đỏ) đưa vào **Chase**: thử RS với mọi tổ hợp xóa trong 8 byte này, và xóa dần các byte yếu nhất.
- Thử thêm giả thiết vùng đệm: byte sau phần nội dung là `0xEC/0x11` luân phiên.

**Kết quả:**

- 48 ứng viên RS, chỉ **1** cho bản tin hợp lệ: `000000585623`.
- Ứng viên này chỉ cần sửa **3/208 bit**. 3 ô bị sửa (đỏ) nằm sát **góc phải-dưới**, vùng tối nhất và xa các finder nhất.
- Hai ứng viên kế tiếp phải lật 25 và 51 bit, và bản tin hỏng.

### B6. Cổng chống báo sai (`gate`)

| tiêu chí                               | ngưỡng     | giá trị                |     |
| -------------------------------------- | ---------- | ----------------------:| --- |
| format nhất / nhì                      | ≥ 1,4      | 5,29                   | ✓   |
| Δchi phí / điểm format                 | ≤ 0,6      | 0,0014                 | ✓   |
| tỉ lệ bit phải lật                     | ≤ 8,5%     | 1,4%                   | ✓   |
| khoảng cách tới ứng viên khác nội dung | ≥ 0,25     | không có đối thủ (9,9) | ✓   |
| byte đệm đúng                          | ≥ npad − 1 | 11/11                  | ✓   |

Qua đủ điều kiện "chắc chắn" mà **không cần** `hint`, dù `hint` cũng trùng. B trả `000000585623`.

---

## C — Làm sạch ảnh rồi đọc bằng zxing/WeChat

Ý tưởng: không tự giải mã. Thử nhiều cách biến crop thành một ảnh QR "dễ đọc", rồi đưa cho zxing (chỉ nhận khi còn ≥ 25% khả năng sửa lỗi) và WeChat CNN. Mỗi lần đọc được là 1 phiếu, cần 2 phiếu giống nhau.

Bước 0 giống hệt B, cho phiếu đầu tiên từ crop 0. Crop đã đọc thì `read_pass` bỏ qua ở các bước sau.

### C1a. Tìm tâm finder

![C1a](giai_thich_BC/C1a_finders.png)

**Cách làm:**

- Giống B nhưng thô hơn: mẫu finder mờ theo PSF vệt, thử **9 cỡ ô × 3 góc xoay** (−6°, 0°, +6° quanh góc của `minAreaRect`).
- Lấy cực đại cục bộ có NCC > 0,35, nội suy dưới pixel, giữ 8 điểm cách xa nhau.
- Ghép bộ ba tl/tr/bl theo tỉ lệ cạnh, góc gần vuông và chiều quay.

**Kết quả:** bộ ba tốt nhất nằm đúng 3 finder của tem chính, không bị tem bên cạnh kéo đi.

### C1b. Khớp lưới trên từng crop

![C1b](giai_thich_BC/C1b_grids.png)

**Cách làm:**

- Ước N ≈ khoảng cách finder / cỡ ô + 7 → **N = 21** ở cả 5 crop.
- Dựng góc bằng affine từ 3 tâm (cam), rồi Gauss–Newton 8 tham số (xanh), với Jacobian lấy từ gradient của mẫu đã warp.

**Kết quả:**

- NCC 0,86–0,88, đều trên ngưỡng 0,55, nên cả 5 crop có lưới.
- Con số này không so trực tiếp với NCC của B, vì C chỉ tính trên ô đã biết và dùng mẫu khác.

### C2. warp — bước chốt mã ở lượt này

![C2](giai_thich_BC/C2_warp.png)

**Cách làm:**

- Nắn mã về lưới vuông **8 px/ô**.
- Chuẩn hóa đen/trắng theo percentile của ô finder đen và trắng.
- Phủ viền trắng 4 ô làm quiet zone sạch, rồi đọc.
- Thử trên cả ảnh gốc và ảnh flat-field.

**Thấy gì:**

- So với crop gốc, ảnh warp đã thẳng, đủ tương phản và có viền trắng. Đây là ba thứ zxing cần.
- Ô vẫn còn dính nhau ở vùng dữ liệu bên phải.

**Kết quả:**

| crop               | 0                           | 1     | 2   | 3   | 4   |
| ------------------ | --------------------------- | ----- | --- | --- | --- |
| warp từ ảnh gốc    | ✓ (đã đọc ở bước 0, bỏ qua) | **✓** | —   | —   | —   |
| warp từ flat-field | —                           | ✓     | ✓   | —   | —   |

Trong `read_pass` thật, crop 1 đọc được ngay ở lần thử đầu, nên có **phiếu thứ 2**. C trả `000000585623` sau 1,5 s; log là `[('warp', 'warp')]`.

### C3. photo — chỉnh sáng và khử nhiễu

![C3](giai_thich_BC/C3_photo.png)

**Cách làm (crop 1):** tạo 4 biến thể, mỗi biến thể phóng ×4 rồi đọc:

- **flat-field**: chia cho nền sáng cục bộ (đóng hình thái cỡ ~3 ô rồi làm mượt), đưa nền trắng về 200;
- **gamma 0,6**;
- **khử nhiễu NLM**;
- **bilateral**.

**Kết quả:**

- Flat-field kéo tem và băng về cùng một mức sáng: góc tối hết tối.
- ff, gamma, nlm đọc được; bilateral thì không.
- Cả ba lần đọc đều do WeChat; zxing không đọc được biến thể nào.

**Phát hiện: bước này có thể đọc nhầm tem bên cạnh.**

- Trên **crop 0**, biến thể bilateral cho `000000585545`, **khác đáp án**.
- Kiểm tra vị trí WeChat trả về: tâm mã đọc được ở khoảng (110, 157) trong crop sau khi trừ phần viền đệm. Tâm tem đang đọc là (87, 92). Đó là **tem phía dưới**, lọt một phần vào crop (thấy rõ ở ảnh Bước 0).
- Nguyên nhân: bước photo đưa **cả crop** cho decoder. WeChat tự tìm QR nên đọc bất cứ mã nào trong ảnh, không chỉ tem trong `bbox`.
- Lần đọc sai này chỉ là 1 phiếu nên không được báo ở lượt mẫu. Nhưng nếu 2 crop cùng đọc trúng tem bên cạnh thì C sẽ báo sai mã.
- Hiện chưa có lọc nào chặn: cả B và C đều chưa kiểm tra vị trí mã đọc được so với `bbox`, và chưa lọc dạng `^\d{12}#\d{12}$`.

### C4. sweep — khử mờ theo độ dài vệt

**Bị bỏ qua ở lượt này**, vì vệt mờ ước tính 0,52 px < 1 px.

Khi vệt dài (băng nhanh hoặc exposure dài), bước này:

- phóng ×2;
- khử mờ Wiener với 5 độ dài vệt (×1,0 / 0,94 / 0,88 / 0,82 / 1,06) × 2 mức k;
- xếp hạng 10 ảnh theo độ khớp ô chức năng;
- đọc 4 ảnh đầu.

Muốn có ảnh của bước này, chạy script với `--cond mo` (thêm vệt 4 px).

### C5. lsq — giải giá trị ô rồi vẽ lại mã sạch

![C5](giai_thich_BC/C5_lsq.png)

**Cách làm (crop 1):** gần giống bài toán của B nhưng đơn giản hơn:

- PSF cố định (Gauss 0,7, không chọn σ).
- Ánh sáng tuyến tính theo mặt phẳng (6 tham số) thay vì lưới nút.
- Không tự giải mã: ô đã biết được ghim về khuôn, ô dữ liệu được kéo dần về bản "đẩy về 0/1" của vòng trước.

**Hàng trên — 4 vòng:**

- Phần dư giảm từ 0,056 xuống 0,014 sau vòng 2, rồi đứng yên.
- Khác với B, **nhiều ô vẫn xám** sau 4 vòng, nhất là nửa phải. Lực kéo về 0/1 ở đây yếu hơn số hạng μ·x(1−x) của B.

**Hàng dưới:**

- Phần dư bằng nhau ở mọi hệ số độ dài vệt, vì vệt chỉ 0,52 px nên kernel gần như không đổi.
- `render_hard` (ngưỡng 0,5, vẽ 8 px/ô) cho một mã sạch nhưng **zxing không đọc được**: còn quá nhiều ô sai so với khả năng sửa lỗi.
- **dd** khớp lại góc theo mọi ô vừa quyết định, làm đổi màu 7 ô ở góc phải-dưới, nhưng vẫn chưa đủ.

### C6. joint — gộp phương trình của nhiều crop

![C6](giai_thich_BC/C6_joint.png)

**Cách làm:** đưa phương trình của cả 5 crop (mỗi crop giữ lưới riêng) vào cùng bài toán lsq.

**Kết quả:**

- Gộp 5 crop **không làm ô rõ hơn bao nhiêu**: vùng phải-dưới vẫn nhiều ô xám, có chỗ còn xám hơn bản 1 crop. Một khả năng (chưa kiểm chứng) là lưới của từng crop lệch nhau một chút, nên các phương trình kéo cùng một ô về các hướng khác nhau.
- Vẽ lại vẫn không đọc được.
- So với B3, khác biệt chính là thiếu tiên nghiệm nhị phân đủ mạnh, và thiếu bước sửa lỗi tự làm có tính độ tin từng bit (Chase).

### C7. stack — xếp chồng rồi khử mờ

![C7](giai_thich_BC/C7_stack.png)

**Hàng trên — căn theo lưới:**

- Warp từng crop (đã flat-field) về lưới 8 px/ô, rồi lấy trung bình 5 ảnh.
- Ảnh trung bình mịn hơn, ít hạt hơn từng ảnh, nhưng cạnh ô vẫn nhòe.
- Wiener làm ảnh xám đi chứ không nét lên, vì vệt mờ thật gần bằng 0 nên mô hình khử mờ không đúng.

**Hàng dưới — căn theo vận tốc:**

- Dịch các crop về tọa độ crop cuối theo `origin + v·Δframe`, tinh chỉnh bằng phase correlation.
- Chỉ **2/5 crop** được giữ: các crop xa nhau tới 88 frame (467 → 555) nên phase correlation bị loại vì độ tin thấp hoặc lệch > 12 px.

**Kết quả:** không đọc được.

---

## Tóm tắt từ lượt mẫu

1. **B thắng nhờ hai thứ C không có.**
   - Tiên nghiệm nhị phân đủ mạnh: 27% ô lưỡng lự về 0% (B3).
   - Tự giải RS có tính độ tin từng bit: chỉ cần sửa 3 bit ở vùng yếu nhất (B5).
   - Các bước giải ô của C (lsq, joint) để lại nhiều ô xám và zxing không đọc được.
2. **Chọn version bằng độ chênh format (B1b) là mắt xích quan trọng.** NCC hình học của V1 và V2 gần như bằng nhau; độ chênh format thì khác nhau hàng trăm lần.
3. **C đọc được lượt này chỉ nhờ bước rẻ nhất (warp).** Nắn thẳng và thêm viền trắng là đủ cho crop 1, dù cascade của `PassDecoder` (có warp riêng) đã thất bại trên chính crop này. Khác biệt nằm ở lưới: C khớp lưới bằng finder + Gauss–Newton, còn `PassDecoder` warp theo `quad` của YOLO.
4. **Rủi ro báo sai ở C:** bước photo (và các bước đọc cả crop) có thể đọc tem bên cạnh (C3). Cần lọc vị trí mã đọc được so với `bbox`, hoặc lọc dạng nội dung tem.
5. **Giới hạn của lượt mẫu:**
   - Vệt mờ nhỏ (0,52 px) nên bước sweep không chạy, và Wiener ở bước stack không giúp được.
   - Góc phải-dưới đã đúng ngay nên B1d không dịch.
   - Một lượt không đại diện cho tỉ lệ đọc. Số liệu tổng hợp xem `reports/So sánh chất lượng các hướng đọc QR.md`.
