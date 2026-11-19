# Định vị và theo dõi tem QR nhỏ trên băng chuyền: hai camera 8 MP, Jetson Nano hoặc PC chỉ có CPU

Bối cảnh (lấy từ đề bài, không phải nguồn web): 2 × Basler a2A2840-48umBAS mono 2856×2848, ống 4 mm; mỗi camera phủ 1,5–1,6 m bề ngang, 0,525–0,56 mm/px; QR 32 mm, version 2 (25×25 ô), mức M → QR ≈ 55–61 px, 2,2–2,44 px/ô; buồng tối dài 60 cm, ánh sáng có kiểm soát, dải ROI ≈ 2856×1072 trên mỗi camera; băng 80–120 mm/s. Phần mềm hiện tại: YOLOv8-seg "qrdet" cỡ s, imgsz 1280, chạy toàn khung ≤ mỗi 400 ms: 980 ms/khung trên Ryzen 5 5500U, 190 ms trên GTX 1650.

Ghi chú phương pháp: 15 lượt tìm/tải trong phiên này, cộng các trích dẫn dùng lại từ ghi chú trước (`research_notes/Tối ưu đọc QR băng chuyền/01_detect_track_inference.md`, giả định phần cứng khác). Phần lớn số liệu Jetson Nano gốc đến từ diễn đàn NVIDIA và repo cộng đồng, không phải benchmark chính thức. Mọi phép tính số học cho hệ thống này nằm ở mục "Inferences" và phải được đo lại trên dữ liệu thật.

**Phép tính nền dùng xuyên suốt (suy ra từ đề bài):**
- Vận tốc ảnh: 80–120 mm/s ÷ 0,56–0,525 mm/px ≈ **143–229 px/s**.
- Thời gian tem ở trong buồng 60 cm: 600/120 = **5 s** đến 600/80 = **7,5 s**. Dải 1072 px × 0,525–0,56 ≈ 563–600 mm, khớp với buồng tối.
- Dải ROI 2856×1072 = **3,06 Mpx/camera**, tức 6,12 Mpx cho cả hai camera. Khung đầy đủ là 8,13 Mpx.
- Resize 2856 → 1280 (×0,448): QR 55–61 px còn khoảng 25–27 px, tức **~1 px/ô** (khớp mô tả trong đề bài).
- Vệt mờ = v × t_exp ÷ mm/px. Ở 120 mm/s và 0,525 mm/px, mỗi 1 ms phơi sáng cho 0,23 px mờ; giữ mờ ≤ 1 px cần t ≤ ~4,4 ms.

---

## 1. Thực tế Jetson Nano: JetPack/CUDA/TensorRT/Python, ultralytics/torch, benchmark TensorRT, bộ nhớ, pypylon, VPI/OpenCV CUDA

### Takeaway
Jetson Nano gốc (Maxwell, compute 5.3) bị giữ ở JetPack 4.6.x (L4T 32.7, TensorRT 8.2, VPI 1.2, Python 3.6, PyTorch 1.10 cp36). Nó **không chạy được torch 2.x hay ultralytics bản mới một cách chính thức**, **không có INT8**, và YOLOv8n TensorRT FP16 chỉ đạt khoảng 19 fps (input không được nêu, nhiều khả năng 640), YOLOv8s khoảng 9 fps. Orin Nano (JetPack 5/6/7) nhanh hơn khoảng một bậc độ lớn: YOLOv8n TensorRT FP16 640 khoảng 4,4 ms, YOLO26n khoảng 4,6 ms. Như vậy chỉ Orin Nano mới gánh nổi detect CNN dày đặc trên hai dải 8 MP. Trên Nano gốc, phần định vị phải gần như hoàn toàn cổ điển hoặc chỉ dùng CNN trên dải vào.

### Cited Findings
**Phiên bản phần mềm**
- Bảng tương thích của Ultralytics: Jetson Nano chỉ hỗ trợ JetPack 4; Orin Nano/Orin NX/AGX Orin hỗ trợ JetPack 5, 6, 7. Có image Docker `ultralytics/ultralytics:latest-jetson-jetpack4`. Hướng dẫn cài PyTorch chỉ có cho JetPack 7.2/6.1/5.1.2 (JetPack 5.1.2: torch 2.1.0, torchvision 0.16.2, cp38). Thiết bị lớp Nano được nhắc đến là reComputer J1020 v2 (Nano 4GB, JetPack 4.6.1) — [Ultralytics Jetson guide](https://docs.ultralytics.com/guides/nvidia-jetson/)
- Wheel PyTorch 1.10.0 chính thức của NVIDIA cho JetPack 4.6 là Python 3.6 (cp36) — [Ultralytics docs (YOLOv5 on Jetson Nano)](https://docs.ultralytics.com/yolov5/tutorials/running_on_jetson_nano)
- Người dùng báo ultralytics cần Python ≥ 3.7/3.8, xung đột với wheel torch cp36. Cài Python 3.8 trên Nano từng gây lỗi illegal instruction. Nhân viên NVIDIA nói họ chỉ cung cấp gói Python 3.6 cho JetPack 4 — [NVIDIA forum: Unable to install ultralytics in python3.6](https://forums.developer.nvidia.com/t/unable-to-install-ultralytics-in-python3-6-in-jetpack4-6/275989); [NVIDIA forum: Ultralytics YOLO and Jetson Nano 4.6](https://forums.developer.nvidia.com/t/ultralytics-yolo-and-jetson-nano-4-6/334440)
- Cách vòng: tự build PyTorch 1.10 cho Python 3.8 từ mã nguồn (hướng dẫn cộng đồng trên JetPack 4.5.1), hoặc lên JetPack 5. Lưu ý Nano gốc không có JetPack 5 — [UWARG docs](https://uwarg-docs.atlassian.net/wiki/x/c4C9lg); [NVIDIA forum](https://forums.developer.nvidia.com/t/ultralytics-yolo-and-cuda-for-jetson-nano-4-6/282017)
- JetPack 4.6.1 gồm TensorRT 8.2, VPI 1.2 (Python binding chất lượng production), L4T 32.7.1. JetPack 4.6 là bản lớn cuối cùng cho Nano/TX1/TX2. VPI 2.0 bỏ hỗ trợ Nano và TX2, nên Nano dừng ở VPI 1.2 với backend CPU và GPU (VPI 1.2 thêm erode/dilate, min/max location trên CPU và GPU). VisionWorks không còn sau JetPack 4.6.x. OpenCV đi kèm JetPack 4.6.1 là 4.1.1; không tìm được xác nhận rằng bản này bật CUDA — [NVIDIA forum: JetPack 4.6.1 announcement](https://forums.developer.nvidia.com/t/announcing-jetpack-4-6-1-release-with-l4t-32-7-1/205680); [NVIDIA forum: Future of VPI & Jetson Nano](https://forums.developer.nvidia.com/t/future-of-vpi-jetson-nano/212840); [VPI 1.2 release notes](https://docs.nvidia.com/vpi/1.2/1.1/release_notes.html)

**Độ chính xác số và tốc độ**
- Nano không có INT8 phần cứng: theo nhân viên NVIDIA, Maxwell (compute 5.3) chỉ hỗ trợ FP16/FP32, và INT8 cần phần cứng từ kiến trúc > 7.x. Người dùng đo thấy engine FP16 và INT8 trên Nano cùng tốc độ (4–5 fps trong một case) — [NVIDIA forum: why Jetson Nano not support INT8](https://forums.developer.nvidia.com/t/why-jetson-nano-not-support-int8/84060); [NVIDIA forum: Is INT8 PTQ even possible on Jetson Nano](https://forums.developer.nvidia.com/t/is-int8-ptq-even-possible-on-jetson-nano/218184); [NVIDIA forum: FP16 does not decrease inference time on Jetson Nano](https://forums.developer.nvidia.com/t/fp16-does-not-decrease-inference-time-on-jetson-nano/223376)
- Q-engineering (repo cộng đồng, model FP16, chỉ tính thời gian suy luận, không nêu input size): Jetson Nano YOLOv5nu 20 fps, **YOLOv8n 19 fps, YOLOv8s 9,25 fps**; Orin Nano YOLOv8n/s 100 fps, YOLOv8m 40 fps. Repo ghi "int8 không tăng fps, mAP kém hơn đáng kể". Nano dùng nhánh TensorRT 8.x, và engine phải build đúng phiên bản TensorRT trên thiết bị — [Qengineering/YoloV8-TensorRT-Jetson_Nano](https://github.com/Qengineering/YoloV8-TensorRT-Jetson_Nano)
- Bài đăng diễn đàn: YOLOv8n khoảng 6,1 fps trên Nano JetPack 4.6 (không nêu runtime) — [NVIDIA forum: YOLOv8 object detection on Jetson Nano](https://forums.developer.nvidia.com/t/yolov8-object-detection-on-jetson-nano-real-time-ai-demonstration-only-for-jetson-nano/293648)
- Orin Nano 8GB, JetPack 6.2.2, MAXN_SUPER, YOLOv8n 640, batch 1 (repo cá nhân): PyTorch FP32 20,88 ms; TensorRT FP32 8,36 ms; **TensorRT FP16 4,43 ms (225 fps)**; TensorRT INT8 3,49 ms (286 fps). Không có số ở input 1280 — [hokwangchoi/jetson-orin-nano-benchmarks](https://github.com/hokwangchoi/jetson-orin-nano-benchmarks)
- Ultralytics, YOLO26n imgsz 640, chưa tính pre/post-processing: Orin Nano Super PyTorch 15,60 ms; TensorRT FP32 7,53 ms; **FP16 4,57 ms** (mAP50-95 0,4800); INT8 3,80 ms (mAP 0,4490, giảm 3,1 điểm). Orin NX 16GB FP16 4,13 ms. Không có số cho Nano gốc — [Ultralytics Jetson guide](https://docs.ultralytics.com/guides/nvidia-jetson/)

**USB, camera và pypylon**
- USB của Nano: 4 cổng USB 3.0 nằm sau một hub tích hợp và **chia chung 5 Gbps**. Có báo cáo lỗi "No space left on device" khi mở camera USB3 thứ hai vì thiếu băng thông — [NVIDIA forum: four USB 3.0 cameras on Nano](https://forums.developer.nvidia.com/t/can-i-use-four-usb-3-0-cameras-on-nvidia-jetson-nano-board-without-loosing-speed-of-video-streaming/185709); [NVIDIA forum: cannot stream 2 USB cameras](https://forums.developer.nvidia.com/t/cannot-stream-2-usb-cameras-no-space-left-on-device-28/75084); [NVIDIA forum: USB3 bandwidth dual high-speed cameras](https://forums.developer.nvidia.com/t/usb3-bandwidth-issue-with-dual-high-speed-cameras-on-jetson-orin-nano/282365)
- pypylon có wheel manylinux aarch64: bản 2.2.0 cho CPython 3.6–3.11, các bản mới hơn có wheel abi3 cho glibc ≥ 2.31. Ubuntu 18.04 (JetPack 4) dùng glibc 2.27, nên trên JetPack 4 chỉ dùng được dòng wheel manylinux_2_27 cũ (ví dụ 2.2.0 cp36); điểm này là suy luận từ tag wheel. Trên Orin AGX có người không cài được wheel 2.2.0 và phải build từ mã nguồn — [PyPI pypylon 2.2.0](https://pypi.org/project/pypylon/2.2.0/); [PyPI pypylon](https://pypi.org/project/pypylon); [NVIDIA forum: Pypylon on Jetson Orin AGX](https://forums.developer.nvidia.com/t/pypylon-basler-on-jetson-orin-agx-development-kit/261272)

### Inferences
- **Băng thông USB trên Nano gốc**: một khung Mono8 2856×2848 là 8,13 MB. Ở 10 fps toàn khung, mỗi camera cần 81 MB/s, hai camera 163 MB/s, nằm trong 5 Gbps (~625 MB/s lý thuyết; thực tế USB3 Vision thường chỉ được ~350–400 MB/s, chưa có nguồn trong phiên này). Dùng ROI cảm biến 2856×1072 (3,06 MB) thì ở 15 fps hai camera chỉ cần ~92 MB/s. **Bắt buộc dùng ROI cảm biến** nếu muốn fps cao trên hub dùng chung; đẩy cả hai camera chạy fps tối đa toàn khung sẽ vượt hub.
- **Bộ nhớ 4 GB dùng chung CPU/GPU**: một dải mono 3,06 MB; nếu chuyển sang BGR 3 kênh như code hiện tại (`latest_frame` BGR) thì 9,2 MB/dải. Hai camera × (10 buffer grab + vài bản sao) chỉ khoảng 100–200 MB, không phải nút thắt. Nút thắt là OS + CUDA context + TensorRT engine + Python (thường 1–2 GB trên Nano; chưa có nguồn). Khuyến nghị: giữ **mono 1 kênh** suốt pipeline trên Jetson, bỏ chuyển BGR.
- **Ngân sách CNN trên Nano gốc** (ngoại suy từ 19 fps ≈ 53 ms/ảnh 640² YOLOv8n FP16): tile kín một dải 2856×1072 bằng ảnh 640×640 cần 5×2 = 10 tile, hai camera 20 tile, tức khoảng 1,05 s mỗi lượt quét. Với YOLOv8s (~108 ms/tile) là khoảng 2,2 s. Cộng thêm pre/post-processing trên CPU ARM A57 yếu. → **Quét toàn dải liên tục bằng CNN trên Nano gốc là không khả thi**; chỉ chạy CNN trên dải vào (xem mục 2) hoặc dùng định vị cổ điển.
- **Orin Nano**: khoảng 4,5 ms/tile 640 FP16 cho model n, nên 20 tile ≈ 90 ms + pre/post. Quét toàn hai dải ~3–5 lần/s là khả thi. INT8 chỉ có lợi trên Orin, và mất ~3 điểm mAP trên COCO (YOLO26n).
- **Một codebase chạy trên cả hai**: Python 3.6 trên JetPack 4 không tương thích với code repo hiện tại (dataclass, f-string đều ổn, nhưng torch 2.x, ultralytics và OpenCV 5 thì không). Hướng chung khả thi: model export **ONNX opset 11–12**, chạy bằng TensorRT 8.2 trên Nano, TensorRT 8.6/10 trên Orin, ONNX Runtime/OpenVINO trên CPU; phần định vị cổ điển viết bằng OpenCV/numpy thuần. Như vậy bỏ được phụ thuộc torch/ultralytics lúc chạy.

### Gaps
- Không có benchmark chính thức YOLOv8n/s TensorRT FP16 trên Nano gốc kèm input size rõ ràng, và không có số ở imgsz 1280 cho Nano hay Orin Nano.
- Không xác nhận được OpenCV 4.1.1 trong JetPack 4.6 có CUDA hay không (theo hiểu biết chung là không; phải tự build), cũng không có số đo VPI 1.2 trên Nano cho threshold/morphology ở 3 Mpx.
- Không tìm được nguồn về tốc độ thực tế của Basler pylon USB3 trên Nano (CPU A57 có thể là nút thắt khi copy/chuyển đổi khung) hay về hỗ trợ GigE.
- Không có số đo bộ nhớ thường trú cụ thể của TensorRT + CUDA context trên Nano 4 GB.

---

## 2. Chiến lược phát hiện ở độ phân giải gốc: tile, dải vào, định vị cổ điển, CNN nhẹ, heatmap

### Takeaway
Trong buồng tối có ánh sáng đồng nhất, tem trắng/QR trên nền kính và con lăn là bài toán "tìm đốm sáng có kết cấu cỡ 55–61 px". Đây chính là loại bài toán mà đầu đọc công nghiệp giải bằng định vị cổ điển rẻ (khối liên thông, thống kê, texture, tháp ảnh theo kích thước ô). Cách hiệu quả nhất trên cả Jetson và CPU là: (1) **giữ độ phân giải gốc** (không resize 2856 → 1280), (2) **chỉ phát hiện ở dải vào** rồi theo dõi, (3) dùng **ngưỡng + khối liên thông + lọc hình học** làm bộ đề xuất chính, và chỉ dùng CNN nhỏ (YOLO-n/PicoDet/NanoDet) trên tile cố định khi bộ cổ điển không đủ. Không có tài liệu học thuật nào báo cáo độ trễ cho QR ≤ 60 px trên phần cứng biên.

### Cited Findings
**Đầu đọc công nghiệp định vị thế nào** (dùng lại từ ghi chú 01)
- Dynamsoft cung cấp các chế độ định vị kết hợp được: `LM_CONNECTED_BLOCKS` (khối liên thông, cho ảnh rõ), `LM_STATISTICS` (thống kê; vẫn định vị được khi nhị phân hóa làm hỏng finder pattern), `LM_LINES`, `LM_SCAN_DIRECTLY` (nhanh nhất, cần ảnh tốt và mã nằm ngang/dọc), `LM_CENTRE`, và `LM_NEURAL_NETWORK` thêm từ bản 11.2.2000 — [Dynamsoft localization modes](https://www.dynamsoft.com/barcode-reader/docs/core/parameters/reference/localization-modes.html)
- HALCON `find_data_code_2d` bắt đầu tìm ở tầng tháp ảnh cao nhất mà các ô còn tách được (theo module size tối đa trong model). Giới hạn `module_size_min/max` và `symbol_shape` giúp tăng tốc rõ rệt — [HALCON find_data_code_2d](https://www.mvtec.com/doc/halcon/13/en/find_data_code_2d.html); [HALCON set_data_code_2d_param](https://www.mvtec.com/doc/halcon/13/en/set_data_code_2d_param.html)
- Cognex PowerGrid định vị dựa trên **texture** (mẫu ô sáng/tối xen kẽ bên trong mã) thay vì finder pattern (thông cáo, mang tính marketing) — [Automate.org](https://www.automate.org/vision/news/powergrid-technology-for-2d-barcode-reading)
- Bằng sáng chế SICK "dynamic image regionalization" nhắm vào việc khoanh vùng mã trong ảnh trước khi giải; đoạn trích không đủ chi tiết về phương pháp — [US10229301](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/10229301)

**Thư viện định vị/giải mã mã nguồn mở**
- Benchmark của Dynamsoft (đối thủ thương mại, cần thận trọng) trên 536 ảnh: BoofCV 60,69% @ 104,95 ms/ảnh; OpenCV WeChat 48,89% @ 757,71 ms; ZBar 38,95% @ 157,31 ms; ZXing 31,87% @ 179,57 ms. Một lần chạy khác với phiên bản khác cho thứ tự tốc độ ngược lại (BoofCV 205,48 ms, WeChat 175,06 ms), tức xếp hạng tốc độ không ổn định giữa các lần chạy — [Dynamsoft QR benchmark](https://www.dynamsoft.com/codepool/qr-code-reading-benchmark-and-comparison.html); [Dynamsoft multi-barcode benchmark](https://www.dynamsoft.com/codepool/multiple-barcodes-reading-benchmark-and-comparison.html)
- Tác giả BoofCV tự nhận BoofCV và Quirc là hai thư viện mã nguồn mở nhanh nhất, ZXing có thể chỉnh nhanh hơn nhưng đổi lại kém bền (tự công bố) — [DZone](https://dzone.com/articles/new-qr-code-reader-library)

**CNN nhẹ và tile**
- arXiv 2511.22937 (11/2025), YOLOv8 trên barcode/QR: "accuracy" 88,95% (n), 97,10% (s), 94,10% (m). Bài không nói về băng chuyền hay QR nhỏ — [arXiv 2511.22937](https://arxiv.org/pdf/2511.22937)
- PicoDet-S (PaddleDetection, COCO): 320 → 29,1 mAP, 9,56 ms Paddle-Lite trên Snapdragon 865; 416 → 32,5 mAP, 15,20 ms. CPU OpenVINO trên i7-10750H: 4,8 ms (320), 6,6 ms (416). Bản README cũ hơn cho số khác (416: 30,7 mAP, 9,82 ms), nghĩa là số phụ thuộc phiên bản — [PaddleDetection README mirror](https://openi.pcl.ac.cn/Awesome-PaddlePaddle/Aweso202301041519173/src/branch/master/PaddleDetection); [PaddleDetection v2.3 mirror](https://github.com/KyrieHee/PaddleDetection/blob/release/2.3/configs/picodet)
- NanoDet-Plus-m (ncnn, ARM 4×A76): 320 → 27,0 mAP, 11,97 ms; 416 → 30,4 mAP, 19,77 ms. YOLOX-Nano 416: 25,8 mAP, 19,23 ms — [DefTruth/nanodet](https://github.com/DefTruth/nanodet); [PaddleDetection README_en](https://gitee.com/xiaoqin00/PaddleDetection/blob/release/2.6/configs/picodet/README_en.md)
- SAHI (slicing): +5,1–6,8 AP vật nhỏ khi chỉ cắt lát lúc suy luận, +12,7–14,5 AP khi fine-tune trên lát; patch 640/400, overlap 25%. Chi phí tăng theo số tile — [arXiv 2202.06934](https://arxiv.org/abs/2202.06934v2)
- Y-Net phân đoạn barcode trên ảnh rất lớn, lập luận rằng thu nhỏ ảnh làm mất mã nhỏ; 16 ms end-to-end (phần cứng không nêu trong abstract) — [arXiv 2102.06868](https://www.arxiv.org/abs/2102.06868)
- Bài SBrT 2025 đánh giá đọc barcode trên băng chuyền tự động theo read rate và thời gian xử lý mỗi frame (chưa trích được số) — [SBrT 2025](https://biblioteca.sbrt.org.br/articlefile/4929.pdf)

### Inferences
- **Vấn đề lớn nhất của pipeline hiện tại là resize, không phải model**: ở imgsz 1280 trên khung 2856, QR chỉ còn ~1 px/ô, nên mạng chỉ thấy "đốm kết cấu". Ở độ phân giải gốc, QR rộng 55–61 px, đúng cỡ vật mà detector 640 tile phát hiện tốt.
- **Bộ đề xuất cổ điển (khuyến nghị làm đường chính)**, dựa vào ánh sáng có kiểm soát:
  1. Lấy mẫu xuống ×4 (dải 714×268): QR còn ~14–15 px, vẫn là một khối tương phản cao trên nền đồng nhất.
  2. Tính độ lệch so với nền: ảnh nền trung vị cập nhật chậm của buồng tối (kính/con lăn tĩnh), hoặc bản đồ "năng lượng gradient/độ lệch chuẩn cục bộ" trong cửa sổ ~4×4 px ở ảnh ×4 (tương tự ý tưởng texture của PowerGrid).
  3. Ngưỡng Otsu/cố định → morphology close → `connectedComponentsWithStats` → lọc theo diện tích (tương ứng ~40–80 px cạnh ở độ phân giải gốc), độ đặc (solidity) và `minAreaRect` gần vuông, với mọi góc xoay.
  4. Tùy chọn xác nhận cấu trúc trên ROI gốc ~96×96: tìm 3 finder pattern bằng tỉ lệ 1:1:3:1:1 (kiểu zxing/OpenCV `QRCodeDetector.detect`) hoặc gửi thẳng vào zxing-cpp `ReadBarcodes` trên crop.

  Chi phí: các phép này O(số pixel) với hằng số nhỏ. Trên ảnh ×4 (0,19 Mpx/camera) có thể chỉ vài ms trên CPU x86 và vài chục ms trên A57; chưa có số đo, phải benchmark. Nhược điểm: chỉ đúng khi nền thật sự đồng nhất. Bụi, vết bẩn trên kính hay vạch con lăn sẽ thành ứng viên giả; giải pháp là lọc bằng texture và finder pattern, hoặc bằng CNN tí hon phân loại crop 64×64 (rất rẻ).
- **Phát hiện ở dải vào rồi theo dõi**: tem đi qua dải cao H px trong thời gian (H − 61)/v. Ở 229 px/s, nếu muốn mỗi tem nằm trọn trong dải ≥ 2 lần detect cách nhau 0,5 s thì H ≥ 61 + 229 × 1,0 ≈ 290 → **dải 2856×320** (0,91 Mpx, bằng 30% dải ROI). Trên Nano gốc với YOLOv8n FP16: dải 2856×320 ≈ 5 tile 640×320 ≈ 2,5 tương đương 640², tức ~130 ms/camera, ~270 ms cho hai camera mỗi 0,5 s, tức ~55% GPU. Khả thi nhưng sát; cổ điển sẽ rẻ hơn nhiều.
- **Tile toàn dải**: 640×640, overlap 64 px → 5×2 = 10 tile/camera. Hợp lý trên Orin Nano (~90 ms cho 20 tile FP16 model n) hoặc trên CPU với OpenVINO (xem mục 3), không hợp lý trên Nano gốc.
- **Model**: hệ thống chỉ cần box/quad thô, nên detect thuần (không seg) là đủ; bỏ proto/mask head. Một detector 1 lớp ("QR/tem") trên tile 640 ở độ phân giải gốc, train lại bằng dữ liệu hiện trường, nên thử theo thứ tự: YOLOv8n/YOLO11n/YOLO26n detect (export ONNX dễ nhất cho TensorRT 8.2) → PicoDet-S (rất nhanh trên CPU qua OpenVINO) → NanoDet-Plus (ncnn trên ARM). Số "n kém s ~8 điểm" của arXiv 2511.22937 là trên ảnh barcode tổng quát và có thể không áp dụng khi vật không bị resize.
- **Heatmap/center-point**: vì vị trí sau đó được tinh chỉnh bằng zxing/warp, một mạng heatmap stride 4–8 với backbone rất nhỏ (kiểu CenterNet) trên ảnh ×2 có thể đủ và rẻ hơn YOLO; chưa có số liệu công bố cho QR.

### Gaps
- Không có bài báo nào báo cáo accuracy/latency cho phát hiện QR ≤ 60 px (~2 px/ô) trên Jetson hay CPU; không có số liệu NanoDet/PicoDet cho QR.
- Không có số đo ms của định vị khối liên thông/finder pattern trên ảnh 3 Mpx cho Python/OpenCV trên A57 hoặc Ryzen 5500U.
- Không tìm được mô tả thuật toán `LM_NEURAL_NETWORK` của Dynamsoft hay của "dynamic image regionalization" của SICK.

---

## 3. Tối ưu suy luận trên CPU (ONNX Runtime/OpenVINO) và so với Jetson

### Takeaway
Trên CPU x86, OpenVINO FP32 nhanh hơn PyTorch khoảng 2,3–2,9×, INT8 thêm khoảng 2,3× cho model s (ít với model n). Model n ở 640 chỉ tốn khoảng 11–36 ms trên Intel Core Ultra. Kết hợp với **giảm pixel** (dải vào hoặc tile ở độ phân giải gốc), mức 980 ms hiện tại có thể giảm xuống còn vài chục đến khoảng 100–200 ms trên Ryzen 5500U. Tuy vậy, phần lớn lợi ích đến từ bỏ resize/giảm diện tích và thay seg-s bằng det-n, không đến từ runtime.

### Cited Findings
- Ultralytics Academy, Intel Core Ultra 7 155H, YOLO26: s PyTorch 70,92 ms → OpenVINO FP32 36,16 → INT8 15,54 ms (mAP 0,5632 → 0,5471); n 33,19 → 13,43 → 11,40 ms. Trên laptop dùng chung: ONNX Runtime p50 30,0 / p95 46,4 ms, OpenVINO p50 22,8 / p95 113,5 ms (đuôi độ trễ dài hơn). "INT8 hiếm khi đáng với model n"; hiệu chỉnh INT8 nên dùng > 300 ảnh — [Ultralytics Academy: OpenVINO on CPU](https://academy.ultralytics.com/courses/yolo-in-production/openvino-on-cpu)
- Raspberry Pi 5 (ARM Cortex-A76, gần với CPU ARM biên), YOLO26n FP32 640, không tính pre/post: PyTorch 299,09 ms; ONNX 125,99; OpenVINO 104,55; **NCNN 67,03 ms** — [Ultralytics Raspberry Pi guide](https://docs.ultralytics.com/guides/raspberry-pi/)
- PicoDet-S OpenVINO trên i7-10750H: 4,8 ms (320), 6,6 ms (416) — [PaddleDetection README mirror](https://openi.pcl.ac.cn/Awesome-PaddlePaddle/Aweso202301041519173/src/branch/master/PaddleDetection)
- Kết quả trái chiều về INT8: lợi ~2,3× với model s trên Core Ultra; Lenovo/Intel trên Xeon 6 thấy INT8 chỉ lợi rõ với model lớn nhất (throughput server) — [Ultralytics Academy](https://academy.ultralytics.com/courses/yolo-in-production/openvino-on-cpu); [Lenovo Press LP2345](https://lenovopress.lenovo.com/lp2345-accelerating-real-time-object-detection-yolo-models-intel-xeon-6-openvino)

### Inferences
- **Ước lượng cho Ryzen 5 5500U** (ngoại suy, phải đo): hiện tại YOLOv8s-seg PyTorch ở 1280² (1,64 Mpx) mất 980 ms, tức ~600 ms/Mpx. Chuyển sang detect-n + ONNX Runtime/OpenVINO FP32 có thể giảm khoảng 2,5 (runtime) × ~2,5 (s → n) ≈ ~6×, tức ~100 ms/Mpx. Khi đó:
  - dải vào 2856×320 × 2 camera (1,83 Mpx) ≈ **~180 ms mỗi 0,5 s**;
  - toàn hai dải (6,1 Mpx) ≈ ~600 ms.

  Như vậy CPU chỉ đủ cho **dải vào + định vị cổ điển**, còn quét toàn dải bằng CNN chỉ nên làm thưa (vài giây một lần) để bắt tem sót.
- OpenVINO chạy được trên AMD nhưng mức tối ưu cho Zen chưa được kiểm chứng; ONNX Runtime CPU EP là lựa chọn trung lập hơn. Nên đo cả hai bằng `tools/bench_decode.py`.
- Ghim số luồng suy luận (ví dụ 4/12 luồng) để không tranh CPU với cascade giải mã và ComboBC; OpenVINO có p95 dài trên CPU dùng chung.
- Một artifact ONNX duy nhất (detect, 1 lớp, input 640×640 hoặc 640×320 cố định) phục vụ được cả TensorRT 8.2 (Nano), TensorRT 10 (Orin), ONNX Runtime/OpenVINO (CPU), và NCNN/ONNX Runtime trên ARM CPU nếu cần.

### Gaps
- Không có benchmark công bố cho YOLOv8/YOLO11/YOLO26 hay PicoDet trên CPU AMD Zen 2/3 di động (Ryzen 5500U).
- Không có số cho ONNX Runtime CUDA EP trên Jetson Nano (JetPack 4) so với TensorRT.

---

## 4. Theo dõi và lập lịch cho hai camera: vận tốc băng biết trước, Kalman/ByteTrack, chồng lấn, khử trùng, khi nào dừng

### Takeaway
Hệ công nghiệp không "track bằng thị giác thuần": chúng dùng encoder/vận tốc băng để chiếu vị trí vật về phía trước một cách gần như tất định, và dùng phép chiếu đó cả để gán mã–vật lẫn để khử lần giải trùng. Với băng 80–120 mm/s và chuyển động tịnh tiến, có thể thay tracker tham lam theo vận tốc từng track bằng **một vận tốc băng chung** (đo từ encoder/PLC hoặc ước lượng robust từ trung vị các track), cổng ghép hẹp vài chục px, và tọa độ băng chung cho hai camera để khử trùng.

### Cited Findings
- Bằng sáng chế Cognex "Associating a code with an object": vị trí vật trên băng = vị trí ban đầu + thay đổi số xung encoder × khoảng cách mỗi xung. Vị trí mã trong ảnh được chiếu ngược thành tia trong tọa độ băng rồi gán cho bề mặt vật mà tia cắt gần nhất. Trường nhìn camera phải đủ dài để chụp trọn một mã — [US9305231B2](https://patents.google.com/patent/US9305231)
- Bằng sáng chế Zebra "4D barcode mapping": chiếu dữ liệu vật 3D đã đánh dấu về phía trước bằng vận tốc băng; lần giải mới khớp với phép chiếu thì được coi là **giải trùng**; cũng dùng để phát hiện quét hỏng — [US12067449B2](https://patents.google.com/patent/US12067449)
- SICK TTC100-2 / Lector65x System: cảm biến quang để trigger và encoder tăng dần để biết vị trí vật trên băng — [Manualshive SICK TTC100-2](https://manualshive.com/en/manual/sick/ttc100-2/1264606?page=22); [SICK Lector65x System overview](https://cdn.sick.com/media/familyoverview/1/51/951/familyOverview_Lector65x-System_g326951_en.pdf)
- SICK Lector85x quảng cáo "real-time tracking tích hợp" để gán mã đúng vật khi nhiều vật cùng trong khung (marketing, tài trợ) — [Food Processing (sponsored)](https://www.foodprocessing.com.au/content/processing/sponsored/identifies-codes-like-no-other-meet-the-new-sick-lector85x-1372784429)
- Scandit MatrixScan track nhiều mã qua frame và trả vị trí mỗi frame xử lý (di động, không có encoder) — [Scandit docs 5.10](https://docs.scandit.com/5.10/android/android-multiple-scanning.html)

### Inferences
- **Mô hình chuyển động**: vị trí (x, y) và góc của tem gần như không đổi theo phương ngang băng; theo phương dọc thì y(t) = y0 + v_băng·t. Khi đã có v_băng chung, Kalman cho từng track chỉ cần ước lượng y0 và sai số nhỏ; ByteTrack-style chỉ thêm một điều hữu ích là chấp nhận detection độ tin cậy thấp nếu khớp vị trí dự đoán. Cổng ghép có thể là ~(mờ + sai số v × Δt): với sai số vận tốc 5% và Δt = 1 s ở 229 px/s, sai lệch ~11 px, nên cổng ~30–40 px thay vì trần 900 px hiện tại. Cổng hẹp giảm hẳn lỗi ghép nhầm khi tem dày.
- **Nguồn vận tốc**: tốt nhất là encoder hoặc tốc độ từ PLC đóng dấu cho mỗi frame. Nếu không có, dùng trung vị vận tốc các track đã xác nhận trong N giây gần nhất. Vận tốc biến thiên 80–120 mm/s nên phải ước lượng liên tục, không cố định.
- **Hai camera**: mỗi camera phủ 1,5–1,6 m trên băng rộng 3,25 m, tức hai camera phủ 3,0–3,2 m. Phần chồng lấn (nếu có) hay khoảng hở phụ thuộc lắp đặt. Hiệu chuẩn mỗi camera về **tọa độ băng chung** (mm ngang, mm dọc) bằng homography một lần. Tem trong vùng chồng lấn được gán một ID duy nhất theo khoảng cách trong tọa độ băng; khử trùng theo (nội dung, vị trí băng ± dung sai) thay cho chỉ theo nội dung trong 30 s như `merged_stats` hiện tại. Cách này giống phép chiếu 4D của Zebra.
- **Một thread decode, luân phiên** (như `DualDecodeWorker`) là đúng trên Nano/CPU. Lập lịch theo ưu tiên: (1) detect dải vào của camera A, rồi B, xen kẽ mỗi ~0,5 s; (2) ROI của các track chưa xác nhận, ưu tiên track gần lối ra (sắp hết thời gian); (3) bỏ hẳn track đã xác nhận (2 lần giải giống nhau), chỉ kiểm tra lại thưa (ví dụ 1 lần/2 s) để phát hiện tem dính chồng hoặc tách.
- **Số frame cần cho mỗi tem**: thời gian lưu 5–7,5 s. Nếu ROI của một tem được giải ~4–5 lần/s, mỗi tem có 20–37 lần thử. Với tỉ lệ giải từng frame chỉ 20%, xác suất có < 2 lần giải đúng trong 20 lần là ≈ 0,8^20 + 20·0,2·0,8^19 ≈ 0,069. Như vậy cần nhắm ≥ 30 lần thử, hoặc tỉ lệ từng frame ≥ 30% (với 20 lần thử thì xác suất thất bại khi p = 0,3 ≈ 0,0076). Đây là phép tính nhị thức minh họa, giả định các lần thử độc lập (thực tế không độc lập: cùng góc, cùng vết bẩn).
- **Exposure**: ở 120 mm/s và 0,525 mm/px, vệt mờ = 0,23 px/ms. Giữ mờ ≤ 0,5 ô (~1,1–1,2 px) cần t ≤ ~5 ms; buồng tối có đèn mạnh nên làm được. Điều này giảm phụ thuộc vào Wiener/xếp chồng ROI.
- **Khi nào dừng**: dừng xử lý ROI ngay khi 2 lần giải giống nhau (đã có), nhưng giữ track vị trí tới khi ra khỏi buồng để chặn tạo track mới cho cùng tem (khử trùng trong một camera).

### Gaps
- Không tìm được tài liệu công khai về độ phân giải encoder, dung sai gán mã hay thuật toán chồng lấn của tunnel Cognex/SICK/Datalogic.
- Không có số liệu ByteTrack/Kalman so với vận tốc chung cho vật tịnh tiến trên băng.
- Chưa biết dây chuyền có encoder hay tín hiệu tốc độ từ PLC; chưa biết bố trí hai camera có chồng lấn hay không.

---

## 5. QR nhỏ ~25 px: có đáng phát hiện không?

### Takeaway
Không. Ở 0,525–0,56 mm/px, mã 25 px chỉ đạt 1,0–1,2 px/ô (version 1 hoặc 2), dưới mức tối thiểu ~2 px/ô mà toàn bộ pipeline hiện tại đã phải vật lộn. Detect riêng nó tốn thêm chi phí mà gần như không có cơ hội giải được.

### Cited Findings
- Đầu đọc công nghiệp coi kích thước ô tối thiểu là tham số trung tâm (HALCON `module_size_min`; chế độ `small_modules_robustness='high'` cho ô rất nhỏ nhưng tốn bộ nhớ/thời gian hơn) — [HALCON set_data_code_2d_param](https://www.mvtec.com/doc/halcon/13/en/set_data_code_2d_param.html)
- Bằng sáng chế Cognex yêu cầu trường nhìn đủ để chụp trọn mã; không nêu ngưỡng px/ô — [US9305231B2](https://patents.google.com/patent/US9305231)

### Inferences
- 25 px ÷ 21 ô (v1) ≈ 1,19 px/ô; ÷ 25 ô (v2) = 1,0 px/ô. Dưới Nyquist (2 px/ô); ngay cả super-resolution đa frame cũng khó tái tạo ổn định.
- Nếu nội dung QR nhỏ cần thiết: suy vị trí của nó từ QR lớn theo bố cục tem cố định (không cần detect), và chỉ thử giải bằng xếp chồng đa frame khi QR lớn thất bại. Nếu không cần thì bỏ qua hoàn toàn. Một lưu ý thực tế: nó có thể bị nhầm thành ứng viên giả trong định vị cổ điển, nên lọc theo diện tích ở mục 2 phải loại nó ra (diện tích ~1/5 QR lớn).

### Gaps
- Không có nguồn nào công bố ngưỡng px/ô tối thiểu chính thức cho QR (HALCON, Cognex, ISO). Phần "~2 px/ô" là quy ước thực hành, chưa có trích dẫn trong phiên này.

---

## 6. Sản phẩm thương mại và triển khai trên Jetson làm gì

### Takeaway
Cognex/SICK/Keyence/Datalogic/Dynamsoft định vị mã chủ yếu bằng thuật toán cổ điển (finder pattern, texture, khối liên thông, thống kê, tháp ảnh theo kích thước ô). "AI" xuất hiện gần đây chủ yếu cho lọc ảnh/giải mã khó, hoặc như một chế độ định vị tùy chọn. Tunnel công nghiệp dựa vào cảm biến quang + encoder để theo dõi và gán mã. Không tìm được nghiên cứu tình huống công khai, định lượng, nào về đầu đọc QR công nghiệp chạy trên Jetson.

### Cited Findings
- Cognex PowerGrid: định vị theo texture, đi "từ trong ra", vẫn tìm được mã khi finder/clock/quiet zone hỏng (marketing) — [Automate.org](https://www.automate.org/vision/news/powergrid-technology-for-2d-barcode-reading)
- Cognex DataMan 580 (tunnel logistics): cảm biến 9 MP, "1D/2D QuickSort"; "tới 99,9% read rate" là số marketing — [Datasheet DM580](https://riverplus.com/cdn/shop/files/Datasheet_DM580.pdf)
- Keyence SR-X: chip AI tích hợp, huấn luyện > 100.000 ảnh, dùng cho "AI filter" và thuật toán giải; không có nguồn nói AI dùng để định vị — [Keyence SR-X](https://www.keyence.com/products/barcode/barcode-readers/sr-x/); [Vision Systems Design](https://www.vision-systems.com/factory/article/55020046/keyence-launches-ai-powered-code-reader-line)
- SICK Lector85x: tracking tích hợp, băng tới 3,5 m/s (marketing); Lector65x System dùng bộ điều khiển MSC800 + cảm biến quang + encoder — [Food Processing (sponsored)](https://www.foodprocessing.com.au/content/processing/sponsored/identifies-codes-like-no-other-meet-the-new-sick-lector85x-1372784429); [SICK Lector65x System](https://cdn.sick.com/media/familyoverview/1/51/951/familyOverview_Lector65x-System_g326951_en.pdf)
- Dynamsoft thêm `LM_NEURAL_NETWORK` từ 11.2.2000 như một chế độ bên cạnh các chế độ cổ điển — [Dynamsoft localization modes](https://www.dynamsoft.com/barcode-reader/docs/core/parameters/reference/localization-modes.html)
- Tunnel Cognex: encoder + dimensioner + chiếu tia ảnh → tọa độ băng; Zebra: chiếu 4D theo vận tốc băng để khử trùng; SICK: gán mã với vật trong hệ thống tracking băng (bằng sáng chế) — [US9305231B2](https://patents.google.com/patent/US9305231); [US12067449B2](https://patents.google.com/patent/US12067449); [US9193534 (SICK)](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/9193534)

### Inferences
- Kiến trúc tham chiếu khớp với ngành, và đã được điều chỉnh cho Jetson/CPU: (1) ảnh mono, ROI cảm biến, exposure ngắn, ánh sáng đồng nhất; (2) định vị cổ điển ở ảnh ×4 + xác nhận finder pattern trên crop gốc; CNN nhỏ chỉ ở dải vào hoặc làm bộ phân loại crop; (3) theo dõi bằng vận tốc băng chung trong tọa độ băng chung cho hai camera; (4) dồn compute vào giải mã ROI của các track chưa xác nhận (zxing → WeChat → xếp chồng), dừng khi đủ 2 lần đọc.
- Trên Nano gốc: Python 3.6 + TensorRT 8.2 + VPI 1.2 + pypylon wheel cũ là một ngăn xếp riêng, khó bảo trì chung với bản Windows/CPU. Nếu chưa mua phần cứng, Orin Nano bớt rủi ro phần mềm hơn nhiều (JetPack 6, Python 3.10, torch 2.x, ultralytics chính thức). Đây là nhận định, không phải đề xuất đổi ràng buộc.

### Gaps
- Không có tài liệu kỹ thuật nội bộ cho Cognex 2DMax, Keyence SR-X Drive, Datalogic Matrix; không có số ms định vị tách riêng của bất kỳ sản phẩm nào.
- Không tìm được nghiên cứu tình huống công khai (số liệu read rate/độ trễ) về đầu đọc QR/barcode băng chuyền chạy trên Jetson Nano hay Orin Nano.
