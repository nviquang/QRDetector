# Khóa ảnh chụp trước, tinh gọn thuật toán sau

> **Cấu hình cũ (trước 18/11/2026).** Tài liệu này lập theo thông số đã thay thế (tem 25/36 mm, camera cao 1 m, 0,673 mm/px, băng 100 mm/s, nội dung 12#12 hoặc version 1, một camera, máy CPU). Ràng buộc hiện hành: mục "Bài toán và ràng buộc" trong `README.md`. Kỹ thuật và tài liệu tham khảo vẫn dùng được, nhưng số px/ô và mọi đề xuất đổi tem, nội dung, version/mức sửa lỗi, camera, ống kính, line-scan, đầu đọc thương mại hay vị trí dán tem không còn áp dụng.
> **Đã bị thay thế** bởi `reports/Đọc QR hai camera buồng tối.md`. Phần 2 và Phần 3 của báo cáo này dựa trên giả định được đổi phần cứng/tem, sai với ràng buộc hiện hành.

Vì sao hệ thống chưa đọc được tem khi băng chạy? Câu trả lời ngắn: ảnh chụp đang hỏng trước khi thuật toán kịp làm gì. Thuật toán không phải chỗ yếu. Trên dữ liệu hiện trường 13/11/2026, tem đứng yên đọc 100% (2/2 lượt, 112/112 phát hiện). Tem chạy thì 0/4 lượt, kể cả khi đã thêm cả B lẫn C và quét vệt mờ tới 18 px **[nội bộ, đo]**. Vệt mờ dọc ước lượng bằng mắt là 10–20 px, trong khi một ô QR chỉ khoảng 2,3 px. Một vệt như vậy phủ 4–9 ô, nên không bộ giải nào khôi phục nổi. Muốn có vệt ≤2 px để cascade hiện có tự đọc được thì exposure phải ≤ khoảng 3 ms. Thế nhưng code vẫn mặc định 12,9 ms, và lúc quay nhiều khả năng AE đang bật. Vì vậy việc rẻ nhất và mạnh nhất có hai phần. Phần một: khóa exposure 3 ms và thêm đèn đủ mạnh, lý tưởng là strobe đồng bộ, cộng tấm che đèn trần. Phần hai: quay lại một bộ lượt chạy có đáp án rồi mới quyết định phần mềm cần đi xa đến đâu. Về phần mềm, cả ba tầng đều có dư địa tối ưu cho máy chỉ có CPU:
- **Phát hiện:** chạy trên dải vào ở độ phân giải gốc thay cho YOLO toàn khung (980 ms/khung CPU), có thể kèm bộ định vị cổ điển.
- **PassDecoder:** chuyển từ gộp pixel sang gộp xác suất từng ô.
- **B/C:** chỗ yếu là σ cố định hoặc lưới σ thô. Bản thân bộ giải không phải chỗ yếu, và thời gian chạy có thể giảm nhiều lần bằng tối ưu cấu trúc.

Thoát khỏi khung "camera góc rộng + phần mềm nặng", có những đòn bẩy lớn hơn mọi cải tiến thuật toán: tem lớn hơn, mã toàn số ở mức sửa lỗi Q, cố định vị trí dán tem, hai camera ống 8 mm hoặc line-scan, và đọc tay dự phòng. Còn hai điều phải xác nhận trước mọi việc. Thứ nhất, **định dạng nội dung chưa chốt**: mã thật đọc được là 14 số `#` 12 số và tem có vẻ là version 2. Điều này trái với "12#12, V1-M" trong README, và trái với giả định của một số ghi chú nghiên cứu. Thứ hai, **chưa có lớp lọc nội dung và vị trí nào** chặn đọc sai.

## Quy ước nguồn số liệu và các điểm đính chính

Mỗi con số trong báo cáo được gắn một trong bốn nhãn. **[nội bộ, đo]** là số nhóm tự đo trên dữ liệu thật hoặc mô phỏng, lấy từ code, `CLAUDE.md` và các báo cáo trong `reports/`. **[tài liệu]** là số từ bài báo hoặc tài liệu kỹ thuật, có kèm liên kết. **[nhà cung cấp]** là số marketing hoặc benchmark do chính hãng công bố, chưa ai kiểm chứng độc lập. **[ước lượng]** là phép tính hoặc suy luận của các ghi chú nghiên cứu, chưa đo.

Có ba đính chính so với các ghi chú nghiên cứu.

**Định dạng nội dung.** Ghi chú 02 viết rằng "định dạng đã chốt" là `^\d{12}#\d{12}$` và khuyên bật regex đó. Ghi chú 03 khuyên bỏ giả thuyết V3 "vì tem đã chốt là V1". Cả hai đều dựa trên README cũ. EDA hiện trường đọc được ba mã thật dạng **14 số `#` 12 số** (ví dụ `18000090001000#000000001612`). QR trên tem rộng khoảng 25 ô, tức version 2 **[nội bộ, đo]**.

Tính dung lượng như sau (bảng dung lượng của [Thonky](https://www.thonky.com/qr-code-tutorial/character-capacities) và [độ dài trường đếm](https://www.thonky.com/qr-code-tutorial/data-encoding)):

| Nội dung | Số bit | Version/mức sửa lỗi vừa |
|---|---|---|
| 12#12, tách ba đoạn | 128 | Vừa khít V1-M |
| 14#12, tách ba đoạn | 135 | Không vừa V1-M; phải là V1-L (sửa lỗi ~7%) hoặc V2-M |
| 14#12, byte mode | Lớn hơn | Có thể là V2-L |

Báo cáo trước giả định trường hợp cuối cùng (byte mode, V2-L).

Hệ quả có hai mặt. Nếu bật `code_pattern` theo định dạng cũ thì **mọi mã thật bị loại**. Nếu bỏ V2 khỏi B để tăng tốc thì B hỏng toàn bộ. Định dạng, version, mức sửa lỗi và cách tách đoạn phải được chốt bằng cách giải mã tem tĩnh rồi đối chiếu với khách hàng. Chưa chốt xong thì chưa ghim bit nội dung hay dựng từ điển.

**Thời gian tem nằm trong khung.** Ghi chú 01 lo rằng chưa rõ chiều nào là chiều băng chạy. Theo giả định của ghi chú 04, vùng đọc rộng 1,6 m và dài 0,6 m dọc băng. Khi đó tem nằm trong vùng khoảng 6 s ở 100 mm/s, tức khoảng 149 px/s **[ước lượng]**. Nhưng bản ghi 13/11 chỉ được 14–17 fps, khoảng cách giữa hai frame dao động 40–150 ms, và có lúc ngắt 0,3–1,2 s **[nội bộ, đo]**. Số frame thực tế của mỗi tem ít hơn lý thuyết.

**Số "2,2–2,6 px/ô".** Đây là số tính cho QR V1 trên tem 36 mm. EDA đo cạnh QR 55–75 px (trung vị 60) trên khoảng 25 ô, tức **~2,3 px/ô** **[nội bộ, đo]**.

## Phần 1. Từng tầng của pipeline hiện tại

### 1.1 Phát hiện và theo dõi: YOLO toàn khung thu nhỏ mã còn khoảng 1 px/ô

**Hiện trạng.** Bộ phát hiện là YOLOv8-seg `qrdet` "s", imgsz 1280 (dải rộng dùng 1600), chạy tối đa mỗi 400 ms. Mỗi lần mất 980 ms trên CPU và 190 ms trên GTX 1650 **[nội bộ, đo 31/10]**. Giữa hai lần chạy, hệ thống đoán ROI theo vận tốc của từng lượt, mỗi 2 frame. Tracker ghép láng giềng gần nhất theo kiểu tham lam, cổng strict có trần 900 px. Cần 2 lần đọc giống nhau mới báo mã. QR nhỏ khoảng 25 px không bao giờ được phát hiện. Trong 4 video chạy, YOLO chỉ trả đúng một phát hiện mỗi frame, tức tem thứ hai trong khung cũng bị bỏ sót **[nội bộ, đo]**. Phép tính nhanh giải thích vì sao detect vừa đắt vừa mong manh. Khung 2856 px thu về 1280 thì QR 54–60 px chỉ còn khoảng 24–27 px, **xấp xỉ 1 px/ô**. Lúc đó mạng phải nhận ra một "đốm kết cấu", vì không còn thấy finder pattern **[ước lượng]**.

**Tối ưu thuật toán.** Đối tượng cần tìm là **tem trắng 36 mm trên nền băng/kính khá đồng nhất**, không phải QR tùy ý giữa cảnh phức tạp. Ba thay đổi có cơ sở:

- **Thu nhỏ vùng phải detect, không thu nhỏ ảnh.** Chỉ detect trên một dải ở mép vào, rộng khoảng 320 px dọc băng và giữ nguyên độ phân giải gốc. Mỗi tem sẽ nằm trọn trong dải khoảng (320 − 54)/149 ≈ 1,8 s. Detect mỗi 0,5–1 s vẫn thấy mỗi tem ít nhất 2 lần, mà QR vẫn giữ kích thước 54–60 px là cỡ YOLO phát hiện tốt **[ước lượng]**. Sau đó vị trí được dự đoán bằng **một vận tốc băng chung**, thay cho vận tốc riêng của từng lượt, và chỉ cần tái định vị cục bộ trong ROI khoảng 150×150 px. Có thể thêm một lần quét toàn khung thưa, vài giây một lần, để vớt tem bị sót.
- **Bộ định vị cổ điển thay hoặc bổ sung cho YOLO.** Có thể dùng trừ nền, ngưỡng cộng morphology cộng connected components lọc theo diện tích và tỉ lệ cạnh của tem, hoặc bản đồ mật độ cạnh trên cửa sổ khoảng 16×16 px. Chi phí kỳ vọng vài đến vài chục ms trên dải hàng triệu pixel **[ước lượng, phải đo trên `data/field`]**. Cách này còn bắt được tem dán ngược chỉ lộ QR nhỏ, và bắt được tem thứ hai mà YOLO bỏ sót.
- **Tracker dựa trên prior băng chuyền.** Chuyển động gần như tịnh tiến đều, nên Kalman hay ByteTrack không thêm được bao nhiêu so với một vận tốc băng chung. Ý hay nhất của ByteTrack vẫn dùng được ở dạng đơn giản: nhận cả phát hiện độ tin cậy thấp nếu nó khớp vị trí dự đoán. Có vận tốc chung thì có thể thu cổng từ 900 px xuống vài chục px, và **kiểm tra mã đọc được có nằm trong bbox dự đoán không**. Kiểm tra này chặn đúng lỗi đã gặp: C từng đọc nhầm tem bên cạnh **[nội bộ, quan sát]**.

**Tối ưu inference trên CPU.** Phần lợi lớn nhất đến từ việc **giảm số pixel**, không đến từ runtime. Chi phí tích chập gần như tuyến tính theo pixel. Dải 2880×320 (khoảng 0,92 Mpx, độ phân giải gốc) so với 1280² (1,64 Mpx) đã giảm khoảng 1,8 lần. Trên một Intel Core Ultra 7, Ultralytics đo các mức sau ([Ultralytics Academy](https://academy.ultralytics.com/courses/yolo-in-production/openvino-on-cpu)) **[tài liệu, của hãng phần mềm]**:

| Model | PyTorch FP32 | OpenVINO FP32 | OpenVINO INT8 |
|---|---|---|---|
| YOLO26s | 70,9 ms | 36,2 ms | 15,5 ms |
| YOLO26n | 33,2 ms | 13,4 ms | 11,4 ms |

Tức là đổi sang OpenVINO nhanh khoảng 2,3–2,9 lần. INT8 thêm khoảng 2,3 lần với model "s" nhưng gần như không thêm gì với "n". Hiệu chỉnh INT8 bằng 4 ảnh làm mAP rơi 3,2 điểm, nên cần trên 300 ảnh đại diện. Cùng nguồn ghi ONNX Runtime p50 30,0 / p95 46,4 ms, còn OpenVINO p50 22,8 / p95 113,5 ms. OpenVINO nhanh hơn ở trung vị nhưng **đuôi dài hơn** trên CPU dùng chung, nên phải ghim số luồng và tách khỏi tiến trình B/C.

Có ba điểm phải nhớ khi dùng các số này. Đây là YOLO26, không phải YOLOv8-seg. Kết quả về INT8 còn trái chiều: Lenovo/Intel thấy INT8 chỉ có lợi rõ với model lớn trên Xeon 6 ([Lenovo Press LP2345](https://lenovopress.lenovo.com/lp2345-accelerating-real-time-object-detection-yolo-models-intel-xeon-6-openvino)). Và CPU máy hiện trường chưa được xác nhận. Ghi chú 03 giả định Ryzen 5 5500U; nếu đúng là AMD thì phải đo cả ONNX Runtime lẫn OpenVINO.

Gộp ba yếu tố (dải gốc, OpenVINO FP32, rồi INT8) có thể đưa 980 ms xuống khoảng 100–250 ms/lần, chưa tính việc đổi "s" sang "n" **[ước lượng ngoại suy, phải đo bằng `tools/bench_decode.py --band`]**. Ngoài ra, hệ thống chỉ dùng quad thô, không dùng mask. Huấn luyện hoặc xuất một model detect thuần sẽ bỏ được đầu mask. Nếu thêm model WeChat chạy qua OpenCV thì detect có thể bỏ hẳn torch trên máy hiện trường, đồng thời bỏ luôn ràng buộc "import torch trước PyQt5".

Về đổi "s" sang "n": một nghiên cứu năm 2025 đo YOLOv8n đạt 88,95% so với 97,10% của YOLOv8s trên barcode/QR ([arXiv 2511.22937](https://arxiv.org/pdf/2511.22937)) **[tài liệu]**. Chỉ nên đổi sau khi huấn luyện lại trên crop độ phân giải gốc. SAHI (cắt lát) tăng AP vật nhỏ 5–7 điểm nhưng nhân chi phí theo số tile ([arXiv 2202.06934](https://arxiv.org/abs/2202.06934v2)). Với ta, dải vào là một "lát" duy nhất, nên đã có lợi của SAHI mà không phải trả chi phí đó.

**Sản phẩm thực tế làm gì.** Đầu đọc công nghiệp coi định vị là bài toán **cổ điển, rẻ, giới hạn theo kích thước ô**:

- **HALCON** bắt đầu tìm ở tầng kim tự tháp cao nhất mà ô còn tách được, nên giới hạn `module_size_min/max` quyết định trực tiếp tốc độ ([HALCON find_data_code_2d](https://www.mvtec.com/doc/halcon/13/en/find_data_code_2d.html)).
- **Cognex PowerGrid** định vị theo kết cấu ô sáng/tối xen kẽ "từ trong ra", không cần finder ([Automate.org](https://www.automate.org/vision/news/powergrid-technology-for-2d-barcode-reading)) **[nhà cung cấp]**.
- **Dynamsoft** xếp hàng loạt chế độ định vị cổ điển (connected blocks, statistics, scan directly…). Chế độ mạng nơ-ron chỉ được thêm từ bản 11.2.2000, như một lựa chọn thêm ([Dynamsoft localization modes](https://www.dynamsoft.com/barcode-reader/docs/core/parameters/reference/localization-modes.html)).
- **Keyence SR-X** dùng "AI" cho bộ lọc và bộ giải mã khó, không có nguồn nào nói AI dùng để định vị ([Keyence SR-X](https://www.keyence.com/products/barcode/barcode-readers/sr-x/)).
- **SICK** gán mã cho vật bằng cảm biến quang cộng encoder tăng dần, không bằng tracking thị giác thuần ([SICK TTC100-2](https://manualshive.com/en/manual/sick/ttc100-2/1264606?page=22); [Lector65x System](https://cdn.sick.com/media/familyoverview/1/51/951/familyOverview_Lector65x-System_g326951_en.pdf)). Lector85x có "real-time tracking" để gán mã đúng vật khi nhiều vật cùng trong khung **[nhà cung cấp]**.

**Khuyến nghị.** Có năm việc, theo thứ tự:
1. Đổi lập lịch sang "dải vào ở độ phân giải gốc cộng vận tốc băng chung".
2. Thêm kiểm tra vị trí mã so với bbox dự đoán.
3. Xuất detect sang OpenVINO hoặc ONNX Runtime, ghim luồng, đo trên CPU hiện trường.
4. Thử bộ định vị cổ điển (connected components, mật độ cạnh) song song với YOLO trên `data/field`, đo recall theo tem chứ không theo QR.
5. Không cố đọc QR 25 px (khoảng 1 px/ô). Chỉ cần che nó khỏi cửa sổ khớp, và dùng nó để định vị tem khi tem dán ngược.

### 1.2 PassDecoder: đọc từng frame và xếp chồng đang làm mượt thay vì khôi phục

**Hiện trạng.** Chuỗi xử lý: zxing phóng ×4 với 3 binarizer, rồi warp cộng quiet zone, rồi WeChat (stretch, CLAHE, ×3 CNN), rồi Wiener theo vận tốc. Cuối cùng, tối đa 8 ROI hỏng được căn bằng phase correlation, xếp chồng, rồi chạy lại zxing/Wiener/WeChat. Trên dữ liệu bán thực ở phòng thí nghiệm, PassDecoder đọc được 74,6% lượt, 0 đọc sai **[nội bộ, đo]**. Ở hiện trường chạy: 0/4 **[nội bộ, đo]**.

Ở 2,3 px/ô, hệ thống đang dưới ngưỡng khuyến nghị của ngành:

| Nguồn | Ngưỡng px/ô | Nhãn |
|---|---|---|
| Bài báo *Sensors* 2022 | Không nhỏ hơn 3–3,5 px để giải mã thực tế ([DOI 10.3390/s22197230](https://api.crossref.org/works/10.3390%2FS22197230)) | [tài liệu] |
| Omron | Tối thiểu 2,5, tốt từ 3,5 ([Omron V460-H](https://www.manualslib.com/manual/3258151/Omron-V460-H.html?page=50)) | [nhà cung cấp] |
| Viziotix | Tối thiểu 2 ([Viziotix](https://www.viziotix.com/wp-content/uploads/2024/11/2024.11.14.How-to-Select-the-Best-Camera-for-Barcode-Scanning-Whitepaper-Viziotix.pdf)) | [nhà cung cấp] |

**Tối ưu thuật toán.** Cách xếp chồng hiện tại là căn chỉ bằng dịch chuyển, phóng ×4 rồi lấy trung bình ("interpolate-then-average"). Cách này có hai điểm yếu: nó làm mượt thay vì khôi phục tần số cao, và nó bỏ qua xoay/phối cảnh nhỏ giữa các frame. Có bốn nâng cấp, xếp theo chi phí.

(a) **Shift-and-add lên lưới mịn kèm trọng số robustness**, kiểu kernel regression của Wronski và cộng sự. Mỗi pixel gốc được đặt vào lưới ×2/×3 theo độ lệch dưới pixel. Vùng căn sai bị loại bằng thống kê lân cận. Bản gốc chạy khoảng 100 ms cho mỗi frame 12 MP trên điện thoại ([arXiv 1905.03277](https://arxiv.org/pdf/1905.03277.pdf)) **[tài liệu]**, nên với ROI khoảng 60×60 px và 8 frame, chi phí gần như chắc chắn dưới 10 ms **[ước lượng]**.

(b) **Căn affine/homography** bằng `cv2.findTransformECC` hoặc theo 4 góc từ decoder.

(c) **Gộp ở mức ô thay vì mức pixel.** Lấy mẫu tâm ô theo homography của từng frame, cộng log-likelihood của từng ô qua mọi frame (có trọng số theo chất lượng frame), rồi thử giải sau mỗi frame. Đây đúng là thiết kế của bằng sáng chế Scanbuy US8150163, nay đã hết hiệu lực: tinh chỉnh góc dưới pixel bằng khớp template, 3 đặc trưng cho mỗi bit, gộp kiểu Naive Bayes, loại frame kém, thường cần 5–20 frame ([US8150163](https://patents.google.com/patent/US8150163)) **[tài liệu]**. Cách này dùng được cả 10–60 frame thay vì 8, và cho ra đúng dạng xác suất mà RS mềm và nhận dạng tập đóng (Phần 2) cần.

(d) **Wiener có PSF hiệu chỉnh** từ cạnh finder đã biết, thay cho PSF chỉ suy từ vận tốc × exposure. Exposure mặc định 12,9 ms khiến gợi ý vệt mờ sai khoảng 3 lần **[nội bộ, đo]**. Cách ước lượng PSF từ finder có cơ sở trong van Gennip và cộng sự ([arXiv 1410.6333](https://arxiv.org/pdf/1410.6333)).

Mạng khử mờ học sâu thì không hợp với CPU. EG-Restormer đạt 90% nhưng cần 26 M tham số và 0,91 s cho ảnh 512². LENet nhẹ (0,28 M tham số) chỉ đạt 49% ([arXiv 2510.12098](https://arxiv.org/html/2510.12098v1)) **[tài liệu, phần cứng không nêu]**.

**Tối ưu inference trên CPU.** Hệ thống đã ghi nhận zxing một mình đọc 84% frame sắc, thêm WeChat thì 99% **[nội bộ, đo]**. Vậy thời gian thật bị tiêu ở frame mờ, tức nhánh thất bại. Ý **định tuyến theo độ mờ** của ADNet áp dụng thẳng được: đo phương sai Laplacian hoặc độ tương phản ROI để bỏ các bước vô ích. ROI rất mờ thì không chạy zxing thẳng; ROI sắc thì không chạy Wiener. Ở ADNet, định tuyến giảm 19% thời gian mà giữ nguyên 90% tỉ lệ đọc, còn định tuyến ngẫu nhiên chỉ đạt 72% ([arXiv 2510.12098](https://arxiv.org/html/2510.12098v1)) **[tài liệu]**. Song song bằng thread pool theo ROI có lợi vì zxing-cpp và cv2 nhả GIL. Rủi ro là detector WeChat dùng chung toàn cục không khóa (theo `CLAUDE.md`), nên phải tạo một instance cho mỗi luồng hoặc đặt khóa.

**Sản phẩm thực tế làm gì.**
- **Dynamsoft** có ba cơ chế đáng tham khảo: `MultiFrameResultCrossFilter` mặc định cửa sổ 5 frame và cần 2 frame giống nhau ([Dynamsoft CrossVerificationCriteria](https://www.dynamsoft.com/capture-vision/docs/mobile/programming/maui/api-reference/utility/cross-verification-criteria.md)), nên quy tắc "2 lần đọc giống nhau" của ta đã ngang mức thương mại; `ScaleUpModes` tự phóng mã khi ô khoảng 2 px; `DeblurModes` là danh sách thuật toán nhị phân hóa/khử mờ có thứ tự ưu tiên ([DeblurMode](https://www.dynamsoft.com/capture-vision/docs/core/enums/barcode-reader/deblur-mode.html)).
- **HALCON** có `small_modules_robustness='high'` cho ô rất nhỏ, đổi lại tốn nhiều bộ nhớ và thời gian ([HALCON set_data_code_2d_param](https://www.mvtec.com/doc/halcon/13/en/set_data_code_2d_param.html)).
- **SICK Lector85x** quảng cáo "AI-based segmentation and super resolution" mà không mô tả thuật toán ([SICK](https://www.sick.com/in/en/c/g568570)) **[nhà cung cấp]**.
- **Siêu phân giải đa frame cho đầu đọc mã** đã được cấp bằng sáng chế (US9501683, [US9916489](https://patents.google.com/patent/US9916489)).
- **Đại học Nagoya** (Kato và cộng sự) làm SR đa frame cho QR với PSF ước lượng từ finder và ràng buộc nhị phân, báo 98% nhận dạng, hơn SR thường 15,7 điểm ([Nagoya pubdb 886](https://pubdb.vislab.is.i.nagoya-u.ac.jp/~murase/pdf/886-pdf.pdf)) **[tài liệu, chưa kiểm được điều kiện thử]**.

**Chống đọc sai: lỗ hổng chung của mọi tầng.** `code_pattern=None` nghĩa là nội dung đọc sai vẫn được báo và gửi lên server. Có bốn chốt chặn rẻ:
1. **Regex nội dung cấu hình được.** Dùng `^\d{14}#\d{12}$` sau khi khách hàng xác nhận, không dùng `^\d{12}#\d{12}$` cũ.
2. **Kiểm tra vị trí** mã đọc được so với bbox của lượt.
3. **Hai bộ giải độc lập cùng đồng ý** cho kết quả từ bộ giải tái tạo. Zeng và cộng sự dùng quy tắc này và đạt 0 chuỗi sai trên 955 ảnh ([arXiv 2610.34788](https://arxiv.org/html/2610.34788)) **[tài liệu, preprint chưa kiểm chứng độc lập]**.
4. **Đối chiếu danh sách sản xuất** nếu khách cung cấp được. Cognex "Match String" và Keyence preset/DV-90 làm đúng việc này sau khi giải mã ([Cognex docs](https://docs.cognex.com/is_573/web/EN/ezb/Content/EasyBuilder/Inspect_ID_ReadID_Param_Setting.htm); [Keyence DV-90](https://www.manualsdir.com/manuals/658141/keyence-dv-90.html?page=62)).

**Khuyến nghị.** Bật các chốt chặn trên trước mọi tối ưu khác. Thêm định tuyến theo độ mờ (fail fast). Thay xếp chồng pixel bằng shift-and-add có trọng số, sau đó chuyển dần sang gộp LLR mức ô. Không đầu tư vào mạng khử mờ ảnh-sang-ảnh.

### 1.3 Bộ đọc nền B và C: sai mô hình mờ, không thiếu frame

**Hiện trạng.**
- **Cách chạy:** B (`grid_sr`) và C (`preproc_sweep`) chạy trong một tiến trình riêng, nhận 5 crop. B chọn σ từ 5 giá trị `SIGMAS = (0.45, 0.6, 0.75, 0.95, 1.2)`. Bước căn finder dùng σ cố định 0,75. C dùng σ = 0,7 cố định.
- **Kết quả tổng hợp held-out:** B 95,6%, C 96,3%, B→C 98,6%, 0 đọc sai. Thời gian p95 13–19 s **[nội bộ, đo]**.
- **Điểm hỏng:** cả hai hỏng khi cộng Gauss σ 0,8–1,5 lên trên mờ chuyển động. Tăng từ 5 lên 30 frame không cứu được, k = 30 còn tệ hơn **[nội bộ, đo]**.
- **σ thực tế:** quy đổi từ độ rộng cạnh, σ tổng trên frame chạy khoảng 1,33 px, tức nằm ngoài lưới của B và lệch 0,5–1 px so với C **[ước lượng từ số đo nội bộ, giả định Gauss]**.
- **Đọc nhầm:** C từng đọc ra mã của tem bên cạnh, vì không có bước kiểm tra vị trí.

**Tối ưu thuật toán.** Ba nhóm việc, theo thứ tự lợi ích trên chi phí.

**Nhóm 1: ước lượng PSF liên tục và dị hướng.** Preprint của Zeng và cộng sự đo được rằng ở vệt khoảng 4 ô, dung sai sai số độ dài vệt chỉ còn **8–11%**. Đánh giá thấp độ dài được dung thứ hơn đánh giá cao (54% thiếu so với 29% thừa ở vệt 2 ô). Bài này cũng cho thấy lưới ứng viên quỹ đạo cộng khớp xen kẽ mã ↔ quỹ đạo giảm lỗi từ 22,7% xuống 6,9% ([arXiv 2610.34788](https://arxiv.org/html/2610.34788)) **[tài liệu, preprint; thử ở ≥8 px/ô, không có mờ tròn]**. Bước σ hiện tại 0,15–0,25 px (15–25% ở σ khoảng 1) có thể đã vượt dung sai này.

Cách làm cụ thể: tách `s` trong `psf_points` thành `s_x` và `s_y`, thêm góc θ của vệt. Rồi ước lượng theo thứ tự: σ_x từ cạnh dọc của finder/timing (không chịu vệt dọc), sau đó L và σ_y. Cuối cùng tinh chỉnh chung (σ_x, σ_y, L, θ, pha lưới) bằng Gauss–Newton trên phần dư của mọi ô đã biết **[ước lượng]**. Nguyên lý "một cạnh chỉ cho biết mờ vuông góc với nó, PSF dị hướng cần cạnh nhiều hướng" là chuẩn của phương pháp slanted edge ([VIGRA SlantedEdgeMTF](https://ukoethe.github.io/vigra/doc-release/vigra/group__SlantedEdgeMTF.html)). Tỉ lệ gradient gx/gy 1,23–1,87 trên frame chạy, so với 0,95 khi tĩnh **[nội bộ, đo]**, gợi ý chuyển động lệch hướng hoặc rung. Đó là mờ có hướng, không phải Gauss đẳng hướng.

**Nhóm 2: bộ quyết định.**
- Tính khoảng cách nhỏ nhất giữa các mẫu ô cho thấy sự kiện lỗi tối thiểu dưới mờ chồng là **cặp dọc** và **bàn cờ 2×2** **[nội bộ, tính toán]**. ICM lật một ô mỗi bước không thoát được các cực tiểu đó. Vì Q đã có sẵn, ICM theo khối (cặp, bộ ba dọc, khối 2×2, tối đa 16 tổ hợp) gần như không tốn thêm.
- Bước xa hơn là BCJR/Viterbi theo cột (trạng thái 2³ vì bộ nhớ ISI khoảng 3 ô), luân phiên hàng–cột như phát hiện ảnh nhị phân trên kênh ISI 2-D ([arXiv cs/0609155](https://ar5iv.arxiv.org/html/cs/0609155)). Cách này cho LLR hậu nghiệm thật thay cho LLR "lật một ô".
- Phía RS: `chase_block` hiện xóa tới toàn bộ phần dư. Dự án go-qr đo được rằng xóa hết phần dư với độ tin cậy kém sinh **codeword sai ở hơn 99% khối không cứu được** ([go-qr PR #185](https://github.com/piglig/go-qr/pull/185)). Khi giữ biên 2 byte mỗi khối, cùng dự án nâng ảnh mờ đọc được từ 73,3% lên 82,2% mà không báo sai lần nào qua đường giải mềm ([go-qr PR #186](https://github.com/piglig/go-qr/pull/186)) **[tài liệu, bài viết dự án, chưa bình duyệt]**. Phải giới hạn 2e + s ≤ d − 1 − biên.
- Koetter–Vardy/ABP không đáng làm với khối RS ngắn của QR v1–v3.

**Nhóm 3: đa frame và vị trí.**
- **Trọng số frame theo phần dư.** Dùng Huber hoặc 1/phần dư chuẩn hóa, để khi k tăng thì kết quả không xấu đi. Hiện B chỉ khớp trường biến dạng trên 3 frame tốt nhất và dịch cùng một δ cho góc dưới phải ở mọi frame.
- **Ghim bit nội dung.** Sau khi chốt định dạng, có thể ghim khoảng 62% bit dữ liệu biết trước (nếu đúng là 14#12 ở byte mode, V2-L) **[nội bộ, tính toán]**.
- **Kiểm tra vị trí.** Mã giải ra phải nằm trong bbox đầu vào.

**Tối ưu inference trên CPU.** Chưa có profile thật. Phân tích cấu trúc code cho thấy cổ chai là **dựng lại ma trận A thưa nhiều lần**, không phải bước giải x. Mỗi pixel có khoảng 125 điểm PSF. `build_matrix` bị gọi trong 33 giả thuyết góc × số frame, trong quét 5 σ, và trong Jacobian sai phân 32 cột của `fit_warp` **[nội bộ, đọc code]**. Theo thứ tự nên làm:
1. **Profile trước** bằng `cProfile` trên 20–30 lượt.
2. **Tách A thành hai phần**: lấy mẫu hình học và PSF. Render x lên lưới mịn rồi chập kernel tách được hoặc FFT, để đổi σ/L chỉ còn là đổi kernel 1-D.
3. **Jacobian giải tích** thay cho sai phân trong `fit_warp` và `refine_geometry`.
4. **Thô–tinh và dừng sớm** theo biên điểm format.
5. **Giới hạn version theo kết quả đã chốt.** Lưu ý: nếu tem là V2 thì đừng bỏ V2 như ghi chú 03 gợi ý.
6. **Dùng Q đặc**: 841×841 float64 chỉ khoảng 5,6 MB.
7. **Song song hóa các giả thuyết** trong tiến trình nền, đặt `OMP_NUM_THREADS=1` cho mỗi worker.
8. **Numba** sau cùng. Poster HEAD2024 báo 40–60× trên 8 lõi cho lõi tích chập viết lại thành vòng lặp ([HEAD2024](https://sbs.wustl.edu/Posters/HEAD2024_compton_imaging_poster.pdf)) **[tài liệu]**. Với code đã vector hóa NumPy, kỳ vọng thực tế khoảng 3–10× **[ước lượng]**.

Gộp các bước 2–5 có thể đưa B từ 4–15 s xuống khoảng 1–3 s **[ước lượng, chưa đo]**. Để so sánh: phương pháp mô hình cạnh tranh nhất đã công bố cũng mất trung vị 5,8 s, p90 33,8 s trên GPU ([arXiv 2610.34788](https://arxiv.org/html/2610.34788)). Tức B không chậm bất thường so với lớp phương pháp này.

**Sản phẩm thực tế làm gì.** Không hãng lớn nào công bố giải mã theo mô hình thuận như B. Những gì gần nhất có thể kể:
- **Cognex PowerGrid**: giả thuyết lưới từ kết cấu toàn mã. Gợi ý cho B là dùng tự tương quan/phổ của ROI để ràng buộc bước lưới trước khi khớp finder.
- **HALCON**: khuyên thu hẹp không gian tìm kiếm (kích thước ô, hình dạng) khi bật chế độ ô nhỏ ([HALCON get_data_code_2d_param](https://www.mvtec.com/doc/halcon/2605/en/get_data_code_2d_param.html)). Đó đúng là chiến lược tăng tốc ở trên.
- **Bằng sáng chế kiểu Cognex** thử tổ hợp ô hợp lệ cho mã thiếu độ phân giải ([USPTO 10599902](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/10599902)).

**Khuyến nghị.** Bước một là thí nghiệm oracle trong một ngày: đưa σ tổng và L đúng vào B và C trên bộ chuẩn mờ chồng. Nếu oracle đọc được thì làm Nhóm 1. Nếu oracle vẫn hỏng thì làm Nhóm 2. Song song, profile rồi tách A khỏi PSF. Mọi kết quả của B/C phải qua kiểm tra vị trí, regex và RS có biên. Nếu phía chụp đạt vệt ≤2 px, B/C chỉ còn là lớp dự phòng; khi đó nên dừng tối ưu chuyên sâu ở mức "đúng σ, đúng biên RS".

### Tổng hợp Phần 1

| Tầng | Cổ chai chính | Tối ưu thuật toán đáng làm nhất | Tối ưu CPU đáng làm nhất | Sản phẩm tham chiếu |
|---|---|---|---|---|
| Phát hiện + theo dõi | YOLO toàn khung thu QR còn khoảng 1 px/ô, 980 ms | Dải vào độ phân giải gốc, vận tốc băng chung, kiểm tra vị trí | OpenVINO/ONNX Runtime, model detect thuần, ghim luồng | HALCON (kim tự tháp theo ô), PowerGrid, SICK encoder |
| PassDecoder | Xếp chồng pixel làm mượt, không có lọc nội dung | Gộp LLR mức ô, shift-and-add có trọng số, PSF từ finder | Định tuyến theo độ mờ, fail fast, thread pool | Dynamsoft cross-filter 2/5, Scanbuy US8150163 |
| B/C | σ cố định hoặc lưới thô; Chase xóa hết phần dư | σ liên tục dị hướng, ICM khối/BCJR, Chase có biên | Tách A/PSF, Jacobian giải tích, dừng sớm | Zeng 2026 (mô hình thuận), HALCON small modules |

## Phần 2. Đặt lại bài toán: định danh từng tấm kính, không phải "giải QR khó"

### Mục tiêu thật là ID đúng cho mỗi tấm, và có nhiều đường tới đó

Đặt lại cho đúng, bài toán là: **mỗi tấm kính đi qua vùng 1,6 × 0,6 m với tốc độ 100 mm/s phải được gán đúng ID**, recall gần 100%, đọc sai gần 0, chi phí thấp. Giải QR ở 2,3 px/ô với mờ 10–20 px chỉ là một cách, và là cách khó nhất. Hai lý do khiến khung này đổi thứ tự ưu tiên. Thứ nhất, điều kiện chụp đang nằm ngoài vùng mà mọi tài liệu QR đã kiểm chứng: các phương pháp có số liệu làm ở 3–8 px/ô trở lên và chỉ với một loại mờ. Thứ hai, ngành kính phẳng không đọc tem dán ngẫu nhiên trên toàn bề rộng. HEGLA in laser một ID ảo sinh từ kế hoạch sản xuất lên tấm gốc trước khi cắt, đặt ở vị trí do máy quyết định, rồi đọc tự động ở mọi công đoạn ([HEGLA](https://www.hegla.com/en/news/news-hegla/laser-marking-the-smooth-permanent-tracking-method/)). LiSEC LMS khắc Data Matrix/QR lên kính ([LiSEC](https://www.lisec.com/solutions/individual-machines/detail/laser-processing/lms-a-laser-marking-system)). Nói cách khác, ngành giải bài toán bằng **kiểm soát vị trí và quy cách mã**, không bằng thuật toán.

### Đòn bẩy phần cứng: exposure và đèn đứng trước mọi thứ

Vệt mờ (mm) bằng tốc độ nhân exposure ([Quality Magazine](https://www.qualitymag.com/articles/98039-machine-vision-technologies-adapt-for-higher-speeds-evolving-needs)). Ở 100 mm/s và 0,673 mm/px:

| Exposure | Vệt (mm) | Vệt (px) | Phần ô (≈1,55 mm) |
|---|---|---|---|
| 12,9 ms (mặc định code) | 1,29 | 1,9 | ~0,8 ô |
| 3 ms (khuyến nghị) | 0,30 | 0,45 | ~0,2 ô |
| 1 ms (strobe) | 0,10 | 0,15 | ~0 |
| 67–135 ms (suy ngược từ vệt 10–20 px hiện trường) | 6,7–13,5 | 10–20 | 4–9 ô |

Bảng là **[ước lượng]** từ công thức. Thử nghiệm nội bộ cho thấy cascade đọc ảnh tĩnh thêm mờ tổng hợp tới 3 px và hỏng từ 4–5 px **[nội bộ, đo]**. Khóa exposure 3 ms đưa ảnh chạy về gần điều kiện ảnh tĩnh, nơi hệ thống đã đọc 100%.

Cái giá là ảnh tối hơn nhiều lần, nên cần đèn. Smart Vision Lights quảng cáo chế độ xung 1 ms ở dòng gấp 10 lần chế độ liên tục ([Photonics.com](https://www.photonics.com/Articles/Machine-Vision-Lights-Boost-Canning-Line/a70108)) **[nhà cung cấp]**. Đèn bar LED khoảng 1,8 m hai bên, kích theo tín hiệu exposure-out của camera Basler, là cấu hình hợp lý. Tấm che phía trên vùng đọc là cách rẻ nhất để loại phản xạ đèn trần. EDA thấy một số crop cháy trắng hoàn toàn khi tem nằm dưới vệt phản xạ **[nội bộ, đo]**.

Phân cực chéo chặn được phản xạ gương ([Epic Systems](https://epicsysinc.com/blog/eliminating-glare-with-polarization/)) nhưng có hai lưu ý. Nó tốn tới khoảng 10 lần ánh sáng ([VA Imaging](https://va-imaging.com/en-us/blogs/machine-vision-knowledge-center/polarization-in-your-machine-vision-application)), đi ngược với exposure ngắn. Và ở góc tới gần vuông góc, phản xạ ít bị phân cực, nên polarizer thụ động kém hiệu quả với đèn trần **[ước lượng]**. Nên ưu tiên đặt đèn lệch khỏi nón phản xạ gương và nghiêng camera 10–20°.

Nếu đèn không đủ để xuống 2 px, còn hai phương án dự phòng **[ước lượng]**. Một là exposure xen kẽ giữa các frame, để các frame không chung điểm không của MTF. Hai là xung strobe mã hóa kiểu flutter shutter, biến PSF hộp thành PSF băng rộng khả nghịch ([MERL TR2006-124](https://www.merl.com/publications/docs/TR2006-124.pdf)).

Còn một chẩn đoán cần làm. Phần σ khoảng 1 px thêm vào trên frame chạy khó đến từ quang học, vì ảnh tĩnh cùng ống kính vẫn đọc 100%. Ứng viên là chuyển động lệch hướng, rung khung khi băng chạy, hoặc thiết lập gain/exposure khác. Nhiễu trên frame chạy là 2,2–3,4, so với 1,2–1,3 khi tĩnh **[nội bộ, đo]**. Cách kiểm: dán tem cố định lên khung trong lúc băng chạy, và chụp tem tĩnh ở nhiều vị trí với cùng thiết lập.

### Đòn bẩy px/ô: quang học, số camera, line-scan

Để có 3–5 px/ô trên 1,6 m cần khoảng 3.000–5.000 px theo chiều ngang **[ước lượng]**. Hiện camera phủ khoảng 1,92 m, nên tối đa chỉ được khoảng 2,7 px/ô dù có cắt FOV. Các phương án:

| Phương án | px/ô kỳ vọng | Chi phí | Ghi chú |
|---|---|---|---|
| 1 camera, ống 6 mm | ~3,4 | Một ống kính | FOV chỉ ~1,29 m, **không phủ đủ 1,6 m** [ước lượng] |
| 2 camera, ống 8 mm | ~4,6–5,3 | +1 camera Basler + 2 ống | Mỗi camera ~0,85–0,97 m, chồng lấn ≥60 mm; `main_dual.py` đã gộp cùng mã trong 30 s [ước lượng] |
| 3 camera 5 MP | ~6,7 | +2–3 camera | Tải CPU tương đương nếu dùng dải ROI [ước lượng] |
| Line-scan 8k + encoder | ~7 | Thân máy 2.159 € niêm yết, frame grabber CXP-12 ~1.589 € ([Basler shop](https://www.baslerweb.com/en/shop/r2L8192-80cc/)) + đèn vạch + ống khổ lớn | Mỗi tem xuất hiện đúng một lần, bỏ được tracker và đa frame; cần encoder tì lên kính [tài liệu giá, còn lại ước lượng] |
| Đầu đọc thương mại (Lector85x ×2, hoặc Datalogic AV7000 12K) | 5–8 | Báo giá riêng | Lector85x phủ tới ~800 mm mỗi đầu ([SICK flyer](https://cdn.sick.com/media/docs/8/08/608/flyer_lector_identification_system_en_im0102608.pdf)); AV7000 12K phủ 1.600 mm một lần chụp ([Datalogic](https://www.datalogic.com/eng/products/industrial-automation/fixed-industrial-barcode-readers/av7000-pd-709.html)) [nhà cung cấp] |

Lưu ý: tăng px/ô thì vệt mờ tính theo px cũng tăng cùng tỉ lệ, nên exposure phải ngắn đi tương ứng. Hai camera ống 8 mm là phương án giữ nguyên phần mềm và có rủi ro thấp nhất. Line-scan thay đổi kiến trúc nhiều nhất nhưng thanh lịch nhất về thuật toán: ảnh liền mạch và không mờ theo chiều chạy.

### Đòn bẩy quy cách mã và quy trình: gần như miễn phí

**Tem lớn hơn.** Tem 50 mm làm ô to hơn khoảng 39%, đưa px/ô lên khoảng 3,2 với chính camera hiện tại. Tem 60 mm cho khoảng 3,8 **[ước lượng]**. Đây là cách rẻ nhất để vượt ngưỡng 3–3,5 px/ô.

**Nội dung toàn số, mức sửa lỗi Q.** Ký tự `#` không thuộc bộ alphanumeric của QR, nên phải mã hóa thành nhiều đoạn. Bỏ `#` thì 24–26 chữ số vừa V1-Q: mức sửa lỗi khoảng 25%, ô vẫn 21×21 **[ước lượng từ bảng dung lượng]**. Nếu tem hiện là V2, quay về V1-Q còn làm ô to hơn khoảng 19% trên cùng tem (25/21). Nên thêm một chữ số kiểm tra mod-10/11 để chặn đọc sai.

**Data Matrix.** Kích thước nhỏ nhất 10×10 ô và quiet zone chỉ 1 ô, so với 4 ô của QR ([qr-code-generator.com](https://www.qr-code-generator.com/blog/data-matrix-vs-qr-codes)). 24 số vừa 16×16, cho khoảng 2,0 mm/ô trên tem 36 mm **[ước lượng từ trí nhớ bảng ISO 16022, cần kiểm bằng thư viện sinh mã]**. Đổi lại, WeChat không đọc Data Matrix, chỉ zxing đọc được.

**Cố định vị trí dán tem.** Nếu dán trong vùng khoảng 150×150 mm ở một góc xác định thì FOV chỉ cần khoảng 250 mm. Một camera 2–5 MP sẽ cho 10–15 px/ô, gần như chắc chắn đạt 100% **[ước lượng]**.

**Cảm biến quang và đọc tay dự phòng.** Một cảm biến quang ở mép vào có thể kích strobe và chụp đúng lúc, theo mẫu chuẩn "photo-eye + đầu đọc + encoder" của logistics ([industrialmonitordirect](https://industrialmonitordirect.com/blogs/knowledgebase/industrial-barcode-scanner-edge-trigger-with-photoeye-integration)). Tấm nào không đọc được thì báo động để người vận hành quét bằng máy quét tay. Cách này đổi yêu cầu "đọc 100%" thành "100% được xử lý", và là cách thực tế duy nhất để bảo đảm không tấm nào đi tiếp mà không có ID.

**Hai QR trên một tem.** Phải hỏi khách mã nào cần đọc và hai mã có cùng nội dung không.

RFID không hợp: kính có thể gây nhiễu thẻ RF ([USPTO 12400100](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/12400100)), và không tìm thấy tài liệu dùng RFID cho từng tấm kính. Khắc laser là chuẩn của ngành, nhưng mã trên kính trong có tương phản thấp và cần đặt ở vị trí cố định. Vì vậy nó chỉ là phương án dài hạn nếu khách đầu tư máy khắc.

### Paradigm thuật toán khác: từ "giải mở" sang "nhận dạng có tiên nghiệm"

**Nhận dạng tập đóng theo likelihood.** Nếu có danh sách mã sản xuất trong ngày, mỗi ứng viên được render qua mô hình hình học và mờ đã có trong `qr/solvers`, rồi so với các crop. Ứng viên có log-likelihood cao nhất được chọn, kèm điều kiện biên với ứng viên nhì phải vượt ngưỡng. Hai mã khác nhau một chữ số khác nhau ở cả khối dữ liệu lẫn toàn bộ codeword EC, nên khoảng cách mức ô lớn **[ước lượng]**. Đây cũng là lý do marker từ điển kiểu ArUco chịu mờ tốt nhờ khoảng cách Hamming tối thiểu ([OpenCV ArUco](https://docs.opencv.org/4.x/d5/dae/tutorial_aruco_detection.html)). Rủi ro chính là tem không có trong danh sách, nên phải có lớp "không thuộc tập" và vẫn quay về đọc mở.

Về sản phẩm: Cognex và Keyence chỉ so chuỗi **sau** khi đã giải mã. Không tìm thấy hãng nào dùng chuỗi kỳ vọng để hỗ trợ giải mã. Mã thật cho thấy cấu trúc mạnh, nhiều số 0 và phần đuôi giống số thứ tự (`…1612`, `…1610`) **[nội bộ, quan sát]**. Vì vậy prior "tem sau gần tem trước" đáng kiểm tra trên danh sách thật, nhưng chỉ dùng để xếp thứ tự thử.

**Tích lũy niềm tin từng ô theo thời gian, kèm quy tắc dừng tuần tự.** Đây là bản đầy đủ của mục 1.2(c): báo sớm lượt dễ, dồn tính toán cho lượt khó. Ý tưởng có từ bằng sáng chế Scanbuy ([US8150163](https://patents.google.com/patent/US8150163)) và SR đa frame của Nagoya.

**Khai thác cấu trúc nội dung đã biết.** Ghim header, vị trí `#` và byte đệm. Ô kém tin cậy được đánh dấu erasure: RS sửa được số erasure gấp đôi số lỗi ([USPTO 9166623](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/9166623)). Giải mã list/vượt giới hạn làm tăng xác suất ra một từ mã hợp lệ nhưng sai, nên bắt buộc lọc bằng regex, danh sách và kiểm tra khớp ngược với ảnh.

**Học máy ở vai bộ phân loại ô, không ở vai bộ giải đầu-cuối.** Transformer giải QR đầu tiên (2025) nhận chuỗi bit và **luôn xuất chuỗi kể cả khi sai**. Nó còn "sửa" chuỗi thành chuỗi hợp lý (dtv2009 → dtv2008) ([arXiv 2506.20305](https://arxiv.org/html/2506.20305)) **[tài liệu]**. Đó là đúng kiểu đọc sai mà ta không được phép có. Lợi thế của ta là sinh được dữ liệu tổng hợp vô hạn bằng mô hình thuận. Một CNN nhỏ (crop khoảng 60×60, đầu ra 25×25 logit) chạy vài chục ms trên CPU **[ước lượng]** có thể làm LLR thứ hai cho RS mềm, hoặc làm phiếu độc lập cho cổng chống báo sai.

**OCR dòng số in.** Tesseract cần x-height ≥10 px ([EasyRPA](https://docs.easyrpa.eu/help/docs/Data-Analyst-Guide/OCR-Tuning-Guide/Evaluating-and-Enhancing-Image-Quality-for-OCR)), trong khi chữ cao 2–3 mm chỉ được 3–4,5 px ở 0,673 mm/px **[ước lượng]**. OCR mở không khả thi. Chỉ có xác minh chuỗi kỳ vọng kiểu OCVMax ([Cognex OCVMax](https://docs.cognex.com/vpro_950/web/EN/help/html/c2da0f57-4fd9-4938-9a5e-14f61d0edb9d.htm)) là đáng thử, và chỉ khi chữ đủ lớn.

**Siêu phân giải sinh (GAN, diffusion).** Hướng này có rủi ro "bịa" mã: PSNR/SSIM/LPIPS không bắt được ảo giác ([arXiv 2507.14367](https://arxiv.org/html/2507.14367v2)). Chỉ chấp nhận được nếu mọi kết quả qua phép kiểm "suy giảm ngược khớp ảnh gốc". Repo đã đúng khi không dùng Real-ESRGAN.

**Event camera.** Đọc được QR khi chuyển động nhanh nhờ tối ưu trong không gian mã ([Nagata et al., WACV 2020](https://openaccess.thecvf.com/content_WACV_2020/papers/Nagata_QR-code_Reconstruction_from_Event_Data_via_Optimization_in_Code_Subspace_WACV_2020_paper.pdf)), nhưng không thực tế cho dự án này.

| Hướng thay thế | Đòn bẩy lên recall | Đòn bẩy chống đọc sai | Chi phí | Phụ thuộc |
|---|---|---|---|---|
| Khóa exposure + strobe + tấm che | Rất lớn | Trung bình | Thấp | Không |
| Tem lớn hơn / toàn số V1-Q / chữ số kiểm tra | Lớn | Lớn | ~0 | Khách hàng đồng ý |
| Cố định vị trí dán tem | Rất lớn | Lớn | ~0 phần cứng | Quy trình nhà máy |
| 2 camera ống 8 mm | Lớn | Trung bình | Thấp–trung bình | Không |
| Line-scan 8k + encoder | Lớn | Trung bình | Trung bình | Đổi kiến trúc |
| Đầu đọc thương mại | Lớn | Lớn | Cao (báo giá) | Nhà cung cấp |
| Nhận dạng tập đóng | Trung bình–lớn | Rất lớn | Phần mềm | Danh sách sản xuất kịp thời |
| Gộp LLR mức ô + RS mềm có biên | Trung bình | Lớn | Phần mềm | Chốt định dạng |
| Đọc tay dự phòng | Bảo đảm 100% được xử lý | — | Thấp | Người vận hành |

## Phần 3. Lộ trình ưu tiên: đo trước, rồi phần cứng rẻ, rồi phần mềm

### Năm phép đo phải có trước mọi quyết định

1. **Chốt quy cách mã.** Giải mã 20–30 tem tĩnh, đọc version, mức sửa lỗi, mode và mask (zxing-cpp trả được các thông tin này), rồi đối chiếu với khách. Hỏi luôn vai trò của QR nhỏ.
2. **Quay lại lượt chạy có đáp án.** Đọc tĩnh một loạt tem để biết mã, rồi cho chính các tem đó chạy qua băng với exposure khóa 3 ms, AE tắt, và ghi exposure thật vào `meta.json`. Đây là bộ đánh giá quyết định cho mọi bước sau.
3. **Profile trên CPU hiện trường.** Xác nhận model CPU, đo ms của detect, PassDecoder và B/C theo từng bước, và đo fps ghi/xử lý thật. Bản ghi 13/11 chỉ đạt 14–17 fps.
4. **Chẩn đoán phần mờ thêm.** Tem cố định trên khung lúc băng chạy, tem tĩnh ở nhiều vị trí, đo góc chuyển động từ finder.
5. **Thí nghiệm oracle σ cho B/C** trên bộ chuẩn mờ chồng.

### Thứ tự đầu tư

| Ưu tiên | Việc | Chi phí | Hiệu quả kỳ vọng | Cơ sở | Cổng quyết định |
|---|---|---|---|---|---|
| 0 | Năm phép đo ở trên | 2–4 ngày | Biết đang ở phía "ảnh hỏng" hay "thuật toán thiếu" | — | Bắt buộc |
| 1 | Khóa exposure ≤3 ms trong code mặc định và cấu hình hiện trường; lấy exposure thật cho gợi ý vệt mờ; regex cấu hình được (chưa bật tới khi chốt định dạng); kiểm tra vị trí mã so với bbox | ~1–2 ngày, 0 đồng | Vệt từ 10–20 px về <1 px nếu đủ sáng; chặn đọc nhầm tem bên cạnh | [ước lượng] từ công thức; cascade đọc tới 3 px [nội bộ, đo] | Lượt có đáp án: tỉ lệ đọc chạy so với tĩnh |
| 2 | Đèn bar LED strobe đồng bộ + tấm che đèn trần, đèn lệch nón phản xạ | Vài trăm đến ~1.500 USD [ước lượng, chưa có giá có nguồn] | Đưa ảnh chạy về điều kiện ảnh tĩnh (đã đọc 100%) | [nhà cung cấp] OverDrive; [nội bộ, đo] ảnh tĩnh | Nếu lượt chạy đạt ≥ tĩnh thì B/C chỉ còn dự phòng, dừng tối ưu sâu |
| 3 | Đề xuất với khách: tem 50–60 mm, nội dung toàn số V1-Q + chữ số kiểm tra, vùng dán cố định | ~0 phần cứng | px/ô từ 2,3 lên 3,2–3,8; sửa lỗi 25%; chống đọc sai mạnh | [ước lượng] | Khách chấp nhận hay không |
| 4 | Detect dải vào ở độ phân giải gốc + vận tốc băng chung + OpenVINO/ONNX Runtime | 1–2 tuần | 980 ms xuống ~100–250 ms/lần, giải phóng CPU cho giải mã | [tài liệu] Ultralytics; [ước lượng] ngoại suy | Recall theo tem không giảm trên `data/field` |
| 5 | PassDecoder: định tuyến theo độ mờ, shift-and-add có trọng số, rồi gộp LLR mức ô | 2–4 tuần | Bớt thời gian nhánh thất bại; tăng tỉ lệ lượt từ mức 74,6% phòng thí nghiệm | [tài liệu] ADNet, Wronski, Scanbuy; [nội bộ, đo] 74,6% | So trên bộ chuẩn và lượt có đáp án, 0 đọc sai |
| 6 | B/C: σ liên tục dị hướng, ICM khối, Chase có biên, trọng số frame; tách A/PSF, Jacobian giải tích | 2–4 tuần | Mờ chồng đọc được; p95 từ 13–19 s xuống vài giây | [tài liệu] Zeng 2026, go-qr; [ước lượng] tốc độ | Chỉ làm sâu nếu bước 2 không đạt; oracle quyết định nhánh |
| 7 | 2 camera ống 8 mm (hoặc line-scan 8k nếu muốn bỏ tracking) | 1 camera + ống kính; line-scan ~3.700 € + đèn + ống | px/ô lên 4,6–7 | [ước lượng]; [tài liệu] giá Basler | Khi bước 3 không được chấp nhận và bước 2 vẫn chưa đủ |
| 8 | Nhận dạng tập đóng / bộ phân loại ô / xác minh danh sách | 3–6 tuần nghiên cứu | Biên tin cậy có ý nghĩa xác suất; vớt lượt `pass_unconfirmed` | [ước lượng]; không có tài liệu trực tiếp | Cần danh sách sản xuất kịp thời |
| Song song | Quy trình đọc tay dự phòng + báo động | Thấp | Bảo đảm 100% tấm được xử lý | Đề xuất | Triển khai cùng bản hiện trường đầu tiên |

Hai bước đầu gần như chắc chắn đem lại nhiều hơn mọi bước phần mềm cộng lại. Lý do: cùng pipeline đó, khi ảnh sắc, đã đọc được 100%. Nếu chỉ còn ngân sách cho một việc thì đó là đèn cộng exposure ngắn. Nếu được thêm một việc thứ hai thì đó là thương lượng quy cách tem với khách.

## Kết luận

Toàn bộ câu chuyện nghiên cứu đã chuyển từ câu hỏi "thuật toán nào đọc nổi QR 2,3 px/ô mờ 10–20 px" sang câu hỏi "vì sao ta lại để ảnh mờ 10–20 px". Câu hỏi thứ nhất không có lời giải trong tài liệu. Câu hỏi thứ hai có lời giải tốn vài trăm đô và một dòng cấu hình. Phần mềm hiện có, từ cascade, PassDecoder đến B/C, đã ở mức ngang hoặc vượt các đầu đọc thương mại công bố về cơ chế đa frame và chống đọc sai, trừ việc thiếu lọc nội dung và vị trí. Phần mềm nên được tối ưu để **rẻ trên CPU và an toàn trước đọc sai**, chứ không phải để bù cho khâu chụp hỏng.

Điều đáng chú ý nhất về dài hạn là các sản phẩm thành công trong ngành, từ tunnel logistics của SICK/Cognex đến hệ đánh dấu kính của HEGLA/LiSEC, đều thắng bằng cách **giảm bất định trước khi chụp**: encoder thay cho tracking, vị trí mã cố định thay cho tìm kiếm toàn trường, mã đủ lớn thay cho siêu phân giải. Nếu khách chấp nhận dù chỉ một trong ba thay đổi (tem lớn hơn, vùng dán cố định, hoặc nội dung toàn số V1-Q), phần lớn độ phức tạp của B/C sẽ không còn cần thiết. Cần ghi rõ để tránh sai lầm tốn kém nhất trước mắt: bật regex hoặc ghim bit theo định dạng "12#12, V1" cũ, trong khi tem thật là 14#12 và có vẻ là V2.
