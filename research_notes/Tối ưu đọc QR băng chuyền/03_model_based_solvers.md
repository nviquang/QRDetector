# Tối ưu bộ giải tái tạo QR dựa trên mô hình (B grid_sr, C preproc_sweep): thuật toán, tốc độ CPU, công trình và sản phẩm liên quan

Ghi chú này mở rộng báo cáo `reports/Giải mã QR khi mờ chồng.md` (đã có: bảng thử nghiệm nội bộ 1–7, phân tích MTF ~5% ở tần số ô, ghim bit nội dung, kế hoạch ưu tiên 1–6/A–D). Ở đây không nhắc lại các điểm đó, chỉ bổ sung (i) số liệu dung sai tham số mờ mới từ tài liệu, (ii) phân tích mã nguồn `qr/solvers/grid_sr` để chỉ ra chỗ tốn thời gian, (iii) nguồn về RS mềm, phát hiện 2-D ISI, học máy và sản phẩm thương mại.

Quy ước: "[nội bộ]" là quan sát từ đọc mã trong repo (`qr/solvers/grid_sr/grid_model.py`, `grid_sr.py`), không phải số liệu tài liệu. Mọi ước lượng tốc độ không có nguồn đều nằm ở mục Inferences.

## 1. Ước lượng PSF mù cho mã vạch/QR (σ, mờ chuyển động, PSF dị hướng) từ cạnh finder/timing

### Takeaway
Tài liệu xác nhận hai điều trực tiếp áp dụng cho B: (a) dung sai sai số tham số mờ của khớp mô hình QR rất hẹp (8–11% độ dài vệt khi vệt ~4 ô) và đánh giá thấp được dung thứ hơn đánh giá cao; (b) một cạnh chỉ cho mờ vuông góc với nó, nên PSF dị hướng phải ước lượng từ các cạnh nhiều hướng — điều mà finder/timing của QR cung cấp sẵn. Lưới σ cố định 5 mức, bước 0,15–0,25 px, với σ căn finder cố định 0,75, là quá thô so với các dung sai đó.

### Cited Findings
- Preprint Xidian (Zeng et al., arXiv 2610.34788, eess.IV, 2026) đo dung sai sai số tham số chuyển động khi giải QR mờ chuyển động: với tịnh tiến 4 ô ở vận tốc đều, dung sai độ dài chỉ còn **8–11%**; đánh giá thấp độ dài được dung thứ hơn đánh giá cao (tịnh tiến 2 ô, tỉ lệ vận tốc 2,1: dung sai **54% thiếu / 29% thừa**); sai độ dài và hướng ghép chặt: ở tịnh tiến 2 ô, thừa 10% độ dài làm dung sai hướng hẹp từ 13° xuống 8° — [arXiv 2610.34788](https://arxiv.org/html/2610.34788)
- Cùng bài: pipeline dùng mạng dự đoán quỹ đạo bậc hai cho 4 góc, rồi **lưới tìm ứng viên** (thang độ dài 0,70–1,35 bước 0,05; xoay ±10° bước 5°; lệch độ dài cục bộ ±0,05/±0,10) xếp hạng theo sai số trên **các vùng chức năng cố định của QR**, rồi nghịch đảo tuyến tính có chỉnh hóa (CG, λ = 10⁻³, dự phòng 3×10⁻², 10⁻², 3×10⁻³) và 3 vòng khớp xen kẽ mã nhị phân ↔ quỹ đạo — [arXiv 2610.34788](https://arxiv.org/html/2610.34788)
- Phần cắt bỏ trên 955 ảnh chụp tay: đọc trực tiếp 150 đúng (lỗi 84,3%) → + quỹ đạo từ mạng 738 (22,7%) → + tìm quỹ đạo 836 (12,5%) → + khớp xen kẽ 889 (6,9%); 0 chuỗi sai, 66 ảnh bị từ chối, trong đó 63/66 ở dưới 12 px/ô. Trên ảnh tổng hợp, quỹ đạo thật (oracle) cho lỗi 17% so với 23% của pipeline đầy đủ — khoảng cách do ước lượng tham số chỉ còn ~6 điểm — [arXiv 2610.34788](https://arxiv.org/html/2610.34788)
- Hạn chế tự nêu của bài: chỉ mô hình vật phẳng cứng, quỹ đạo bậc hai, trọng số thời gian đều; **không mô hình lệch nét chồng (coupled defocus)**, biến dạng không phẳng, che khuất; tổng hợp dùng ≥8 px/ô — [arXiv 2610.34788](https://arxiv.org/html/2610.34788)
- Phương pháp cạnh nghiêng (slanted edge): một cạnh chỉ cho mờ vuông góc với cạnh đó; MTF dị hướng cần nhiều cạnh ở các hướng khác nhau; VIGRA có hàm khớp Gauss vào MTF (`mtfFitGaussian`) và nêu Gauss là xấp xỉ tốt cho nhiều camera thật — [VIGRA SlantedEdgeMTF](https://ukoethe.github.io/vigra/doc-release/vigra/group__SlantedEdgeMTF.html)
- Joshi, Szeliski, Kriegman (CVPR 2008) mở rộng ước lượng PSF từ cạnh sang giải trực tiếp PSF 2-D bằng cách dự đoán ảnh sắc từ cạnh — [PSF estimation using sharp edge prediction](https://www.academia.edu/65900695/PSF_estimation_using_sharp_edge_prediction)
- Tham số hóa Gauss/lệch nét có thể mơ hồ với PSF dị hướng (cùng một tham số thang nhưng lượng mờ khác nhau theo hướng) — [IIT Jodhpur, Blur parameter locus curve](https://research.iitj.ac.in/pdf/postprint-blur-parameter-locus-curve-and-its-applications)
- Kato et al. (Nagoya) dùng chính finder pattern cố định của QR để ước lượng PSF (các phương pháp trước giả định PSF đã biết) trong siêu phân giải đa frame cho QR độ phân giải thấp; số liệu định lượng chưa kiểm chứng (chỉ xem được tóm tắt) — [Nagoya, Multi-frame SR for low resolution QR-code recognition](https://pubdb.vislab.is.i.nagoya-u.ac.jp/~murase/pdf/886-pdf.pdf)
- Esedoglu: bài toán mã vạch khác khử nhiễu thông thường vì kernel không biết trước hoàn toàn; ước lượng kernel đồng thời với mã — [Esedoglu, barcodes](https://dept.math.lsa.umich.edu/~esedoglu/Papers_Preprints/barcodes_esedoglu.pdf)
- [nội bộ] Trong `psf_points`, PSF = hộp pixel ⊛ Gauss ⊛ đoạn vệt; σ đi vào **một** hệ số `s = sqrt(σ² + 1/12)` dùng chung cho cả trục x và y (lưới quadrature 5×5 điểm trọng số nhị thức), vệt mờ là 5 điểm đều (`motion_offsets(npts=5)`). `search_corner` và căn finder dùng σ cố định 0,75; `fit_geometry` chọn σ trong `SIGMAS = (0.45, 0.6, 0.75, 0.95, 1.2)`.

### Inferences
- Đổi sang PSF dị hướng gần như miễn phí trong mã hiện có: tách `s` thành `s_x = sqrt(σ_x² + 1/12)`, `s_y = sqrt(σ_y² + 1/12)` trong `psf_points` (dx nhân s_x, dy nhân s_y), cộng thêm góc θ của vệt. Số đo nội bộ (cạnh 10–90% dọc ~6,4 px, ngang ~3,5 px; tĩnh ngang ~2,5 px) gợi ý σ_x ≠ σ_y sau khi trừ vệt; với Gauss, độ rộng 10–90% ≈ 2,56σ, nên ngang 3,5 px ↔ σ_x tổng ≈ 1,37 px (gồm cả hộp pixel), tĩnh 2,5 px ↔ ≈ 0,98 px. Đây là quy đổi giả định Gauss, cần xác nhận bằng khớp ESF thật.
- Thứ tự ước lượng hợp lý theo cấu trúc QR: (1) σ_x từ các cạnh **dọc** của finder và timing dọc (cạnh dọc không chịu vệt chuyển động dọc), (2) rồi L và σ_y từ cạnh ngang khi σ_x đã biết, (3) cuối cùng tinh chỉnh chung (σ_x, σ_y, L, θ, dịch pha lưới) bằng Gauss–Newton trên phần dư của **mọi** ô đã biết (finder, timing, separator, format sau khi giải format, vùng đệm nếu ghim nội dung). Vì phần dư chỉ phụ thuộc trơn vào 4–5 tham số này, một Jacobian sai phân 5 cột (5 lần `build_matrix`) mỗi vòng là đủ — rẻ hơn nhiều so với quét lưới 5 σ × hypothesis.
- Từ dung sai 8–11% của Zeng et al. ở vệt ~4 ô (của ta ~2,8 ô) và bất đối xứng thiếu/thừa, bước lưới σ hiện tại (0,15–0,25 px ở σ ~1, tức 15–25%) có thể đã vượt dung sai; nếu buộc phải quét lưới thì nên lệch về phía đánh giá thấp và bước ≤0,1 px.
- Cepstrum: với vệt ~6,5 px trên vùng chỉ ~54×54 px, số không phổ của hộp nằm ở ~1/6,5 chu kỳ/px, nhưng cửa sổ quá ngắn và cấu trúc nhị phân mạnh của QR làm cepstrum nhiễu; ước lượng tham số từ vùng chức năng đã biết (cách Zeng et al. và Kato et al. làm) hợp với bài toán hơn. Không tìm được nguồn đo cepstrum trên QR nhỏ (xem Gaps).

### Gaps
- Không tìm được bài nào ước lượng σ_x, σ_y, L, θ đồng thời từ finder/timing của QR ở ~2–3 px/ô và báo sai số ước lượng; Zeng et al. ở ≥8 px/ô (tổng hợp) và không có lệch nét.
- Không lấy được bản đầy đủ bài Kato et al. (số liệu đọc được) và bài Fan et al. (Sensors 2017, khớp ESF tích phân) — chỉ có đoạn trích từ kết quả tìm kiếm.
- Không có nguồn định lượng về cepstrum/phổ cho mờ chuyển động trên QR rất nhỏ.

## 2. Tái tạo có ràng buộc nhị phân, bộ quyết định ô và giải mã Reed–Solomon mềm

### Takeaway
Hướng "tiên nghiệm nhị phân + ràng buộc hộp [0,1]" đang là dòng chính trong toán ứng dụng (ADMM, PCLS 2026), nhưng với mã 2-D nhỏ đã biết hình học, lời giải gần tối ưu thật sự là bài toán phát hiện trên kênh ISI 2-D: có sẵn công cụ BCJR/SOVA theo hàng–cột và phát hiện MRF lặp, rất hợp với mờ chủ yếu một chiều (dọc). Phía RS, Chase/GMD (đang dùng) là lựa chọn đúng về chi phí; Koetter–Vardy và ABP cho thêm khoảng 0,5–1 dB trong viễn thông nhưng đắt hơn nhiều và không có bằng chứng trên QR.

### Cited Findings
- De Cezaro, Hafemann, Leitão (arXiv 2606.01156, nộp 31/5/2026): khử chập bán mù cho mã vạch 1-D theo khung Piecewise Constant Level Set; phương pháp Lagrange tăng cường, chứng minh tồn tại nhân tử tổng quát và không có khe đối ngẫu, kèm sơ đồ lặp kiểu ADMM, thử với nhiều phương sai mờ và mức nhiễu (tóm tắt không có số) — [arXiv 2606.01156](https://arxiv.org/abs/2606.01156)
- Rioux/Choksi et al.: tiên nghiệm nhị phân (KL) nới rộng bề rộng kernel giải được khoảng 4 lần so với tiên nghiệm đều trong thí nghiệm của họ (đã nêu trong báo cáo cũ) — [Rioux et al., KL](https://www.math.mcgill.ca/rchoksi/pub/KL.pdf)
- Phát hiện lặp trên kênh ISI 2-D: bài Radioengineering 2014 mở rộng BCJR và SOVA một chiều lên hai chiều, mô hình kernel ISI không gian như máy trạng thái hữu hạn 2-D — [Radioengineering 2014](https://www.radioeng.cz/fulltexts/2014/14_02_0618_0631.pdf)
- Zhu, Cheng, Sivakumar, Belzer: phát hiện ảnh nhị phân (MRF) trên kênh ISI 2-D có nhiễu bằng cách nối hai bộ phát hiện SISO — bộ phát hiện ISI phản hồi quyết định mềm lặp hàng–cột và bộ phát hiện MRF — [arXiv cs/0609155](https://ar5iv.arxiv.org/html/cs/0609155)
- Chase so với GMD: GMD là lặp giải mã lỗi-và-xóa, mỗi lần xóa thêm số chẵn vị trí kém tin cậy nhất (độ phức tạp tuyến tính); Chase thử mẫu lỗi trên vị trí kém tin cậy (độ phức tạp mũ) nhưng thường tốt hơn hẳn; sơ đồ lai chạy Chase trên một phần vị trí, chỉ xóa (GMD) trên phần còn lại — [USPTO 12413252](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/12413252)
- Chase nhanh dựa trên syndrome/Gröbner chia sẻ tính toán giữa các mẫu thử, chi phí O(n) cho mỗi tọa độ thay đổi thêm — [arXiv 2008.01796](https://arxiv.org/pdf/2008.01796)
- Jiang & Narayanan đề xuất GMD mức bit và các phương pháp khai thác cấu trúc mức bit của RS để giảm độ phức tạp; giải mã BP thích nghi (ABP) cho RS(255,239) được báo lợi ~0,75 dB tại FER 10⁻⁴ — [arXiv cs/0506073](https://arxiv.org/pdf/cs/0506073). (Ghi chú: con số 0,75 dB đến từ đoạn trích kết quả tìm kiếm, chưa đối chiếu bảng gốc.)
- Lợi ích của giải mã mềm RS trong viễn thông: các con số rải rác 0,7–1 dB so với giải mã cứng cho mã tốc độ cao (một sơ đồ lai dùng KV ở tầng hai báo ~0,8–0,9 dB so với RS giải cứng; bằng sáng chế DOCSIS báo ~1 dB ở 1024-QAM); lý thuyết cho rằng giải cứng mất ~2–3 dB trên AWGN — [arXiv 0810.0567](https://arxiv.org/pdf/0810.0567); [USPTO 8908810](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/8908810). (Mức độ chắc chắn thấp: các nguồn khác mã, khác kênh; quy kết từng số cho từng bài chưa kiểm tra bản gốc.)
- Zeng et al. chỉ chấp nhận chuỗi khi **ít nhất hai bộ giải mã (ZBar, ZXing, WeChat) đồng ý**, và đạt 0 chuỗi sai trên 955 ảnh — [arXiv 2610.34788](https://arxiv.org/html/2610.34788)
- [nội bộ] `Solver` của B chuyển về dạng chuẩn tắc: Q = Σ BᵢᵀBᵢ/σ² kích thước N×N (N = 441/625/841 cho V1/V2/V3), gradient Nesterov chiếu với μ tăng dần; `icm` lật **một** ô mỗi bước theo gain = gᵢdᵢ + ½Qᵢᵢdᵢ²; `llr` lấy chênh chi phí lật đơn ô với các ô khác giữ nguyên.

### Inferences
- Vì Q đã sẵn (ma trận tương tác cặp giữa các ô), bài toán quyết định là một bài QUBO nhỏ (≤841 biến) có cấu trúc dải: với mờ chủ yếu dọc (~2,8 ô) và σ ngang ~0,5 ô, mỗi ô tương tác mạnh với ~±2 ô dọc và ±1 ô ngang. Ba nâng cấp theo thứ tự chi phí:
  1. ICM theo khối: thử mọi tổ hợp của cặp dọc, bộ ba dọc và khối 2×2 (≤16 tổ hợp, tính bằng chính Q) — vá đúng sự kiện lỗi tối thiểu mà báo cáo cũ đã chỉ ra. Chi phí chỉ vài nghìn phép tính trên Q.
  2. BCJR/Viterbi theo cột: coi mỗi cột ô là một chuỗi với bộ nhớ ISI ~3 ô (trạng thái 2³ = 8), điều kiện hóa các cột lân cận bằng xác suất mềm hiện tại, luân phiên cột ↔ hàng (đúng sơ đồ hàng–cột của Zhu et al.). Cho **LLR hậu nghiệm thật** thay cho LLR "lật một ô", là đầu vào tốt hơn cho Chase/GMD.
  3. Loopy BP / mean-field trên đồ thị cặp lấy từ Q (biên = phần tử ngoài đường chéo vượt ngưỡng), có thể làm mịn bằng annealing nhiệt độ.
- LLR mức bit → byte: Chase hiện xóa 8 byte yếu nhất. Với LLR hậu nghiệm tốt, có thể chuyển sang GMD+Chase lai (xóa dần theo độ tin cậy byte, Chase 2^k trên k≈3–4 byte yếu nhất nhưng chưa xóa), giữ ràng buộc 2e + s ≤ d − 1 − biên an toàn để giữ 0 báo sai. KV/ABP không đáng công với khối RS ngắn của QR v1–v3 (vài chục byte mỗi khối) khi bit nội dung đã ghim được nhiều; lợi 0,5–1 dB đo trên kênh viễn thông không chuyển thẳng sang bài toán này.
- Cổng chống báo sai có thể bổ sung "≥2 bộ giải mã độc lập đồng ý" như Zeng et al., ngoài regex `^\d{12}#\d{12}$` (chưa bật trong code theo CLAUDE.md).

### Gaps
- Không tìm được bài nào áp dụng BCJR/BP 2-D hay giải mã RS mềm cho QR/Data Matrix mờ, nên lợi ích là suy luận.
- Chưa đọc được nội dung chính và số liệu của arXiv 2606.01156 (PDF nén, trang tóm tắt không có số).
- Không có số đo trực tiếp lợi ích Chase-2 + GMD mức bit trên mã RS ngắn của QR.

## 3. Khớp mô hình đa frame chung (đăng ký trong mô hình) và độ cong tem

### Takeaway
Các hệ đa frame cho mã vạch trong tài liệu (Kato et al., bằng sáng chế US8150163) đều tích lũy thông tin qua frame với đăng ký dưới pixel, và Zeng et al. cho thấy vòng khớp xen kẽ mã ↔ hình học là bước quyết định (+53 ảnh, từ 12,5% xuống 6,9% lỗi). Kết quả nội bộ "30 frame tệ hơn 5" là dấu hiệu hình học/PSF từng frame không được tinh chỉnh trong mô hình: B hiện chỉ dùng 3 frame tốt nhất cho trường biến dạng và chung một bộ góc dịch cho góc dưới phải.

### Cited Findings
- Pipeline Kato et al.: căn frame chính xác dưới pixel, dựng ảnh trung bình độ phân giải cao kèm bản đồ trọng số, rồi tìm finder để nắn lưới mã; PSF ước lượng từ finder — [Nagoya](https://pubdb.vislab.is.i.nagoya-u.ac.jp/~murase/pdf/886-pdf.pdf)
- US8150163: siêu phân giải đa frame thời gian thực cho giải mã mã vạch trên thiết bị di động, làm việc với ảnh bị aliasing; nếu giải mã chưa thành công thì tích lũy thông tin qua frame kế tiếp cho tới khi đọc được hoặc hết thời gian; dùng tìm kiếm chính xác dưới pixel để ước lượng giá trị bit ở độ phân giải cao hơn ảnh gốc — [US8150163](https://patents.google.com/patent/US8150163)
- Zeng et al.: khớp xen kẽ 3 vòng tinh chỉnh mã nhị phân và quỹ đạo theo ảnh là bước cuối cho thêm 53/955 ảnh đúng; giới hạn là chỉ mô hình vật phẳng cứng, không có biến dạng không phẳng — [arXiv 2610.34788](https://arxiv.org/html/2610.34788)
- Mô hình SR đa frame chuẩn: mỗi frame thấp phân giải là ảnh cao phân giải bị dịch/biến dạng, mờ, lấy mẫu xuống và cộng nhiễu, rồi nghịch đảo mô hình đó — [US8150163](https://patents.google.com/patent/US8150163); giới hạn hiệu năng SR theo sai số đăng ký được Robinson & Milanfar phân tích (đã trích trong ghi chú cũ) — [Milanfar, SR performance](https://users.soe.ucsc.edu/%7emilanfar/publications/journal/SRPerformanceFinal.pdf)
- [nội bộ] `fit_warp` của B: Gauss–Newton cho trường biến dạng chung 4×4 nút (32 tham số), Jacobian **sai phân hữu hạn** (32 lần `Template.sample` mỗi frame), chỉ trên 3 frame điểm cao nhất, 2 vòng; `search_corner` dịch **cùng một δ** cho góc dưới phải ở mọi frame; `refine_geometry` tinh chỉnh 4 góc theo bước 0,2/0,1/0,05.

### Inferences
- Tách tham số hình học thành phần chung (trường biến dạng/cong của tem, dùng chung mọi frame vì tem là vật cứng–cong cố định trong lượt) và phần riêng từng frame (đồng nhất hóa 8 tham số hoặc affine + dịch, cộng vận tốc/L riêng nếu băng không đều). Hiện mới có phần chung trên 3 frame và góc riêng từng frame; thiếu bước kiểm tra phần dư từng frame để **giảm trọng số hoặc loại frame lệch** (trọng số = 1/phần dư chuẩn hóa, hoặc Huber). Đây là cách hợp lý nhất để khi k tăng thì kết quả không xấu đi.
- Độ cong tem: trường 4×4 bilinear đủ cho cong nhẹ một chiều (tem dán trên bề mặt trụ lớn). Nếu tem cong mạnh, mô hình trụ tham số (bán kính + trục, 2–3 tham số) ổn định hơn 32 tham số tự do ở mã chỉ 25 ô; chưa có số đo độ cong thật nên chưa biết cần hay không.
- Khởi tạo nóng: kết quả PassDecoder/YOLO từng frame (góc, vận tốc) và x của lượt trước cùng mã không dùng được (mã khác nhau), nhưng x từ C (bình phương tối thiểu ô) có thể làm điểm khởi đầu cho B và ngược lại, tránh giải lại từ 0,5.

### Gaps
- Không tìm được công trình nào báo số liệu đa frame cho QR 2–3 px/ô kèm mờ chuyển động, hay mô hình tem cong trong khớp mô hình QR.

## 4. Tăng tốc trên CPU (Ryzen 5 5500U): chỗ tốn thời gian và mức tăng kỳ vọng

### Takeaway
Theo cấu trúc mã [nội bộ], phần giải x (Nesterov trên Q ≤841×841) không phải cổ chai; thời gian nằm ở việc **dựng lại ma trận A thưa nhiều lần** (mỗi pixel ~125 điểm PSF: 25 điểm Gauss × 5 điểm vệt) bên trong các vòng quét giả thuyết và Jacobian sai phân. Tăng tốc lớn nhất đến từ giảm số lần dựng A (Jacobian giải tích, quét thô–tinh, dừng sớm theo biên format), sau đó mới là Numba. Tài liệu cho thấy Numba 40–60× với lõi tích chập viết lại thành vòng lặp, và trong gradient chiếu ~96% thời gian là phép nhân ma trận.

### Cited Findings
- Poster HEAD2024 (ảnh Compton, Richardson–Lucy): Numba tăng tốc **40–60× trên 8 lõi** so với mã gốc cho lõi tích chập; muốn đạt hiệu năng tốt phải viết lại phép toán vector hóa thành vòng lặp lồng nhau — [HEAD2024 poster](https://sbs.wustl.edu/Posters/HEAD2024_compton_imaging_poster.pdf)
- Escande & Weiss (khử chập ℓ1 nhanh): **96%** thời gian nằm ở đánh giá gradient, gồm hai phép nhân ma trận thưa–vector; ảnh 1024×1024 khử mờ trong 0,15 s (phần cứng chưa kiểm chứng từ đoạn trích) — [Escande & Weiss 2015](https://pescande.perso.math.cnrs.fr/assets/publis/2015_ultra_fast_l1_deconv_Escande_Weiss.pdf)
- Mức tăng tốc của gradient chiếu có tỉ lệ so với Richardson–Lucy phụ thuộc mạnh vào bài toán và đối tượng, nên không chuyển được giữa các bài toán — [Towards real-time image deconvolution, PMC3755287](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC3755287/)
- Zeng et al.: trung vị 5,8 s/ảnh, p90 33,8 s (trên một GPU dùng chung); bước tìm và bước khớp chiếm 9% và 38% thời gian; các mạng tinh chỉnh 1,2–5,4 s; Pan et al. 34 s — [arXiv 2610.34788](https://arxiv.org/html/2610.34788). Tức là phương pháp mô hình cạnh tranh nhất đã công bố cũng ở cùng bậc thời gian với B (4–15 s).
- Halcon: chế độ `small_modules_robustness = 'high'` tăng khả năng giải mã ô rất nhỏ nhưng tăng đáng kể bộ nhớ, và tài liệu khuyên thu hẹp tham số tìm kiếm (khoảng kích thước ô…) vì nếu không thời gian chạy tăng đáng kể — [MVTec HALCON get_data_code_2d_param](https://www.mvtec.com/doc/halcon/2605/en/get_data_code_2d_param.html)
- [nội bộ] Các điểm gọi `build_matrix` (mỗi lần: tính homography ngược cho np_pixel × |pts| điểm, floor, dựng `csr_matrix` từ COO):
  - `search_corner`: 2 vòng lưới (5×5 = 25, rồi 3×3 − 1 = 8) = 33 giả thuyết × `SEARCH_N` frame, mỗi giả thuyết dựng A rồi giải 3 μ × 30 vòng;
  - `quick_margin`: mỗi giả thuyết phiên bản/góc giải 3 μ × 50 vòng;
  - `fit_geometry`: quét 5 σ;
  - `solve`: 3 vòng ngoài, mỗi vòng `refine_geometry` (bước 0,2/0,1/0,05 trên 8 tọa độ góc) + `build_frames` + (từ vòng 2) `fit_warp` 2 vòng × 3 frame × 32 cột Jacobian sai phân + `build_frames` lần nữa; `apply_format` thêm 2 vòng × 4 μ × 80;
  - `Solver.build` tính `sp.diags(g)·A` rồi BᵀB thưa mỗi lần.
- [nội bộ] `Solver.solve` gọi `sp.linalg.norm(Q, 1)` và `np.where` hai lần mỗi vòng; với N ≤ 841, Q dạng đặc chỉ ~5,6 MB (float64).

### Inferences
Ước lượng dưới đây là suy luận, cần đo bằng `cProfile`/`line_profiler` trên 20–30 lượt thật trước khi làm:
1. **Đo trước** (1 giờ): `python -m cProfile -o b.prof` trên một lượt khó; nếu `build_matrix` + `Solver.build` + `Template.sample` chiếm >60% như phân tích cấu trúc gợi ý, thứ tự bên dưới là đúng.
2. **Tách A thành phần hình học và PSF**: với một lưới pixel cố định trong ROI, A = (ma trận lấy mẫu ô theo homography) ∘ (PSF). Có thể render x lên lưới mịn (ví dụ 8 px/ô, như C đang làm) rồi chập PSF bằng FFT/separable và lấy mẫu bilinear. Khi đó đổi σ_x, σ_y, L chỉ là đổi kernel 1-D (separable Gauss theo x, Gauss ⊛ hộp theo y), không phải dựng lại 450 nghìn phần tử thưa. Với ROI ~60×60 px, phép tiến/lùi bằng FFT hoặc lọc tách được cỡ 10⁵ phép tính, nhỏ hơn ~1 bậc so với dựng CSR.
3. **Jacobian giải tích thay sai phân hữu hạn** trong `fit_warp` (32 lần sample → 1 lần sample + gradient ảnh template × đạo hàm tọa độ theo nút bilinear) và trong `refine_geometry`/`refine` (8 tham số góc): giảm ~10–30× riêng các bước này.
4. **Thô–tinh và dừng sớm**: `search_corner` dùng 2 lớp lưới 33 giả thuyết; có thể thay bằng 1–2 bước Gauss–Newton trên 2 tham số δ (trơn) hoặc lưới thô với ít vòng Nesterov hơn và chỉ trên vùng gần góc (br_only đã có). Dừng sớm khi biên điểm format giữa giả thuyết tốt nhất và thứ hai vượt ngưỡng; bỏ phiên bản V3 nếu tem đã chốt là V1 (CLAUDE.md: "in QR version 1 mức M"), giảm 1/3 số giả thuyết phiên bản và N từ 841 xuống 441.
5. **Bộ giải x**: dùng Q đặc (`np.ndarray`) và `L = ‖Q‖₂` ước lượng bằng vài bước lũy thừa một lần, bỏ `np.where` bằng mặt nạ chỉ số tự do; khởi tạo nóng μ-continuation từ x của vòng ngoài trước (đã làm một phần) và dừng khi ‖Δx‖∞ < 10⁻³. Với N ≤ 841, matvec đặc ~0,3–0,5 ms, nên 1.000 vòng ~0,5 s là trần.
6. **Numba** sau cùng, cho các vòng lặp đã cố định: lõi tính A (homography + floor + cộng dồn trọng số theo ô, tránh COO→CSR), `Template.sample`, ICM theo khối, BCJR theo cột. Theo poster HEAD2024, mức 40–60× có được khi viết lại thành vòng lặp lồng và chạy song song 8 lõi; trên 5500U (6 lõi/12 luồng) và với mã đã vector hóa NumPy, kỳ vọng thực tế thấp hơn, cỡ 3–10× cho từng lõi. Lưu ý chi phí biên dịch JIT lần đầu (dùng `cache=True` vì tiến trình nền spawn mới).
7. **Song song**: tiến trình nền hiện chạy MỘT bộ giải; các giả thuyết phiên bản/góc độc lập nhau nên có thể chạy song song bằng `concurrent.futures` trong tiến trình đó (đặt `OMP_NUM_THREADS=1` cho từng worker để tránh tranh luồng BLAS). Với 6 lõi, giảm p95 khoảng 2–4× ở giai đoạn giả thuyết; không giúp các bước tuần tự (vòng ngoài).
- Kết hợp 2–5 có thể đưa B từ 4–15 s xuống cỡ 1–3 s mà chưa cần Numba; đây là ước lượng chưa đo.

### Gaps
- Không có profile thật của B/C trong repo được đọc trong phiên này; mọi phân bổ thời gian là suy từ cấu trúc mã.
- Không tìm được benchmark trực tiếp Numba so với SciPy sparse cho gradient chiếu trên ảnh nhỏ (~60×60).

## 5. Các phương án học máy (CNN phân loại ô, mạng unrolled) và chi phí CPU

### Takeaway
Các mạng khử mờ QR công bố đều là ảnh→ảnh, ảnh lớn, mã to, đọc bằng ZBar; tốt nhất ~90% trên tập 150 ảnh nhưng cần 0,7–0,9 s và 26 M tham số mỗi ảnh; mạng nhẹ 0,28 M tham số chỉ 49%. Trên ảnh chụp tay thật, phương pháp mô hình của Zeng et al. thắng mọi mạng (93,1% so với 83,6% của NAFNet-32). Không có bài nào về bộ phân loại từng ô cho QR mờ cho LLR vào RS; đây vẫn là khoảng trống, phù hợp vai trò "bộ ước lượng LLR chịu sai σ" bên cạnh B.

### Cited Findings
- ADNet (arXiv 2510.12098, 10/2025): định tuyến theo mức mờ giữa EG-Restormer (26,13 M tham số, 565 GFLOPs ở 512×512, 0,910 s, DR 90,0%) và LENet (0,28 M, 3,87 GFLOPs, 0,23–0,28 s, DR 49,3%); ADNet 90% DR trong 0,737 s (−19% thời gian); NAFNet-32 81,3%, Restormer 88,7%. Tập đánh giá chỉ 150 ảnh (100 tổng hợp, 50 thật), huấn luyện trên 1.822 ảnh QR tổng hợp mờ chuyển động không đều; giải mã bằng ZBar; không nêu phần cứng, không nêu kích thước ô; tác giả nhận xét ràng buộc cạnh quan trọng cho khả năng giải mã hơn độ chính xác từng pixel — [arXiv 2510.12098](https://arxiv.org/html/2510.12098v1)
- Trên 955 ảnh chụp tay của Zeng et al.: NAFNet-32 83,6%, MIMO-UNet+ 81,9%, EG-Restormer 73,7%, Restormer 71,3%, DeepDeblur 57,0%, DeMoE 43,9%, DeblurGAN-v2 25,7%; bản trọng số công bố (không tinh chỉnh) chỉ 12,1–25,1% — [arXiv 2610.34788](https://arxiv.org/html/2610.34788)
- Công trình liên quan được ADNet nhắc: Pu et al. (CNN kép đảo suy biến mã 2-D), Li et al. (CNN sâu + ngưỡng thích nghi); các bài này chuyển mô hình khử mờ chung sang QR mà không đưa tiên nghiệm riêng của QR vào — [arXiv 2510.12098](https://arxiv.org/html/2510.12098v1)
- Dynamsoft thử một mô hình ESRGAN có sẵn: chưa huấn luyện trên QR và giới hạn đầu vào 50×50 px nên kết quả hạn chế; ảnh đầy đủ độ phân giải tăng khoảng cách quét hơn 2 lần so với luồng video 1080p (130 cm so với 65 cm cho mã 2×2 cm) — [Dynamsoft, Long-distance QR scanning](https://www.dynamsoft.com/codepool/long-distance-qr-code-scanning-resolution.html)
- Bằng sáng chế mô tả mạng đánh dấu ô lỗi để đưa vào RS xóa (đã nêu trong báo cáo cũ) — [USPTO 12524638](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/12524638)

### Inferences
- Chi phí CPU: bộ phân loại ô nhỏ (đầu vào K frame đã nắn về lưới 25×25 ô ở 4–8 px/ô, vài lớp tích chập, đầu ra 25×25 logit) có cỡ 10⁵–10⁶ tham số và dưới 1 GFLOP, tức vài chục ms trên CPU qua ONNX Runtime/OpenCV DNN — nhỏ hơn ~2 bậc so với Restormer ở 512×512. Đây là ước lượng từ quy mô, không phải số đo.
- Mạng unrolled (mỗi tầng = một bước gradient chiếu của chính mô hình A với σ/L học được + một khối CNN nhỏ) là cầu nối tự nhiên giữa B và học máy: giữ mô hình vật lý, học phần sai mô hình; nhưng không tìm được bài QR nào dùng.
- Vai trò hợp lý: dùng đầu ra mạng làm (a) khởi tạo x cho B, (b) LLR thứ hai cho Chase/GMD, (c) bộ phiếu độc lập cho cổng chống báo sai — không thay B.

### Gaps
- Không tìm được bài nào về CNN phân loại từng ô hay mạng unrolled cho QR ở 2–3 px/ô, cũng không có số đo thời gian trên CPU cho mạng QR (ADNet không nêu phần cứng).
- Không đọc được bản đầy đủ của preprint trên preprints.org (202606.0184, HTTP 403) xuất hiện trong kết quả tìm kiếm về QR deblurring.

## 6. Sản phẩm thương mại công khai làm giải mã "theo mô hình ký hiệu"

### Takeaway
Không nhà cung cấp lớn nào công bố chi tiết giải mã theo mô hình thuận như B. Cognex PowerGrid định vị theo kết cấu ô "từ trong ra ngoài" thay vì finder; Halcon có chế độ chịu ô rất nhỏ đánh đổi bộ nhớ/thời gian; Dynamsoft có các chế độ khử mờ chọn tự động; các tuyên bố ngưỡng px/ô (0,7–5 px) là của nhà cung cấp, chưa kiểm chứng độc lập. Bằng chứng gần nhất với "khớp mô hình ký hiệu" là các bằng sáng chế Cognex thử tổ hợp ô hợp lệ cho mã thiếu phân giải.

### Cited Findings
- Cognex PowerGrid (12/2014, DataMan 300 X): thuật toán định vị dựa trên kết cấu, tìm mẫu ô sáng–tối xen kẽ bên trong mã thay vì bắt đầu từ finder; đọc được mã khi finder, clocking pattern hoặc quiet zone bị hỏng nặng hay mất hẳn; động lực: phần lớn mã không đọc được mà Cognex phân tích bị hỏng finder/clocking/quiet zone. Các nguồn đều là tin ra mắt, không có số đo độc lập — [A3/Automate, PowerGrid](https://www.automate.org/vision/news/powergrid-technology-for-2d-barcode-reading); [Vision Systems Design](https://vision-systems.com/boards-software/article/16746154/cognex-announces-powergrid-algorithm-for-barcode-readers)
- Bằng sáng chế kiểu Cognex thử tổ hợp ô hợp lệ cho mã thiếu độ phân giải (đã nêu trong báo cáo cũ) — [USPTO 10599902](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/10599902)
- MVTec HALCON: tham số `small_modules_robustness` ('low' mặc định, 'high' tăng khả năng giải mã ô rất nhỏ, tốn bộ nhớ đáng kể); tìm kiếm bắt đầu ở tầng kim tự tháp cao nhất mà ô còn tách được theo kích thước ô tối đa; kết quả báo phương pháp nào (độ bền thấp/cao) đã giải mã — [HALCON get_data_code_2d_param](https://www.mvtec.com/doc/halcon/2605/en/get_data_code_2d_param.html); [HALCON get_data_code_2d_results](https://www.mvtec.com/doc/halcon/2505/en/get_data_code_2d_results.html)
- Dynamsoft: `DeblurModes` để null thì chương trình tự chọn thuật toán khử mờ cho mã hơi mờ; khuyến nghị ô ≥2 px cho mã 1-D; nhấn mạnh kích thước ô quyết định khả năng đọc hơn độ phân giải — [Dynamsoft, check if barcode image is clear enough](https://www.dynamsoft.com/barcode-reader/docs/core/introduction/how-to-guide/check-if-the-barcode-image-is-clear-enough-for-recognition.html); [Dynamsoft blurry barcodes](https://www.dynamsoft.com/barcode-dataset/blurry-barcodes/)
- Viziotix tuyên bố thuật toán Nano-Scan tìm vạch hẹp chỉ 0,7 px/vạch nhưng vẫn khuyến nghị tối thiểu 1,5 px/vạch hẹp cho mã 1-D; đa số bộ giải mã cần 3–5 px/vạch (tuyên bố nhà cung cấp) — [Viziotix whitepaper](https://www.viziotix.com/wp-content/uploads/2024/11/2024.11.14.How-to-Select-the-Best-Camera-for-Barcode-Scanning-Whitepaper-Viziotix.pdf)

### Inferences
- Bài học dùng được từ PowerGrid: định vị/giả thuyết lưới dựa vào kết cấu ô toàn mã (tự tương quan theo bước ô) bền hơn chỉ dựa vào finder khi finder mờ nặng; với B, có thể dùng phổ/tự tương quan của ROI để ràng buộc bước lưới trước khi NCC finder — giảm số giả thuyết.
- Halcon cho thấy sản phẩm thương mại xử lý ô rất nhỏ bằng chế độ riêng tốn kém và khuyên thu hẹp không gian tìm kiếm — đúng chiến lược tăng tốc ở mục 4 (biết trước phiên bản, kích thước ô, hướng chuyển động).

### Gaps
- Không tìm được tài liệu công khai của Keyence, Zebra, Honeywell, SICK về giải mã theo mô hình hay ngưỡng px/ô cho mã mờ; tài liệu Cognex/Halcon không tiết lộ thuật toán bên trong.
- Không có benchmark độc lập so sánh các sản phẩm thương mại ở 2–3 px/ô có mờ chuyển động.
