# EDA dữ liệu hiện trường (06/11 và 13/11/2026) và đề xuất làm sạch

> **Cấu hình cũ (trước 18/11/2026).** Tài liệu này lập theo thông số đã thay thế (tem 25/36 mm, camera cao 1 m, 0,673 mm/px, băng 100 mm/s, nội dung 12#12 hoặc version 1, một camera, máy CPU). Ràng buộc hiện hành: mục "Bài toán và ràng buộc" trong `README.md`. Kỹ thuật và tài liệu tham khảo vẫn dùng được, nhưng số px/ô và mọi đề xuất đổi tem, nội dung, version/mức sửa lỗi, camera, ống kính, line-scan, đầu đọc thương mại hay vị trí dán tem không còn áp dụng.

Dữ liệu: 5 thư mục pylon ban đầu (`cheo/`, `gan/`, `xa/`, `xuong1/`, `xuong2/`), tổng 9.808 file TIFF, 47 GB. Từ
14/11/2026 toàn bộ nằm ở `data/field/raw/` (bản duy nhất, không có trên git; nên sao lưu ra ổ khác) và 5 thư mục cũ đã
bị xóa; tên file gốc tra theo cột `orig_dir`/`orig_name` của manifest. Các tên thư mục cũ trong báo cáo dưới đây là
nơi dữ liệu nằm lúc làm EDA.
Hình và manifest từng frame: `reports/eda_2026-11/` (`frames_manifest.csv`: đường dẫn, phiên quay, thời điểm ghi,
độ sáng, cháy sáng, độ nét, số QR phát hiện/đọc được, nội dung).

Cách đo: đọc toàn bộ frame (độ sáng TB, % pixel ≥250, phương sai Laplacian ở 1/2 độ phân giải, thumbnail 1/8 để tính
chênh lệch giữa hai frame liền nhau và so với nền median); chạy `ImprovePipeline(multi_frame=False)` (YOLO
imgsz 1280 + cascade từng frame) trên mọi frame của ngày 13/11 và 1/3 số frame ngày 06/11.

## 1. Các video KHÔNG bị trộn lẫn: tên file đã tách được

Tên file Basler có dạng `Basler_a2A2840-48umBAS__42023350__<YYYYMMDD_HHMMSSmmm>_<số thứ tự>.tiff`. Phần
`<YYYYMMDD_HHMMSSmmm>` là **thời điểm bắt đầu một lần ghi**, số thứ tự chạy lại từ 0000 cho mỗi lần ghi. Mỗi tiền
tố là một video riêng: số thứ tự liên tục, không thiếu số nào, thời điểm ghi file (mtime) tăng đơn điệu. Như vậy
13 video tách được hoàn toàn theo tiền tố, không cần đoán theo nội dung ảnh.

| Thư mục | Video (tiền tố) | Frame | Kích thước | Thời lượng | fps ghi | Nội dung |
|---|---|---:|---|---:|---:|---|
| cheo | 20261106_173102461 | 1679 | 1792×992 | 67 s | 25,0 | Phòng thí nghiệm, băng đen chéo, tem thử 8 mã |
| gan | 20261106_172658547 | 1743 | 1792×992 | 70 s | 25,0 | Phòng thí nghiệm, băng dọc gần |
| xa | 20261106_172246399 | 1615 | 1792×992 | 65 s | 25,0 | Phòng thí nghiệm, băng dọc xa |
| **cheo** | **20261113_111206382** | 56 | 2856×2848 | 2,7 s | 20,7 | **Xưởng, đứng yên**, 2 tem thật đọc được 56/56 |
| **cheo** | **20261113_132745078** | 741 | 2856×2848 | 48 s | 15,7 | Xưởng, không có tem (có vệt phản xạ kính), đổi exposure ở frame 259 và 324 |
| **cheo** | **20261113_132944090** | 184 | 2856×2848 | 11 s | 16,9 | Xưởng, không có tem (có vệt phản xạ kính) |
| xuong1 | 20261113_133123291 | 1602 | 2856×2848 | 97 s | 17,0 | Xưởng chạy; tem chỉ ở frame 1447–1551 |
| xuong2 | 20261113_133521948 | 313 | 2856×2848 | 20 s | 16,7 | Có tem ở frame 0–162 (bắt đầu giữa lượt) |
| xuong2 | 20261113_133546659 | 266 | 2856×2848 | 18 s | 15,9 | Có tem ở frame 0–41 |
| xuong2 | 20261113_133640302 | 563 | 2856×2848 | 42 s | 15,1 | Con lăn trống, 0 phát hiện |
| xuong2 | 20261113_133735410 | 246 | 2856×2848 | 16 s | 15,8 | Có tem ở frame 4–170 |
| xuong2 | 20261113_133806945 | 204 | 2856×2848 | 15 s | 15,3 | Có kính, 0 phát hiện |
| xuong2 | 20261113_134415246 | 596 | 2856×2848 | 50 s | 14,4 | **Camera bị dịch** (~36 px), có kính, 0 phát hiện |

Nhận xét:

- **Ba video của ngày 13/11 (981 frame, 8 GB) nằm nhầm trong `cheo/`**, chung thư mục với video phòng thí nghiệm
  06/11. Ảnh đứng yên duy nhất ở xưởng là `cheo/…20261113_111206382_*` (56 frame), không có thư mục `xuong/`.
- `xuong2` gồm 6 lần ghi ngắn nối tiếp nhau (cách nhau 4–40 s, riêng lần cuối cách 6 phút). Một lượt kính có thể
  bị cắt ngang giữa hai lần ghi (133521948 bắt đầu khi tem đã ở trong khung).
- mtime là lúc file được ghi xuống đĩa, không phải lúc chụp. Ngày 06/11 ghi đều 25 fps (ROI nhỏ). Ngày 13/11 ảnh
  toàn khung 8 MB nên chỉ ghi được 14–17 fps, khoảng cách giữa hai frame dao động 40–150 ms, có lúc ngắt 0,3–1,2 s
  (16 lần). Rất có thể camera chụp nhanh hơn và frame bị bỏ khi ghi đĩa không kịp: **khoảng cách thời gian giữa hai
  frame không đều và không biết chính xác**, không được giả định fps cố định khi tính vận tốc/vệt mờ.

## 2. Chất lượng ảnh

| Nhóm | Độ sáng TB (0–255) | % cháy sáng | Độ nét (var Laplacian) | Ghi chú |
|---|---:|---:|---:|---|
| Phòng thí nghiệm 06/11 | 43–46 | 0,04 | 46–76 | Ổn định, tem nét |
| Xưởng đứng yên | 12,7 | 0,1 | 17 | Rất tối nhưng tem đọc được |
| Xưởng chạy | 20–34 | 0–1,3 | 10–34 | Tối, kính phản xạ đèn gây cháy sáng cục bộ |

- **Bối cảnh xưởng khác hẳn phòng thí nghiệm**: tem dán trên **tấm kính** chạy trên con lăn. Kính phản xạ đèn trần
  (dải trắng phía trên, vạch trắng đứt đoạn, vệt sáng dọc) và tạo bóng mờ chồng lên nền. Đoạn có kính đi qua làm độ
  sáng TB tăng 4–6 mức và tỉ lệ khác nền tăng mạnh (`chuoi_thoi_gian.png`).
- **Điểm đổi cấu hình trong video** (`diem_doi.png`): `cheo/132745078` frame 259–324 sáng gấp ~1,5 lần (đổi
  exposure/gain rồi trả lại); `xuong2/134415246` camera bị xê dịch và từ frame ~525 ảnh thay đổi liên tục.
- **Mờ chuyển động rất nặng** (`cat_qr.png`, hàng dưới): tem đi theo trục dọc ảnh, 9,5–18 px/frame ghi
  (`xuong1` ~18, `xuong2` ~12). Vệt mờ dọc ước lượng bằng mắt 10–20 px trong khi một ô QR chỉ ~2,3 px. Exposure lúc
  quay quá dài so với tốc độ băng (có thể AE đang bật). Một số crop cháy sáng trắng hoàn toàn khi tem nằm dưới vệt
  phản xạ.
- QR trên tem: cạnh ~55–75 px (trung vị 60), khoảng 25 ô (version 2), ~2,3 px/ô. Mỗi tem có thể có hơn một QR.

## 3. Kết quả đọc QR bằng pipeline hiện tại

| Nhóm | Frame quét | Frame có phát hiện | Phát hiện | Đọc được |
|---|---:|---:|---:|---:|
| Phòng thí nghiệm 06/11 | 1.680 | 84 % | 3.992 | 3.795 (95 %) |
| Xưởng đứng yên | 56 | 100 % | 112 | 112 (100 %) |
| Xưởng chạy (7 video) | 3.790 | 12 % (khoảng 470 frame) | 456 | **1** |
| Xưởng không có tem (2 video, cheo) | 925 | 0 | 1 (nhầm) | 0 |

Bảng trên chỉ dùng cascade từng frame (`multi_frame=False`: phóng ROI/CLAHE/stretch → zxing/WeChat), là mức thấp
nhất. Chạy lại bằng thuật toán đầy đủ của `main_basler.py`:

- `PassReader(multi_frame=True)` (PassDecoder: xếp chồng ROI, Wiener theo vận tốc) cho mọi frame có tem, đồng hồ lấy
  từ mtime, exposure không biết (thử vệt 2/3/4,5/6,5 px như app). Lượt nào PassDecoder không đọc được thì lấy 5 crop
  trải đều mà PassReader định gửi đi, rồi chạy `ComboBC` (B = `grid_sr`, rồi C = `preproc_sweep`) trực tiếp, lần
  lượt với `blur_px` = 0, 6, 10, 14, 18 px (exposure thật không biết nên phải quét).

| Video | Frame | Lượt | PassDecoder | ComboBC (5 mức vệt mờ) | Vận tốc tracker | Cạnh QR |
|---|---|---:|---:|---|---:|---:|
| cheo/111206382 (đứng yên) | 0–55 | 2 | **2/2** | (không cần; thử riêng: B đọc được cả 2) | 0 | ~58 px |
| xuong1/133123291 | 1400–1601 | 1 | 0 | 0/5, 15–92 s mỗi lần | 12,4 px/seq | ~81 px |
| xuong2/133521948 | 0–200 | 1 | 0 | 0/5, 25–113 s | 7,5 px/seq | ~60 px |
| xuong2/133546659 | 0–80 | 1 | 0 | 0/5, 24–56 s | 7,6 px/seq | ~83 px |
| xuong2/133735410 | 0–200 | 1 | 0 | 0/5, 8–38 s | 7,8 px/seq | ~54 px |

Kết luận: **cả B và C đều không đọc được lượt nào khi băng chạy**, kể cả khi cho đúng hướng chuyển động và quét vệt mờ
tới 18 px. Harness hoạt động đúng: cùng cách gọi, B đọc ngay cả 2 tem đứng yên. Như vậy giới hạn nằm ở ảnh chụp
(exposure quá dài so với tốc độ, ô QR ~2,3 px), không phải do bỏ sót bước giải.

**Tem thật có hai QR, YOLO chỉ bắt được một phần** (`hai_tem_mot_phat_hien.png`, `tem_qr_nho_khong_phat_hien.png`, frame `xuong2/133521948_0031`): mỗi tem có một
QR lớn (~60 px) và một QR nhỏ (~25 px), có tem dán ngược chỉ có QR nhỏ trong khung. Ở mọi frame có tem của 4 video
chạy, YOLO chỉ trả **đúng 1** phát hiện (QR lớn của một tem). QR nhỏ và tem thứ hai không được phát hiện lần nào.
Với QR ~25 px (khoảng 1 px/ô), kể cả khi ảnh nét cũng khó đọc. Cần hỏi khách hàng mã nào là mã cần đọc và hai QR có
cùng nội dung không.

- Ở xưởng lúc băng chạy, YOLO vẫn tìm được QR lớn (độ tin cậy ~0,78), nhưng mọi bộ đọc đều thất bại: vấn đề nằm ở
  **ảnh chụp** (exposure, phản xạ), không phải ở bước detect.
- **Định dạng nội dung thật khác định dạng đã chốt.** Ba mã thật đọc được: `06000040000400#111111111111`,
  `18000090001000#000000001612`, `09000060000500#000000001610`, tức **14 số `#` 12 số**, không khớp
  `^\d{12}#\d{12}$` trong CLAUDE.md/README. Nếu bật `code_pattern` theo định dạng cũ thì mọi mã thật sẽ bị loại.
  Tem thử ngày 06/11 là mã giả (`111111111111#111111111111`, `444444444444#4444…`, `000000585546`…), không phản ánh
  định dạng thật.
- Tỉ lệ dữ liệu có ích của 13/11: khoảng 470/4.771 frame (~10 %) có tem, ~4,3 GB/39 GB. Phần còn lại là con lăn
  trống hoặc kính không có tem.

## 4. Đề xuất làm sạch

Nguyên tắc: **không sửa và không xóa thư mục gốc** cho tới khi bộ đã làm sạch được kiểm tra; ổ C còn 68 GB trống
(86 % đã dùng) nên tránh sao chép nguyên 47 GB.

### Bước 1. Tổ chức lại theo lần ghi (không cần thuật toán)

Tách theo tiền tố tên file thành `data/field/<ngày>/<tiền tố>/frame_<số thứ tự>.tiff`, bằng `move`/hard link (cùng ổ
đĩa nên không tốn thêm dung lượng). Ba video ngày 13/11 trong `cheo/` chuyển về nhóm xưởng. Mỗi video có file
`meta.json` ghi: bối cảnh (`lab_cheo`/`lab_gan`/`lab_xa`/`xuong_tinh`/`xuong_chay`), kích thước, fps ghi, các khoảng
ngắt, camera/ống kính/khoảng cách, exposure/gain nếu còn nhớ hoặc còn file `.pfs`. Thư mục `data/` cho vào
`.gitignore`.

### Bước 2. Gắn nhãn từng đoạn trong video

Dùng `frames_manifest.csv` (đã có sẵn số phát hiện mỗi frame) để chia mỗi video thành các đoạn:

| Nhãn đoạn | Tiêu chí | Dùng cho |
|---|---|---|
| `pass` | Chuỗi frame liên tiếp có phát hiện, cho phép hở ≤6 frame, dài ≥3 frame; thêm 10 frame đệm mỗi đầu | Benchmark đọc theo lượt (`PassDecoder`), huấn luyện/kiểm tra |
| `glass_no_label` | Có kính (tỉ lệ khác nền cao) nhưng không phát hiện tem | Đo báo nhầm, nền khó |
| `empty` | Con lăn trống, khác nền ≈ 0 | Giữ 50–100 frame mỗi video làm mẫu âm/nền, bỏ phần còn lại |
| `config_change` | Bước nhảy độ sáng >3 mức (cheo/132745078 frame 259–324) hoặc camera dịch (134415246 từ frame ~525) | Tách thành đoạn riêng; không trộn vào phép đo vận tốc |
| `static` | 56 frame đứng yên gần như giống hệt nhau | Giữ 1–3 frame làm ảnh chuẩn, không tính như 56 mẫu độc lập |

Mỗi đoạn `pass` lưu `start_idx`, `end_idx`, số tem, vận tốc ước lượng (px/frame ghi) và cờ `cut_at_start` hoặc
`cut_at_end` khi lượt chạm đầu/cuối video (133521948, 133546659).

### Bước 3. Nhãn đáp án (ground truth)

Pipeline hiện tại chỉ đọc được 1 trong khoảng 470 frame chạy, nên **không thể tự sinh nhãn nội dung** cho dữ liệu
chạy. Hướng làm:

1. Mỗi lượt lấy frame nét nhất (var Laplacian cao nhất trong vùng tem) và gán nội dung bằng tay. Nếu có danh sách
   mã của lô kính hôm 13/11 thì đối chiếu, nếu không thì ghi `unknown` (vẫn dùng được để đo tỉ lệ phát hiện).
2. Nhãn theo tem chứ không theo frame: `pass_id`, `label_id`, `text`, bbox ở frame đầu/cuối.
3. Cập nhật định dạng mã thành `^\d{14}#\d{12}$` (cần xác nhận lại với khách hàng) trước khi bật `code_pattern`.

### Bước 4. Giảm dung lượng (tùy chọn, không mất thông tin)

- TIFF không nén → PNG nén mức 3: 8,15 MB còn 3,35 MB mỗi frame (−59 %), không mất dữ liệu.
- Với các đoạn `pass`, có thể lưu thêm bản cắt dải dọc theo vùng tem đi qua (toàn bề rộng × vùng y có tem) để
  benchmark nhanh, giữ ảnh toàn khung làm bản gốc.
- Sau bước 1–2: giữ khoảng 470 frame có tem + 1.000 frame nền thay vì 4.771, tức còn khoảng 5 GB (TIFF) hoặc 2 GB
  (PNG) cho dữ liệu xưởng.

### Bước 5. Kiểm tra sau khi làm sạch

- Tổng số frame trước = sau + số đã bỏ có chủ đích; mỗi video giữ số thứ tự gốc (không đánh lại số) để truy ngược.
- Chạy lại `ImprovePipeline` và `PassReader(multi_frame=True)` trên bộ đã làm sạch, số phát hiện mỗi đoạn `pass`
  phải khớp manifest.

### Đã làm (14/11/2026): `python tools/clean_field_data.py`

Script đọc `reports/eda_2026-11/frames_manifest.csv`, ghi ra `data/field/` (đã thêm `data/` vào `.gitignore`).
Ban đầu mọi ảnh là hard link tới TIFF gốc. Sau khi kiểm tra từng file (cùng dữ liệu trên đĩa, cùng kích thước),
5 thư mục cũ đã bị xóa: **`data/field/raw/` giờ là bản duy nhất, tuyệt đối không xóa**. Chạy lại script an toàn: nó
không đụng tới `raw/` (trừ cập nhật `meta.json`, giữ các trường exposure/gain/ống kính/khoảng cách đã điền), chỉ dựng
lại `curated/` (hard link tới `raw/`, kiểm tra còn bản ở `raw/` trước khi xóa), ảnh cắt và các CSV; cột điền tay của
`labels/passes.csv` được giữ (dòng không còn khớp lượt nào giữ lại với `label=orphan`). `run_bc.py` và
`experiments/bench/build.py` (clip `gan`/`xa`/`cheo`) đã chuyển sang đọc từ `raw/`.

| Đầu ra | Nội dung |
|---|---|
| `raw/<tiền tố>_<bối cảnh>/frame_NNNN.tiff` | 13 lần ghi, 9.808 frame, giữ số thứ tự gốc; `meta.json` mỗi lần ghi (bối cảnh, tư thế camera A/B, fps ghi, các lần ngắt ghi, điểm đổi exposure; exposure/gain/ống kính/khoảng cách để `null` chờ điền) |
| `frames.csv` | Nhãn từng frame + đường dẫn gốc, độ sáng, % cháy sáng, phát hiện/nội dung |
| `segments.csv` | 38 đoạn: 10 `pass`, 12 `glass_no_det`, 14 `empty`, 1 `static`, 1 `config_change` |
| `curated/…`, `curated.csv` | 6.467 frame: 4.887 lượt (kèm 10 frame đệm), 765 kính không phát hiện, 747 nền trống, 65 đổi cấu hình, 3 đứng yên |
| `labels/passes.csv`, `labels/crops/` | 11 dòng (10 lượt + 1 đứng yên), frame giữa lượt + ảnh cắt quanh QR; cột `text`, `n_labels_visible`, `note` để điền tay; `auto_texts` là nội dung pipeline đọc được |

Bối cảnh: `lab_xa`/`lab_gan`/`lab_cheo` (06/11), `xuong_tinh`, `xuong_khong_tem` (2 video trong `cheo/`: không có
tem nhưng có vệt phản xạ kính), `xuong_chay`. Video `134415246` gắn tư thế camera `B`: cả video lệch so với các video
khác, không phải bị dịch giữa chừng.

Quy tắc gắn nhãn: `pass` = các frame có phát hiện liên tiếp (hở ≤10 frame đã quét, dài ≥3); `glass_no_det` = frame
xưởng có ≥0,1 % pixel cháy sáng (vệt phản xạ đèn trên kính) mà không có lượt. Đây là heuristic: video `134415246` có
tem trắng chạy qua ở frame ~520–590 nhưng YOLO không phát hiện nên vẫn là `glass_no_det`. `config_change` = mức sáng
kẹp giữa hai lần đổi (chênh lệch frame kề >10 và độ sáng đổi >3 mức), chỉ có ở `cheo/132745078` frame 259–323.

Kiểm tra: `frames.csv` = 9.808 = số file gốc = số link trong `raw/`; mọi link trùng file gốc (`samefile`); không thiếu
số thứ tự; `curated` là tập con của `raw`. Có 54 frame có phát hiện không vào `curated`, đều có chủ đích: 53 frame
đứng yên trùng lặp và 1 phát hiện nhầm trong video không có tem. Phần lab chiếm phần lớn `curated` vì tem có mặt gần
suốt video. Chưa chạy lại pipeline trên `curated`: dữ liệu giống hệt file gốc nên phát hiện trùng manifest.

Ở bước 4, chưa chuyển sang PNG/cắt dải (tùy chọn, cần quyết định có giữ TIFF gốc không).

## 5. Không phải lỗi làm sạch, cần xử lý ở lần quay sau

Dữ liệu chạy ngày 13/11 gần như không đọc được vì cách quay, làm sạch không cứu được:

- **Exposure**: tem đi khoảng 12–18 px mỗi frame ghi, vệt mờ 10–20 px so với ô QR 2,3 px. Cần cố định exposure theo
  công thức chế độ băng chuyền (`t = mờ_px × mm/px ÷ v`, mục tiêu ≤1,5 px), tắt AE, bù bằng gain/đèn.
- **Ghi đĩa**: toàn khung 8 MB chỉ ghi được ~16 fps và có frame bị bỏ. Dùng ROI dải (như ngày 06/11, 1792×992 ghi
  ổn định 25 fps) hoặc ghi AVI/nén; ghi kèm timestamp camera (chunk data) để biết khoảng thời gian thật giữa các
  frame.
- **Phản xạ kính**: đổi góc camera/đèn hoặc dùng kính lọc phân cực để giảm vệt sáng trùng vị trí tem.
- Mỗi lần ghi nên đặt tên thư mục theo kịch bản và giữ file cấu hình camera (`.pfs`) kèm theo; không ghi đổi
  exposure/dịch camera giữa chừng một video.
