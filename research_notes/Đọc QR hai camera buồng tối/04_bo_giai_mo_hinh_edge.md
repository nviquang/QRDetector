# Bộ giải tái tạo QR dựa trên mô hình (B `grid_sr`) cho V2-M cố định, 2,2–2,44 px/ô, ảnh nét — thích nghi thuật toán, tăng tốc trên Jetson Nano / CPU, vai trò bộ đọc chính

Bối cảnh cố định: Basler mono 8 MP, ống 4 mm; tem QR 32 mm, version 2 (25×25), mức M, **một khối RS (44,28)**: 28 byte dữ liệu + 16 byte EC, d = 17; nội dung `số#số` độ dài thay đổi, mã hóa tách đoạn numeric/byte/numeric; nhãn ở vị trí và góc xoay bất kỳ; băng 80–120 mm/s; buồng tối 60 cm, exposure ≤2,5 ms → vệt mờ ≤0,5 px. Suy giảm chính: lấy mẫu thưa (2,2–2,44 px/ô), mờ quang học σ, nhiễu, phối cảnh/méo nhẹ ở mép ảnh.

Ký hiệu `[nội bộ]` = đọc trực tiếp từ repo (`qr/solvers/grid_sr/grid_model.py`, `grid_sr.py`, `reports/Giải thích thuật toán B và C.md`) hoặc từ phép tính/đo nhỏ chạy trong phiên này; không có URL vì là mã nguồn/tính toán cục bộ.

## (A) Thay đổi thuật toán khi đã cố định V2-M và mờ nhỏ; mức lợi kỳ vọng so với zxing ở 2,2–2,4 px/ô

### Takeaway
Cố định V2-M cho phép bỏ gần hết các bước tốn thời gian của B (giả thiết V1/V3, quét σ, quét góc phải-dưới) và thay bằng neo 4 điểm (3 finder + alignment pattern tại ô (18,18)), σ liên tục/dị hướng ước từ ô chức năng, rồi một bài QUBO 625 biến cố định cấu trúc. Tài liệu chỉ cho bằng chứng gián tiếp về mức lợi so với bộ đọc thường (Kato et al.: +15,7% trung bình, +38% tối đa so với SR thông thường, 98% nhận dạng ở ảnh độ phân giải thấp; Zeng et al.: 93,1% so với 15,7% đọc trực tiếp, nhưng ở ≥8 px/ô và mờ chuyển động); không có nguồn nào đo đúng ở 2,2–2,4 px/ô với ảnh nét, nên phải tự đo trên tập hiện trường.

### Cited Findings
- Kato, Deguchi, Takahashi, Ide, Murase (Nagoya, ICDAR 2011) "Low Resolution QR-Code Recognition by Applying Super-Resolution Using the Property of QR-Codes": SR đa frame có **ràng buộc mẫu nhị phân** (pixel gần biên đen-trắng bị nhòe thành xám), dựng ảnh độ phân giải cao từ nhiều ảnh thấp; báo **98%** nhận dạng trên ảnh mà phương pháp thường không đọc được, tăng **15,7% trung bình, 38,0% tối đa** so với SR thông thường — [ICDAR 2011 bibtex/abstract](https://bibtex.github.io/ICDAR-2011-KatoDTIM.html); [IEEE 6065459](https://ieeexplore.ieee.org/document/6065459)
- Bản mở rộng IEICE "Two-step Super-Resolution with Binary and Grid Constraints": bước SR 1 nhằm tăng khả năng phát hiện finder **và alignment pattern**, bước 2 giải ô dựa trên vị trí đã phát hiện (ràng buộc lưới) — [IEICE abstract](https://www.ieice.org/ken/paper/2010090520aG/eng/); [Nagoya PDF 1015](https://www.vislab.is.i.nagoya-u.ac.jp/~murase/pdf/1015-pdf.pdf). Không trích được bảng số (PDF tiếng Nhật, không giải nén được trong phiên này).
- Kato et al. ước lượng PSF từ chính finder pattern cố định của QR (đã trích trong ghi chú cũ) — [Nagoya PDF 886](https://pubdb.vislab.is.i.nagoya-u.ac.jp/~murase/pdf/886-pdf.pdf)
- Zeng et al. (Xidian, arXiv 2610.34788, 2026): trên 955 ảnh thật mờ chuyển động, đọc trực tiếp chỉ 150 đúng (lỗi 84,3%) → pipeline mô hình đầy đủ 889 đúng (**93,1%**), **0 chuỗi sai**, 66 từ chối; NAFNet-32 83,6%, MIMO-UNet+ 81,9%, Pan et al. 20,3%, **van Gennip et al. 17,1%** — [arXiv 2610.34788](https://arxiv.org/html/2610.34788)
- Cùng bài: ảnh tổng hợp và phép đo dung sai dùng **≥8 px/ô**; ảnh thật được thu nhỏ 2×; 562/955 ảnh dưới 12 px/ô chiếm **63/66** ca từ chối ("liên hệ thực nghiệm", không phải nhân quả); không mô hình lệch nét, cong, mòn — [arXiv 2610.34788](https://arxiv.org/html/2610.34788)
- Tiên nghiệm nhị phân (KL) nới bề rộng kernel giải được ~4 lần so với tiên nghiệm đều (mã vạch 1-D) — [Rioux/Choksi et al., KL](https://www.math.mcgill.ca/rchoksi/pub/KL.pdf)
- Các bài học sâu cho QR độ phân giải thấp: Sancar (PeerJ CS 2025) thử EDSR/VDSR/ESPCN/SRCNN trên 4.593 QR thật mà OpenCV QRCodeDetector không đọc được và báo SR cải thiện khả năng đọc — [PeerJ cs-2841](https://peerj.com/articles/cs-2841); Shindo et al. (GCCE 2022) CNN 3 lớp tích chập để khử nhiễu + SR QR — [GCCE 2022 Shindo](https://www.ams.giti.waseda.ac.jp/data/pdf-files/2022_GCCE_shindo.pdf); Tanaka et al. (GCCE 2024) nhấn mạnh giá trị gần **tâm ô** là quyết định — [GCCE 2024 Tanaka](https://www.ams.giti.waseda.ac.jp/data/pdf-files/2024GCCE_tanaka.pdf) (không mở được bản đầy đủ, chỉ có đoạn trích tìm kiếm).
- Bộ đọc công nghiệp: Cognex VisionPro ID Tool yêu cầu mã 1-D ≥**1,6 px/ô** (cao 50 px), mã bưu chính ≥2,5 px; tài liệu 2-D (Data Matrix) chỉ cho ký hiệu >50 px và ô ≤10 px — [Cognex VisionPro 9.5 ID Tool](https://docs.cognex.com/vpro_950/web/EN/help/html/b5e68d1a-d0cd-4b1f-be49-e4c3c674b735.htm). HALCON có chế độ `small_modules_robustness='high'` cho ô rất nhỏ, đổi lại tốn bộ nhớ/thời gian và khuyên thu hẹp miền tìm kiếm — [HALCON get_data_code_2d_param](https://www.mvtec.com/doc/halcon/2605/en/get_data_code_2d_param.html)
- [nội bộ] Lượt mẫu `xa_04` (V1-L, **2,16 px/ô**, vệt 0,52 px): `PassDecoder` (zxing 3 binarizer → warp → WeChat → Wiener → xếp chồng) chỉ đọc 1/5 crop (không chốt), cascade 3/25 frame; B đọc đúng trong 4,1 s, chỉ phải lật 3/208 bit; đối chứng "1 frame" của B cho x gần giống 5 frame vì ảnh đủ nét. b chỉ 3–9 mức xám, g 15–35 mức xám, giảm >½ từ góc này sang góc kia → ngưỡng cố định thất bại.
- [nội bộ] Ở B1b, NCC hình học V1 vs V2 chỉ chênh ~0,01 trong khi độ chênh format chênh hàng trăm lần (1707,7 vs 4,0) → giả thiết version hiện giải bằng "giải nhanh x + chấm format" cho mỗi giả thiết, tức tốn một lần `build_matrix` + giải cho mỗi (version, crop).
- [nội bộ] σ hiện quét trong `SIGMAS = (0.45, 0.6, 0.75, 0.95, 1.2)`, chọn theo NCC; PSF đẳng hướng `s = sqrt(σ² + 1/12)` dùng chung 2 trục; `search_corner` quét δ lưới 5×5 (bước 1,2 px) rồi 3×3 (0,5 px), mỗi δ dựng ma trận cho 3 frame (~34×3 ≈ 100 lần `build_matrix`).

### Inferences
- **Bỏ giả thiết V1/V3**: `finder_triples` chỉ cần khoảng cách finder ứng với 25 ô (tâm finder cách nhau 18 ô); loại 2/3 bộ ba ứng viên và toàn bộ vòng "quick_margin" so version. Cổng format vẫn giữ nhưng chỉ còn 8 mã format hợp lệ của mức M (mask 0–7) thay vì 32 → tăng khoảng cách tới mã nhì, giảm báo sai format.
- **Neo alignment pattern**: V2 có một alignment 5×5 tâm ở ô (18,18) (theo chuẩn ISO 18004, bảng vị trí alignment V2 = {6, 18}). Khớp mẫu alignment (đã làm mờ theo σ) trong cửa sổ ±3 px quanh vị trí suy từ affine 3 finder → có 4 điểm neo → homography trực tiếp (8 tham số) thay cho `search_corner` 34 δ × 3 frame. Lợi kép: nhanh hơn và xử lý phối cảnh/méo ở mép ảnh 4 mm. Ở 2,3 px/ô alignment chỉ rộng ~11,5 px, lõi đen 1 ô ~2,3 px; NCC vẫn khả thi vì mẫu 5×5 có cấu trúc đen-trắng-đen; nếu đỉnh NCC yếu (dưới ngưỡng) thì rơi về `search_corner` hiện có với lưới nhỏ hơn (3×3).
- **Ô biết trước của V2-M**: finder + separator (3×64 = 192), timing (2×9 = 18 ô ngoài vùng finder), alignment 25, ô tối cố định 1, hai bản format 30 → ~266/625 ô là chức năng; dữ liệu+EC = 44×8 = 352 bit + 7 bit thừa (V2 có 7 remainder bits). Sau khi chốt format, có thêm **mode indicator** đầu (4 bit `0001` numeric) — đúng như ràng buộc "chỉ biết mode indicator/cấu trúc".
- **σ liên tục, dị hướng, từ ô chức năng**: thay quét 5 σ bằng Gauss–Newton trên (σ_x, σ_y, [θ], b, g) với phần dư chỉ trên pixel phụ thuộc ô đã biết; Jacobian theo σ có thể tính giải tích vì PSF Gauss tách được: ∂/∂σ của tích phân Gauss trên ô = hiệu hai hàm Gauss tại hai mép ô (đạo hàm của erf). Với ảnh nét (σ ≈ 0,45–0,8 px theo B1b) và hộp pixel 1/12, mô hình tích phân ô dạng erf tách được theo u,v (trong hệ ô) là chính xác hơn lưới quadrature 5×5 hiện tại và rẻ hơn 25 lần số điểm.
- **Đa frame (hàng chục frame)**: ở 100 mm/s, nhãn 32 mm đi qua trường nhìn trong nhiều frame; với ảnh nét, lợi chính của đa frame là **lệch pha lưới dưới pixel** giữa các frame (mỗi frame lấy mẫu ô ở pha khác) — chính là cơ chế SR của Kato et al. Vì Q = Σ BᵢᵀBᵢ/σᵢ² cộng dồn, chi phí giải không tăng theo số frame (vẫn 625 biến); chỉ chi phí dựng Bᵢ tăng tuyến tính. Gợi ý: chọn 8–16 frame có pha lưới trải đều (pha = phần lẻ của tọa độ tâm ô theo pixel), trọng số Huber theo phần dư từng frame.
- **Lợi kỳ vọng so với zxing**: suy luận từ `xa_04` (2,16 px/ô, ảnh khá nét: zxing/WeChat 1/5 crop, B đọc đúng) và từ Kato (+15,7…38%): ở 2,2–2,44 px/ô, phần thua của zxing chủ yếu do binarizer ngưỡng cục bộ + lấy mẫu 1 điểm/ô ở tâm ước lượng, nhạy với lệch lưới 0,3–0,5 ô; mô hình có ICM/LLR + RS mềm dùng toàn bộ pixel và tương tác ô lân cận. Không có nguồn định lượng cho đúng cấu hình này; cần đo tỉ lệ đọc theo lượt trên `data/field/raw` với `main_replay.py`.

### Gaps
- Không tìm được bài nào đo zxing/ZBar/WeChat so với giải mô hình ở đúng 2,2–2,44 px/ô, ảnh nét; Zeng et al. ở ≥8 px/ô, Kato et al. không lấy được bảng px/ô và số frame.
- Không tìm được nghiên cứu đo độ chính xác định vị alignment pattern ở ~2,3 px/ô.

## (B) Soft-decision / RS có xóa cho khối (44,28): khả năng sửa, xác suất báo sai, cách đặt cổng

### Takeaway
Khối (44,28) có d = 17: sửa được e lỗi và s xóa khi 2e + s ≤ 16. Mỗi xóa thêm làm xác suất "sửa nhầm" (miscorrection) của bộ giải giới hạn khoảng cách tăng nhanh: ~10⁻¹¹ khi không xóa, ~10⁻⁵ khi xóa 8, ~10⁻² khi xóa 12, và **=1 khi xóa 16** (luôn ra một từ mã). Vòng "GMD xóa dần tới nsym" hiện có trong `chase_block` vì thế luôn sinh ứng viên rác; an toàn phải đến từ cổng (format, byte đệm, cấu trúc mode/độ dài, regex, nhiều frame đồng thuận), không từ RS.

### Cited Findings
- McEliece & Swanson (JPL/NASA 1986): xác suất giải sai của bộ giải giới hạn khoảng cách cho RS sửa t lỗi, khi xảy ra >t lỗi, **< 1/t!**; biểu diễn qua Q = xác suất một mẫu lỗi ngẫu nhiên rơi vào hình cầu bán kính t quanh một từ mã khác 0 — [NASA NTRS 19860013319](https://ntrs.nasa.gov/api/citations/19860013319/downloads/19860013319.pdf)
- Cheung (1989) cho công thức chính xác bằng bao hàm–loại trừ; Tolhuizen (1993) mở rộng cận sang **giải lỗi-và-xóa** — [typeset: more on the decoder error probability for RS codes](https://typeset.io/pdf/more-on-the-decoder-error-probability-for-reed-solomon-codes-tmrno8k8dl.pdf); [Springer, Tolhuizen 1993](https://link.springer.com/chapter/10.1007/978-3-7091-2786-5_26)
- Cassuto & Bruck thống nhất hai cận trên xác suất sửa nhầm cho mã MDS tuyến tính — [Technion, Cassuto](https://ycassuto.net.technion.ac.il/files/2018/05/7-5.pdf)
- arXiv 2509.24794 (2025, BCH nhị phân): dạng đóng cho xác suất chuyển trạng thái khi giải lỗi-và-xóa; nêu thực hành thường gặp là **khai báo thất bại nếu số xóa vượt một ngưỡng trước khi giải** để tránh sửa nhầm — [arXiv 2509.24794](https://arxiv.org/html/2509.24794v2)
- Chase vs GMD: GMD xóa dần các vị trí kém tin cậy (tuyến tính), Chase thử mẫu trên vị trí yếu (mũ) nhưng thường tốt hơn; sơ đồ lai — [USPTO 12413252](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/12413252); Chase dựa syndrome chia sẻ tính toán, O(n) mỗi tọa độ đổi thêm — [arXiv 2008.01796](https://arxiv.org/pdf/2008.01796)
- Lợi giải mềm RS trong viễn thông cỡ 0,7–1 dB so với giải cứng (mã dài, kênh khác) — [arXiv 0810.0567](https://arxiv.org/pdf/0810.0567)
- Zeng et al. chấp nhận chuỗi chỉ khi ≥2/3 bộ giải mã (ZBar, ZXing, WeChat) trùng nhau → 0 chuỗi sai/955 — [arXiv 2610.34788](https://arxiv.org/html/2610.34788)
- [nội bộ, tính trong phiên] Xấp xỉ McEliece–Swanson cho mã MDS (44,28) trên GF(256), với s xóa (mã thủng [44−s, 28, 17−s], bán kính t = ⌊(16−s)/2⌋), P_sửa-nhầm ≈ Σ_{i≤t} C(44−s,i)·255ⁱ / 256^{16−s} cho một từ nhận "ngẫu nhiên" (ngoài khả năng sửa):

  | s xóa | t | P≈ | | s xóa | t | P≈ |
  |---|---|---|---|---|---|---|
  | 0 | 8 | 1e−11 | | 9 | 3 | 1,6e−6 |
  | 1 | 7 | 1,6e−12 | | 10 | 3 | 3e−4 |
  | 2 | 7 | 4e−10 | | 11 | 2 | 3e−5 |
  | 4 | 6 | 1,3e−8 | | 12 | 2 | 8e−3 |
  | 6 | 5 | 5e−7 | | 14 | 1 | 0,13 |
  | 8 | 4 | 1,3e−5 | | 16 | 0 | 1 |

  (s lẻ tốt hơn s chẵn kề vì dư 1 bậc tự do kiểm tra.) Cộng dồn theo cận hợp (union) cho các phép thử của `chase_block`: Chase mọi tổ hợp của 8 byte yếu nhất ≈ **2,8e−5**; Chase 6 byte ≈ 6,7e−7; Chase 4 byte ≈ 1,6e−8; vòng GMD xóa dần tới 8 ≈ 1,4e−5, tới 12 ≈ 7,9e−3, tới 16 ≥ 1.
- [nội bộ] `chase_block` hiện chạy `for j in range(0, nsym+1)` (xóa dần tới **16** byte) và Chase trên `width=8` byte, `limit=4000`; cổng `gate` yêu cầu format nhất/nhì ≥1,4, Δchi phí/điểm format ≤0,6, tỉ lệ bit lật ≤8,5%, khoảng cách tới ứng viên khác nội dung ≥0,25, byte đệm ≥ npad−1.

### Inferences
- **Khả năng sửa thực tế**: nếu LLR tốt, Chase/GMD có thể vượt 8 lỗi cứng (tới 16 xóa khi mọi byte sai nằm trong tập yếu); nhưng giữ an toàn nên **giới hạn s ≤ 8–10** và yêu cầu 2e + s ≤ 16 − 2 (biên 2 ký hiệu), tức cắt vòng GMD ở j ≤ 10 (thay vì 16) và Chase width 6 (C(6,·) = 64 phép thử) → cận hợp ~1e−6…4e−4 trước cổng.
- **Cổng cấu trúc thay cho kiểm tra RS bị "tiêu" bởi xóa**: với `số#số` mã hóa numeric(4+10 bit đếm)+byte(4+8+8)+numeric(4+10)+terminator 4 bit, phần còn lại của 28 byte là byte đệm `0xEC/0x11` luân phiên. Ví dụ 12+1+12 ký tự → 132 bit ≈ 17 byte, còn **11 byte đệm = 88 bit kiểm tra độc lập RS**, cộng mode indicator (3×4 bit), trường đếm phải khớp tổng độ dài, mỗi nhóm 10 bit numeric < 1000. Ứng viên rác có xác suất đi qua đệm 11 byte ~256⁻¹¹ nếu yêu cầu đúng hết; cổng hiện cho thiếu 1 byte (npad−1) vẫn ~256⁻¹⁰. Nội dung dài hơn → ít byte đệm hơn → cổng yếu đi; phải tính "số bit kiểm tra hiệu dụng" = 8·(npad đúng) + bit mode/đếm + log₂ cận regex, và đòi ≥ ~40 bit sau khi trừ log₂(số phép thử Chase).
- **Đặt cổng theo số bit**: tổng xác suất báo sai ≈ (số phép thử RS) × P_sửa-nhầm(s) × 2^{−(bit kiểm tra cấu trúc)}. Mục tiêu ≤1e−9/lượt (băng chuyền ~10⁴–10⁵ lượt/ngày) → với Chase 64 phép thử và s ≤ 8 (1,3e−5), cần thêm ≥ ~12 bit cấu trúc; với s = 12 (8e−3) cần ≥ ~25 bit. Ngoài ra yêu cầu **≥2 frame/nhóm frame độc lập** cho cùng nội dung (giống quy tắc 2 lần đọc hiện tại và quy tắc 2/3 bộ giải của Zeng) khi s > 8.
- LLR byte nên lấy từ LLR bit hậu nghiệm (tổng log-xác suất của 8 bit, hoặc min |LLR| như hiện tại); ICM/QUBO cho LLR "có điều kiện" (lật 1 ô, các ô khác giữ) — với mờ nhỏ, tương tác ô lân cận yếu nên LLR đơn ô đã gần đúng.

### Gaps
- Không lấy được công thức Tolhuizen cho lỗi-và-xóa; bảng trên dùng xấp xỉ "từ nhận ngẫu nhiên" (cận trên thô, bỏ qua tương quan giữa các phép thử Chase).
- Không có số đo lợi của Chase/GMD trên khối RS ngắn của QR; con số dB viễn thông không chuyển thẳng.

## (C) Chạy ≤1–2 s/nhãn trên Jetson Nano (ARM A57×4 / Maxwell 128 lõi) và x86

### Takeaway
Bài toán sau khi cố định V2 rất nhỏ (625 biến, ~4.000–4.500 pixel/frame); thời gian hiện tại 4–15 s là do Python dựng lại ma trận thưa ~100+ lần và vòng lặp Python (LM sai phân, ICM từng ô), không phải do đại số. Bỏ giả thiết + neo alignment + PSF tách được dạng erf + Jacobian giải tích + Q đặc 625×625 có thể đưa phần giải xuống cỡ 0,1–0,3 s trên x86 và ~0,5–1 s trên A57 bằng NumPy thuần; Numba/CuPy trên Nano vướng Python 3.6 của JetPack 4.6 nên đường chắc nhất cho Nano là NumPy tối ưu hoặc C++ (Eigen/NEON), GPU không cần thiết cho kích thước này.

### Cited Findings
- Numba: tài liệu cài đặt nói build và test gói conda trên **NVIDIA Jetson TX2** và "có thể chạy" trên AArch64 khác; cài llvmlite "khá khó" vì cần bản LLVM đặc biệt — [Numba installing docs](https://numba.readthedocs.io/en/0.53.0/user/installing.html)
- **Numba 0.54.0 (19/8/2021) nâng Python tối thiểu lên 3.7** → Numba cuối cùng cho Python 3.6 là dòng 0.53.x — [Numba release notes](https://numba.readthedocs.io/en/0.56.4/release-notes.html)
- Trên Jetson Nano người dùng gặp `RuntimeError: Unable to find target for this triple`; có người dựng được LLVM 9.0.1 nhưng chưa cài được Numba trên Python 3.6; moderator NVIDIA chỉ Dockerfile có build Numba cho Python 3.6 trên JetPack 4.x — [NVIDIA forum: Numba on Jetson Nano](https://forums.developer.nvidia.com/t/numba-package-in-python-on-jetson-nano/157343); [NVIDIA forum: installation of numba on the jetson nano](https://forums.developer.nvidia.com/t/installation-of-numba-on-the-jetson-nano/189074); [NVIDIA forum: numba & TensorRT on Nano](https://forums.developer.nvidia.com/t/advice-on-using-numba-tensorrt-on-jetson-nano/234513)
- Bộ wheel không chính thức cho JetPack 4.6/Python 3.6 có numpy, scipy, pycuda, blis — không có numba/llvmlite — [jetson-nano-wheels](https://github.com/jetson-nano-wheels/jetson-nano-wheels)
- CuPy: `cupy-cuda102` (CUDA 10.2 = JetPack 4.6) có wheel `manylinux2014_aarch64` từ v10.0.0, gắn CPython **3.7–3.10**, không thấy cp36 — [PyPI cupy-cuda102 10.0.0](https://pypi.org/project/cupy-cuda102/10.0.0)
- Jetson Nano chỉ được JetPack 4.x (L4T R32.x), bản cuối **JetPack 4.6.4**; JetPack 6 chỉ cho Orin — [NVIDIA forum: jetpack 6 / Nano](https://forums.developer.nvidia.com/t/which-is-compatible-version-of-jetson-nano-jatpack-6-0/293205). Có thể cài Python 3.8 trên Ubuntu 18.04 của Nano — [JetsonHacks 2023](https://jetsonhacks.com/2023/06/12/upgrade-python-on-jetson-nano-tutorial/amp/); nhưng PyTorch cho JetPack 4.6 chỉ có bản Python 3.6, Python 3.8 gặp "illegal instruction" — [NVIDIA forum: ultralytics py3.6 JP4.6](https://forums.developer.nvidia.com/t/unable-to-install-ultralytics-in-python3-6-in-jetpack4-6/275989); [NVIDIA forum: Ultralytics on Nano 4.6](https://forums.developer.nvidia.com/t/ultralytics-yolo-and-jetson-nano-4-6/334440)
- Numba tăng tốc 40–60× trên 8 lõi cho lõi tích chập Richardson–Lucy, với điều kiện viết lại thành vòng lặp lồng — [HEAD2024 poster](https://sbs.wustl.edu/Posters/HEAD2024_compton_imaging_poster.pdf)
- Khử chập ℓ1: 96% thời gian ở đánh giá gradient (hai phép nhân ma trận thưa–vector) — [Escande & Weiss 2015](https://pescande.perso.math.cnrs.fr/assets/publis/2015_ultra_fast_l1_deconv_Escande_Weiss.pdf)
- Zeng et al.: trung vị 5,8 s/ảnh, p90 33,8 s trên GPU dùng chung; tìm 9%, khớp 38% thời gian; tác giả tự nêu cần tăng tốc cho nhúng/di động — [arXiv 2610.34788](https://arxiv.org/html/2610.34788)
- [nội bộ, đo trong phiên trên Ryzen 5 5500U, NumPy/SciPy trong `.venv`] Dựng một ma trận CSR cỡ V2 (4.489 pixel × 25 điểm PSF → 626 cột) mất **~4,7 ms**; 720 vòng gradient chiếu với Q **đặc** 625×625 mất **~84 ms**; cùng số vòng với Q thưa (random, nnz 390k — xấu hơn thực tế) ~250 ms. Thực tế Q dải hẹp (mỗi ô tương tác ~±1–2 ô) nên thưa hơn nhiều; nhưng ở N = 625, Q đặc (3 MB float64) đã đủ nhanh và tránh overhead SciPy.
- [nội bộ] `Solver.solve` mặc định 6 mức μ × 120 vòng = 720 vòng; mỗi vòng có hai `np.where` + `clip`; `refine`/`fit_warp` dùng Jacobian sai phân (8 lần hoặc 32 lần `Template.sample`); `icm` là vòng Python từng ô; `chase_block` tới 4.000 lần `rs_decode` Python.

### Inferences
- **Nguồn thời gian chính và cách cắt** (ước lượng, chưa đo trên Nano):
  1. Giả thiết version + quét σ + `search_corner`: ~100–200 lần dựng ma trận + giải → thay bằng 1 giả thiết, alignment 4 điểm, σ bằng Gauss–Newton 3–5 vòng (mỗi vòng 1 lần dựng với Jacobian giải tích). Cắt ≥10× số lần dựng.
  2. **PSF tách được**: trong hệ ô (sau homography cục bộ gần affine trên vùng 2,3 px), đóng góp ô m vào pixel p ≈ [Φ((u₁−u)/s_u) − Φ((u₀−u)/s_u)]·[Φ((v₁−v)/s_v) − Φ((v₀−v)/s_v)], chỉ khác 0 với 3×3 ô quanh pixel → 9 phần tử/hàng thay vì 25 điểm quadrature rồi gộp; Jacobian theo s_u, s_v, góc, tịnh tiến đều giải tích (đạo hàm Φ là pdf Gauss). Bỏ hẳn sparse SciPy: lưu A dạng mảng (npix × 9) chỉ số + trọng số, AᵀA tích lũy trực tiếp vào Q đặc.
  3. **Dừng sớm**: số vòng μ: 3 mức (0; 0,3; 1,0) × 40 vòng thường đủ khi ảnh nét (bảng B3: ở μ = 0,6 đã 0% ô lưỡng lự); dừng khi max|Δx| < 1e−3. Khởi tạo nóng x bằng nghiệm bình phương tối thiểu Cholesky của Q + λI (625×625 Cholesky ~vài ms).
  4. ICM: dùng gain vector hóa, lật cả nhóm ô không lân cận (tô màu bàn cờ 2×2 hoặc 3×3) mỗi bước thay vì từng ô.
  5. Chase: giảm width 8 → 6 và GMD ≤ 10 (cũng là yêu cầu an toàn ở mục B) → ~75 lần RS thay vì ≤4.000; RS (44,28) bằng thư viện C (`reedsolo` có bản Cython; hoặc tự viết Berlekamp–Massey + Forney trong C) ~µs/lần.
  6. Đa frame: dựng Bᵢ cho 8–16 frame ~5 ms/frame NumPy → <0,1 s.
- **Ước tính tổng**: x86 (Ryzen 5500U) NumPy thuần sau các bước trên ~0,2–0,5 s/nhãn; A57 1,43 GHz thường chậm hơn Zen2 di động khoảng 4–8× đơn luồng (suy luận, không có nguồn đo trực tiếp trong phiên) → ~1–3 s, đạt mục tiêu 1–2 s nếu thêm C++.
- **Lựa chọn trên Nano**: (a) Python 3.6 + NumPy/SciPy từ jetson-nano-wheels: chắc chắn chạy, đủ nếu bỏ sparse và vòng Python; (b) Numba 0.53.x qua conda (Miniforge/Archiconda aarch64) hoặc Docker NVIDIA: khả thi nhưng không có wheel PyPI, rủi ro cài đặt; (c) Python 3.8 venv riêng cho tiến trình giải (tiến trình spawn tách sẵn như `pass_fallback`) — dùng được numba/cupy bản mới hơn nhưng phải tự build llvmlite/cupy cho aarch64+CUDA 10.2, và không dùng chung tiến trình với PyTorch 3.6; (d) **C++ (Eigen + NEON, pybind11)** cho lõi: dựng A, Q, gradient chiếu, ICM, RS — đường đáng tin nhất cho ≤1 s trên A57; ~1.000–1.500 dòng.
- **GPU Maxwell 128 lõi không đáng**: Q·x với N = 625 là 0,4 MFLOP/vòng; overhead khởi chạy kernel CUDA (~10 µs) × 720 vòng và chép dữ liệu ăn hết lợi. Chỉ hợp lý nếu gom nhiều nhãn/giả thiết thành batch; GPU nên dành cho detector (YOLO/TensorRT).
- **FFT PSF** không phù hợp: vùng chỉ ~65×65 px và ma trận lấy mẫu không bất biến dịch (homography), PSF hỗ trợ 3×3 ô → tích chập trực tiếp tách được rẻ hơn FFT.

### Gaps
- Không có số đo NumPy/Numba trên Cortex-A57 cho bài toán cỡ này; tỉ lệ A57/Zen2 là suy luận.
- Không xác nhận được có wheel `cupy-cuda102` cp36 aarch64 cho v9.x (trang PyPI không tải được trong phiên); không thấy tài liệu nào chạy CuPy thành công trên Nano với Python 3.6.

## (D) Có nên thành bộ đọc CHÍNH? Bộ phân loại ô học máy thay bước giải; sản phẩm/nghiên cứu liên quan

### Takeaway
Với ảnh nét ở 2,2–2,44 px/ô, mô hình có giá trị nhất khi chạy **song song với zxing/WeChat ngay trên mỗi lượt** (không chờ 4 s đóng lượt rồi mới giải nền), nhưng chỉ nên là bộ đọc chính khi đã (1) chạy ≤1 s, (2) có cổng tính theo bit kiểm tra như mục B, (3) đo trên tập hiện trường cho thấy báo sai = 0 và tỉ lệ đọc theo lượt cao hơn cascade. Bộ phân loại ô CNN nhỏ là phương án khả thi về chi phí (vài chục nghìn tham số, chạy trên 625 patch) nhưng không tìm được tài liệu đánh giá ở đúng mật độ 2,3 px/ô, và nó mất đi LLR có cơ sở vật lý cần cho cổng.

### Cited Findings
- Zeng et al. dừng ở giai đoạn đầu tiên đạt đồng thuận 2/3 bộ giải → pipeline theo bậc, rẻ trước đắt sau, vẫn 0 báo sai — [arXiv 2610.34788](https://arxiv.org/html/2610.34788)
- US8150163: SR đa frame thời gian thực cho giải mã mã vạch di động; nếu chưa đọc được thì tích lũy qua frame kế tiếp tới khi đọc được hoặc hết giờ — [US8150163](https://patents.google.com/patent/US8150163)
- Tanaka et al. (GCCE 2024) nhấn mạnh giá trị gần tâm ô là quyết định trong QR; Shindo et al. (GCCE 2022) CNN 3 lớp tích chập + 2 ReLU cho QR không đọc được — [GCCE 2024](https://www.ams.giti.waseda.ac.jp/data/pdf-files/2024GCCE_tanaka.pdf); [GCCE 2022](https://www.ams.giti.waseda.ac.jp/data/pdf-files/2022_GCCE_shindo.pdf)
- Sancar 2025: so sánh 4 mô hình SR (EDSR, VDSR, ESPCN, SRCNN) trên 4.593 QR thật thất bại với OpenCV — [PeerJ cs-2841](https://peerj.com/articles/cs-2841)
- HALCON `small_modules_robustness` và giới hạn ô của Cognex (mục A) cho thấy sản phẩm công nghiệp có chế độ riêng cho ô nhỏ nhưng tài liệu không công bố thuật toán/độ chính xác — [HALCON](https://www.mvtec.com/doc/halcon/2605/en/get_data_code_2d_param.html); [Cognex](https://docs.cognex.com/vpro_950/web/EN/help/html/b5e68d1a-d0cd-4b1f-be49-e4c3c674b735.htm)
- [nội bộ] Hiện B/C chỉ chạy khi lượt kết thúc mà `PassDecoder` thất bại; trễ ~4 s chờ đóng lượt + 2–25 s giải, hàng đợi ≤8 lượt (CLAUDE.md).

### Inferences
- **Lộ trình "chính"**: mỗi khi tracker có ≥3 crop của một lượt chưa chốt, chạy bản rút gọn (V2-M, 1 giả thiết, alignment, 3 mức μ) trên 3–5 frame tốt nhất trong tiến trình nền; chốt khi (a) zxing/WeChat ≥2 lần trùng (như hiện nay), hoặc (b) mô hình qua cổng mạnh (s ≤ 8, đủ bit cấu trúc), hoặc (c) mô hình + 1 lần đọc zxing trùng nội dung. (c) là đồng thuận độc lập kiểu Zeng và có thể nâng tỉ lệ chốt nhiều nhất vì các lượt hiện "pass_unconfirmed" (1 lần đọc) sẽ được chốt.
- **CNN phân loại ô**: đầu vào patch 7×7 hoặc 9×9 px quanh tâm ô (đã warp theo homography ước lượng, ~3×3 ô lân cận), đầu ra P(trắng); huấn luyện trên render V2-M tổng hợp: lưới 25×25 ngẫu nhiên hợp lệ, homography + lệch pha dưới pixel ngẫu nhiên, σ 0,4–1,0 px dị hướng, b/g biến thiên như B2 (b 3–9, g 15–35), nhiễu Gauss + lượng tử 8 bit, 2,1–2,6 px/ô. Mạng ~3 lớp conv 3×3 (16–32 kênh) ≈ 10–20k tham số, ~10–30 kFLOP/patch → 625 patch ≈ 10–20 MFLOP/nhãn: vài ms trên CPU (ONNX Runtime/OpenCV DNN), TensorRT không cần. Ưu: nhanh, học được méo không mô hình hóa. Nhược: (1) nhạy sai số hình học — vẫn cần bước định lưới của B; (2) đầu ra xác suất không hiệu chuẩn → LLR cho Chase/cổng kém tin; (3) lệch miền tổng hợp→thật. Đề xuất dùng CNN như **khởi tạo x₀** và/hoặc bộ đọc thứ ba trong bỏ phiếu, giữ bước tối ưu mô hình (vài chục vòng) để có LLR vật lý.
- Nhiều frame với CNN: trung bình logit từng ô qua các frame (sau căn lưới) là xấp xỉ rẻ của khớp chung; hợp khi lệch pha giữa frame đủ trải.

### Gaps
- Không tìm được bài nào dùng CNN phân loại từng ô ở ~2–2,5 px/ô và báo tỉ lệ đọc/báo sai; không có số đo latency CNN cỡ này trên A57 hay TensorRT Nano trong nguồn đã đọc (chi phí trên là ước lượng FLOP).
- Không tìm được sản phẩm thương mại công bố thuật toán tái tạo QR theo mô hình cho ô <2,5 px; Cognex/HALCON chỉ nêu tham số chế độ.
- Không đọc được bản đầy đủ Kato et al. (PDF tiếng Nhật) và Tanaka/Shindo (máy chủ Waseda không phân giải DNS trong phiên).
