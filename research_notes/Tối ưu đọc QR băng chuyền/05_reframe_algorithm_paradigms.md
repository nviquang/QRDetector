# Các mô hình thuật toán thay thế cho bài toán "nhận dạng tem nào đang đi qua" (QR 2,2–2,6 px/ô, nhiều frame, CPU)

Phạm vi: bước ra khỏi chuỗi "detect → tăng cường ảnh → decoder chuẩn → tái tạo theo mô hình". Ghi chú do một researcher viết (17/11/2026), ~17 lượt tìm/đọc nguồn. Lưu ý về nội dung tem: CLAUDE.md/README của repo ghi `^\d{12}#\d{12}$` (in QR version 1 mức M, tách đoạn); đề bài lần này ghi 14 số `#` 12 số. Phép tính dung lượng ở mục 2 cho thấy sự khác biệt này có ý nghĩa thực tế.

## 1. Giải mã tập đóng / có từ điển (danh sách mã sản xuất trong ngày)

### Takeaway
Thiết bị công nghiệp (Cognex Match String, Keyence preset/DV-90) chỉ so mã **sau khi** đã đọc được, nên không giúp đọc ở PPM thấp hơn. Lợi ích thật đến khi đổi bài toán thành **chọn ứng viên có likelihood cao nhất**: render từng mã trong danh sách qua mô hình mờ/lấy mẫu rồi so với ảnh (giống cách ArUco nhận dạng theo từ điển với khoảng cách Hamming tối thiểu). Cách này khai thác cấu trúc ở mức toàn mã, không chỉ ở mức RS. Mình không tìm thấy bài nào đo trực tiếp mức PPM giảm được nhờ cách này cho QR, nên phải tự thử trên dữ liệu hiện trường.

### Cited Findings
- Cognex In-Sight, công cụ Read ID có chế độ "Match String": giải mã rồi so với chuỗi người dùng nhập; tài liệu tách hai lỗi: không đọc được (do in/quang học) và đọc được nhưng không khớp (in sai tem) — [Cognex docs](https://docs.cognex.com/is_573/web/EN/ezb/Content/EasyBuilder/Inspect_ID_ReadID_Param_Setting.htm)
- Cognex VisionPro OCVMax: kiểm tra (verification) chuỗi ký tự kỳ vọng ở từng vị trí, khác với đọc tự do (OCR) — [Cognex OCVMax](https://docs.cognex.com/vpro_950/web/EN/help/html/c2da0f57-4fd9-4938-9a5e-14f61d0edb9d.htm)
- Keyence SR-750: lưu "preset data", so với mã đọc được rồi xuất OK/NG; đọc được nhưng không khớp → NG, không đọc được → ERROR; hỗ trợ ký tự đại diện `?`/`!` — [Keyence SR-750 manual](https://www.manualsdir.com/manuals/658122/keyence-sr-750-series.html?page=14); BL-700 tương tự — [BL-700 manual](https://www.manualsdir.com/manuals/658133/keyence-bl-700-series.html?page=58)
- Keyence DV-90 (data verifier) giữ tối đa 900 bản ghi master, so khớp mã đọc với master — [DV-90 manual](https://www.manualsdir.com/manuals/658141/keyence-dv-90.html?page=62)
- Ở các marker dạng từ điển (ArUco), khoảng cách Hamming tối thiểu giữa các marker quyết định số bit sửa được khi nhận dạng; DICT_6X6_250 có khoảng cách tối thiểu 11 — [OpenCV ArUco tutorial](https://docs.opencv.org/4.x/d5/dae/tutorial_aruco_detection.html); dương tính giả giảm rõ khi khoảng cách Hamming tăng — [MDPI Sensors 22(21):8548](https://mdpi.com/1424-8220/22/21/8548); từ điển nhỏ có khoảng cách lớn hơn nên chịu mờ/che tốt hơn — [Hello Robot docs](https://docs.hello-robot.com/stretch4_docs/working-with-stretch/common_tasks/list-of-aruco)
- Trong list decoding, nếu decoder có thông tin phụ thì có thể lọc danh sách đầu ra để còn đúng từ mã đã gửi — [uOttawa list decoding notes](https://www.site.uottawa.ca/~zhcheng/list_dec.pdf)
- Event camera + QR (WACV 2020): tái tạo bằng tối ưu trong "không gian con của mã" (code subspace) thay vì toàn ảnh, vì dữ liệu sự kiện thưa làm bài toán thiếu điều kiện; đọc được ở cảnh di chuyển nhanh mà camera 330 fps khó đọc — [Nagata et al., WACV 2020](https://openaccess.thecvf.com/content_WACV_2020/papers/Nagata_QR-code_Reconstruction_from_Event_Data_via_Optimization_in_Code_Subspace_WACV_2020_paper.pdf) (chỉ đọc được tóm tắt qua kết quả tìm kiếm, PDF trả 403)

### Inferences
- **Mô hình đề xuất "nhận dạng ML trên tập đóng"**: với danh sách ứng viên C = {c₁…c_N} (N hàng trăm–hàng nghìn/ngày), sinh ma trận ô 21×21 của từng mã (cùng mode/mask/mức EC như máy in — phải xác định đúng encoder của máy in, vì cùng nội dung nhưng khác cách tách đoạn hoặc mask sẽ ra ma trận khác). Với mỗi lượt, đã có ước lượng hình học (homography), vận tốc, exposure (pipeline hiện có): render ma trận → warp → PSF/vệt mờ → lấy mẫu → so với các crop. Điểm = tổng log-likelihood qua mọi frame. Chọn argmax, chấp nhận khi **biên** (điểm tốt nhất − điểm nhì) vượt ngưỡng hiệu chỉnh trên dữ liệu thật. Rẻ hơn tái tạo mù: không phải giải bài toán nghịch, chỉ N lần forward model (có thể lọc trước bằng tương quan rẻ trên ảnh nhỏ).
- Lợi thế lý thuyết: decoder chuẩn cần đúng gần hết 208 ô dữ liệu/EC (sau RS); nhận dạng tập đóng chỉ cần phân biệt ứng viên. Các mã khác nhau 1 chữ số thì khác nhau ở cả một khối codeword dữ liệu và **toàn bộ** codeword EC (RS lan sai khác sang mọi byte EC), nên khoảng cách Hamming mức ô giữa hai ứng viên lớn (ước tính vài chục ô trở lên) — tương tự lý do ArUco nhỏ chịu mờ tốt. Đây là suy luận, cần đo khoảng cách ô thực tế giữa các mã trong một danh sách sản xuất thật.
- **Rủi ro chính: tem không có trong danh sách** (in lại, danh sách đến muộn, tem ngày khác). Tập đóng luôn trả về "ứng viên gần nhất" → phải có lớp "không thuộc tập" (ngưỡng likelihood tuyệt đối + biên), và khi danh sách thiếu thì quay về đọc mở. Vai trò hợp lý nhất: **bộ xác minh/đọc thứ hai** cho lượt mà decoder mở không đọc được hoặc chỉ đọc 1 lần (hiện ghi `pass_unconfirmed`), và kiểm tra chéo kết quả đọc mở (đọc mở ra mã không có trong danh sách → nghi ngờ).
- Kiểu Cognex/Keyence (so sau khi đọc) vẫn nên làm ngay, gần như không tốn gì: lọc `code_pattern` + kiểm tra thuộc danh sách là chốt chặn đọc sai trước khi gửi server.

### Gaps
- Không tìm thấy bài báo nào về "giải mã QR theo maximum-likelihood với codebook đã biết" hay đo PPM tối thiểu khi có danh sách ứng viên. Cần thí nghiệm nội bộ trên `data/field/raw`.
- Không có tài liệu công khai về việc Cognex/Keyence dùng chuỗi kỳ vọng để *hỗ trợ giải mã* (chỉ thấy so sánh sau giải mã).

## 2. Khai thác cấu trúc đã biết: regex, chữ số cố định, RS với ký hiệu đã biết, số serial tuần tự

### Takeaway
Nội dung có định dạng cố định biến nhiều bit dữ liệu thành "đã biết" (header mode, độ dài, phần số chung của lô). Trong RS, ký hiệu đã biết loại bỏ ẩn số; ô không chắc có thể đánh dấu erasure (sửa được gấp đôi so với lỗi); soft-decision (Koetter–Vardy) thêm khoảng 1,5 dB trên kênh AWGN, nhiều hơn với mã ngắn. Ưu tiên tuần tự (tem sau = tem trước + 1) là prior mạnh nhưng phải xác nhận theo dữ liệu hiện trường.

### Cited Findings
- Decoder RS có thể nhận vị trí erasure; mã sửa được nhiều erasure hơn lỗi; biết trước vị trí có thể sai thì đánh dấu erasure để tăng số lỗi sửa được, trần là n−k erasure — [USPTO 9166623, Reed-Solomon decoder](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/9166623)
- Guruswami–Sudan là trạng thái hiện đại của giải mã đại số RS; có biến thể đa lượt kết hợp lỗi/erasure theo ngưỡng — [arXiv 1104.3419](https://arxiv.org/pdf/1104.3419); list decoder sửa được hơn ⌊(n−k)/2⌋ lỗi nhưng có thể trả về danh sách — [arXiv cs/0702130](https://arxiv.org/abs/cs/0702130)
- Koetter–Vardy chuyển thông tin độ tin cậy thành bội số nội suy (multiplicity) — [Peikert, RS list decoding notes](https://web.eecs.umich.edu/~cpeikert/pubs/reed-solomon-list.pdf); lợi ích ~1,5 dB trên AWGN, "nhiều hơn" trên kênh fading — [TV Technology](https://www.tvtechnology.com/news/new-coding-scheme-improves-reedsolomon-error-correction); với mã ngắn/tỉ lệ thấp có thể tới 9 dB — [Gross et al., arXiv cs/0506073](https://arxiv.org/pdf/cs/0506073); Jiang–Narayanan: vượt trội với mã RS tỉ lệ thấp nhưng độ phức tạp có thể quá lớn — [NYCU repository](https://ir.lib.nycu.edu.tw/bitstream/11536/46769/1/160301.pdf)
- Dung lượng QR version 1 mức M: 128 bit dữ liệu, tối đa 34 số, 20 ký tự alphanumeric, 14 byte — [Thonky character capacities](https://www.thonky.com/qr-code-tutorial/character-capacities), [JpGraph docs](https://api.webmapp.it/jpgraph-4.2.0/docs/chunkhtml/ch27.html); độ dài trường đếm ký tự ở version 1–9: numeric 10 bit, alphanumeric 9 bit, byte 8 bit (mode indicator 4 bit) — [Thonky data encoding](https://www.thonky.com/qr-code-tutorial/data-encoding)
- Transformer học giải QR "vượt giới hạn sửa lỗi lý thuyết" nhờ học cấu trúc văn bản (prior nội dung), xem mục 3 — [arXiv 2506.20305](https://arxiv.org/abs/2506.20305)

### Inferences
- **Tính dung lượng (tự tính từ bảng Thonky)**: 12#12 tách 3 đoạn = numeric 12 số (4+10+40 = 54 bit) + byte "#" (4+8+8 = 20) + numeric 12 (54) = **128 bit, vừa khít V1-M**. 14#12: numeric 14 số = 4+10+47 = 61 bit → tổng 135 bit **> 128**, không vừa V1-M; máy in phải dùng V1-L, V2-M hoặc cách mã hóa khác. Cần xác nhận định dạng thật (12 hay 14 số) và version/mức EC trên tem thật trước khi làm từ điển hoặc ràng buộc bit, vì ma trận render phụ thuộc hoàn toàn vào điều này.
- Với 12#12/V1-M: toàn bộ header đoạn (mode, độ dài), vị trí "#", chuỗi pad (128 bit đầy nên không có pad) đều đã biết → chỉ còn 24 chữ số là ẩn (~80 bit thông tin trên 128 bit dữ liệu + 80 bit EC). Mỗi nhóm 3 số là 10 bit nhưng chỉ nhận giá trị 0–999 (loại ~2,3% tổ hợp) → kiểm tra hợp lệ nhẹ.
- Nếu các tem trong ngày chung tiền tố (mã lô, ngày) thì các codeword đó coi như đã biết: thay vì đoán, ghim chúng rồi giải RS cho phần còn lại (ít ẩn hơn → sửa được nhiều lỗi/erasure hơn ở phần ẩn). Kết hợp: ô có độ tin cậy thấp (từ tích lũy nhiều frame) → erasure; nhiều phương án → thử nhiều lần (multi-trial, như arXiv 1104.3419) và chỉ chấp nhận kết quả khớp regex + danh sách.
- Cảnh báo đọc sai: RS ở V1 có rất ít codeword EC; giải đại số vượt giới hạn hoặc list decoding làm tăng xác suất ra một từ mã hợp lệ nhưng sai. Bắt buộc lọc bằng regex + danh sách + kiểm tra khớp lại ảnh (render ngược và so likelihood) trước khi báo.
- **Prior serial tuần tự**: nếu dữ liệu hiện trường cho thấy tem liên tiếp hơn nhau 1, ứng viên c_{prev}+1, +2… được xếp hạng trước trong bộ nhận dạng tập đóng ở mục 1 (giảm N hiệu dụng xuống vài ứng viên → rẻ và biên lớn). Chỉ dùng làm thứ tự thử/prior, không được bỏ qua ngưỡng xác minh, vì tem có thể bị bỏ, in lại hoặc đảo thứ tự.

### Gaps
- Không tìm được tài liệu nào về RS/QR với "known plaintext symbols" làm trợ giúp giải mã (kết quả chủ yếu về mật mã học). Bảng khối RS chính xác của V1-M (số codeword EC, số lỗi sửa được, số bit chống giải sai p) cần đọc ISO/IEC 18004 — chưa kiểm được trong phiên này.
- Chưa biết các tem trong một ngày có chung tiền tố hay chạy tuần tự không — cần kiểm tra danh sách sản xuất/`data/field`.

## 3. Bộ giải học sâu đầu-cuối (đọc bit/ký tự trực tiếp)

### Takeaway
Bộ giải QR học máy đầu tiên được công bố (Transformer, 2025) nhận **chuỗi bit đã lấy mẫu**, không nhận ảnh, và luôn trả về chuỗi kể cả khi sai — tức là có nguy cơ đọc sai mà không báo lỗi. Các hướng học sâu khác (SR, pix2pix, deblur) vẫn đưa ảnh cho decoder chuẩn. Không có bằng chứng công khai về bộ giải học máy đọc QR ~2 px/ô với tỉ lệ đọc sai được kiểm soát.

### Cited Findings
- Yoda, Kawamoto, Kera (2025): Transformer 6 lớp encoder + 6 lớp decoder, 8 head; đầu vào là chuỗi bit trải phẳng (cách sắp xếp tốt nhất 95,5%); version 1–3 mức L; 500.000 mẫu huấn luyện (tên miền Tranco); độ chính xác sạch 98,3% (v1), 94,8% (v2), 93,9% (v3); với v3-L vượt tỉ lệ thành công lý thuyết khi >9 bit lật, vượt pyzbar khi >9 bit lật hoặc burst >4; mô hình chú ý vào bit dữ liệu và bỏ qua bit EC — [arXiv 2506.20305 (HTML)](https://arxiv.org/html/2506.20305)
- Cùng bài: lỗi thường là "gần đúng" (dtv2009 → dtv2008), tự "sửa" từ viết sai thành từ thật; khác pyzbar, Transformer **luôn xuất chuỗi** dù sai; tập không có TLD chỉ đạt 3,0%, leetspeak 72,5% do ít chữ số trong dữ liệu huấn luyện — [arXiv 2506.20305 (HTML)](https://arxiv.org/html/2506.20305)
- Các hướng học sâu khác vẫn là tiền xử lý: SR (SRCNN/ESPCN/VDSR/EDSR) cải thiện khả năng đọc QR độ phân giải thấp — [PeerJ CS 2841 / PMC12192636](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12192636/); pix2pix tinh chỉnh ảnh QR xa — [IEEE 10014313](https://ieeexplore.ieee.org/document/10014313); deblur chuyển động hai mạng — [arXiv 2510.12098](https://arxiv.org/html/2510.12098v1); phát hiện + giải mã trên thiết bị đeo dựa trên ZXing — [arXiv 2410.05497](https://arxiv.org/pdf/2410.05497.pdf)
- Dynamsoft: khả năng đọc phụ thuộc kích thước ô hơn là độ phân giải; khuyến nghị ô hẹp nhất ≥2 px cho mã 1D; với ô nhỏ thì phóng to lặp (`BarcodeScaleModes`) — [Dynamsoft small module size](https://www.dynamsoft.com/barcode-reader/docs/core/programming/features/read-barcodes-with-small-module-size.html), [Dynamsoft clarity check](https://www.dynamsoft.com/barcode-reader/docs/core/introduction/how-to-guide/check-if-the-barcode-image-is-clear-enough-for-recognition.html)

### Inferences
- Bài toán của ta thuận lợi cho học máy hơn bài Transformer: nội dung chỉ là 24 chữ số, ma trận cố định 21×21, mô hình mờ biết được (vận tốc × exposure), nên có thể **tổng hợp dữ liệu vô hạn** bằng forward model đã có trong `qr/solvers` (render → warp → vệt mờ → lấy mẫu 2,2–2,6 px/ô → nhiễu → nén). Một CNN nhỏ (crop ~60×60, đầu ra 24 lớp × 10 chữ số, hoặc 441 xác suất ô) chạy CPU vài ms — ước lượng, chưa đo.
- Thiết kế an toàn: dùng mạng để ra **xác suất từng ô/chữ số** (soft), rồi đưa qua RS/erasure (mục 2) hoặc chấm điểm danh sách ứng viên (mục 1) — không để mạng tự xuất chuỗi cuối. Bài Transformer cho thấy mạng học prior nội dung và "sửa" sai thành chuỗi hợp lý — với chữ số ngẫu nhiên thì prior không giúp mà còn có hại; đầu ra cuối phải qua RS và kiểm tra khớp lại ảnh.
- Ngưỡng chấp nhận phải hiệu chỉnh để đọc sai ~0 trên tập kiểm tra lớn (≥10⁴–10⁵ lượt tổng hợp + toàn bộ dữ liệu hiện trường), đo riêng "đọc sai" và "không đọc".

### Gaps
- Không tìm được số liệu công khai của Scandit/Dynamsoft về bộ giải ML ở ≤3 px/ô, tỉ lệ đọc sai, hay chi phí CPU. Bài PeerJ (SR) không truy cập được toàn văn (403), không rõ có đo đọc sai không.

## 4. Hướng video/thời gian: tích lũy niềm tin từng ô qua nhiều frame

### Takeaway
Ý tưởng tích lũy thống kê bit qua frame cho mã 2D đã có từ 2006 (bằng sáng chế Scanbuy, nay hết hiệu lực): căn góc dưới-pixel bằng khớp template, ước lượng bit theo nhiều đặc trưng, gộp kiểu Naive Bayes, loại frame kém, thử giải lại sau mỗi frame. Nhóm Nagoya làm SR nhiều frame cho QR với PSF ước lượng từ finder pattern và ràng buộc nhị phân/lưới (98% nhận dạng, +15,7% so với SR thường). Event camera là hướng phần cứng, còn sớm.

### Cited Findings
- US 8150163 B2 (Scanbuy, nộp 2007, cấp 2012, hết hiệu lực do không nộp phí): tinh chỉnh góc dưới-pixel bằng tối thiểu sai số template–ảnh warp (sai số giảm từ ~20% xuống ~10% trong ví dụ QR); 3 đặc trưng/bit (cường độ + 2 lần làm sắc); bỏ phiếu đều, ví như Naive Bayes gộp log-likelihood; bộ ước lượng tuyến tính chấm chất lượng frame, loại frame vượt ngưỡng; phân phối xác suất version cập nhật qua frame; giải không được thì sang frame tiếp và tiếp tục tích lũy, thường 5–20 frame; không nêu PPM tối thiểu — [Google Patents US8150163](https://patents.google.com/patent/US8150163)
- Kato và cộng sự (ĐH Nagoya): SR nhiều frame cho QR độ phân giải thấp; PSF ước lượng từ cạnh finder pattern (bước sigmoid → đạo hàm → PSF 1D → giả định đẳng hướng); ràng buộc mẫu nhị phân (ICDAR 2011); 98% nhận dạng, +15,7% so với SR thường; bản sau thêm ràng buộc lưới — [Nagoya pubdb 886](https://pubdb.vislab.is.i.nagoya-u.ac.jp/~murase/pdf/886-pdf.pdf), [Nagoya pubdb 1015](https://www.vislab.is.i.nagoya-u.ac.jp/~murase/pdf/1015-pdf.pdf); Choksi et al. (McGill) ước lượng σ PSF Gauss từ finder pattern hình L — [arXiv 1410.6333](https://arxiv.org/pdf/1410.6333v3.pdf)
- Nhận dạng barcode trong video có mô hình thời gian kiểu HMM, lan truyền niềm tin về nhãn và mức nhiễu qua frame — [KoreaScience JAKO201414753675548](https://koreascience.or.kr/article/JAKO201414753675548.pdf) (chỉ đọc tóm tắt qua tìm kiếm, toàn văn lỗi kết nối)
- Bằng sáng chế 1D gộp ID giải được qua các frame liên tiếp trước khi báo, mang bounding box giữa frame — [USPTO 11244183](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/11244183)
- Event camera: QR từ dữ liệu sự kiện bằng tối ưu trong không gian mã (WACV 2020, xem mục 1); bằng sáng chế định vị mã bằng cảm biến sự kiện — [USPTO 12705449](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/12705449); Pepperl+Fuchs ra mắt đầu đọc 1D/2D tới 3,5 m/s (4/2026), nguồn không xác nhận dùng cảm biến sự kiện — [Control.com](https://control.com/news/pepperlfuchs-releases-industrial-event-camera-and-1d-2d-code-reader/)

### Inferences
- Pipeline hiện tại (xếp chồng tối đa 8 ROI hỏng rồi giải) là gộp **ở mức pixel**. Chuyển sang gộp **ở mức ô** (LLR từng ô = Σ log-likelihood theo frame, trọng số theo chất lượng frame, sau khi hiệu chỉnh hình học dưới-pixel từng frame) tận dụng được cả 10–60 frame thay vì 8, chịu được lệch căn chỉnh giữa frame tốt hơn và cho ra đúng dạng đầu vào cho erasure/soft RS (mục 2) và chấm điểm tập đóng (mục 1). Điều kiện tiên quyết: forward model mỗi frame (vệt mờ theo vận tốc × exposure — đã có).
- Quy tắc dừng tuần tự (sequential test): tiếp tục tích lũy tới khi biên log-likelihood giữa ứng viên tốt nhất và nhì vượt ngưỡng, tương tự cách patent thử giải sau mỗi frame — cho phép báo sớm lượt dễ và dồn tính toán cho lượt khó.
- Event camera không thực tế cho dự án (đổi phần cứng, công cụ thiếu, chưa có benchmark độc lập).

### Gaps
- Không tìm thấy nguồn nào đo cụ thể LLR mức ô tích lũy cho QR ≤3 px/ô, hay so sánh gộp mức ô với gộp mức pixel. Không đọc được toàn văn bài KoreaScience và WACV 2020.

## 5. Đối tượng nhận dạng khác: OCR dòng số in, QR nhỏ thứ hai, kiểm tra chéo

### Takeaway
OCR chung (Tesseract) cần chiều cao chữ x ≥10 px (tốt nhất 20–30 px). Ở 0,673 mm/px, dòng số cao 2–3 mm chỉ được ~3–4,5 px, nên OCR mở gần như chắc chắn không dùng được. Hướng khả thi hơn là **xác minh** chuỗi kỳ vọng theo kiểu OCV (so mẫu từng vị trí với ứng viên đã biết), không phải đọc tự do. PaddleOCR mobile chạy CPU khoảng 0,6 s/ảnh, quá chậm nếu chạy mỗi frame.

### Cited Findings
- Tesseract: x-height <10 px gần như không có kết quả đúng, <8 px phần lớn chữ bị coi là nhiễu; khuyến nghị 20–30 px x-height — [EasyRPA OCR guide](https://docs.easyrpa.eu/help/docs/Data-Analyst-Guide/OCR-Tuning-Guide/Evaluating-and-Enhancing-Image-Quality-for-OCR); dưới ~15 px phải huấn luyện riêng hoặc phóng ảnh — [Tesseract wiki (Training)](https://github.com/tesseract-ocr/tesseract/wiki/Training-Tesseract/5bfc90de237a620ecb0b5ada7dee495bdeb1ac25); iDigBio khuyến nghị x-height ≥20 px — [iDigBio](https://www.idigbio.org/node/106); sai số tương quan mạnh nhất với chiều cao chữ hoa tính bằng pixel — [tesseract-ocr group](https://groups.google.com/g/tesseract-ocr/c/Wdh_JJwnw94/m/24JHDYQbBQAJ)
- PaddleOCR PP-OCRv5: bản server ~3,79 s/ảnh, bản mobile ~0,62 s/ảnh trên CPU (phần cứng khác nhau giữa các bảng); từ điển lớn hơn nên chậm hơn v4 — [PaddleOCR PP-OCRv5 docs](https://www.paddleocr.ai/latest/en/version3.x/algorithm/PP-OCRv5/PP-OCRv5.html)
- Cognex OCVMax: kiểm tra ký tự kỳ vọng tại từng vị trí — [Cognex OCVMax](https://docs.cognex.com/vpro_930sr1/web/help/html/c2da0f57-4fd9-4938-9a5e-14f61d0edb9d.htm); Keyence giới thiệu kiểm tra đọc ngược kết hợp OCR, OCV và mã tại trạm in — [Keyence blog](https://www.keyence.com/blog/read-back-marking-station-ocr-ocv-code-verification-pharma.jsp)

### Inferences
- Ước lượng: chữ cao h mm → h ÷ 0,673 px (2 mm ≈ 3 px, 3 mm ≈ 4,5 px, 5 mm ≈ 7,4 px); kém xa ngưỡng 10 px của Tesseract. OCR tự do không khả thi trừ khi chữ ≥7 mm hoặc đổi quang học. Cần đo kích thước chữ thật trên tem.
- OCV/ML theo tập đóng cho dòng chữ: render chuỗi ứng viên bằng đúng font máy in → làm mờ/lấy mẫu → tương quan, dùng chung khung chấm điểm với QR ở mục 1. Hai nguồn bằng chứng (QR + chữ) gần như độc lập → nhân likelihood → biên lớn hơn, giảm đọc sai. Chỉ nên làm sau khi xác nhận font/kích thước chữ đủ (≥ ~5 px chiều cao) và chữ không bị che.
- QR nhỏ thứ hai (nếu có trên tem) còn ít px/ô hơn → không đọc riêng được; giá trị chỉ là bằng chứng phụ cho chấm điểm tập đóng (nếu nội dung liên quan biết trước).

### Gaps
- Không có số liệu PaddleOCR/CRNN cho chữ số cao 3–7 px, cũng không có thông số chữ in trên tem thật (chiều cao, font). Chưa xác minh tem có QR thứ hai và nội dung của nó.

## 6. Super-resolution huấn luyện cho mã: nguy cơ "bịa" mã sai

### Takeaway
SR cho mã giúp tăng tỉ lệ đọc (BARGAIN báo +11,27% với barcode; các bài QR báo cải thiện khả năng đọc), nhưng không bài nào tìm được tách riêng **đọc sai** khỏi **đọc đúng**. Tài liệu về hallucination trong SR cảnh báo PSNR/SSIM/LPIPS không bắt được nội dung bịa. Với mục tiêu đọc sai gần 0, SR sinh (GAN/diffusion) chỉ chấp nhận được nếu mọi kết quả phải qua kiểm tra nhất quán với ảnh gốc (degrade ngược) + regex + danh sách.

### Cited Findings
- BARGAIN (SR cho barcode): biên sắc nét, tăng ~11,27% độ chính xác giải mã; không rõ có đo đọc sai — [AMiner BARGAIN](https://aminer.org/pub/659b7349939a5f4082ed98ec/bargain-a-super-resolution-technique-to-gain-high-resolution-images-for-barcodes)
- SRCNN/ESPCN/VDSR/EDSR cải thiện khả năng đọc QR suy giảm/độ phân giải thấp — [PMC12192636](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12192636/)
- "Hallucination Score" (2025): PSNR, SSIM, MUSIQ, LPIPS thường không bắt được hallucination; định nghĩa đầu ra là hallucination nếu không thể suy giảm hợp lý về ảnh độ phân giải thấp — [arXiv 2507.14367](https://arxiv.org/html/2507.14367v2)
- Mô hình GAN có thể sinh nhiễu dạng chấm do bất định mô hình; nội dung bịa đáng lo hơn trong ứng dụng y tế/pháp y — [arXiv 1912.12879](https://arxiv.org/pdf/1912.12879)
- Bằng chứng cùng hướng: Transformer giải QR "sửa" chuỗi thành từ hợp lý và luôn xuất kết quả — [arXiv 2506.20305](https://arxiv.org/html/2506.20305)

### Inferences
- Cơ chế đọc sai: mạng SR học prior "trông giống QR" → ở 2,2 px/ô có thể tô ô sai một cách sắc nét; RS ở V1 chỉ có ít codeword EC, nên một ảnh bịa có thể rơi vào từ mã hợp lệ khác (hiếm nhưng không bằng 0); quét nhiều biến thể SR × nhiều frame làm tăng xác suất đó.
- Biện pháp: (1) tiêu chí "degrade ngược" như Hallucination Score — mã giải được phải render + làm mờ ra khớp ảnh gốc ở mọi frame, so với ứng viên nhì; (2) regex + danh sách; (3) đo tỉ lệ đọc sai trên tập lớn có nhãn, kể cả tem **không** có trong danh sách. Repo đã không dùng Real-ESRGAN/basicsr — phù hợp.
- So với SR sinh, hướng mục 1 + 4 (nhận dạng likelihood có forward model rõ ràng) cho biên/độ tin cậy có ý nghĩa xác suất, dễ kiểm soát đọc sai hơn.

### Gaps
- Không tìm được bài nào đo tỉ lệ đọc sai (sai nội dung) của SR cho QR/barcode. Toàn văn PeerJ và BARGAIN không truy cập được trong phiên này.
