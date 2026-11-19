# Đặt lại bài toán ở mức thu ảnh / phần cứng / hệ thống: các hướng thay cho "1 camera góc rộng + phần mềm nặng"

Bối cảnh (từ đề bài): tem 36×36 mm có QR (nội dung dạng 14 số `#` 12 số, cộng một QR nhỏ hơn), băng con lăn 100 mm/s, vùng đọc rộng 1,6 m × dài 0,6 m, tem nằm bất kỳ đâu trên bề rộng, xoay bất kỳ, kính phản chiếu đèn trần. Cấu hình hiện tại: Basler a2A2840-48um (2856×2848), ống 4 mm, cao 1 m → 0,673 mm/px → 2,2–2,6 px/ô; video hiện trường mờ 10–20 px (AE bật) → 0/4 lượt chạy đọc được, tem đứng yên đọc 100%.

Ghi chú phương pháp: chỉ khoảng 20 lần tìm/tải trang. Nhiều trang datasheet PDF của Cognex quá lớn để tải (DM580/DM380 Quick Reference) nên bảng FOV của họ không lấy được. Giá thiết bị đọc mã công nghiệp gần như đều là "liên hệ báo giá". Các phép tính trong mục "Inferences" là của người viết, dựa trên số liệu có nguồn, chưa kiểm chứng trên camera thật.

## 1. Bao nhiêu pixel/ô (PPM) là đủ, và với 1,6 m thì cần độ phân giải bao nhiêu?

### Takeaway
Nguồn khoa học tìm được cho ngưỡng thực tế khoảng 3–3,5 px/ô đối với QR. Hệ hiện tại chỉ có 2,2–2,6 px/ô, tức nằm dưới ngưỡng ngay cả khi ảnh không mờ. Để có 3–5 px/ô trên bề rộng 1,6 m cần khoảng 3.000–5.000 px theo chiều ngang, gấp 1,1–1,8 lần cảm biến 2856 px hiện tại, chưa kể dư cho chồng lấn và tem xoay.

### Cited Findings
- Bài báo trên tạp chí *Sensors* (9/2022) kết luận rằng để giải mã thực tế, mỗi ô QR không nên nhỏ hơn 3–3,5 pixel, bất kể đặc tính MTF của quang học — [DOAJ, Sensors Sep 2022](https://doaj.org/article/6ffe9a2e5d9345e7a1400c1b9f97fc60); [PubMed 36236331](https://www.pubmed.gov/36236331/). Không đọc được toàn văn vì PubMed chặn cookie, nên phương pháp đo chưa xác minh.
- Cognex quảng cáo 1DMax/Hotbars II đọc mã 1D tới 0,8 PPM. Đây là số cho mã 1D, không áp dụng cho mã 2D — [Datasheet Cognex DM150/260](https://cdn.i-pulse.nl/isotron/production/products/955/Datasheet-Cognex-DM150-260.pdf). Đây là số marketing, lấy ở điều kiện thuận lợi nhất.
- Thông số đầu đọc thường ghi "độ phân giải mã tối thiểu" theo mm ở một khoảng cách cụ thể, không ghi PPM. Ví dụ: Keyence SR-X300 đọc ô 2D nhỏ nhất 0,024 mm với FOV 104×65 mm ở 300 mm; bản góc rộng SR-X300W có FOV 267×166 mm ở 300 mm và ô 2D nhỏ nhất 0,060 mm (bảng thông số của Keyence trình bày khó đọc) — [Keyence SR-X specs](https://www.keyence.com/products/barcode/barcode-readers/sr-x/specs); [datasheet phân phối SR-X300W](https://www.eurosensor.com/img/pdf/keyence-sr-x300w-barcode-reader-pdf-60590.pdf).
- Không tìm được con số PPM chính thức của Cognex cho mã 2D trong các kết quả tìm kiếm — [kết quả tìm Cognex DM150/260](https://www.controleng.com/articles/ec-dataman-150-260-series/).

### Inferences
- **Kích thước ô hiện tại:** 2,2–2,6 px × 0,673 mm/px ≈ 1,5–1,75 mm/ô. QR V1 có 21 ô, tức mã rộng khoảng 31–37 mm, gần như chiếm hết tem 36 mm với vùng trống rất hẹp.
- **Độ phân giải cần để phủ 1,6 m (chưa tính chồng lấn), với ô ≈ 1,6 mm:**

  | Mục tiêu PPM | mm/px | Số px cần theo chiều ngang 1,6 m |
  |---|---|---|
  | 3 | 0,53 | ~3.000 |
  | 4 | 0,40 | ~4.000 |
  | 5 | 0,32 | ~5.000 |

  Cảm biến 2856 px hiện tại cho tối đa khoảng 2,7 PPM, và chỉ đạt mức đó nếu toàn bộ 2856 px phủ đúng 1,6 m. Thực tế camera đang phủ khoảng 1,92 m.
- **Tem xoay 45°:** cạnh ô nằm chéo lưới pixel. Người viết ước lượng nên dư thêm khoảng 20–40% PPM, tức nhắm 4–5 PPM thay vì 3. Đây là suy luận, chưa có nguồn.
- **Mờ chuyển động cộng dồn:** 10–20 px mờ tương đương 4–9 ô, nên mã không thể giải được bằng bất kỳ phần mềm nào. Riêng việc khóa exposure thấp đã quan trọng hơn mọi cải tiến thuật toán (xem mục 4).

### Gaps
- Không đọc được ISO/IEC 15415 hay ISO/IEC 15416 (tài liệu trả phí). Cũng không lấy được hướng dẫn PPM chính thức cho mã 2D của Cognex, Keyence hay Zebra. Con số "3–5 PPM" hay gặp trong ngành chưa có nguồn chính thức trong ghi chú này.

## 2. Các phương án camera: nhiều camera, line-scan, area-scan độ phân giải cao, ống dài hơn, liquid lens

### Takeaway
Hướng đơn giản và rẻ nhất về phần cứng là chia 1,6 m cho 2–3 camera area-scan, hoặc dùng một camera line-scan 8k có encoder. Cả hai đều cho 5–7 PPM, gấp 2–3 lần hiện tại. Line-scan 8k có giá niêm yết khoảng 2.200 € cho thân máy, nhưng cần thêm đèn vạch, ống kính khổ lớn và có thể cả frame grabber.

### Cited Findings
- **Line-scan và encoder:** mỗi xung encoder kích một dòng ảnh. Nếu cần 5 px/mm thì encoder phải ra 5 xung/mm băng; tốc độ băng phải đo chính xác để ảnh không méo — [Eureka Magazine, encoder cho line-scan](https://eurekamagazine.co.uk/content/technology-spotlights/machine-vision-system-components-and-operation-encoder-resolution-for-line-scan-cameras).
- **Line-scan đọc mã logistics:** Basler có ví dụ camera line-scan đặt giữa hai băng, khe chỉ 0,2 mm, khoảng làm việc 480 mm, đọc mã ở đáy kiện hàng — [Basler, code scanning/OCR](https://www.baslerweb.com/en-in/use-cases/code-scanning-ocr/).
- **Datalogic AV7000:** đầu đọc line-scan 8.000 px phủ băng tới 1.200 mm; bản 12.000 px phủ tới 1.600 mm "trong một lần chụp", đọc mã mật độ cao tới 6 mil (≈0,15 mm), có autofocus và đèn xung PLS. Hướng tới phân loại bưu kiện — [Datalogic AV7000](https://www.datalogic.com/eng/products/industrial-automation/fixed-industrial-barcode-readers/av7000-pd-709.html). Trang không ghi tốc độ băng và giá.
- **Giá line-scan Basler racer 2 r2L8192-80cc (8k):** shop Basler ghi giá niêm yết net 2.159 €, giao khoảng 4 tuần; đại lý Mỹ ghi 2.375 USD. Frame grabber CXP-12 khoảng 1.589 €; cáp I/O 10 m khoảng 62 € — [Basler shop](https://www.baslerweb.com/en/shop/r2L8192-80cc/); [Machine Vision Store](https://machinevisionstore.com/catalog/details/35441). Có bản GigE 4k là r2L4096-14gc — [Basler shop](https://www.baslerweb.com/en-us/shop/r2l4096-14gc/).
- **Line-scan dải cao:** từ 4k (172 kHz, 10GigE) tới 16k (400 kHz, 100GigE) — [Emergent Vision](https://emergentvisiontec.com/applications/inspection-and-automation/warehouse-automation/). Basler cũng ra dòng CXP-12 8k và 16k từ năm 2024 — [edge-ai-vision](https://www.edge-ai-vision.com/2024/07/basler-presents-new-cxp-12-line-scan-cameras-with-8k-and-16k-resolution/).

### Inferences

**Line-scan 8k phủ khoảng 1,8 m (dư 0,1 m mỗi bên):**
- Độ phân giải 0,22 mm/px, tương đương ~7 PPM với ô 1,6 mm. Line-scan 4k cho 0,44 mm/px, ~3,6 PPM, chỉ vừa đủ.
- Theo chiều băng chạy, độ phân giải đặt bằng encoder, ví dụ 0,22 mm/dòng. Ở 100 mm/s chỉ cần khoảng 455 dòng/s, rất thấp so với khả năng 80 kHz của camera.
- Exposure mỗi dòng có thể tới khoảng 2 ms mà không mờ theo chiều chạy, nên đèn vạch liên tục là đủ, không cần strobe.
- Ảnh tạo ra liền mạch, mỗi tem xuất hiện đúng một lần, nên không cần ghép frame hay theo dõi lượt. Khi đó có thể bỏ phần lớn tracker và pipeline nhiều frame trong code hiện tại.
- Khối lượng xử lý chỉ khoảng 8192 × 455 ≈ 3,7 Mpx/s, nhẹ hơn luồng 8 MP hiện tại ở chế độ toàn khung.
- Rủi ro: con lăn trượt hoặc kính trượt trên con lăn làm ảnh méo nếu encoder gắn vào con lăn. Có thể dùng encoder bánh lăn tì lên kính, hoặc chấp nhận sai số nhỏ vì QR chịu được méo nhẹ.
- Ống kính cho cảm biến line-scan 8k thường dài hơn khoảng 57 mm (ngàm M72/M58). Nếu phủ 1,8 m ở cao 1 m thì cần góc mở rất rộng; thực tế có thể phải nâng camera lên khoảng 2–3 m. Đây là suy luận, chưa có giá ống kính.

**2–3 camera area-scan đặt cạnh nhau:**
- Ví dụ 2 × Basler 8 MP (2856 px), mỗi camera phủ khoảng 0,85 m, chồng lấn ≥ 60 mm (lớn hơn đường chéo tem ≈ 51 mm). Kết quả khoảng 0,30 mm/px, ~5,3 PPM, với ống khoảng 8 mm ở cao 1 m.
- Hoặc 3 × camera 5 MP (2448 px), mỗi camera phủ khoảng 0,58 m: ~0,24 mm/px, ~6,7 PPM.
- Với 100 mm/s và vùng đọc dài 0,6 m, mỗi camera chỉ cần dải ROI khoảng 150–200 mm dọc băng ở ~5–10 fps. Tải CPU vì vậy tương đương hoặc thấp hơn hiện tại.
- Phương án này giữ nguyên toàn bộ phần mềm hiện có, chỉ cần chạy nhiều luồng camera và gộp kết quả trùng (app `main_dual.py` đã có cơ chế gộp cùng mã trong 30 giây).

**Một camera area-scan 20–25 MP (~5.000–5.500 px ngang):**
- Cho khoảng 0,29–0,32 mm/px, ~5 PPM, một thiết bị duy nhất.
- Nhược điểm: băng thông và CPU tăng 2,5–3 lần, cảm biến lớn cần ống kính đắt, độ sâu trường ảnh giảm.
- Không tìm được giá có nguồn cho phương án này.

**Liquid lens / autofocus:** không cần thiết. Kính phẳng trên con lăn nên khoảng cách cố định; khác biệt chỉ là độ dày kính, vài mm tới khoảng 20 mm, nằm trong độ sâu trường ảnh khi khép khẩu f/5.6–f/8. Đây là suy luận.

### Gaps
- Không có giá có nguồn cho camera area-scan 20–65 MP, ống kính line-scan khổ lớn, đèn vạch line-scan dài 1,8 m, encoder.
- Không kiểm chứng được line-scan Basler GigE 8k cụ thể có chạy trực tiếp vào PC không cần frame grabber hay không.

## 3. Đầu đọc mã công nghiệp gắn cố định góc rộng và hệ "tunnel" logistics

### Takeaway
Các đầu đọc góc rộng 9–17 MP (Cognex DataMan 380/580, Keyence SR-5000, SICK Lector85x, Datalogic AV7000) giải quyết đúng loại bài toán này trong logistics: băng rộng, mã bất kỳ hướng nào, tốc độ tới 3,5 m/s. Với 1,6 m thường cần 2 đầu (Lector85x tối đa khoảng 800 mm mỗi đầu), hoặc 1 đầu line-scan 12k (AV7000). Giá đều là báo giá riêng; nhiều khả năng đắt hơn tự tích hợp camera, nhưng có sẵn đèn xung, autofocus và thuật toán đã được kiểm chứng.

### Cited Findings
- **Cognex DataMan 580:** cảm biến 9 MP, quảng cáo "phủ băng rộng". Một đầu chính gom dữ liệu từ các đầu phụ để mở rộng FOV; dùng trong Modular Vision Tunnel cho đọc 5–6 mặt — [Control.com](https://control.com/news/cognex-revamps-vision-solutions-to-promote-large-area-scanning-on-factory-floor/); [vision-systems.com](https://www.vision-systems.com/cameras-accessories/article/14289908/code-reading-tool-for-logistics-operations). Bảng FOV theo ống 16/25/35 mm nằm trong DM580 Quick Reference, nhưng không tải được vì file quá lớn — [Cognex docs](https://docs.cognex.com/dmst_2421/EN/DM580_Quick_Reference.pdf).
- **Cognex DataMan 380:** giá "theo báo giá" (các mẫu DM3808/3812/3816). Một tin rao eBay 861 USD là của DM374, không phải DM380 — [Metoree](https://us.metoree.com/products/56099/); [eBay](https://www.ebay.com/p/4048915824).
- **Keyence SR-5000:** bản cơ sở 2448×2048 (5 MP), autofocus, 48 LED trắng. Bản WCL được ghi 4096×2160 (8,9 MP); một bảng khác ghi 5456×3076 (16,8 MP) mà không rõ thuộc mẫu nào. Keyence quảng cáo "FOV siêu rộng", một đầu thay nhiều đầu đọc — [Keyence SR-5000](https://www.keyence.com/products/vision/barcode/sr-5000/models/sr-5000); [SR-5000WCL](https://www.keyence.com/products/barcode/barcode-readers/sr-5000/models/sr-5000wcl/); [ví dụ ứng dụng](https://www.keyence.com/solutions/application-selecting/?case_id=1359). Không có số FOV cụ thể; các khẳng định "tốt nhất phân khúc" là marketing.
- **SICK Lector85x:** 12 MP (4096×3008 hoặc 6048×2048 tùy biến thể), còn có bản 9 và 5 MP. Đọc ở băng tới 3,5 m/s, độ rộng trường đọc tới khoảng 800 mm, khoảng làm việc 500–2.400 hoặc 500–3.000 mm. Tần số 15 Hz ở 12 MP (có nguồn ghi tới 30 Hz). Mã nhỏ nhất 0,1 mm, 32 LED đỏ tích hợp, dynamic focus, theo dõi 3D gán mã cho vật — [SICK flyer](https://cdn.sick.com/media/docs/8/08/608/flyer_lector_identification_system_en_im0102608.pdf); [SICK product overview](https://www.sick.com/media/productoverview/0/70/570/productoverview_Lector85x_g568570_en.pdf); [datasheet V2D8512R](https://res.cloudinary.com/sonepar-fr/raw/upload/s--eINA2krH--/v1/documents/67/V2D8512R-1MCXXXAL0SXXXX_1123615_fr.pdf); [baltdevgrupp](https://baltdevgrupp.ee/?p=7115145). Các nguồn mâu thuẫn nhau về độ phân giải và tần số; số liệu khác nhau theo biến thể.
- **Datalogic AV7000 12K:** phủ 1.600 mm trong một lần chụp (xem mục 2) — [Datalogic](https://www.datalogic.com/eng/products/industrial-automation/fixed-industrial-barcode-readers/av7000-pd-709.html).
- **Cấu trúc hệ logistics điển hình:** photo-eye phát hiện vật, đầu đọc đọc mã, encoder theo dõi vị trí — [industrialmonitordirect](https://industrialmonitordirect.com/blogs/knowledgebase/industrial-barcode-scanner-edge-trigger-with-photoeye-integration) (blog, độ tin cậy trung bình).

### Inferences
- Thông số "mã nhỏ nhất 0,1 mm" của Lector85x chỉ đạt ở khoảng cách gần; ở khoảng cách đủ để phủ 800 mm thì ô tối thiểu lớn hơn nhiều. Ô 1,6 mm của tem này là rất to so với mã logistics thông thường (0,25–0,5 mm), nên đầu đọc 9–12 MP phủ 0,8 m sẽ có khoảng 0,2–0,3 mm/px, tức 5–8 PPM.
- Đầu đọc thương mại giải luôn bài toán mờ (đèn xung tích hợp) và chói (có tùy chọn đèn/ống kính), nhưng phụ thuộc nhà cung cấp và đắt. Người viết ước lượng (không có nguồn) mỗi đầu cỡ vài nghìn tới hơn 10 nghìn USD, khó đạt yêu cầu "chi phí thấp".
- Tunnel logistics (5–6 mặt) là quá mức cần thiết: tem luôn ở mặt trên kính phẳng.

### Gaps
- Không có giá công khai của DM380/DM580, SR-5000, Lector85x, AV7000, Zebra FS70/VS70, Datalogic Matrix 320/450N. Không tìm hiểu được Zebra và Datalogic Matrix do hết lượt tìm kiếm.
- Không có bảng FOV/PPM chính thức của DM580 vì PDF quá lớn để tải.

## 4. Chiếu sáng: strobe đồng bộ để triệt mờ, polarizer chống chói kính, dome/dark-field

### Takeaway
Mờ chuyển động là yếu tố số 1. Ở 100 mm/s, exposure phải ≤ 3–4 ms để mờ ≤ ¼ ô (0,4 mm); strobe LED 0,2–1 ms gần như xóa hết mờ (0,02–0,1 mm). Vì tem giấy tán xạ còn kính phản xạ gương, phân cực chéo (polarizer trên đèn và analyzer vuông góc trên ống kính) là kỹ thuật kinh điển để xóa ảnh đèn trần phản trên kính.

### Cited Findings
- **Công thức mờ:** vệt mờ (px) = tốc độ × exposure × (số px / FOV). Ví dụ: băng 800 ft/phút, FOV 2 ft, camera 3 MP cần exposure 73 µs để mờ 1 px — [Quality Magazine](https://www.qualitymag.com/articles/98039-machine-vision-technologies-adapt-for-higher-speeds-evolving-needs).
- **Smart Vision Lights "Dual OverDrive":** xung 1 ms ở dòng gấp 10 lần chế độ liên tục ("deca"), quá 1 ms thì về OverDrive thường. Ví dụ ứng dụng lon bia: exposure giảm từ 40–50 µs xuống 12 µs, không tăng gain, hết mờ, năng suất từ khoảng 4.000 lên gần 6.000 lon/phút. Sườn xung chậm gây thêm mờ — [Photonics.com](https://www.photonics.com/Articles/Machine-Vision-Lights-Boost-Canning-Line/a70108); [vision-systems.com](https://vision-systems.com/cameras-accessories/news/55310562/innovation-in-led-lighting-improves-image-quality-for-objects-in-motion). Số liệu do nhà cung cấp đưa ra (case study).
- **Phân cực chéo:** một polarizer trên đèn, một trên ống kính đặt vuông góc, chặn phản xạ gương. Ánh sáng phản xạ từ bề mặt bóng bị phân cực phần lớn, trong khi ánh sáng tán xạ từ nhãn vẫn tới được camera — [Epic Systems](https://epicsysinc.com/blog/eliminating-glare-with-polarization/); [1stVision](https://www.1stvision.com/machine-vision-solutions/?p=5197); [vision-systems.com](https://www.vision-systems.com/home/article/14068739/uses-for-polarization-imaging-in-machine-and-computer-vision).
- **Đèn lệch trục:** đèn vòng đồng trục dễ tạo điểm chói trên mã bán phản xạ; dời đèn lệch trục thì điểm chói ra khỏi tầm nhìn camera. Nên thử cách này trước khi thêm polarizer — [1stVision](https://www.1stvision.com/machine-vision-solutions/?p=5197). Có camera phân cực (Sony Polarsens) cho trường hợp chói nhiều góc — [The Imaging Source](https://www.theimagingsource.com/en-us/resource/glossary/polarization-cameras-in-machine-vision/).

### Inferences

**Ngân sách exposure ở v = 100 mm/s** (mờ = v × t):

| Exposure | Mờ (mm) | px @0,673 | px @0,30 | phần ô 1,6 mm |
|---|---|---|---|---|
| 12,9 ms (mặc định demo) | 1,29 | 1,9 | 4,3 | 0,8 ô (nặng) |
| 4 ms | 0,40 | 0,6 | 1,3 | 0,25 ô |
| 2 ms | 0,20 | 0,3 | 0,7 | 0,13 ô |
| 1 ms (strobe) | 0,10 | 0,15 | 0,3 | ~0 |
| 0,2 ms (strobe) | 0,02 | — | — | 0 |

- Mờ 10–20 px trong video hiện trường tương ứng exposure khoảng 67–135 ms, do AE bật trong môi trường thiếu sáng. Chỉ cần khóa exposure ≤ 4 ms là đã loại phần lớn mờ, nhưng ảnh sẽ tối hơn khoảng 3–30 lần. Vì vậy cần thêm đèn, hoặc tăng gain nhưng nhiễu sẽ tăng.
- **Đề xuất cụ thể:** đèn bar LED trắng/đỏ dài khoảng 1,8 m đặt hai bên, chạy chế độ strobe OverDrive kích theo tín hiệu exposure out của camera (Basler có line I/O). Exposure 0,5–1 ms. Ánh sáng ngắn và mạnh còn có lợi phụ là lấn át đèn trần, giảm tương đối độ chói do phản xạ đèn trần.
- **Polarizer:** mỗi lớp lọc làm mất khoảng một nửa ánh sáng hoặc hơn (suy luận dựa trên kiến thức chung về polarizer tuyến tính, chưa có nguồn). Dùng phân cực chéo kết hợp exposure ngắn càng cần đèn mạnh.
- **Ánh sáng trần và mái che:** lắp tấm che (shroud hoặc rèm đen) phía trên vùng đọc là cách rẻ nhất để loại phản xạ đèn trần. Chụp nghiêng khoảng 10–20° so với pháp tuyến kính cũng giúp, vì camera thẳng đứng nhìn đúng ảnh phản xạ của trần ngay trên đầu. Đây là suy luận.
- **Line-scan:** đèn vạch liên tục và kính phẳng cho phép đặt camera và đèn theo hình học lệch gương (đèn và camera không đối xứng qua pháp tuyến), đơn giản hơn so với area-scan.

### Gaps
- Không có giá có nguồn cho đèn strobe Smart Vision Lights, CCS hay polarizer khổ lớn.
- Không có dữ liệu đo về tỉ lệ phân cực của phản xạ đèn trần trên kính float ở góc gần vuông góc. Lưu ý vật lý: ở góc tới gần 0°, phản xạ gương ít bị phân cực hơn so với góc Brewster (~56°), nên polarizer thụ động trên camera mà không có đèn phân cực riêng sẽ kém hiệu quả với đèn trần. Đây là suy luận, cần thử thực tế.

## 5. Thay đổi cơ khí / quy trình: dẫn tem về vị trí cố định, photo-eye, dừng/chậm, đọc tay dự phòng

### Takeaway
Đây là đòn bẩy mạnh nhất về chi phí. Nếu quy trình dán tem bắt buộc tem nằm ở vị trí cố định (ví dụ góc trước-trái, cách mép 50–100 mm) và xoay theo hướng cố định, thì FOV chỉ cần khoảng 200–300 mm. Khi đó một đầu đọc rẻ hoặc camera 2–5 MP cho hơn 10 PPM, gần như chắc chắn đạt 100%.

### Cited Findings
- **Mẫu photo-eye + đầu đọc + encoder** là chuẩn trong logistics: phát hiện vật, đọc, gán mã theo vị trí — [industrialmonitordirect](https://industrialmonitordirect.com/blogs/knowledgebase/industrial-barcode-scanner-edge-trigger-with-photoeye-integration).
- **Ngành kính đã chuẩn hóa vị trí mã:** HEGLA khuyến nghị đánh dấu tấm kính gốc trước khi cắt; mã có thể đặt ở vùng nhìn thấy hoặc vùng khuất — [HEGLA](https://www.hegla.com/en/news/news-hegla/laser-marking-the-smooth-permanent-tracking-method/). Patent Saint-Gobain mô tả đọc mã ở các giai đoạn sản xuất khác nhau, kể cả khi kính đã xếp chồng, đọc từ mặt chính hoặc từ cạnh — [US10696587B2](https://patents.google.com/patent/US10696587B2/pl); [EP3105706B1](https://data.epo.org/gpi/EP3105706B1).
- **Đọc qua khe giữa hai băng:** Basler dùng line-scan đọc mã qua khe hẹp 0,2 mm, khoảng làm việc 480 mm — [Basler](https://www.baslerweb.com/en-in/use-cases/code-scanning-ocr/).

### Inferences
- **Phương án A, vị trí tem cố định:** quy định dán tem trong vùng 150 × 150 mm ở một góc xác định, có gá hoặc mẫu dán. Khi đó chỉ cần 1 camera khoảng 2–5 MP nhìn vùng khoảng 250 × 250 mm cho 0,1–0,15 mm/px, tức 10–15 PPM, hoặc một đầu đọc góc rộng giá trung bình (Keyence SR-X300W có FOV 267 × 166 mm ở 300 mm). Nếu kính chạy lệch ngang, dùng thanh dẫn biên (side guide) hoặc chọn mép tham chiếu cố định của băng.
- **Phương án B, giới hạn theo một trục:** nếu không ép được vị trí ngang nhưng ép được tem nằm gần mép trước (ví dụ ≤ 150 mm), thì vẫn phải phủ 1,6 m ngang nhưng chỉ ở dải hẹp dọc băng. Line-scan hoặc dải ROI rất hợp với trường hợp này.
- **Photo-eye kích chụp:** cảm biến phát hiện mép trước kính, kích strobe và chụp đúng lúc tem đi qua tâm FOV, có thể chụp 2–3 frame để dự phòng. Cách này bỏ được YOLO chạy liên tục, giảm tải CPU và loại các lượt "ma".
- **Chậm hoặc dừng:** 100 mm/s đã chậm. Dừng băng tốn thời gian chu kỳ; dữ liệu hiện tại cho thấy tem đứng yên đọc 100%, nhưng có lẽ không cần dừng nếu đã có strobe.
- **Dự phòng đọc tay:** lượt không đọc được thì báo động, người vận hành quét bằng máy quét tay hoặc nhập số in bên dưới QR. Cách này biến yêu cầu "100%" thành "100% được xử lý" và chặn kính không định danh đi tiếp. Đây là đề xuất, chưa có nguồn case study.
- **Đọc từ dưới qua kính:** nếu tem dán mặt dưới, hoặc mặt trên nhưng đọc xuyên kính trong, có thể đặt camera giữa các con lăn nhìn lên. Lợi ích là tránh đèn trần hoàn toàn. Rủi ro là bụi, mảnh kính và con lăn che. Đây là suy luận.

### Gaps
- Chưa biết quy trình dán tem tại nhà máy có thể bắt buộc được vị trí và hướng hay không (cần hỏi khách hàng).
- Không tìm được case study cụ thể về đọc tem giấy trên kính ở dây chuyền gia công kính phẳng.

## 6. Đổi định danh: tem/QR lớn hơn, Data Matrix, cấu hình in, RFID, khắc laser, OCR dự phòng

### Takeaway
Rẻ nhất là in lại mã cho tối ưu: bỏ `#` để nội dung toàn số, khi đó vừa QR V1-Q (ECC 25%), hoặc tăng cỡ tem lên 50 mm. Ngành kính dùng nhiều Data Matrix/QR khắc laser lên kính (LiSEC LMS, HEGLA boraident). RFID trên kính có rủi ro vì kính làm nhiễu RF, và chưa thấy dùng phổ biến cho từng tấm.

### Cited Findings
- **Kích thước tối thiểu:** Data Matrix ECC200 nhỏ nhất 10×10 ô, QR nhỏ nhất 21×21 ô. Data Matrix cần vùng trống 1 ô, QR cần 4 ô. Dung lượng tối đa: Data Matrix 3.116 số, QR 7.089 số — [qr-code-generator.com](https://www.qr-code-generator.com/blog/data-matrix-vs-qr-codes); [Pryor](https://www.pryormarking.com/?p=23740). Một blog tự mâu thuẫn về việc Data Matrix "nhỏ hơn 40%", không dùng con số này.
- **LiSEC LMS (Laser Marking System):** khắc vĩnh viễn mã vạch, Data Matrix, QR, chữ số, số seri, dấu TSG lên kính — [LiSEC](https://www.lisec.com/solutions/individual-machines/detail/laser-processing/lms-a-laser-marking-system).
- **HEGLA boraident ES-Guard:** in laser bằng băng chuyển (transfer tape), mặt kính không bị tổn hại như khắc CO2. Mã là QR hoặc Data Matrix, đọc tự động ở mọi công đoạn, làm được trên kính có phủ. Khuyến nghị đánh dấu trước khi cắt — [HEGLA](https://www.hegla.com/en/news/news-hegla/laser-marking-the-smooth-permanent-tracking-method/); [Glass Bulletin](https://glassbulletin.com/?p=5654). Với mã trên profile, khuyến nghị tối thiểu 10×10 mm để đọc lâu dài — [glassonweb](https://www.glassonweb.com/news/clearly-marking-knowledge-profiles-hegla-boraident).
- **RFID:** một số loại kính, giống kim loại, gây nhiễu thẻ RF — [USPTO, on-metal RFID patent](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/12400100). Thẻ "glass tag" của HID là LF/HF bọc thủy tinh, không phải nhãn UHF cho kính tấm — [HID](https://www.hidglobal.com/products/glass-tags-industry-and-logistics). Không tìm thấy tài liệu dùng RFID cho từng tấm kính trong gia công.

### Inferences

**Dung lượng QR V1** (số data codeword theo bảng ISO/IEC 18004 mà người viết nhớ, cần đối chiếu tiêu chuẩn): L 19, M 16, Q 13, H 9 byte.
- `#` không thuộc bộ ký tự alphanumeric của QR, nên phải mã hóa nhiều đoạn: số + byte + số.
- **12 số `#` 12 số:** 54 + 20 + 54 = 128 bit = 16 byte, vừa khít V1-M. Khớp với "V1 mức M tách đoạn" trong README.
- **14 số `#` 12 số (như đề bài nói):** 61 + 20 + 54 = 135 bit, quá 128 bit của V1-M. Mã này phải là V1-L (ECC chỉ khoảng 7%) hoặc V2-M (25 ô, ô nhỏ hơn 16%). Cần kiểm tra tem thật đang in version và mức ECC nào.
- **Bỏ `#`, toàn số:**
  - 24 số: 4 + 10 + 80 = 94 bit → 12 byte, vừa V1-Q.
  - 26 số: 101 bit → 13 byte, vừa V1-Q.
  - V1-H chỉ chứa khoảng 17 số, nên không dùng được.
  - Chuyển từ M lên Q tăng khả năng sửa lỗi từ khoảng 15% lên 25% mà kích thước ô không đổi. Rất có ích khi ảnh mờ hoặc chói cục bộ.

**Data Matrix:** suy luận từ bảng ISO/IEC 16022 theo trí nhớ, cần đối chiếu. ECC200 nén 2 số vào 1 codeword.
- 24 số → 12 codeword, vừa 16×16. 24 số + `#` → 13 codeword → 18×18.
- Trên tem 36 mm, tính cả vùng trống 1 ô:
  - DM 16×16: 36/18 ≈ 2,0 mm/ô, to hơn khoảng 25% so với QR V1 ~1,6 mm.
  - DM 18×18: ≈ 1,8 mm/ô, to hơn khoảng 12%.
- Nghĩa là PPM tăng tương ứng với cùng camera. Tuy nhiên Data Matrix hầu như không có trong pipeline hiện tại (WeChat là bộ giải QR); zxing đọc được Data Matrix.

**Tem lớn hơn:** tem 50 mm thay 36 mm làm ô to hơn khoảng 39%, PPM từ 2,4 lên khoảng 3,3 ngay với camera hiện tại. Tem 60 mm cho khoảng 4 PPM. Chi phí tem gần như không đổi. Đây là cách rẻ nhất để vượt ngưỡng 3–3,5 PPM.

**Dải chữ số lớn để OCR dự phòng:** in dòng số cao khoảng 5–8 mm cạnh QR, kèm checksum (ví dụ chữ số kiểm tra mod-10/11 trong 26 số) để loại đọc sai. Cũng nên bật lọc `^\d{12}#\d{12}$` (hoặc 14#12) cùng checksum để bảo đảm "không đọc sai"; CLAUDE.md cho biết code hiện vẫn chưa lọc (`code_pattern=None`).

**Khắc laser trực tiếp lên kính:** đây là cách chuẩn của ngành (LiSEC, HEGLA) cho định danh vĩnh viễn. Nhưng mã khắc trên kính trong có độ tương phản thấp, phải đọc bằng đèn dark-field hoặc đèn nền, và thường chỉ khoảng 10–20 mm, nên không giải quyết được bài toán đọc trên toàn bề rộng 1,6 m. Hệ thống thật đặt mã ở vị trí cố định do máy quyết định, đầu đọc đặt đúng chỗ đó.

### Gaps
- Chưa xác minh trực tiếp bảng dung lượng QR/DM từ ISO/IEC 18004 và 16022; các con số trên dựa vào kiến thức nền và cần kiểm chứng bằng thư viện sinh mã (ví dụ `segno`, `pylibdmtx`).
- Không có dữ liệu về DotCode trong ngữ cảnh này.
- Không có giá máy khắc laser LiSEC LMS / HEGLA ES-Guard.

## 7. Dây chuyền kính (LiSEC, HEGLA, Bystronic glass, Glaston, Grenzebach) theo dõi tấm kính thế nào?

### Takeaway
Ngành kính phẳng chuyển dần sang ID ảo sinh từ kế hoạch sản xuất, khắc hoặc in laser lên tấm kính gốc (QR/Data Matrix) trước khi cắt, rồi đọc ở các trạm. Mã luôn ở vị trí do máy quyết định, không phải "bất kỳ đâu trên 1,6 m". Không tìm được thông tin cụ thể về Bystronic, Glaston, Grenzebach.

### Cited Findings
- LiSEC có máy LMS khắc mã (barcode/DM/QR/chữ số/TSG) lên kính — [LiSEC LMS](https://www.lisec.com/solutions/individual-machines/detail/laser-processing/lms-a-laser-marking-system); [LiSEC Laser Processing (issuu)](https://issuu.com/lisec/docs/lisec_laser_processing).
- HEGLA boraident: một ID ảo sinh ở khâu lập kế hoạch sản xuất được in laser lên tấm kính trước khi cắt; mã đi theo sản phẩm suốt vòng đời và được hệ thống tracking đọc tự động ở mọi công đoạn — [HEGLA](https://www.hegla.com/en/news/news-hegla/laser-marking-the-smooth-permanent-tracking-method/); [HEGLA GTI 3/2025 (PDF)](https://www.glassonline.com/wp-content/uploads/2025/06/028_029_HEGLA-GTI-3_2025.pdf).
- VDMA bàn về track & trace và blockchain trong ngành kính; các tấm được gắn mã QR hoặc Data Matrix máy đọc được, thường kèm logo, trước khi cắt — [Glass International / VDMA](https://www.glass-international.com/features/why-use-blockchain-and-track-trace-in-the-glass-industry); [glasstec](https://www.glasstec-online.com/en/Media_News/Press/Press_material/Professional_articles/Specialist_Article_VDMA_Why_use_blockchain_and_track_trace_in_the_glass_industry).
- Saint-Gobain có patent về mã khắc trong kính ở các độ sâu khác nhau, đọc từ mặt hoặc cạnh, ở nhiều giai đoạn kể cả khi xếp chồng — [US10696587B2](https://patents.google.com/patent/US10696587B2/pl); [method for reading, US 2016/0371523](https://uspto.report/patent/app/20160371523).
- Ngành kính rỗng (chai lọ) có giải pháp traceability riêng của Emhart — [Emhart Glass](https://emhartglass.com/Traceability) (khác ngành kính phẳng).

### Inferences
- Thực tế ngành cho thấy nhà máy kính nghiêm túc thường không đọc tem dán ngẫu nhiên trên toàn bề rộng mà kiểm soát vị trí mã ngay từ khâu tạo mã. Nếu khách chưa có máy khắc laser, phiên bản rẻ của cách này là chuẩn hóa vị trí dán tem (mục 5).
- **Xếp hạng chi phí/hiệu quả cho bài toán này** (suy luận tổng hợp):
  1. Khóa exposure ≤ 2–4 ms, thêm đèn strobe và tấm che đèn trần (vài trăm tới khoảng 1.500 USD, chưa có nguồn giá). Bắt buộc với mọi phương án.
  2. Tăng cỡ tem lên 50–60 mm hoặc in V1-Q toàn số kèm checksum (gần như 0 đồng), cộng lọc regex/checksum trong code.
  3. Chuẩn hóa vị trí dán tem để dùng FOV nhỏ (0 đồng phần cứng, cần thay đổi quy trình).
  4. 2 camera area-scan (thêm 1 camera Basler và ống 8 mm) hoặc 1 line-scan 8k + encoder (thân máy khoảng 2.200 € + đèn vạch + ống kính + có thể frame grabber khoảng 1.600 €).
  5. Đầu đọc thương mại 2 × 9–12 MP hoặc AV7000 12K: báo giá, đắt nhất nhưng ít rủi ro tích hợp.

### Gaps
- Không tìm được tài liệu về hệ đọc mã của Bystronic glass, Glaston, Grenzebach, cũng như đầu đọc cụ thể (hãng, mẫu) mà LiSEC/HEGLA dùng để đọc mã trên dây chuyền.
- Không tìm được case study công khai về đọc tem giấy dán ngẫu nhiên trên kính ở băng rộng 1,6 m với số liệu tỉ lệ đọc.
