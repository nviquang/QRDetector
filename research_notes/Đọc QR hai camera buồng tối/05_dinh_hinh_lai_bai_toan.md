# Định hình lại bài toán: các hướng giải thay thế cho đọc tem QR V2-M ở 2,2–2,44 px/ô (hai camera Basler 8 MP, buồng tối, Jetson Nano/CPU)

Phạm vi: các hướng ra khỏi chuỗi "YOLO detect → tăng cường ảnh → zxing/WeChat → fallback theo mô hình", với phần cứng cố định (camera, ống kính 4 mm, QR 32 mm V2-M 25×25, nội dung `số#số` dài thay đổi, tốc độ băng 80–120 mm/s, Jetson Nano hoặc PC chỉ CPU). Được phép đổi: chiều cao camera (trường nhìn 1,5–1,6 m), chiếu sáng buồng tối, tham số camera và toàn bộ phần mềm. Ghi chú do một researcher viết ngày 18/11/2026, 15 lượt tìm/đọc nguồn. Trích dẫn dùng lại từ `research_notes/Tối ưu đọc QR băng chuyền/05_reframe_algorithm_paradigms.md` được ghi rõ là "(ghi chú cũ)"; ghi chú đó viết cho V1-M, tem 36 mm.

Số liệu nền (tự tính, không có nguồn ngoài): ô QR = 32/25 = 1,28 mm → 2,2–2,44 px/ô tương ứng 0,52–0,58 mm/px. Vệt mờ = v × t ÷ mm/px: 120 mm/s × 1 ms ≈ 0,2 px; × 3 ms ≈ 0,65 px; × 5 ms ≈ 1,1 px. Thời gian trong buồng 600 mm ÷ (80–120 mm/s) = 5–7,5 s, tức 50–75 frame nếu xử lý 10 frame/s. Nghĩa là **mờ chuyển động là thông số điều khiển được bằng chiếu sáng** (đèn mạnh hơn → exposure ≤1–2 ms → vệt <0,5 px), còn giới hạn cứng thật sự là lấy mẫu ~2,3 px/ô cộng PSF quang học của ống kính 4 mm.

## 1. Đầu đọc/SDK thương mại ở ~2 px/ô: họ công bố gì, có mua chạy trên Jetson/ARM được không

### Takeaway
Không hãng nào công bố ngưỡng px/ô tối thiểu cho mã 2D có thể kiểm chứng; con số "0,8 PPM" của Cognex chỉ dành cho mã 1D, Halcon chỉ cho phép đặt `module_size_min` xuống 1 px và tự khuyến nghị 3–4 px. Dynamsoft và Halcon có bản ARM64/Jetson thật, giá không công khai (Dynamsoft khởi điểm 1.499 USD/năm). Phương án "mua" đáng làm như **phép thử chuẩn** trên dữ liệu hiện trường (bản dùng thử miễn phí), không nên coi là lời giải chắc chắn.

### Cited Findings
- Cognex 1DMax + Hotbars II đọc mã **1D** hỏng/in kém tới 0,8 px/ô; với 2DMax/PowerGrid tài liệu chỉ nói đọc được mã mất nhiều finder pattern, clock pattern hoặc quiet zone, **không nêu px/ô** — [Cognex DataMan 150/260 datasheet](https://sensotek.ru/images/Cognex/pdf/DataMan%20150-260%20Datasheet1.pdf), [Automation World: Cognex 2-D](https://www.automationworld.com/home/product/13312846/cognex-corporation-cognex-revs-up-2-d-barcode-reading), [IMVE: PowerGrid](https://www.imveurope.com/press-releases/powergrid)
- DataMan 262 UHD ghi "minimum module size 0,7 mil (18 µm)" với ống 25 mm — kích thước vật lý, không phải px/ô — [DM262 UHD datasheet](https://cdn.i-pulse.nl/isotron/production/products/955/datasheet-dm262-uhd-en.pdf)
- Công cụ ReadIDMax (In-Sight): mã phải dài >50 px, ô không quá 10 px; mã 1D ô tối thiểu 1,6 px — [Cognex ReadIDMax docs](https://docs.cognex.com/is_621/web/EN/ise/Content/Reference/ReadIDMax.htm)
- HALCON `set_data_code_2d_param` (bản 23.05): `module_size_min` cho QR/Data Matrix trong khoảng 1–100 px, mặc định 6 (chế độ enhanced 2, maximum 1); `small_modules_robustness='high'` "tăng khả năng giải mã ô rất nhỏ" nhưng có thể tăng mạnh bộ nhớ; tài liệu khuyến nghị **ít nhất 3–4 px/ô** để đọc tối ưu — [MVTec HALCON 23.05 docs](https://www.mvtec.com/doc/halcon/2305/en/set_data_code_2d_param.html)
- HALCON chạy trên mọi board NVIDIA Jetson; cần HALCON 26.05+ cho aarch64 (theo hướng dẫn Allied Vision); runtime license là node-locked, vĩnh viễn; giá chỉ báo theo yêu cầu — [MVTec: HALCON for Jetson](https://www.mvtec.com/products/embedded-vision/all-products/nvidia-jetson), [Allied Vision: HALCON on Alecs](https://www.alliedvision.com/assets/support/Camera-Documentation/Allied-Vision/FAQs-Application-Notes/Alecs/Getting-Started-with-HALCON-on-Alecs-V1.0.0.pdf), [MVTec editions/licensing](https://www.mvtec.com/products/halcon/editions-licensing), [HALCON EULA (NuGet)](https://feed.nuget.org/packages/HalconDotNet/19.5.0/License)
- Dynamsoft Barcode Reader: hỗ trợ ARM64 từ 7.6.x, có hướng dẫn chạy trên Jetson Nano, wheel aarch64 (bundle 11.6.5000); có loại license "Embedded" = máy ARM chạy Linux; giá từ 1.499 USD/năm (thuê bao năm), per-device thì phải hỏi sales — [Dynamsoft Jetson Nano](https://www.dynamsoft.com/codepool/jetson-nano-arm64-barcode-sdk.html), [Dynamsoft Docker ARM64](https://www.dynamsoft.com/codepool/docker-arm64-arm32-python-barcode-qr-recognition.html), [Dynamsoft license types](https://www.dynamsoft.com/license-server/docs/about/licenseTypes.html), [Dynamsoft pricing](https://www.dynamsoft.com/barcode-reader/pricing/), [ComponentSource](https://www.componentsource.com/product/barcode-reader/prices)
- Dynamsoft: khả năng đọc phụ thuộc kích thước ô; khuyến nghị ô hẹp ≥2 px cho mã 1D; với ô nhỏ dùng phóng to lặp (`BarcodeScaleModes`) — [Dynamsoft small module size](https://www.dynamsoft.com/barcode-reader/docs/core/programming/features/read-barcodes-with-small-module-size.html) (ghi chú cũ)
- Scandit Linux: gói Debian (ví dụ amd64), khuyến nghị ảnh 1280×720 (800×600–1920×1080); không thấy bản ARM64 công khai hay ngưỡng px/ô — [Scandit Linux add SDK](https://docs.scandit.com/sdks/linux/add-sdk/), [Scandit system requirements](https://docs.scandit.com/7.6.7/system-requirements/)
- Keyence SR-X ("AI-powered"): cell tối thiểu 0,024 mm (SR-X300), 0,010 mm với phụ kiện SR-XHR, cảm biến 1920×1200; không công bố px/ô và không dùng từ "super resolution" trong spec — [Keyence SR-X specs](https://www.keyence.co.uk/products/barcode/barcode-readers/sr-x/specs/)

### Inferences
- Các con số vật lý (µm) của đầu đọc chuyên dụng đến từ quang học phóng đại, không chuyển thành năng lực ở 2,3 px/ô. Tài liệu chính hãng mà ta đọc được (HALCON) đặt mức khuyến nghị 3–4 px/ô — cao hơn hiện trạng ~1,5 lần. Không có cơ sở để tin một SDK thương mại sẽ đạt ~100% ở 2,2–2,44 px/ô; cũng không có cơ sở để loại trừ.
- Đề xuất: lấy 100–300 crop/lượt từ `data/field/raw`, chạy bản dùng thử Dynamsoft (ARM64/x64) và HALCON (`default_parameters='maximum_recognition'`, `module_size_min=1`, `small_modules_robustness='high'`) trên PC trước, đo cả đọc đúng **và** đọc sai, đo thời gian/khung. Đây là phép thử rẻ nhất để biết trần "mua". Lưu ý: bộ nhớ khi `small_modules_robustness='high'` có thể là vấn đề trên Jetson Nano 4 GB.
- Cả SDK thương mại đều là hộp đen giải mã từng ảnh; không tận dụng được 50–75 frame của một lượt, nên tối đa chỉ thay vị trí của zxing/WeChat trong pipeline, không thay được hướng tích lũy ở mục 3.

### Gaps
- Không tìm thấy con số px/ô tối thiểu cho mã 2D của Cognex 2DMax, Keyence SR-X, SICK hay Datalogic; không tìm thấy giá per-device cho Dynamsoft Embedded hay HALCON runtime aarch64 (đều phải hỏi sales).
- Không có benchmark tốc độ Dynamsoft/HALCON trên Jetson Nano.
- Không xác minh được Scandit có bản Linux ARM64 thương mại.

## 2. Hướng học đầu-cuối: mạng ra xác suất từng ô rồi giải RS

### Takeaway
Đã có tiền lệ công nghiệp gần đúng kiến trúc này: bằng sáng chế ABBYY (2022) dùng mạng dự đoán **tâm ô + bản đồ nhị phân + độ tin cậy từng ô**, dựng lưới, rồi sửa lỗi RS, huấn luyện trên dữ liệu tổng hợp. Bộ giải học máy công khai còn lại (Transformer 2025) nhận chuỗi bit, không nhận ảnh, và luôn xuất chuỗi kể cả khi sai. Chưa có bài nào đo ở ~2 px/ô; chi phí trên Jetson Nano của một CNN cỡ ResNet-18 là ~10–20 ms/ảnh (FP16, TensorRT), nên CNN nhỏ trên crop ~60–70 px là khả thi về tính toán.

### Cited Findings
- US 11960966 B2 (ABBYY Development, nộp 16/5/2022, cấp 16/4/2024): backbone chung + nhiều đầu phân loại, xuất **tâm ô ứng viên, bản đồ cường độ nhị phân và độ tin cậy từng ô**; dựng lưới bằng cách theo dõi đoạn hàng/cột (dung sai ~20–30% kích thước ô); ước lượng kích thước ô (vùng liên thông, finder pattern, histogram run-length) rồi đổi tỉ lệ ảnh về kích thước ô lúc huấn luyện, thất bại thì ước lượng lại và thử lại; sửa lỗi bằng Reed–Solomon, ô thiếu điền giá trị tạm; dữ liệu tổng hợp: xóa/thêm ô, nhòe, méo, phối cảnh, chiếu sáng không đều, chói, mờ — [Google Patents US11960966B2](https://patents.google.com/patent/US11960966B2/en)
- Yoda, Kawamoto, Kera (2025): Transformer giải QR từ chuỗi bit đã lấy mẫu (v1–3 mức L, 500.000 mẫu); đúng 98,3% (v1), 94,8% (v2), 93,9% (v3); vượt giới hạn sửa lỗi lý thuyết nhờ học cấu trúc văn bản; mô hình bỏ qua bit EC, **luôn xuất chuỗi dù sai**, lỗi kiểu "gần đúng" (dtv2009 → dtv2008), chữ số/leetspeak kém (72,5%) — [arXiv 2506.20305](https://arxiv.org/html/2506.20305) (ghi chú cũ)
- CMES 2025: mô hình nhẹ + bộ dữ liệu tổng hợp phục hồi mã 1D/QR hỏng trong logistics; tỉ lệ giải QR tăng 14% → 99% trên tập huấn luyện nhưng chỉ 15% → 68% trên tập kiểm định (khoảng cách tổng quát hóa lớn) — [Tech Science CMES v143n3](https://www.techscience.com/CMES/v143n3/62816/html)
- SR học sâu (EDSR/VDSR/ESPCN/SRCNN) cải thiện khả năng đọc QR độ phân giải thấp nhưng vẫn đưa ảnh cho decoder chuẩn — [PeerJ CS / PMC12192636](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12192636/); Leygonie et al. (2023) phân loại QR nhiễu bằng học sâu — [DeepAI 2307.10677](https://deepai.org/publication/deep-learning-for-classification-of-noisy-qr-codes)
- Jetson Nano ResNet-18 (224×224): 52,5 fps FP32, 91 fps FP16 (≈19 ms và ≈11 ms/ảnh); Nano hỗ trợ FP16, không INT8 — [NVIDIA GTC 2020 s22676](https://developer.download.nvidia.com/video/gputechconf/gtc/2020/presentations/s22676-developing-real-time-neural-networks-for-jetson.pdf); số đo cộng đồng mâu thuẫn nhau (TRT FP16 2,1 ms hoặc 18 ms ở 256×256 trong cùng repo) — [kentaroy47 benchmark](https://github.com/kentaroy47/benchmark-FP32-FP16-INT8-with-TensorRT); có trường hợp FP16 gần như không nhanh hơn — [NVIDIA forum](https://forums.developer.nvidia.com/t/fp16-does-not-decrease-inference-time-on-jetson-nano/223376)

### Inferences
- **Thiết kế đề xuất**: crop đã chỉnh hình học (homography từ finder + alignment pattern ở ô (18,18) của V2) → CNN nhỏ (vài trăm nghìn tham số) → **LLR cho 352 ô dữ liệu/EC** (44 codeword × 8 bit) + 15 bit format. Không để mạng xuất chuỗi; đầu ra chỉ là xác suất, chuyển cho RS/erasure (mục 5) hoặc chấm điểm tập đóng (mục 4). Như vậy tránh được hiện tượng "tự sửa thành chuỗi hợp lý" của Transformer, vốn rất nguy hiểm với chữ số ngẫu nhiên.
- Chi phí ước tính (chưa đo): crop 64×64, CNN cỡ 1/10 ResNet-18 → <2 ms/crop trên Nano GPU, vài ms trên CPU x86; 2 camera × vài tem/khung × 10 khung/s vẫn trong ngân sách. Phần đắt vẫn là detect toàn khung 8 MP.
- **Dữ liệu tổng hợp**: render V2-M với đúng encoder của máy in (tách đoạn, mask) → warp ngẫu nhiên (xoay 0–360°, lệch pha dưới-pixel) → PSF quang học đo từ ảnh thật (cạnh finder) + vệt mờ v×t → lấy mẫu 2,0–2,6 px/ô → Bayer/nhiễu Poisson-Gauss, gamma, cháy sáng → lượng tử 8 bit. Bài CMES cho thấy khoảng cách train/val lớn nếu dữ liệu tổng hợp lệch thực tế ⇒ bắt buộc hiệu chỉnh (calibration) LLR trên crop thật có nhãn (nhãn lấy từ các lượt đọc chắc hoặc từ danh sách sản xuất).
- Ưu điểm so với SR/tăng cường ảnh: đầu ra có ý nghĩa xác suất, dùng được trong tích lũy Bayes qua frame (mục 3) và ngưỡng chống đọc sai định lượng được.

### Gaps
- Không tìm thấy bài báo nào đo đọc QR/DataMatrix bằng mạng phân loại ô ở ≤3 px/ô, hay đo tỉ lệ đọc sai của bộ giải học máy.
- Không đọc được toàn văn bằng sáng chế ABBYY phần sau (trang dài) nên không rõ kích thước ô huấn luyện và độ chính xác báo cáo.
- Chưa có benchmark CNN nhỏ (crop 64×64) trên Jetson Nano — phải tự đo.

## 3. Tích lũy niềm tin từng ô qua cả lượt (Bayes tuần tự) và lập lịch chọn frame tốt

### Takeaway
Cách gộp xác suất bit kiểu Naive Bayes qua nhiều frame, loại frame kém và thử giải lại sau mỗi frame đã có từ bằng sáng chế Scanbuy 2007 (đã hết hiệu lực); SR nhiều frame cho QR đạt 98% nhận dạng (+15,7% so với SR thường). Với 50–75 frame/lượt, gộp **ở mức ô** (cộng LLR) tận dụng toàn bộ lượt, trong khi pipeline hiện tại chỉ xếp chồng tối đa 8 ROI ở mức pixel. Không tìm thấy nguồn đo trực tiếp ở ~2 px/ô.

### Cited Findings
- US 8150163 B2 (Scanbuy): tinh chỉnh góc dưới-pixel bằng tối thiểu sai số template–ảnh warp; 3 đặc trưng/bit; gộp như Naive Bayes; bộ ước lượng tuyến tính chấm chất lượng frame và loại frame kém; phân phối xác suất version cập nhật qua frame; giải không được thì tích lũy tiếp, thường 5–20 frame — [Google Patents US8150163](https://patents.google.com/patent/US8150163) (ghi chú cũ)
- Kato et al. (Nagoya): SR nhiều frame cho QR, PSF ước lượng từ cạnh finder pattern, ràng buộc nhị phân/lưới; 98% nhận dạng, +15,7% so với SR thường — [Nagoya pubdb 886](https://pubdb.vislab.is.i.nagoya-u.ac.jp/~murase/pdf/886-pdf.pdf), [Nagoya pubdb 1015](https://www.vislab.is.i.nagoya-u.ac.jp/~murase/pdf/1015-pdf.pdf) (ghi chú cũ); ước lượng σ PSF Gauss từ finder hình L — [arXiv 1410.6333](https://arxiv.org/pdf/1410.6333v3.pdf) (ghi chú cũ)
- Saint-Gobain đọc mã trên tấm kính đang chạy: encoder gắn với băng kích camera theo quãng đường tấm đã đi, nên số frame/vị trí chụp xác định theo hình học chứ không theo thời gian — [US 9767334 B2](https://patents.google.com/patent/US9767334B2/Direct)

### Inferences
- **Thuật toán đề xuất**: với mỗi lượt (track) và mỗi frame f: căn hình học dưới-pixel (khớp template finder/alignment), tính LLR_f(i) cho 352+15 ô (bằng CNN ở mục 2 hoặc bằng forward model PSF + Gauss), trọng số w_f theo chất lượng; LLR(i) = Σ_f w_f·LLR_f(i). Vì băng chuyền tịnh tiến đều, ô i ở các frame khác nhau rơi vào **pha lấy mẫu dưới-pixel khác nhau** → cộng nhiều frame thực chất là SR ở mức ô mà không cần dựng ảnh. Giả định độc lập giữa frame bị vi phạm (PSF/tem giống nhau) ⇒ phải hiệu chỉnh LLR tổng (ví dụ nhân hệ số <1 học trên dữ liệu thật) để không quá tự tin.
- **Quy tắc dừng tuần tự**: sau mỗi frame thử giải (hard decision + erasure cho |LLR| nhỏ); chỉ chấp nhận khi (a) RS hội tụ với số lỗi sửa ≤ ngưỡng chặt hơn t=8 (ví dụ ≤4), (b) cú pháp nội dung đúng (mục 5), (c) render lại mã giải được khớp các frame tốt hơn hẳn phương án nhì (biên log-likelihood). Lượt dễ báo sau vài frame, lượt khó dùng hết 5–7,5 s.
- **Lập lịch frame**: điểm chất lượng rẻ = phương sai Laplace trên crop × độ tương phản finder × khoảng cách tới tâm quang học (ống 4 mm có méo và sụt MTF ở rìa trường 1,5 m) × không cháy sáng. Xử lý theo thứ tự điểm giảm dần thay vì theo thời gian; tem ở rìa ảnh chỉ dùng làm bằng chứng bổ sung. Với hai camera chồng vùng, mỗi tem có thể có frame từ cả hai, gộp LLR chung (sau khi căn hình học riêng từng camera).
- Đòn bẩy phần cứng được phép: chiếu sáng mạnh, đều, khuếch tán trong buồng tối → exposure ≤1–2 ms (vệt <0,5 px), gain thấp (ít nhiễu) — làm LLR mỗi frame sắc hơn, quan trọng hơn mọi thuật toán khử mờ.

### Gaps
- Không có số đo công khai về số frame cần để gộp LLR mức ô đạt ~100% ở 2,2–2,4 px/ô, hay so sánh gộp mức ô với xếp chồng mức pixel; phải thử trên `data/field/raw`.
- Không tìm thấy tài liệu đo MTF ống 4 mm ở rìa trường cho camera 8 MP này.

## 4. Xác minh tập đóng khi có danh sách mã trong ngày

### Takeaway
Đầu đọc công nghiệp (Cognex Match String, Keyence preset/DV-90) chỉ so mã **sau khi** đọc, không giúp đọc ở px/ô thấp hơn. Lợi ích thật là đổi bài toán thành chọn ứng viên có likelihood lớn nhất có biên; với V2-M, hai mã khác nhau bất kỳ khác nhau ở ≥17 codeword (RS (44,28) là mã MDS, d = 17), nên khoảng cách mức ô giữa hai ứng viên rất lớn — đây là lý do lý thuyết để tin có thể đọc ở PPM thấp hơn decoder mở. Không có bài báo nào đo mức PPM giảm được.

### Cited Findings
- Cognex Read ID "Match String": giải mã rồi so chuỗi; tách "không đọc được" và "đọc được nhưng không khớp" — [Cognex docs](https://docs.cognex.com/is_573/web/EN/ezb/Content/EasyBuilder/Inspect_ID_ReadID_Param_Setting.htm) (ghi chú cũ); Keyence SR-750 preset data → OK/NG/ERROR — [Keyence SR-750 manual](https://www.manualsdir.com/manuals/658122/keyence-sr-750-series.html?page=14) (ghi chú cũ); Keyence DV-90 giữ tối đa 900 bản ghi master — [DV-90 manual](https://www.manualsdir.com/manuals/658141/keyence-dv-90.html?page=62) (ghi chú cũ)
- V2-M: 28 codeword dữ liệu, 16 codeword EC, 1 khối — [Thonky error correction table](https://www.thonky.com/qr-code-tutorial/error-correction-table)
- Ở marker từ điển (ArUco), khoảng cách Hamming tối thiểu quyết định số bit sửa được; DICT_6X6_250 có khoảng cách tối thiểu 11 — [OpenCV ArUco](https://docs.opencv.org/4.x/d5/dae/tutorial_aruco_detection.html) (ghi chú cũ); dương tính giả giảm rõ khi khoảng cách tăng — [MDPI Sensors 22(21):8548](https://mdpi.com/1424-8220/22/21/8548) (ghi chú cũ)
- Tái tạo QR bằng tối ưu trong "không gian con mã" thay vì toàn ảnh (dữ liệu event camera) — [Nagata et al., WACV 2020](https://openaccess.thecvf.com/content_WACV_2020/papers/Nagata_QR-code_Reconstruction_from_Event_Data_via_Optimization_in_Code_Subspace_WACV_2020_paper.pdf) (ghi chú cũ)

### Inferences
- **Khoảng cách giữa ứng viên (tự tính)**: RS(44,28) trên GF(256) có d = n−k+1 = 17 ⇒ hai nội dung khác nhau cho ≥17 codeword khác nhau; mỗi codeword khác nhau trung bình ~4 bit khác ⇒ ước tính ≥~68 ô khác nhau trên 352 ô (nếu cùng mask; khác mask thì còn nhiều hơn). Decoder mở cần ≥(352−~64) ô gần đúng; phân biệt hai ứng viên chỉ cần tổng bằng chứng trên ~68 ô đó vượt nhiễu, và cộng được qua 50–75 frame. Đây là suy luận, phải đo khoảng cách thực tế trên danh sách thật.
- **Thuật toán**: với danh sách C (N mã), sinh trước ma trận 25×25 từng mã bằng đúng encoder máy in; mỗi lượt: điểm(c) = Σ_i LLR(i)·(2·bit_c(i)−1) (tích vô hướng với vector LLR đã tích lũy ở mục 3) — chi phí N × 367 phép cộng, N = 10⁴ chỉ ~4·10⁶ phép/lượt, không đáng kể cả trên Nano. Chấp nhận khi điểm₁ − điểm₂ ≥ biên **và** điểm₁ đạt ngưỡng tuyệt đối (để phát hiện "không thuộc danh sách").
- **Khi tem không có trong danh sách** (in lại, danh sách đến muộn): tập đóng luôn trả "gần nhất" ⇒ bắt buộc ngưỡng tuyệt đối; dưới ngưỡng → quay về giải mở (mục 3/5). Ngược lại, giải mở ra mã **không** có trong danh sách → đánh dấu nghi ngờ thay vì gửi.
- **Không có danh sách**: vẫn dùng được biến thể "tập đóng cục bộ": ứng viên = các kết quả RS/list decoding ở mục 5 + mã của lượt trước ±k (nếu serial tuần tự) → chấm lại bằng likelihood toàn ảnh; giảm đọc sai nhưng không giảm PPM yêu cầu nhiều như danh sách thật.

### Gaps
- Không tìm thấy bài báo hay tài liệu hãng nào dùng chuỗi kỳ vọng để **hỗ trợ giải mã** QR (chỉ so sau giải mã), hay đo PPM tối thiểu khi có codebook.
- Chưa biết server có cấp danh sách theo ngày được không, kích thước N, tỉ lệ tem ngoài danh sách.

## 5. Khai thác cấu trúc nội dung `số#số` dài thay đổi: ghim bao nhiêu bit

### Takeaway
Với V2-M (224 bit dữ liệu) và nội dung ngắn như 12#12, sau khi giả thuyết độ dài (n₁, n₂) thì **mọi bit trừ bit chữ số đều đã biết**: header mode/độ dài, byte `#` = 0x23, terminator, bit đệm và các byte pad 0xEC/0x11. Với 12#12, chỉ 80/224 bit dữ liệu là ẩn, tương đương ~18/28 codeword dữ liệu ghim cứng; điều này vừa tăng khả năng sửa lỗi ở phần ẩn vừa là bộ lọc chống đọc sai rất mạnh.

### Cited Findings
- Mode indicator 4 bit; độ dài trường đếm ký tự ở version 1–9: numeric 10 bit, alphanumeric 9 bit, byte 8 bit; numeric mã hóa 3 số → 10 bit, 2 số → 7 bit, 1 số → 4 bit; sau dữ liệu có terminator tối đa 4 bit 0, đệm 0 tới biên byte, rồi lặp byte pad 236 (0xEC) và 17 (0x11) — [Thonky data encoding](https://www.thonky.com/qr-code-tutorial/data-encoding) (ghi chú cũ, quy tắc pad lấy từ cùng trang)
- V2-M: 28 codeword dữ liệu + 16 EC, 1 khối (sửa tối đa 8 lỗi hoặc 16 erasure theo n−k = 16) — [Thonky error correction table](https://www.thonky.com/qr-code-tutorial/error-correction-table)
- Decoder RS nhận vị trí erasure, sửa được nhiều erasure hơn lỗi, trần n−k erasure — [USPTO 9166623](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/9166623) (ghi chú cũ); soft-decision Koetter–Vardy thêm ~1,5 dB trên AWGN, nhiều hơn với mã ngắn — [Gross et al., arXiv cs/0506073](https://arxiv.org/pdf/cs/0506073) (ghi chú cũ); multi-trial lỗi/erasure — [arXiv 1104.3419](https://arxiv.org/pdf/1104.3419) (ghi chú cũ)

### Inferences
- **Bảng bit (tự tính, giả định máy in tách 3 đoạn numeric/byte/numeric như README mô tả)**: bit đoạn numeric n số = 4 + 10 + ⌊n/3⌋·10 + {0,4,7}[n mod 3]. 12#12: 54 + 20 + 54 = 128 bit → +4 terminator = 132 → đệm tới 136 (17 byte) → 11 byte pad. Bit đã biết = 224 − 80 (24 chữ số) = **144 bit**. 14#12: 61+20+54 = 135 → còn 89 bit chữ số → ~135 bit biết. Dung lượng tối đa: 224 − 20 − 28 = 176 bit cho chữ số ⇒ tổng ~52 chữ số; nội dung dài hơn sẽ không vừa V2-M.
- **Giả thuyết độ dài**: (n₁, n₂) có ít tổ hợp (ví dụ 8–20 × 8–20 ≈ 169); thử hết, mỗi giả thuyết ghim các codeword đã biết rồi giải RS phần còn lại. Nếu máy in có thể dùng 1 đoạn byte cho toàn chuỗi hoặc thứ tự đoạn khác, cộng thêm vài giả thuyết encoder. Format info (15 bit, BCH) cho mức M + mask: mask thường suy được từ 8 giả thuyết hoặc giải BCH.
- **Lợi ích RS**: với 12#12, ~18 codeword dữ liệu ghim ⇒ còn ~10 dữ liệu + 16 EC = 26 vị trí ẩn, vẫn 16 ký hiệu dư ⇒ sửa 8 lỗi trên 26 vị trí thay vì trên 44 (ngân sách lỗi theo tỉ lệ tăng ~1,7 lần), hoặc tới 16 erasure; ô có |LLR| thấp đánh dấu erasure. Mỗi nhóm 3 chữ số chỉ nhận 0–999 trong 1024 giá trị 10 bit → kiểm tra hợp lệ phụ.
- **Lợi ích chống đọc sai** (quan trọng nhất): kết quả RS giải mà làm lệch bất kỳ codeword "đã biết" nào ⇒ loại. Xác suất một từ mã sai ngẫu nhiên khớp ~144 bit cố định là không đáng kể (~2⁻¹⁴⁴ nếu coi như ngẫu nhiên — ước lượng thô). Cộng regex `^\d+#\d+$` và độ dài hợp lệ. Hiện code vẫn `code_pattern=None` (theo CLAUDE.md) — đây là việc rẻ nhất cần làm ngay.
- Giới hạn: list decoding (Guruswami–Sudan) trên mã rút gọn tỉ lệ 10/26 cho bán kính ~n(1−√R) ≈ 9,9 lỗi — chỉ hơn t=8 chút, nên lợi ích chính đến từ ghim bit + erasure/soft, không từ list decoding.

### Gaps
- Chưa xác minh encoder thực tế của máy in (tách đoạn, mask, có dùng ECI hay không) và dải độ dài n₁, n₂ thật — phải kiểm trên tem/ảnh thật.
- Không tìm được giá trị p (số codeword dành cho chống giải sai) của V2-M trong ISO/IEC 18004 từ nguồn công khai trong phiên này.
- Không có tài liệu về RS/QR dùng "known plaintext symbols" để hỗ trợ giải mã (chỉ là suy luận từ lý thuyết mã).

## 6. Triển khai tương tự: đọc mã px/ô thấp trên băng rộng, kính, Jetson

### Takeaway
Ngành kính dùng mã khắc laser trên tấm kính đang chạy với đầu đọc gắn sát băng (encoder kích chụp) — tức là giải bằng quang học gần, không phải đọc px/ô thấp trên trường nhìn rộng. Không tìm thấy triển khai công khai nào đọc QR ~2 px/ô trên băng rộng >3 m hay hệ đọc mã công nghiệp dựa trên Jetson có số liệu; bài toán này hiện thuộc dạng tự phát triển.

### Cited Findings
- Saint-Gobain: thiết bị đọc mã nhận dạng trên tấm kính đang chạy, đặt ngang băng, encoder đo chuyển động tấm và kích chụp; mã khắc ngay sau cắt dải float, thường khắc cả hai mặt — [US 9767334 B2](https://patents.google.com/patent/US9767334B2/Direct); phương pháp dò và đọc mã ma trận trên nền kính — [USPTO 12086681](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/12086681); đọc qua mép kính bằng phản xạ toàn phần — [USPTO 9875384](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/9875384)
- Prinz Optics/ipf electronic: dây chuyền kính đặc biệt, mỗi tấm có mã 2D đọc bằng camera trước khi phủ; lỗi do phản xạ và tấm không vuông góc camera, đọc sai làm dừng sản xuất; giải bằng cảm biến mạnh hơn + chiếu sáng thích ứng — [ipf app Prinz Optics](https://www.ipf-electronic.de/fileadmin/PIM/assets/app/pr/in/ipf_app_Prinz_Optics_en.pdf)
- Dynamsoft có hướng dẫn chạy đọc mã trên Jetson Nano nhưng không công bố số đo — [Dynamsoft Jetson Nano](https://www.dynamsoft.com/codepool/jetson-nano-arm64-barcode-sdk.html)
- Pepperl+Fuchs ra mắt đầu đọc 1D/2D tới 3,5 m/s (4/2026), không xác nhận dùng cảm biến sự kiện — [Control.com](https://control.com/news/pepperlfuchs-releases-industrial-event-camera-and-1d-2d-code-reader/) (ghi chú cũ)

### Inferences
- Bài học từ ngành kính áp dụng được: (1) chiếu sáng là yếu tố quyết định (phản xạ trên kính/tem bóng) — trong buồng tối nên dùng ánh sáng khuếch tán/dome dải dài hoặc chiếu xiên tránh phản xạ gương về camera; (2) kích chụp hoặc gắn nhãn frame theo vị trí băng (encoder) giúp dự đoán vị trí tem giữa frame, giảm chi phí detect (chỉ detect khi tem mới vào, còn lại dự đoán + tinh chỉnh cục bộ) — rất quan trọng trên Jetson Nano vì detect toàn khung 8 MP là phần đắt nhất.
- Các hệ đọc logistics công suất cao thường giải bằng nhiều camera độ phân giải cao/ống dài để có ≥3–4 px/ô; với ràng buộc cố định ở đây, lợi thế duy nhất còn lại là **thời gian quan sát dài (50–75 frame) và cấu trúc nội dung** — hai thứ mà đầu đọc thương mại một ảnh không khai thác.
- Xếp hạng hướng đi (suy luận tổng hợp): (a) ngay: lọc cú pháp + ghim bit đã biết + danh sách (nếu có) làm chốt chống đọc sai; chiếu sáng để exposure ≤1–2 ms; (b) ngắn hạn: thử Dynamsoft/HALCON trên dữ liệu thật làm mốc; (c) trung hạn: LLR mức ô (forward model hoặc CNN nhỏ) tích lũy qua lượt + RS có erasure + giả thuyết độ dài; (d) nếu có danh sách: chấm điểm tập đóng bằng tích vô hướng LLR, gần như miễn phí về tính toán.

### Gaps
- Không tìm thấy case study công khai về đọc QR px/ô thấp trên băng chuyền rộng (gỗ, thép tấm, logistics) có số liệu px/ô và tỉ lệ đọc; không tìm thấy hệ đọc mã công nghiệp thương mại chạy trên Jetson có công bố hiệu năng.
- Không tìm thấy dự án mã nguồn mở nào làm giải mã QR soft-decision/tích lũy nhiều frame.
