# Tối ưu khâu DETECT + TRACK + LẬP LỊCH cho đọc QR nhỏ trên băng chuyền (CPU)

Bối cảnh hệ thống (lấy từ `CLAUDE.md`/`README.md` của repo, không phải nguồn web): Basler a2A2840-48umBAS 2856×2848, 0,673 mm/px, tem 36 mm → QR ~54 px, 2,2–2,6 px/ô; băng 100 mm/s; vùng đọc 1,6 m × 0,6 m; YOLOv8-seg `qrdet` "s", imgsz 1280 (1600 cho dải rộng), 980 ms/khung trên CPU, 190 ms trên GTX 1650; YOLO tối đa mỗi 400 ms, giữa các lần chạy thì đoán ROI theo vận tốc track; QR nhỏ ~25 px không bao giờ được YOLO phát hiện.

Ghi chú phương pháp: 16 lượt tìm/tải. Nhiều thông tin về sản phẩm thương mại chỉ có ở tài liệu marketing; đã đánh dấu rõ. Không tìm được số liệu độc lập cho phần lớn câu hỏi "sản phẩm X định vị mã thế nào".

## A. Sản phẩm thương mại và thư viện định vị mã thế nào (cổ điển hay deep learning), tốc độ?

### Takeaway
Đầu đọc công nghiệp (Cognex, Keyence, SICK, Dynamsoft, HALCON) chủ yếu dùng định vị **cổ điển** (finder pattern, kết cấu/texture sáng–tối, khối liên thông, thống kê, kim tự tháp ảnh theo kích thước ô) và chỉ gần đây mới thêm "AI" — thường cho bước lọc ảnh/giải mã khó, không phải để định vị trên toàn khung; Dynamsoft mới thêm chế độ định vị bằng mạng nơ-ron (v11.2.2000) như một lựa chọn bên cạnh các chế độ cổ điển. Không có nhà cung cấp nào công bố số ms định vị kiểm chứng độc lập.

### Cited Findings
- **Cognex PowerGrid**: thuật toán định vị dựa trên **kết cấu (texture)**, đi "từ trong ra": thay vì tìm finder pattern, nó tìm mẫu xen kẽ ô sáng/tối bên trong mã, nên vẫn tìm được mã khi finder pattern, clocking pattern hoặc quiet zone hỏng/mất; có trên dòng DataMan 300 "X" (thông cáo báo chí, tính chất marketing) — [Automate.org](https://www.automate.org/vision/news/powergrid-technology-for-2d-barcode-reading); [Pharmaceutical Online](https://www.pharmaceuticalonline.com/doc/cognex-revs-up-d-barcode-reading-0001)
- Cùng nguồn: bộ giải "thông thường dựa trên đặc trưng" bắt đầu từ finder pattern — tức là phương pháp mặc định trong ngành là định vị finder pattern cổ điển — [Automate.org](https://www.automate.org/vision/news/powergrid-technology-for-2d-barcode-reading)
- Nội bộ 2DMax không được mô tả công khai trong các nguồn tìm được; không xác nhận được PowerGrid có nằm trong 2DMax hay không — [kết quả tìm kiếm, IMVE](https://www.imveurope.com/press-releases/powergrid)
- **Cognex DataMan 580** (cho tunnel logistics): cảm biến 9 MP, thuật toán "1D/2D QuickSort", đọc góc nghiêng để giảm khoảng cách giữa kiện; "tới 99,9% read rate" là số marketing cho cả dòng, không phải kết quả tunnel đo được — [Qualitrol product guide (PDF)](https://qualitrol.com/assets/BarcodeReadersProductGuide.pdf); [Datasheet DM580](https://riverplus.com/cdn/shop/files/Datasheet_DM580.pdf)
- **Keyence SR-X**: "AI-Powered Code Reader", chip suy luận AI tích hợp, huấn luyện trên >100.000 ảnh; AI dùng cho "AI filter" và thuật toán giải "SR-X Drive" cho mã bẩn/xước; SR-X100 không có AI filter; SR-X300 cảm biến 1920×1200, khoảng đọc 70–1000 mm. Không có nguồn nào nói AI dùng để định vị mã trong ảnh — [Keyence SR-X](https://www.keyence.com/products/barcode/barcode-readers/sr-x/); [Keyence SR-X300](https://www.keyence.com:443/products/barcode/barcode-readers/sr-x/models/sr-x300/); [Vision Systems Design](https://www.vision-systems.com/factory/article/55020046/keyence-launches-ai-powered-code-reader-line)
- **SICK Lector85x**: "real-time tracking tích hợp" theo dõi mã 3D trong trường nhìn để gán mã đúng vật khi nhiều vật cùng trong khung; băng tới 3,5 m/s; Lector65x 0–3 m/s (marketing) — [Food Processing (sponsored)](https://www.foodprocessing.com.au/content/processing/sponsored/identifies-codes-like-no-other-meet-the-new-sick-lector85x-1372784429); [SICK Lector65x System overview](https://cdn.sick.com/media/familyoverview/1/51/951/familyOverview_Lector65x-System_g326951_en.pdf)
- **Dynamsoft Barcode Reader** có các chế độ định vị kết hợp được, phiên đọc thử lần lượt tới khi đủ số mã: `LM_CONNECTED_BLOCKS` (khối liên thông, ảnh rõ), `LM_LINES`, `LM_STATISTICS` (thống kê màu; vẫn định vị được khi nhị phân hóa làm hỏng position pattern), `LM_SCAN_DIRECTLY` (nhanh nhất nhưng cần ảnh tốt, mã nằm ngang/dọc, có `ScanStride`), `LM_STATISTICS_MARKS` (DPM), `LM_CENTRE`, `LM_NEURAL_NETWORK` (thêm từ bản 11.2.2000) — [Dynamsoft docs: localization modes](https://www.dynamsoft.com/barcode-reader/docs/core/parameters/reference/localization-modes.html); [Dynamsoft Capture Vision enum](https://www.dynamsoft.com/capture-vision/docs/core/enums/barcode-reader/localization-mode.html)
- **HALCON `find_data_code_2d`**: tìm kiếm bắt đầu ở tầng kim tự tháp ảnh cao nhất mà các ô còn tách được (dựa trên kích thước ô tối đa trong model) — tức là giới hạn kích thước ô trong model trực tiếp quyết định tốc độ; có `module_size_min/max`, chế độ `train` từ ảnh mẫu, `small_modules_robustness='high'` để giải ô rất nhỏ (tốn bộ nhớ/thời gian hơn), giới hạn `symbol_shape` giúp tăng tốc đáng kể — [HALCON find_data_code_2d](https://www.mvtec.com/doc/halcon/13/en/find_data_code_2d.html); [HALCON set_data_code_2d_param](https://www.mvtec.com/doc/halcon/13/en/set_data_code_2d_param.html)
- **Scandit MatrixScan** (2017, SDK 5.2): định vị, theo dõi và giải nhiều mã đồng thời; trả vị trí các mã được track mỗi frame xử lý; giữ vị trí không gian của mã cả khi ra khỏi khung. Kiến trúc mạng không được Scandit công bố (nguồn nói CNN+RNN là trang bên thứ ba, chưa kiểm chứng) — [Scandit docs 5.10](https://docs.scandit.com/5.10/android/android-multiple-scanning.html); [Scandit blog](https://www.scandit.com/blog/multiple-barcodes-with-ai/); [FleetOwner](https://www.fleetowner.com/technology/article/21695776/scandit-launches-matrixscan-scanning-ar-tracking-capability)
- **So sánh thư viện (benchmark do Dynamsoft — đối thủ thương mại — thực hiện, cần thận trọng)**: trên 536 ảnh QR thực tế, BoofCV 60,69% @104,95 ms/ảnh; OpenCV WeChat 48,89% @757,71 ms/ảnh (mạnh với mã hỏng nhưng chậm nhất); ZBar 38,95% @157,31 ms; ZXing (Java 3.5.1) 31,87% @179,57 ms; Dynamsoft 195,01 ms — [Dynamsoft QR benchmark](https://www.dynamsoft.com/codepool/qr-code-reading-benchmark-and-comparison.html)
- Benchmark Python của Dynamsoft: zxing-cpp nhanh nhất ~40,2 ms trung bình/ảnh, nhưng chỉ 23,8% khi nhiều mã/ảnh; trên 170 ảnh: Dynamsoft 90,6%, PyZBar 71,2%, zxing-cpp 65,9% — [Dynamsoft Python comparison](https://www.dynamsoft.com/codepool/python-zxing-zbar-barcode.html)
- Dynamsoft (cùng nguồn vendor): ZXing/ZBar tụt dưới 14% trên ảnh mờ/out-of-focus (1D) — [Dynamsoft 1D benchmark](https://dynamsoft.com/codepool/barcode-scanning-accuracy-benchmark-and-comparison.html)

### Inferences
- Ngành công nghiệp coi định vị là bài toán **cổ điển, rẻ, giới hạn theo kích thước ô** (HALCON: kích thước ô quyết định tầng kim tự tháp; Dynamsoft: nhiều chiến lược rẻ chạy trước). Cách hệ thống hiện tại dùng YOLO-seg "s" trên toàn khung là đắt hơn nhiều so với cách làm phổ biến trong sản phẩm.
- Với tem 54 px trên nền băng chuyền đồng nhất, một bộ định vị kiểu "khối liên thông/thống kê" (như `LM_CONNECTED_BLOCKS`/`LM_STATISTICS`) hoặc kiểu PowerGrid (mật độ cạnh/xen kẽ sáng tối trong cửa sổ cỡ ô) rất có thể chạy vài ms đến vài chục ms trên toàn dải bằng OpenCV — cần đo trên dữ liệu `data/field`; chưa có số liệu.
- "AI" trong các đầu đọc thương mại 2024–2026 chủ yếu nhắm tới **giải mã khó** (lọc, phục hồi), giống hướng `PassDecoder`/ComboBC hiện tại, chứ không phải nhắm tới định vị.

### Gaps
- Không tìm được tài liệu kỹ thuật nội bộ của 2DMax, Keyence SR-X Drive, Datalogic Matrix, Zebra/Matrox Iris; không có số ms định vị riêng (tách khỏi giải mã) của bất kỳ sản phẩm nào.
- Không lấy được trang tài liệu OpenCV WeChatQRCode (HTTP 403) để trích kiến trúc detector CNN (theo hiểu biết chung là SSD nhẹ + mô hình SR, nhưng chưa kiểm chứng trong phiên này).
- Không có ngưỡng px/ô tối thiểu chính thức của HALCON cho QR.

## B. Bộ phát hiện nhẹ cho mã nhỏ: YOLO nano, tiled/SAHI, heatmap, cổ điển, trừ nền — độ chính xác/độ trễ?

### Takeaway
Tài liệu học thuật về phát hiện QR **rất nhỏ** (≤60 px, ~2 px/ô) bằng mạng nhẹ gần như không có số liệu độ trễ CPU; kết quả có sẵn cho thấy YOLOv8n kém YOLOv8s khá xa trên barcode/QR, slicing (SAHI) tăng AP vật nhỏ ~5–7 điểm nhưng nhân chi phí theo số tile. Hướng có lợi nhất cho bài toán này là **thu nhỏ vùng phải detect** (dải vào, ROI theo băng) hơn là đổi kiến trúc mạng.

### Cited Findings
- arXiv 2511.22937 (11/2025) so YOLOv8 nano/small/medium cho barcode & QR: "accuracy" 88,95% (n), 97,10% (s), 94,10% (m); không lấy được số độ trễ (trang HTML 404) — [arXiv 2511.22937 PDF](https://arxiv.org/pdf/2511.22937); [papers.cool](https://papers.cool/arxiv/2511.22937)
- Y-Net (arXiv 2102.06868): phân đoạn barcode trên ảnh siêu phân giải (>10k×10k), lập luận rằng thu nhỏ ảnh làm mất thông tin mã nhỏ; end-to-end 16 ms, nhanh hơn YOLOv4 2,5× và Mask R-CNN 5,9×, mAP cao hơn YOLOv4 5,5% trên tập tổng hợp; phần cứng không nêu trong abstract — [arXiv 2102.06868](https://www.arxiv.org/abs/2102.06868)
- SAHI (Akyon et al., ICIP 2022): suy luận cắt lát tăng AP 6,8/5,1/5,3% cho FCOS/VFNet/TOOD trên VisDrone/xView; thêm fine-tuning cắt lát: tổng 12,7/13,4/14,5%; patch 640×640 (VisDrone), 400×400 (xView), overlap 25%; áp dụng cho detector bất kỳ không cần huấn luyện lại — [arXiv 2202.06934](https://arxiv.org/abs/2202.06934v2)
- ASAHI (preprint 2026): +1,7% mAP và nhanh hơn SAHI 20–25% (chưa kiểm chứng độc lập) — [arXiv 2604.19233](https://arxiv.org/pdf/2604.19233)
- `qrdet` (Eric-Canas): YOLOv8 Ultralytics huấn luyện từ đầu trên tập tự gán nhãn, kích cỡ n/s/m/l (mặc định s); README không công bố imgsz, tốc độ, mAP, cũng không nói gì về QR nhỏ — [GitHub qrdet](https://github.com/Eric-Canas/qrdet)
- Model card YOLOv8s barcode/QR trên Hugging Face: F1 cao nhất 0,98 ở conf 0,553 (không bình duyệt) — [Hugging Face](https://huggingface.co/chinhong11/YOLOV8s-Barcode-Detection)

### Inferences
- Phép tính nhanh cho hệ thống hiện tại: QR 54 px trên khung 2856 px resize về imgsz 1280 còn ~24 px (≈1 px/ô) — mạng phải phát hiện "đốm kết cấu" chứ không thấy finder pattern. Với dải rộng imgsz 1600 thì vẫn bị thu nhỏ nếu dải rộng 2856. Chạy detect trên **dải cắt ở độ phân giải gốc** (không resize, ví dụ tile 640×640 hoặc dải 2856×320 pad thành 2880×320) giữ được QR ~54 px — kích thước mà YOLO phát hiện tốt — và giảm số pixel cần xử lý.
- QR nhỏ 25 px: nếu là version 1 (21 ô) thì ~1,2 px/ô; theo kinh nghiệm chung (không có nguồn trong phiên này) giải mã ổn định cần ≥2 px/ô, nên mã 25 px gần như không thể giải ở 0,673 mm/px dù detect được. Khuyến nghị: bỏ qua QR nhỏ, hoặc chỉ dùng vị trí tương đối của nó trên tem (biết trước bố cục tem) chứ không detect riêng.
- Vì vật cần tìm là **tem trắng 36 mm trên băng** (không phải QR tùy ý trong cảnh phức tạp), các phương pháp cổ điển rẻ khả thi: (1) trừ nền/khác biệt khung với nền băng tĩnh hoặc ảnh nền trung vị; (2) ngưỡng + morphology + connected components lọc theo diện tích/tỉ lệ cạnh của tem; (3) bản đồ mật độ cạnh/gradient (kiểu PowerGrid) trên lưới cửa sổ ~16×16 px. Tất cả đều O(số pixel) với hằng số nhỏ; chi phí kỳ vọng vài–vài chục ms trên dải hàng triệu pixel — cần đo.
- Detector heatmap/center-point (CenterNet-like) với backbone rất nhỏ, đầu ra stride 4–8 tại độ phân giải gốc của dải, có thể phù hợp hơn YOLO-seg (bỏ được đầu mask — hệ thống chỉ dùng quad thô); chưa có số liệu công bố cho QR.
- YOLOv8n thay cho s: tiết kiệm ~2–3× FLOPs nhưng arXiv 2511.22937 cho thấy n kém s ~8 điểm trên barcode/QR; trên vật 54 px có thể ổn hơn nếu không bị resize — cần huấn luyện/đánh giá lại trên dữ liệu hiện trường.

### Gaps
- Không tìm được bài báo nào báo cáo độ trễ CPU cho phát hiện QR ≤60 px; không có số liệu NanoDet/RT-DETR/YOLOv10/v11 cho QR nhỏ.
- Không có tài liệu công khai về phát hiện ROI bằng trừ nền trong đầu đọc thương mại.

## C. Tối ưu suy luận trên CPU (OpenVINO, ONNX Runtime, INT8, cắt dải, imgsz) — tăng tốc kỳ vọng?

### Takeaway
Chuyển PyTorch → OpenVINO FP32 cho ~2,3–2,9× trên CPU Intel; INT8 thêm ~2,3× cho model "s" (ít với "n") với mất 1–2 điểm mAP; kết hợp với giảm diện tích ảnh (dải vào thay toàn khung, độ phân giải gốc) có thể đưa 980 ms xuống mức vài chục ms — nhưng phần giảm lớn nhất đến từ **giảm pixel**, không phải runtime.

### Cited Findings
- Ultralytics Academy, Intel Core Ultra 7 155H, COCO128 (YOLO26, không phải YOLOv8; imgsz không nêu): YOLO26s PyTorch FP32 70,92 ms → OpenVINO FP32 36,16 ms → OpenVINO INT8 15,54 ms (mAP50-95 0,5632→0,5471); YOLO26n 33,19 → 13,43 → 11,40 ms; YOLO26m 192,45 → 102,52 → 35,72 ms. Tức OpenVINO/PyTorch ~2,3–2,9×, INT8/FP32 ~1,2× (n), ~2,3× (s), ~2,9× (m) — [Ultralytics Academy: OpenVINO on CPU](https://academy.ultralytics.com/courses/yolo-in-production/openvino-on-cpu)
- Cùng nguồn: "trên n, INT8 hiếm khi đáng đánh đổi độ chính xác"; hiệu chỉnh INT8 bằng 4 ảnh làm mAP rơi 3,2 điểm, khuyến nghị >300 ảnh đại diện; iGPU (OpenVINO `xpu`) YOLO26n FP32 9,13 ms; so runtime trên laptop CPU dùng chung: ONNX Runtime p50 30,0/p95 46,4 ms vs OpenVINO p50 22,8/p95 113,5 ms (OpenVINO nhanh trung vị nhưng đuôi dài hơn) — [Ultralytics Academy](https://academy.ultralytics.com/courses/yolo-in-production/openvino-on-cpu)
- Ultralytics quảng bá OpenVINO "tới 3×" tăng tốc CPU so với PyTorch (claim của vendor; bảng Xeon trong docs chạy FP32) — [Ultralytics docs OpenVINO (bản mirror)](https://dagshub.com/Ultralytics/ultralytics/src/v8.2.97/docs/en/integrations/openvino.md); [Ultralytics blog](https://www.ultralytics.com/blog/achieve-faster-inference-speeds-ultralytics-yolov8-openvino)
- Lenovo/Intel trên Xeon 6 với YOLOv8: INT8 chỉ tăng tốc đáng kể cho model lớn nhất (61,6 → 74,64 fps); tổng PyTorch → OpenVINO tới ~14× throughput cho model lớn nhất (throughput server nhiều luồng, không phải độ trễ đơn ảnh) — [Lenovo Press LP2345](https://lenovopress.lenovo.com/lp2345-accelerating-real-time-object-detection-yolo-models-intel-xeon-6-openvino)
- Kết quả trái chiều về INT8: Ultralytics Academy cho thấy INT8 lợi ~2,3× với model s trên Core Ultra, còn Lenovo thấy lợi ít với model nhỏ trên Xeon 6 (khác thế hệ model, CPU và chỉ số throughput vs latency) — [Ultralytics Academy](https://academy.ultralytics.com/courses/yolo-in-production/openvino-on-cpu); [Lenovo Press](https://lenovopress.lenovo.com/lp2345.pdf)

### Inferences
- Chi phí conv tỉ lệ gần tuyến tính với số pixel đầu vào. Hiện tại: imgsz 1280 vuông ≈ 1,64 Mpx → 980 ms PyTorch CPU. Một dải vào 2880×320 (≈0,92 Mpx, độ phân giải gốc, QR giữ nguyên 54 px) ước ~550 ms PyTorch; cộng OpenVINO FP32 (÷2,3–2,9) → ~200–240 ms; INT8 (÷~2) → ~100–120 ms; đổi s → n thêm ÷~2–3. Đây là ước lượng ngoại suy, phải đo bằng `tools/bench_decode.py --band`.
- Model seg → chỉ cần detect box (hệ thống không vẽ mask, chỉ dùng quad cho warp); export phần detect hoặc huấn luyện model detect thuần bỏ được proto/mask head (tiết kiệm thêm, chưa định lượng).
- Lưu ý repo: CLAUDE.md yêu cầu import torch trước PyQt5; chuyển sang OpenVINO/ONNX Runtime cho detect có thể loại bỏ hẳn phụ thuộc torch trên máy hiện trường (cần kiểm tra các module khác còn dùng torch không).
- Đuôi độ trễ (p95) quan trọng với lập lịch thời gian thực: OpenVINO p95 kém trên CPU dùng chung → nên ghim số luồng (`INFERENCE_NUM_THREADS`) và tách khỏi luồng decode CPU nặng (ComboBC).

### Gaps
- Không có benchmark YOLOv8-seg trên CPU AMD hay CPU văn phòng phổ thông (máy hiện trường) với imgsz 1280/1600; không có số liệu pruning cho YOLO nhỏ.
- Chưa rõ CPU máy hiện trường (Intel hay AMD; OpenVINO chạy trên AMD nhưng tối ưu kém hơn — chưa có nguồn).

## D. Mẹo riêng cho băng chuyền: encoder/trigger, tracker Kalman/ByteTrack, dùng tốc độ băng làm prior, dải ROI; tunnel thương mại làm thế nào?

### Takeaway
Hệ thống công nghiệp (SICK, Cognex tunnel) **không track bằng thị giác thuần**: cảm biến quang báo vật vào, encoder tăng dần cho vị trí vật trên băng, đầu đọc gán mã cho vật theo vị trí; vì vậy định vị chỉ cần chạy khi có vật mới và vị trí về sau được dự đoán gần như tất định. Với băng 100 mm/s và vận tốc cố định, hệ thống này có thể thay YOLO định kỳ toàn khung bằng detect trên **dải vào** + dịch ROI theo tốc độ băng.

### Cited Findings
- SICK TTC100-2 (tủ track-and-trace): cảm biến quang và **encoder tăng dần** cung cấp thông tin chu kỳ đọc và xác định vị trí vật trên băng; tín hiệu trigger từ cảm biến quang khởi động quá trình đọc — [Manualshive, SICK TTC100-2](https://manualshive.com/en/manual/sick/ttc100-2/1264606?page=22)
- Lector65x System: đầu đọc + bộ điều khiển MSC800 + cảm biến quang + encoder — [SICK Lector65x System overview](https://cdn.sick.com/media/familyoverview/1/51/951/familyOverview_Lector65x-System_g326951_en.pdf)
- Lector85x: tracking thời gian thực tích hợp gán mã đúng vật khi nhiều vật trong khung; góc lắp dốc giảm bóng → khoảng cách vật nhỏ hơn (marketing) — [Food Processing (sponsored)](https://www.foodprocessing.com.au/content/processing/sponsored/identifies-codes-like-no-other-meet-the-new-sick-lector85x-1372784429)
- Cognex: "Tunnel Commissioning Assistant" cấu hình cả tunnel; Edge Intelligence là công cụ quản lý/giám sát read-rate, không phải thuật toán tracking — [Logistics Matters / kết quả tìm kiếm DM580](https://www.logisticsmatters.co.uk/?p=1337); [Datasheet DM580](https://riverplus.com/cdn/shop/files/Datasheet_DM580.pdf)
- Scandit MatrixScan: tracking đa mã qua frame, trả vị trí mã đã track mỗi frame (di động, không có encoder) — [Scandit docs 5.10](https://docs.scandit.com/5.10/android/android-multiple-scanning.html)

### Inferences
- **Ngân sách thời gian rất rộng**: 100 mm/s ÷ 0,673 mm/px ≈ 149 px/s. Tem ở trong vùng đọc 6 s (nếu 0,6 m dọc băng) hoặc 16 s (nếu 1,6 m dọc băng). Giữa hai lần YOLO cách 400 ms tem chỉ đi ~59 px (≈ một bề rộng tem). Không cần detect toàn khung thường xuyên.
- **Đề xuất lập lịch "dải vào"**: detect chỉ trên dải ở mép vào, rộng W px dọc chiều băng. Mọi tem nằm trọn trong dải ít nhất (W − 54)/149 s; ví dụ W = 320 → ~1,8 s, nên detect mỗi 0,5–1 s trên dải vẫn thấy mỗi tem ≥2 lần. Sau khi detect, vị trí tương lai = vị trí + v_băng·Δt (vận tốc băng đo một lần hoặc ước lượng robust từ trung vị vận tốc các track), chỉ cần **tái định vị cục bộ** trong ROI nhỏ (~150×150 px) bằng zxing/finder pattern/template matching trên ROI — rẻ hơn YOLO hàng chục lần. Có thể thêm một lần quét toàn khung thưa (vài giây/lần) để bắt tem bị bỏ sót.
- **Tracker**: với chuyển động gần như tịnh tiến đều, Kalman/ByteTrack không đem lại nhiều so với dự đoán vận tốc chung của băng; lợi ích chính của ByteTrack (giữ detection độ tin cậy thấp để nối track) có thể áp dụng đơn giản: chấp nhận detection conf thấp nếu khớp vị trí dự đoán. Dùng **một vận tốc băng chung** (thay vì vận tốc riêng từng track) làm prior giảm lỗi ghép khi track mới chỉ có 1–2 điểm, và cho phép thu hẹp cổng (hiện trần 900 px) xuống cỡ vài chục px.
- **Encoder/trigger**: nếu dây chuyền có encoder hoặc tốc độ băng cố định từ PLC, có thể đóng dấu vị trí băng cho mỗi frame (hoặc dùng timestamp camera × v) thay cho đo vận tốc từ ảnh — tương tự SICK. Cảm biến quang ở mép vào có thể thay cả detect dải vào nếu tem luôn ở vị trí ngang biết trước.
- **Thời điểm đọc tốt nhất**: vì mỗi tem có hàng chục frame, lập lịch giải mã nên ưu tiên các frame tem ở gần tâm quang học (ít méo, sáng đều) và dừng ngay khi đủ 2 lần đọc giống nhau (đã có), giải phóng CPU cho tem khác.
- **QR nhỏ 25 px**: bỏ qua trong detect; nếu cần nội dung của nó, suy vị trí từ QR lớn theo bố cục tem cố định và thử giải trên crop ×SR — nhưng với ~1,2 px/ô (nếu version 1) khả năng thành công thấp.

### Gaps
- Không tìm được tài liệu chi tiết (độ phân giải encoder, thuật toán gán mã–vật) của SICK/Cognex tunnel; chỉ có mô tả cấp hệ thống.
- Không có số liệu công bố về độ chính xác tracking theo encoder so với tracking thị giác cho đầu đọc ảnh.
- Chưa xác minh chiều nào của vùng 1,6 m × 0,6 m là chiều chạy băng — ảnh hưởng thời gian tem trong khung (6 s hay 16 s).
