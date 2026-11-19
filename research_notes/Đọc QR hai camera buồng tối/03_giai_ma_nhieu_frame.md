# Giải mã QR V2-M ở 2,2–2,44 px/ô bằng nhiều frame, chống đọc sai, trên Jetson Nano/CPU

Phạm vi: bước giải mã sau detect cho tem 32 mm, QR version 2 (25×25), mức M (1 khối RS: 28 codeword dữ liệu + 16 EC, sửa tối đa 8 lỗi hoặc 16 erasure). Buồng tối, exposure ≤2,5 ms nên ảnh gần như sắc, 55–61 px/mã. Mỗi tem ở trong khung hình 5–7,5 s, tức hàng chục frame. Không đi sâu vào các bộ giải dựa trên mô hình chạy nền; phần đó do người khác phụ trách.

Soạn sau 17 lượt tìm/đọc web (18/11/2026). Một số trang chính không đọc được: PMC/MDPI chặn bot (bảng số của Skurowski 2022), patent US12524638 trả 404. Các con số có ký hiệu "[tính toán]" là tôi tự tính bằng công thức chuẩn, không lấy từ nguồn. Các nguồn của Dynamsoft là tài liệu vendor/marketing.

## (A) Thuật toán tốt nhất để giải mã ở ~2,3 px/ô với nhiều frame sắc độ phân giải thấp

### Takeaway
Ở 2,2–2,44 px/ô, mã nằm dưới ngưỡng thực dụng 3–3,5 px/ô mà Skurowski et al. (2022) kết luận, nhưng vẫn trên Nyquist (2 px/ô). Một số decoder, nhất là OpenCV, vẫn đọc được một phần ở vùng này. Hướng có cơ sở mạnh nhất cho bài toán là **lấy mẫu lưới ô theo từng frame rồi cộng dồn giá trị mềm của từng ô qua các frame, và đánh dấu ô không chắc là erasure cho Reed–Solomon**. Đây chính là cách Cognex mô tả trong patent US9734376. Cách này tốt hơn "phóng ×4, phase correlation, lấy trung bình ảnh". Siêu phân giải nhiều frame có ràng buộc nhị phân/lưới của nhóm Nagoya là bằng chứng học thuật gần nhất: tỉ lệ đọc ở QR 86×86 px tăng từ 0 lên 0,55 khi dùng khoảng 100 frame.

### Cited Findings
**Giới hạn module nhỏ và decoder**
- Skurowski, Nurzyńska, Pawlyta, Cyran, "Performance of QR Code Detectors near Nyquist Limits" (Sensors 22(19):7230, 2022). Kết luận: để giải mã thực dụng, module QR không nên nhỏ hơn 3–3,5 px, bất kể MTF. Gần Nyquist, OpenCV cho kết quả tốt nhất, ZBar kém nhất. ZBar mạnh với module lớn, còn ZXing và OpenCV có tỉ lệ nhận dạng cao hơn với QR rất nhỏ. Ở vùng sát hoặc dưới Nyquist, nơi các decoder khác thất bại, OpenCV vẫn giải được một phần. Tôi không đọc được bảng số theo px/ô vì trang PMC/MDPI chặn truy cập tự động. — [MDPI](https://mdpi.com/1424-8220/22/19/7230); [PMC9572759](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC9572759/); [tóm tắt Bohrium](https://www.bohrium.com/paper-details/performance-of-qr-code-detectors-near-nyquist-limits/817339142974210048-4100)
- Nghiên cứu QR của BoofCV (Abeles): so BoofCV 0.33, OpenCV 4.0.1, Quirc (2018), ZBar 0.10, ZXing 3.3.3 (TRY_HARDER) trên 16 nhóm ảnh (blurred, close, damaged, perspective…). BoofCV tốt nhất hoặc gần nhất ở mọi nhóm trừ non-compliant/pathological. Quirc tốt ở tình huống thường nhưng kém ở các nhóm mà decoder khác đọc được. ZBar chậm nhất mọi nhóm. Trang này **không có nhóm module nhỏ/độ phân giải thấp**, và kết quả chỉ ở dạng biểu đồ tương đối. — [BoofCV Performance:QrCode](https://boofcv.org/index.php?title=Performance:QrCode)
- Benchmark Dynamsoft (vendor) trên 536 ảnh, 16 nhóm: BoofCV 60,69%, OpenCV WeChat 48,89%, ZBar 38,95%, ZXing 31,87%. Thời gian: BoofCV ~105 ms/ảnh, ZBar 157, ZXing 180, WeChat ~758 ms. Đây là ảnh nguyên khung, không phải ROI nhỏ, và phiên bản ZXing cũ. — [Dynamsoft QR benchmark](https://www.dynamsoft.com/codepool/qr-code-reading-benchmark-and-comparison.html)

**Ghép nhiều frame ở mức ô (khuyến nghị chính)**
- **Cognex US9734376 / US10592715** ("System and method for reading patterns using multiple image frames", tác giả Nadabar):
  - Mỗi frame: chia vùng mã thành các vùng con (ví dụ 4×4 ô). Vùng con bị cháy sáng (saturation index cao) thì đánh dấu "unknown". Các ô còn lại được nhị phân theo ngưỡng histogram (ví dụ Otsu), cho giá trị 0–1.
  - Cộng dồn: độ tin "0" và độ tin "1" của từng ô được cộng riêng qua các frame. Ô unknown không đóng góp; frame không định vị được mã thì giữ nguyên tổng.
  - Quyết định: một ô chỉ được gán 0/1 khi tổng tin cậy một phía vượt phía kia một ngưỡng; nếu không thì vẫn là unknown. Sau **mỗi frame** lại thử giải mã. Với mã có Reed–Solomon (ví dụ DataMatrix), ô unknown được coi là erasure, giúp giảm tải sửa lỗi.
  - Căn chỉnh giữa các frame là ngầm định: lưới ô của từng frame được định vị độc lập.
  - Patent không có số liệu chính xác/tốc độ; ví dụ dùng 3 frame, N tối đa không cố định.
  — [Google Patents US9734376B2](https://patents.google.com/patent/US9734376B2/en); [USPTO 10592715](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/10592715)
- Có một patent tên "Erasure-based quick response (QR) decoding" (US 12524638), nhưng tôi không đọc được nội dung (404). — [USPTO PDF 12524638](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/12524638)
- Nguyên lý errors-and-erasures: RS sửa được A lỗi và B erasure khi 2A + B ≤ n − k. Erasure tốn một nửa ngân sách so với lỗi. — [USPTO 11323138 (RS soft-decision)](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/11323138)
- Họ thuật toán GMD/Chase cho RS: dựng nhiều mẫu erasure từ thông tin mềm (xóa các symbol kém tin cậy nhất), rồi chạy giải mã errors-and-erasures (Berlekamp–Massey) nhiều lần. — [arXiv 0908.2828](https://arxiv.org/pdf/0908.2828); [arXiv 1104.0576](https://arxiv.org/pdf/1104.0576); [arXiv cs/0611090 (ASD dùng thông tin mềm mức bit)](https://arxiv.org/pdf/cs/0611090)
- Một patent UMTS so sánh ba chiến lược nhiều frame: chỉ quyết định cứng, bỏ phiếu, và cập nhật symbol + độ tin cậy. Đây là phiên bản viễn thông của cùng ý tưởng cộng dồn mềm. — [USPTO 7633976](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/7633976)

**Siêu phân giải nhiều frame dành riêng cho QR**
- Kato, Deguchi et al. (Nagoya), ICDAR 2011, "Low Resolution QR-Code Recognition by Applying Super-Resolution Using the Property of QR-Codes":
  - Thêm ràng buộc mẫu nhị phân vào siêu phân giải.
  - Tỉ lệ nhận dạng 98% trên ảnh độ phân giải thấp mà phương pháp thường không đọc được; trung bình hơn siêu phân giải thông thường 15,7 điểm, tối đa 38,0 điểm.
  - Báo cáo tiếng Nhật: khoảng 100 frame webcam liên tiếp. Mã ~126×126 px tăng từ 0,30 lên 0,91; mã ~86×86 px tăng từ 0,00 lên 0,55. Số thử nghiệm nhỏ (107 và 138).
  - Bản sau thêm ràng buộc lưới, siêu phân giải 2 bước, và ước lượng PSF từ finder pattern.
  — [bibtex ICDAR 2011](https://bibtex.github.io/ICDAR-2011-KatoDTIM.html); [IEEE 6065459](https://ieeexplore.ieee.org/document/6065459); [IEICE 2010](https://www.ieice.org/ken/paper/2010090520aG/eng/); [PDF 672](https://pubdb.vislab.is.i.nagoya-u.ac.jp/~murase/pdf/672-pdf.pdf); [PDF 492](https://wine.vislab.is.i.nagoya-u.ac.jp/~murase/pdf/492-pdf.pdf)
- Wronski et al. (SIGGRAPH 2019): ghép burst bằng kernel regression với kernel Gauss bất đẳng hướng, thêm mô hình robustness để loại vùng căn chỉnh sai. Chạy khoảng 100 ms/frame 12 MP trên điện thoại. Có bản cài đặt lại IPOL 2023. — [arXiv 1905.03277](https://arxiv.org/pdf/1905.03277.pdf); [IPOL 2023/460](https://www.ipol.im/pub/art/2023/460/article_lr.pdf)
- Patent "Multi-frame super-resolution barcode imager" (US9916489): ghép các frame lệch nhau sub-pixel thành ảnh độ phân giải cao cho đầu đọc mã. — [Google Patents US9916489](https://patents.google.com/patent/US9916489)

**Độ chính xác lưới lấy mẫu**
- Trong ISO 18004, finder, alignment và timing pattern dùng để căn ký hiệu và xác định lưới lấy mẫu. Từ vị trí finder và alignment suy ra homography để nắn mã về hình vuông. — [USPTO 8515162](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/8515162); [USPTO 10817971](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/10817971)
- ZBar (qrdec.c, Terriberry): homography có độ phân giải 14 bit. Tìm alignment pattern với độ chính xác 2 bit dưới mức module, chịu được việc blur ăn mòn tới 50% module. — [zbar qrdec.c](https://grok.dragonflybsd.org/xref/dports/graphics/zbar/zbar-0.23.90/zbar/qrcode/qrdec.c?a=true)
- rqrr (Rust, bản port quirc): đo timing pattern để ước lượng kích thước lưới; với version >1 thì tìm alignment pattern ở góc thứ tư. — [rqrr grid.rs](https://docs.rs/crate/rqrr/latest/source/src/identify/grid.rs)
- Version 2 có đúng một alignment pattern, tâm tại ô (18,18); timing pattern ở hàng/cột 6. — [Thonky: alignment pattern locations](https://www.thonky.com/qr-code-tutorial/alignment-pattern-locations)

### Inferences
- **Pipeline đề xuất (rẻ, tất định, chạy trên CPU)**, dựa trên Cognex + GMD + cấu trúc V2 cố định. Đây là thiết kế suy luận, chưa đo.
  1. Mỗi frame: ước lượng homography 25×25 (+4 ô quiet zone) từ 4 góc mã. Tinh chỉnh tối thiểu hóa sai khác giữa ảnh và **mẫu cố định đã biết**: 3 finder, timing hàng/cột 6, alignment tại (18,18), ô tối cố định, và 2 bản format info (BCH sau khi đã chốt M). V2 có khoảng 200/625 ô biết trước, đủ để fit homography 8 tham số bằng Gauss–Newton/ECC dưới mức 0,1 ô. Mức sai lưới cần đạt: ở 2,3 px/ô, lệch 0,25 ô (~0,6 px) đã làm giá trị tâm ô lẫn với ô bên cạnh, nên tinh chỉnh dưới 0,1 ô là điều kiện tiên quyết.
  2. Lấy mẫu giá trị xám tại tâm ô (bilinear, hoặc trung bình có trọng số Gauss σ ≈ 0,3 ô). Chuẩn hóa bằng mức đen/trắng ước lượng từ chính các ô cố định của frame đó, gồm cả hiệu chỉnh độ sáng tuyến tính theo vị trí. Kết quả là LLR hoặc z-score của từng ô.
  3. Cộng dồn LLR theo ô qua các frame. Lưới cố định với mã nên không cần căn chỉnh ảnh giữa các frame, bỏ được phase correlation/upscale. Có thể trừ ảnh hưởng ô lân cận (ISI do lens blur ở 2,3 px/ô) bằng một bước giải chập 3×3 trên lưới ô, với kernel ước lượng từ ô cố định.
  4. Chuyển LLR ô sang độ tin cậy codeword. Mỗi codeword gồm 8 ô; độ tin cậy codeword ≈ |LLR| nhỏ nhất trong 8 bit. Bỏ mặt nạ (mask từ format info), giải RS errors-and-erasures, và thử GMD/Chase với số erasure e = 0, 2, 4, …. Giới hạn e ≤ 6 vì lý do an toàn ở mục (C).
  5. Nếu RS thất bại sau frame k, chờ frame k+1 rồi lặp lại. Chi phí tăng thêm mỗi frame chỉ khoảng vài trăm phép toán.
- **Số frame cần**: nhiễu trắng giảm theo √N. Với mã gần như sắc, 4–8 frame có thể đủ để LLR của phần lớn ô vượt ngưỡng. Lỗi hệ thống (sai lưới, ISI) không giảm theo N, nên bước 1 và bước 3 quan trọng hơn số frame. Kato cần khoảng 100 frame vì dùng webcam, mã 86 px và chất lượng ảnh kém hơn. Chưa có nguồn cho đúng cấu hình này; cần đo.
- So với chuỗi hiện tại (zxing 3 binarizer → WeChat → Wiener → xếp chồng ảnh ×4): binarizer của zxing/WeChat bỏ phí thông tin mềm. Lấy trung bình ảnh ×4 sau phase correlation chỉ khử nhiễu và làm nhòe thêm (interpolate-then-average). Lưới ô cố định cộng dồn LLR vừa đúng bản chất bài toán (25×25 giá trị nhị phân) vừa rẻ hơn nhiều.
- Có thể khai thác **cấu trúc dữ liệu đã biết** như "known symbols" thay vì erasure. Mode indicator (0001 numeric / 0100 byte), char count, byte '#' (0x23), terminator và **pad codeword 0xEC/0x11** đều xác định được khi giả thuyết độ dài (L1, L2). Với vài chục cặp độ dài khả dĩ, có thể thử từng giả thuyết, cố định các bit đã biết, và chỉ giải RS cho phần còn lại. Đây là suy luận; cần cẩn thận vì nó tăng xác suất đọc sai nếu dùng làm "sửa ép" (xem C).

### Gaps
- Không đọc được bảng tỉ lệ đọc theo px/ô của Skurowski 2022. Không có đường cong tỉ lệ đọc theo px/ô công khai cho zxing-cpp 2.x/3.x, BoofCV hay quirc.
- Không tìm thấy công bố đo cộng dồn LLR mức ô cho QR (số frame cần, tỉ lệ đọc). Patent Cognex không có số.
- Chưa đọc được nội dung patent "Erasure-based QR decoding" US12524638.

## (B) Tốc độ trên ARM (Jetson Nano A57/Maxwell) và x86 CPU

### Takeaway
Không có benchmark công khai cho zxing-cpp, WeChat hay quirc trên Jetson Nano. Dynamsoft hỗ trợ aarch64/Jetson Nano chính thức nhưng không công bố thời gian. Trên x86, zxing-cpp 3.1.1 tốn trung bình khoảng 70 ms/ảnh **toàn khung** (trung vị khoảng 43 ms, i5-13400F, số của vendor). Với ROI ~60 px, chi phí decode thực chủ yếu đến từ upscale và lặp nhiều binarizer. Pipeline lưới ô cộng dồn LLR có độ phức tạp khoảng 625 mẫu × N frame, gần như miễn phí so với detect.

### Cited Findings
- zxing-cpp 3.1.1 trên i5-13400F (Windows 11), benchmark C++ của Dynamsoft: recall 71,70%, thời gian trung bình 69,90 ms, trung vị 44,73 ms, P95 227,58 ms. Qua Python: trung bình 70,22 ms, trung vị 42,49 ms, recall 67,43%. Đây là ảnh nguyên khung và số của vendor. — [Dynamsoft C++ benchmark](https://www.dynamsoft.com/codepool/benchmark-barcode-reading-cpp-zxing-dynamsoft-barcode-reader.html); [Dynamsoft Python benchmark](https://www.dynamsoft.com/codepool/benchmark-barcode-reading-python-zxing-dynamsoft-barcode-reader.html)
- zxing-cpp có gói aarch64 (Arch Linux ARM, bản 3.0.2), nhưng không có số đo tốc độ. — [archlinuxarm zxing-cpp](https://archlinuxarm.org/packages/aarch64/zxing-cpp)
- Dynamsoft hỗ trợ ARM64 từ bản 7.6.x (Ubuntu 18.04 aarch64, Jetson Nano). Bản v11 (DCV 3.6.50 / DBR 11.6.50) có hướng dẫn C++ cho Jetson. Có wheel Python aarch64 (bundle 11.6.5000). Cần license, có trial 30 ngày. Không có số thời gian trên Jetson. — [Dynamsoft Jetson Nano](https://www.dynamsoft.com/codepool/jetson-nano-arm64-barcode-sdk.html); [Dynamsoft Docker ARM64 Python](https://www.dynamsoft.com/codepool/docker-arm64-arm32-python-barcode-qr-recognition.html)
- Dynamsoft có chế độ dừng sớm khi đã tìm thấy mã (ExpectedBarcodesCount). — [Dynamsoft speed](https://dynamsoft.com/blog/insights/boost-barcode-reading-speed/); [ExpectedBarcodesCount](https://www.dynamsoft.com/barcode-reader/docs/core/parameters/reference/expected-barcodes-count.html)
- Quirc và BoofCV nhanh nhất trong benchmark của BoofCV (tổng 37,4 s và 41,6 s), ZXing 78,3 s, ZBar 115,4 s. BoofCV là Java; quirc là C thuần, nhỏ, dễ biên dịch cho ARM. — [DZone: new QR code reader library](https://dzone.com/articles/new-qr-code-reader-library)
- OpenCV WeChat chậm nhất trong benchmark của Dynamsoft, khoảng 758 ms/ảnh toàn khung. — [Dynamsoft QR benchmark](https://www.dynamsoft.com/codepool/qr-code-reading-benchmark-and-comparison.html)
- Wronski: kernel-regression burst SR chạy khoảng 100 ms/12 MP trên GPU di động. Quy về ROI 60×60 px thì không đáng kể. — [arXiv 1905.03277](https://arxiv.org/pdf/1905.03277.pdf)

### Inferences
- Jetson Nano có 4 lõi Cortex-A57 1,43 GHz. Theo kinh nghiệm chung, mỗi lõi chậm hơn lõi x86 desktop hiện đại khoảng 3–5 lần; đây là ước lượng, không có nguồn đo trong phiên này. Vì vậy chuỗi hiện tại (200–350 ms CPU x86 cho mỗi detection thất bại) có thể lên **khoảng 0,7–1,5 s trên A57**, không chịu nổi khi có hai camera. Ưu tiên:
  - (a) Bỏ upscale ×4 trước zxing. Gọi zxing một lần trên ROI đã nắn (warp 25+8 ô × k px) với `is_pure=True` hoặc ảnh nhị phân từ lưới ô (vẽ lại 25×25 → 4 px/ô).
  - (b) Đưa phần lưới ô + LLR + RS vào C++/NumPy vector hóa. RS(44,28) trên GF(256) với Berlekamp–Massey tốn vài µs; GMD 4–8 lần thử vẫn dưới 1 ms.
  - (c) Bỏ WeChat CNN trên Nano. Model nặng và benchmark cho thấy là decoder chậm nhất.
  - (d) GPU Maxwell 128 core nên dành cho detect (YOLO/TensorRT). Phần giải mã nhỏ, rẽ nhánh nhiều, không hợp GPU.
- Đa luồng: zxing-cpp, OpenCV và NumPy nhả GIL trong phần C/C++, nên có thể dùng thread pool 2–4 luồng theo ROI/camera. Lưu ý detector WeChat toàn cục không có khóa (ghi trong CLAUDE.md dự án).
- Early exit theo frame: khi LLR đã cho RS giải được với 0 erasure và ít lỗi, dừng xử lý tem đó và chỉ theo dõi vị trí (PassReader đã có cơ chế "bỏ cascade QR đã đọc chắc").

### Gaps
- Không có số đo zxing-cpp, quirc, ZBar hay WeChat trên Jetson Nano hoặc Cortex-A57. Không có số đo Dynamsoft trên Jetson. Cần tự đo.
- Không tìm được benchmark decode trên ROI nhỏ (~60 px) thay vì ảnh nguyên khung.

## (C) An toàn chống đọc sai với nội dung độ dài thay đổi

### Takeaway
Reed–Solomon (44,28) đi kèm kiểm tra cấu trúc là hàng rào rất mạnh nếu **không dùng hết ngân sách sửa lỗi**. Xác suất một từ mã rác bị "sửa" thành một codeword hợp lệ là khoảng 9×10⁻¹² khi không có erasure, nhưng tăng lên khoảng 4×10⁻⁷ với 6 erasure, 1×10⁻⁵ với 8 erasure, và 7×10⁻³ với 12 erasure [tính toán]. Ngoài ra, cấu trúc segment numeric/byte '#'/numeric, độ dài khớp số bit, pad codeword 0xEC/0x11 và regex `^\d+#\d+$` thêm vài chục bit kiểm tra. Quy tắc nên là: giới hạn số erasure/lỗi được dùng, kiểm tra cấu trúc nghiêm ngặt, và yêu cầu nhất trí giữa các frame hoặc nhóm frame **độc lập**.

### Cited Findings
- Cấu trúc V2-M: 44 codeword, 28 dữ liệu, 16 EC, 1 khối. Dung lượng 63 chữ số numeric / 26 byte. — [Thonky: error correction table](https://www.thonky.com/qr-code-tutorial/error-correction-table); [Thonky: character capacities](https://www.thonky.com/qr-code-tutorial/character-capacities)
- Pad codeword QR luân phiên 11101100 (0xEC) và 00010001 (0x11) cho tới khi đủ dung lượng; trước đó là terminator tối đa 4 bit 0. — [Thonky: data encoding](https://www.thonky.com/qr-code-tutorial/data-encoding)
- Cận McEliece–Swanson (1986): với mã RS sửa t lỗi, khi xảy ra nhiều hơn t lỗi thì xác suất decoder trả về sai codeword (thay vì báo thất bại) nhỏ hơn 1/t!. Với t = 8, 1/8! ≈ 2,5×10⁻⁵. JPL cho biểu thức chặt hơn dựa trên xác suất một mẫu lỗi ngẫu nhiên rơi vào bán kính t quanh một codeword khác. — [Caltech: McEliece & Swanson 1986](https://resolver.caltech.edu/CaltechAUTHORS:MCEieeetit86b); [JPL TDA 42-84](https://ipnpr.jpl.nasa.gov/progress_report/42-84/84F.html); [Tolhuizen tổng quát hóa](https://link.springer.com/chapter/10.1007/978-3-7091-2786-5_26)
- zxing-cpp Python 2.3: đối tượng kết quả có `valid`, `text`, `bytes`, `format`, `symbology_identifier`, `ec_level`, `content_type`, `position`, `orientation`, `error`. `read_barcodes` có `try_rotate`, `try_downscale`, `text_mode`, `binarizer`, `is_pure`, `return_errors`. **Python 2.3 không có `version` và không có số lỗi RS đã sửa.** C++ có `version()` và từ 3.x chuyển sang `extra(BarcodeExtra::Version/ECLevel)`. — [Debian: zxing-cpp 2.3.0 wrappers/python/zxing.cpp](https://sources.debian.org/src/zxing-cpp/2.3.0-5/wrappers/python/zxing.cpp); [docs.rs zxing-cpp Barcode.h](https://docs.rs/crate/zxing-cpp/0.5.1/source/core/src/Barcode.h); [release notes](https://github.com/nu-book/zxing-cpp/releases)
- Thực hành ngành: Dynamsoft MultiFrameResultCrossFilter mặc định frameWindow = 5, minConsistentFrames = 2 cho barcode. — [Dynamsoft CrossVerificationCriteria](https://www.dynamsoft.com/capture-vision/docs/mobile/programming/maui/api-reference/utility/cross-verification-criteria.md)
- Patent Cognex: cell chỉ được gán giá trị khi chênh lệch tin cậy tích lũy vượt ngưỡng, còn lại để "unknown" (erasure). Đây là cơ chế giữ độ tin cậy, không ép quyết định. — [US9734376B2](https://patents.google.com/patent/US9734376B2/en)

**[tính toán] xác suất một từ rác 44 byte rơi vào vùng giải mã được của RS(44,28), theo số erasure e** (công thức Σ_{i≤⌊(16−e)/2⌋} C(44−e,i)·255^i / 256^(16−e)):

| erasure e | lỗi sửa thêm tối đa | P(sửa nhầm từ rác) |
|---|---|---|
| 0 | 8 | 9,3×10⁻¹² |
| 2 | 7 | 3,7×10⁻¹⁰ |
| 4 | 6 | 1,3×10⁻⁸ |
| 6 | 5 | 4,5×10⁻⁷ |
| 8 | 4 | 1,4×10⁻⁵ |
| 10 | 3 | 3,5×10⁻⁴ |
| 12 | 2 | 7,5×10⁻³ |
| 14 | 1 | 1,2×10⁻¹ |

Lưu ý: GMD/Chase thử K mẫu erasure thì xác suất trên nhân khoảng K lần.

**[tính toán] số pad codeword còn lại (V2-M, 224 bit dữ liệu) với mã hóa segment numeric/byte/numeric**: 12#12 → 128 bit, 11 pad codeword; 6#6 → 16 pad; 20#20 → 4 pad; 25#25 → 216 bit, 0 pad.

### Inferences
- **Bộ lọc đề xuất, theo thứ tự rẻ trước**:
  1. Format info phải giải BCH ra mức **M**, với khoảng cách Hamming nhỏ so với 32 mẫu hợp lệ. Cả hai bản format phải đồng thuận hoặc khoảng cách tổng nhỏ.
  2. Lưới phải là 25×25 (version 2).
  3. Bitstream gồm đúng: numeric(L1) → byte(1, = 0x23) → numeric(L2) → terminator → pad đúng chuỗi 0xEC/0x11. Không có mode khác, không ECI, không bit thừa. Kiểm tra char count khớp số bit.
  4. Regex `^\d+#\d+$`, kèm khoảng độ dài L1/L2 hợp lệ nếu nghiệp vụ biết (ví dụ ≥4 chữ số mỗi bên).
  5. Vị trí mã đã giải nằm trong bbox của track.
  6. Ngân sách RS: chấp nhận ngay khi 2A + B ≤ 8 (dùng ≤ một nửa khả năng). Nếu dùng nhiều hơn thì cần thêm bằng chứng độc lập; với e ≥ 8 thì từ chối.
- Mỗi bước 3–4 thêm hàng chục bit kiểm tra. Ví dụ 11 pad byte đúng là khoảng 88 bit; khả năng một từ sửa nhầm lại đi kèm cấu trúc segment hợp lệ, pad đúng và chỉ gồm chữ số là cực nhỏ. Rủi ro còn lại rơi vào mã dài (ít pad, ví dụ 25#25 không còn pad), nên với độ dài lớn phải chặt hơn về ngân sách RS và đồng thuận.
- **Quy tắc đồng thuận giữa frame nên dựa trên tính độc lập**. Nếu nhiều frame được cộng dồn LLR rồi giải một lần, thì hai lần giải liên tiếp từ cùng tổng tích lũy **không độc lập**: lỗi hệ thống như sai lưới vẫn giữ nguyên. Nên chia các frame thành hai nhóm rời nhau (chẵn/lẻ, hoặc đầu/cuối lượt), giải độc lập rồi yêu cầu khớp. Một lần đọc zxing một frame với ngân sách RS thấp cũng có thể khớp với một lần đọc tích lũy.
- Hiện tại zxing-cpp Python không trả số lỗi đã sửa. Muốn dùng tiêu chí ngân sách RS thì phải tự giải RS (đọc codeword từ lưới) hoặc sửa binding C++. Code dự án hiện còn `code_pattern=None`; bật regex + kiểm tra segment là cải tiến an toàn rẻ nhất.
- Không nên dùng giả thuyết độ dài (L1, L2) để "ép" các bit cấu trúc rồi coi kiểm tra cấu trúc là đã qua: khi đó những bit đó không còn là kiểm tra. Nếu dùng known-symbol thì chỉ dựa vào dư thừa của RS và tính độc lập giữa các frame để xác nhận.

### Gaps
- Không tìm được tỉ lệ misread công bố của các hãng, hay ngưỡng "% ECC đã dùng" mà ngành dùng để loại kết quả (các thông số ISO 15415 như UEC dùng cho verification, chưa thấy dùng để loại lượt đọc).
- Bảng xác suất trên giả định từ rác ngẫu nhiên đều. Lỗi thật có tương quan (cụm ô do sai lưới), nên cần kiểm chứng thực nghiệm bằng cách chạy pipeline trên nhiều frame không có QR hoặc QR khác nội dung để đo tỉ lệ đọc sai.

## (D) Decoder thương mại làm gì

### Takeaway
Cách tiếp cận nhiều frame duy nhất được mô tả cụ thể là patent Cognex: cộng dồn độ tin cậy từng ô qua các frame, coi ô unknown là erasure. Dynamsoft công khai các cơ chế: chuỗi chế độ nhị phân/deblur có ưu tiên, scale-up khi module ~2 px, lọc chéo nhiều frame (2/5), và dừng sớm. Cognex, Keyence, SICK, Halcon chỉ mô tả marketing (texture-based locate, AI, super-resolution) và không công bố PPM tối thiểu cho 2D.

### Cited Findings
- Cognex US9734376: cộng dồn tin cậy 0/1 theo ô, ngưỡng chênh lệch, unknown = erasure, thử giải sau mỗi frame. — [Google Patents](https://patents.google.com/patent/US9734376B2/en)
- Cognex PowerGrid định vị theo texture, không cần finder/clocking/quiet zone; 2DMax kết hợp hình dạng và texture. Đây là marketing, không có số. — [Automate.org PowerGrid](https://www.automate.org/vision/news/powergrid-technology-for-2d-barcode-reading)
- Cognex 1DMax đọc mã 1D tới 0,8 PPM (chỉ 1D). — [Control Engineering DataMan 150/260](https://www.controleng.com/articles/ec-dataman-150-260-series/)
- Dynamsoft:
  - DeblurModes: danh sách ưu tiên (DM_BASED_ON_LOC_BIN, DM_THRESHOLD_BINARIZATION, DM_GRAY_EQUALIZATION, DM_SMOOTHING, DM_SHARPENING_SMOOTHING, DM_MORPHING…).
  - ScaleUpModes: tự phóng mã khi module khoảng 2 px.
  - MultiFrameResultCrossFilter: 5 frame / 2 frame nhất quán.
  - Hỗ trợ aarch64 và Jetson Nano.
  — [DeblurMode](https://www.dynamsoft.com/capture-vision/docs/core/enums/barcode-reader/deblur-mode.html); [ScaleUpModes](https://www.dynamsoft.com/barcode-reader/docs/core/parameters/scenario-settings/how-to-set-scaleup-modes-v7.6.0.html); [CrossVerificationCriteria](https://www.dynamsoft.com/capture-vision/docs/mobile/programming/maui/api-reference/utility/cross-verification-criteria.md); [Jetson Nano](https://www.dynamsoft.com/codepool/jetson-nano-arm64-barcode-sdk.html)
- Halcon: `small_modules_robustness = 'high'` tăng khả năng đọc module rất nhỏ nhưng tốn bộ nhớ, kèm `module_size_min`. — [Halcon set_data_code_2d_param](https://www.mvtec.com/doc/halcon/13/en/set_data_code_2d_param.html)
- SICK Lector85x: "AI-based segmentation and super resolution" (marketing). Keyence SR-X: "AI" học từ hơn 100.000 ảnh (marketing). — [SICK](https://www.sick.com/in/en/c/g568570); [Keyence SR-X specs](https://www.keyence.com/products/barcode/barcode-readers/sr-x/specs)
- Patent multi-frame SR barcode imager US9916489. — [Google Patents](https://patents.google.com/patent/US9916489)
- Ngưỡng bên thứ ba: tối thiểu 2 px/ô cho 2D (Viziotix), tối ưu khoảng 4 px/ô (Omron). — [Viziotix whitepaper](https://www.viziotix.com/wp-content/uploads/2024/11/2024.11.14.How-to-Select-the-Best-Camera-for-Barcode-Scanning-Whitepaper-Viziotix.pdf); [Omron V440-F manual](https://www.manualslib.com/manual/2754015/Omron-V440-F.html?page=204)

### Inferences
- Ở 2,2–2,44 px/ô, hệ thống ở vùng "tối thiểu" theo ngành. Lợi thế riêng của bài toán là **hàng chục frame sắc của cùng một tem**, mà đầu đọc thương mại một-frame không tận dụng. Cách Cognex mô tả (cộng dồn mức ô + erasure) là hướng có cơ sở và rẻ nhất để khai thác lợi thế này. Dynamsoft trên Jetson là phương án mua sẵn đáng thử song song, nhưng không có bằng chứng nó xử lý được 2,3 px/ô; cần dùng trial 30 ngày đo trên dữ liệu hiện trường.
- Lọc 2/5 của Dynamsoft ngang với quy tắc "2 lần đọc giống nhau" hiện tại. Kiểm tra cấu trúc V2-M + regex + ngân sách RS ở mục (C) chặt hơn chuẩn ngành công khai.

### Gaps
- Không có thông tin công khai về việc Keyence/SICK "super resolution" là ghép nhiều frame hay chỉ một frame. Không có benchmark độc lập giữa các hãng ở PPM thấp.
- Chưa đo Dynamsoft hay BoofCV trên ROI 2,3 px/ô; đây là phép đo nên làm trước tiên bằng `data/field/raw`.
