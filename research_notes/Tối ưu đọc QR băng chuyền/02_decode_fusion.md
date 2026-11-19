# Tối ưu giai đoạn giải mã từng frame và ghép nhiều frame (QR nhỏ, mờ chuyển động, 2,2–2,6 px/ô)

Phạm vi: bước sau detect, tức `PassDecoder` (zxing nhiều binarizer → warp → WeChat → Wiener → xếp chồng nhiều ROI). Ghi chú do một nhà nghiên cứu soạn sau khoảng 20 lượt tìm kiếm/đọc web (11/2026). Phần lớn thông tin thương mại là tài liệu hoặc tin marketing của hãng, ít số liệu định lượng. Các chỗ thiếu số ghi rõ trong mục Gaps.

## (C) Sản phẩm thương mại xử lý mã hỏng/mờ/PPM thấp thế nào, và PPM tối thiểu họ công bố

### Takeaway
Các hãng lớn (Cognex, Keyence, SICK, Halcon, Zebra) hầu như **không công bố PPM tối thiểu cho mã 2D**. Thông số họ đưa ra là độ phân giải tối thiểu bằng mm, hoặc "expected module size" như một gợi ý. Con số 2D cụ thể duy nhất tìm được là của bên thứ ba: tối thiểu khoảng 2 px/ô (Viziotix), tối ưu khoảng 4 px/ô (Omron), và một bài báo nêu 3–3,5 px/ô để giải mã thực tế. Hệ thống hiện tại ở 2,2–2,6 px/ô, tức sát hoặc dưới ngưỡng khuyến nghị của ngành. Tính năng "đa frame" mà hãng thương mại công bố rõ nhất (Dynamsoft) là **lọc chéo kết quả giữa các frame** (cửa sổ 5 frame, cần 2 frame giống nhau), không phải ghép ảnh.

### Cited Findings
- **Cognex 1DMax + Hotbars**: đọc mã 1D hỏng hoặc in kém tới 0,8 PPM. Đây là số cho 1D, không áp dụng cho 2D. Không tìm thấy số PPM 2D của 2DMax/PowerGrid. — [Control Engineering: DataMan 150/260](https://www.controleng.com/articles/ec-dataman-150-260-series/); [Datasheet DM150/260](https://qualitrol.com/assets/datasheet_dataman-150_260_en.pdf)
- **Cognex PowerGrid** định vị theo **texture**: tìm mẫu ô sáng/tối xen kẽ thay vì dựa vào finder pattern. Nhờ vậy nó đọc được mã có finder pattern, clocking pattern hoặc quiet zone hỏng nặng hay mất hẳn. Chỉ có trên các model X của DataMan 300. 2DMax kết hợp tìm mẫu theo hình dạng với phân tích texture. Đây là mô tả marketing, không kèm số liệu. — [Automate.org: PowerGrid](https://www.automate.org/vision/news/powergrid-technology-for-2d-barcode-reading); [Metoree listing](https://us.metoree.com/products/56137/)
- **Keyence SR-X** ("AI-Powered Code Reader"): công bố độ phân giải tối thiểu cho mã 2D là 0,024 mm (SR-X300), 0,010 mm với bản độ phân giải cao, và 0,060 mm với bản trường rộng/1,4 MP. Hãng nói chip AI được học từ hơn 100.000 ảnh. Dòng SR-X100 không hỗ trợ AI filter. Không có số PPM hay tỉ lệ đọc định lượng; đây là marketing. — [Keyence SR-X specs](https://www.keyence.com/products/barcode/barcode-readers/sr-x/specs); [Keyence SR-X specs UK](https://www.keyence.co.uk/products/barcode/barcode-readers/sr-x/specs/); [Vision Systems Design](https://www.vision-systems.com/factory/article/55020046/keyence-launches-ai-powered-code-reader-line)
- **SICK Lector85x**: 5/9/12 MP, có "AI-based segmentation and super resolution", đọc ở băng chuyền tới 3,5 m/s. Lector Identification System (dựa trên Lector85x) dùng super-resolution để đọc mã in kém. Lector64x/65x chạy 40 Hz, giải mã thời gian thực; một nguồn khác ghi 70 Hz, mâu thuẫn. Không có mô tả thuật toán hay số PPM. — [SICK image-based code readers](https://www.sick.com/in/en/c/g568570); [SICK Lector Identification System overview](https://cdn.sick.com/media/familyoverview/2/72/972/familyOverview_Lector-Identification-System_g575972_en.pdf); [Lector64x overview](https://cdn.sick.com/media/familyoverview/1/51/851/familyOverview_Lector64x_g322851_en.pdf)
- **MVTec Halcon**: `small_modules_robustness` có giá trị 'low'/'high', mặc định 'low'. Giá trị 'high' tăng khả năng đọc mã có module rất nhỏ nhưng tăng đáng kể bộ nhớ. Khi bật 'high', tài liệu khuyên đặt `module_size_min` (đơn vị pixel) bằng module nhỏ nhất dự kiến. Không có ngưỡng số. — [Halcon get_data_code_2d_param](https://www.mvtec.com/doc/halcon/1805/en/get_data_code_2d_param.html); [set_data_code_2d_param](https://www.mvtec.com/doc/halcon/13/en/set_data_code_2d_param.html)
- Halcon 24.11 (20/11/2024) "tối ưu QR reader, mạnh hơn trong điều kiện khó", chủ yếu khi có nhiều mã trong ảnh. Không có số liệu cho QR nhỏ. — [MVTec press release 24.11](https://www.mvtec.com/application-areas/press-room/press-releases/article/machine-vision-software-becomes-even-more-powerful-and-user-friendly-mvtec-presents-halcon-2411)
- MVTec (cho mã vạch 1D): ảnh nên được lấy nét tối đa, nhất là với mã độ phân giải rất thấp. Khi blur nhỏ, mã 1D có phần tử nhỏ hơn 1 px vẫn đọc được nhờ tính năng sub-pixel. — [MVTec Developers Corner: sub-pixel bar code reader](https://www.mvtec.com/knowledge-base/developers-corner/article/introduction-to-new-sub-pixel-feature-of-bar-code-reader)
- **Zebra Aurora**: có tham số "Expected Module Size (Pixels)" để tăng hiệu năng, nhưng đó chỉ là gợi ý chứ không phải ngưỡng cứng. — [Zebra Aurora Focus: Advanced](https://docs.zebra.com/us/en/machine-vision/zebra-aurora-focus-user-guide/c-aurora-using-fis-tools/c-aurora-advanced.html)
- **Ngưỡng bên thứ ba**: Viziotix khuyên tối thiểu 2 px/ô cho mã 2D và 1,5 px/vạch hẹp cho 1D (decoder của họ đọc 1D tới 0,7 px). Omron khuyên khoảng 4 px/phần tử là tối ưu. — [Viziotix whitepaper 2024](https://www.viziotix.com/wp-content/uploads/2024/11/2024.11.14.How-to-Select-the-Best-Camera-for-Barcode-Scanning-Whitepaper-Viziotix.pdf); [Omron V440-F manual](https://www.manualslib.com/manual/2754015/Omron-V440-F.html?page=204)
- Một bài báo (Sensors 2022, DOI 10.3390/s22197230) kết luận module QR nên không nhỏ hơn 3–3,5 px để giải mã thực tế, bất kể đặc tính MTF. — [Crossref: 10.3390/s22197230](https://api.crossref.org/works/10.3390%2FS22197230)
- **Dynamsoft DeblurModes** là danh sách thuật toán có thứ tự ưu tiên, áp dụng lên vùng chứa mã để tạo ảnh nhị phân, gồm DM_BASED_ON_LOC_BIN, DM_THRESHOLD_BINARIZATION, DM_GRAY_EQUALIZATION, DM_SMOOTHING (làm mượt ảnh xám trước khi nhị phân), DM_SHARPENING_SMOOTHING, DM_MORPHING… Tài liệu các phiên bản mô tả DM_MORPHING không thống nhất. DeblurLevel đã bị bỏ, thay bằng DeblurModes. — [Dynamsoft DeblurMode enum](https://www.dynamsoft.com/capture-vision/docs/core/enums/barcode-reader/deblur-mode.html); [DeblurModes parameter](https://dynamsoft.com/capture-vision/docs/core/parameters/reference/barcode-reader-task-settings/deblur-modes.html)
- **Dynamsoft ScaleUpModes**: tự phóng to mã nhỏ trước khi giải mã. Ví dụ trong tài liệu kích hoạt scale-up khi module khoảng 2 px. — [Dynamsoft: how to set ScaleUpModes](https://www.dynamsoft.com/barcode-reader/docs/core/parameters/scenario-settings/how-to-set-scaleup-modes-v7.6.0.html)
- **Dynamsoft MultiFrameResultCrossFilter**: tính năng "cross verification" kiểm tra kết quả qua nhiều frame. Mặc định cho barcode là frameWindow = 5, minConsistentFrames = 2. Cùng bộ lọc còn có chức năng overlapping và khử trùng lặp. — [Dynamsoft CrossVerificationCriteria (MAUI)](https://www.dynamsoft.com/capture-vision/docs/mobile/programming/maui/api-reference/utility/cross-verification-criteria.md); [MultiFrameResultCrossFilter (JS)](https://dynamsoft.com/capture-vision/docs/web/programming/javascript/api-reference/utility/multi-frame-result-cross-filter.html)
- **Dynamsoft ExpectedBarcodesCount**: mặc định 0. Khi đặt N, vòng thử các chế độ dừng ngay khi đủ N mã. Đây là cơ chế early-exit có sẵn. — [Dynamsoft ExpectedBarcodesCount](https://www.dynamsoft.com/barcode-reader/docs/core/parameters/reference/expected-barcodes-count.html)
- **Bằng sáng chế "Multi-frame super-resolution barcode imager"** (US9501683, US9916489): ghép nhiều frame độ phân giải thấp, lệch nhau một lượng sub-pixel không nguyên, thành một ảnh độ phân giải cao cho đầu đọc mã. Chứng tỏ hướng này đã được ngành mã vạch đăng ký sáng chế. — [Google Patents US9916489](https://patents.google.com/patent/US9916489)

### Inferences
- Ở 2,2–2,6 px/ô, hệ thống đang ở vùng mà ngành coi là giới hạn: tối thiểu 2 theo Viziotix, tối ưu 3–4 theo Omron và bài báo Sensors. Đổi phần cứng hoặc quang học lên ≥3 px/ô có thể đem lại nhiều hơn bất kỳ thuật toán nào. Đây là suy luận, cần đo thực tế.
- Quy tắc "2 lần đọc giống nhau mới báo" của hệ thống tương đương bộ lọc mặc định của Dynamsoft (2/5 frame), nên đã ngang mức thương mại về chống đọc sai.
- Hướng PowerGrid (định vị theo texture, không cần finder) gợi ý một cải tiến: khi YOLO đã cho vùng và vận tốc, có thể ước lượng lưới ô trực tiếp từ chu kỳ texture thay vì để zxing tự tìm finder. Bộ giải `grid_sr` trong `qr/solvers` đi theo hướng này.

### Gaps
- Không tìm thấy PPM 2D tối thiểu chính thức của Cognex 2DMax/PowerGrid, Keyence, SICK, Datalogic hay Zebra. Tài liệu kỹ thuật chi tiết thường cần tài khoản đối tác.
- Không có thông tin công khai về thuật toán "super resolution" hay "multi-shot" của SICK/Keyence: ghép ảnh hay chỉ chọn frame tốt.
- Chưa tìm được nguồn về Scandit hay Datalogic cho bài toán này. Không có benchmark độc lập so sánh các hãng ở PPM thấp.

## (A) Thuật toán tốt hơn: ghép nhiều frame / siêu phân giải

### Takeaway
Có tài liệu chuyên cho QR: Kato et al. (Nagoya) làm siêu phân giải nhiều frame cho QR độ phân giải thấp, dùng **ràng buộc nhị phân** và ước lượng PSF từ finder pattern. Về ý tưởng, cách này vượt xa "dịch chuyển rồi lấy trung bình" mà hệ thống đang dùng. Phương pháp burst SR tổng quát (Wronski/Google 2019) dùng kernel regression cùng mô hình robustness và chạy khoảng 100 ms/12 MP trên di động, nên khả thi trên CPU với ROI nhỏ.

### Cited Findings
- Kato et al. (Nagoya Univ.) làm siêu phân giải nhiều frame cho QR độ phân giải thấp. Phương pháp dùng tính chất nhị phân của QR làm ràng buộc, và bản tiếng Nhật dùng finder pattern cố định để ước lượng PSF. Không đọc được số liệu trong PDF khi kiểm tra. — [Kato et al. PDF 672](https://pubdb.vislab.is.i.nagoya-u.ac.jp/~murase/pdf/672-pdf.pdf); [PDF 886](https://pubdb.vislab.is.i.nagoya-u.ac.jp/~murase/pdf/886-pdf.pdf); [IEEE 6065459](https://ieeexplore.ieee.org/document/6065459)
- Siêu phân giải mã 2D dựa trên sparse representation, khai thác cấu trúc của barcode (KSII 2017). — [koreascience](https://koreascience.kr/article/JAKO201718054544087.pdf)
- Một nghiên cứu PeerJ CS so sánh các mô hình SR một ảnh (EDSR, VDSR, ESPCN, SRCNN) trên QR độ phân giải thấp và kết luận SR cải thiện khả năng đọc mã bị suy giảm. Đây là SR một ảnh, không phải nhiều frame. — [PeerJ CS 2841](https://peerj.com/articles/cs-2841)
- **Wronski et al., "Handheld Multi-Frame Super-Resolution"** (SIGGRAPH 2019): ghép burst bằng kernel regression với kernel Gauss bất đẳng hướng theo structure tensor. Mô hình robustness dùng thống kê lân cận (trung bình và độ lệch chuẩn cục bộ) để loại vùng căn chỉnh sai hoặc bị che. Chạy khoảng 100 ms cho mỗi frame 12 MP trên điện thoại. — [arXiv 1905.03277](https://arxiv.org/pdf/1905.03277.pdf); [Google patent US12182967](https://patents.google.com/patent/US12182967)
- Có bản cài đặt lại mã nguồn mở (IPOL 2023, Lafenetre et al.) và bản Python/GPU trên GitHub. Bản gốc ghép tuần tự để tiết kiệm bộ nhớ. — [IPOL 2023/460](https://www.ipol.im/pub/art/2023/460/article_lr.pdf); [GitHub Jamy-L/Handheld-Multi-Frame-Super-Resolution](https://www.github.com/Jamy-L/Handheld-Multi-Frame-Super-Resolution); [CVPRW 2023 satellite](https://openaccess.thecvf.com/content/CVPR2023W/EarthVision/papers/Lafenetre_Handheld_Burst_Super-Resolution_Meets_Multi-Exposure_Satellite_Imagery_CVPRW_2023_paper.pdf)
- Một bằng sáng chế (US8150163) mô tả tìm kiếm sub-pixel để ước lượng giá trị bit của barcode ở độ phân giải cao hơn ảnh gốc, thiết kế cho ảnh bị aliasing. — [Patsnap US8150163B2](https://eureka.patsnap.com/patent-US8150163B2)

### Inferences
- Cách ghép hiện tại (phase correlation chỉ dịch chuyển → phóng ×4 → trung bình tối đa 8 ảnh) có hai điểm yếu:
  1. Phóng to trước rồi lấy trung bình là "interpolate-then-average". Nó làm mượt thay vì khôi phục tần số cao.
  2. Căn chỉnh chỉ dịch chuyển bỏ qua xoay/phối cảnh nhỏ giữa các frame.
- Hướng nâng cấp có cơ sở trong tài liệu, theo mức chi phí:
  - (a) Shift-and-add lên lưới mịn: đặt từng pixel gốc vào lưới ×2/×3 theo độ lệch sub-pixel, rồi chuẩn hóa theo trọng số, kiểu kernel regression của Wronski.
  - (b) Trọng số robustness để loại frame/vùng căn chỉnh sai.
  - (c) Căn chỉnh affine/homography bằng ECC (`cv2.findTransformECC`) hoặc theo 4 góc từ decoder/YOLO.
  - (d) Ràng buộc nhị phân/lưới ô như Kato: giải trực tiếp giá trị từng ô thay vì tái tạo ảnh.
  Bộ giải `grid_sr` của hệ thống đã đi hướng (d) nhưng chỉ chạy ở tiến trình nền.
- Với ROI khoảng 54×54 px và 8 frame, (a)+(b) gần như chắc chắn dưới 10 ms CPU bằng NumPy. Đây là ước lượng, chưa đo.

### Gaps
- Không lấy được số liệu định lượng (tỉ lệ đọc theo PPM, số frame) của Kato et al. vì PDF không trích được văn bản.
- Không tìm thấy công bố 2024–2026 về burst SR riêng cho QR có benchmark công khai.

## (A) Khử mờ chuyển động: Wiener / RL / TV / học sâu

### Takeaway
Nghiên cứu mới nhất cho QR (arXiv 2510.12098, 2025) cho thấy mạng lớn (Restormer, NAFNet) đạt 81–90% tỉ lệ giải mã sau fine-tune, nhưng tốn 0,8–0,9 s/ảnh 512² (phần cứng không ghi). Mạng nhẹ 0,28 M tham số chỉ đạt 49%. Với ROI nhỏ trên CPU, mạng lớn quá đắt. Cách dùng finder pattern để ước lượng PSF rồi giải tối ưu có chính quy hóa (van Gennip, IEEE TIP) là phương án cổ điển có cơ sở và hợp hơn với hệ thống, vì hệ thống đã biết hướng và độ dài vệt mờ từ vận tốc.

### Cited Findings
- arXiv 2510.12098 (Li, Guo, Li, Zhao, 2025), "Adaptive Edge-Guided Dual-Network Framework for Fast QR Code Motion Deblurring". Tập test 150 mã (100 tổng hợp, 50 thật), giải mã bằng ZBar. Tỉ lệ giải mã sau fine-tune trên GoPro+QRData: LENet 0,28 M tham số 49,33% (0,23–0,28 s); NAFNet-32 81,33% (0,794 s); Restormer 88,67% (0,838 s); EG-Restormer 90,00% (0,910 s); ADNet định tuyến nhẹ/nặng 90% (0,737 s). Phần cứng đo thời gian không được nêu. Bài không so với Wiener/RL; chỉ khẳng định định tính rằng phương pháp truyền thống thất bại với mờ nặng không đồng nhất. PSNR cao hơn không đồng nghĩa giải mã tốt hơn: EG-Restormer có PSNR thấp hơn Restormer nhưng tỉ lệ giải mã cao hơn. — [arXiv 2510.12098](https://arxiv.org/html/2510.12098v1)
- van Gennip et al., "A Regularization Approach to Blind Deblurring and Denoising of QR Barcodes" (arXiv 1410.6333, IEEE TIP). Pipeline: khử nhiễu → ước lượng PSF từ finder pattern góc trên trái (đã biết trước) → giải chập → phân ngưỡng. Không giả định dạng blur. — [arXiv 1410.6333](https://arxiv.org/pdf/1410.6333); [McGill PDF](https://www.math.mcgill.ca/rchoksi/pub/QR.pdf)
- Các hướng khác được 2510.12098 điểm lại: Pan et al. ước lượng kernel bằng KL-divergence dựa trên tính chất ký hiệu barcode; Sörös et al. lặp vòng làm sắc → ước lượng blur → giải mã dựa trên cạnh nổi bật; Dong et al. và Wang et al. dùng GAN cho QR mờ nặng. — [arXiv 2510.12098](https://arxiv.org/html/2510.12098v1)

### Inferences
- Hệ thống hiện dùng Wiener với PSF tuyến tính từ vận tốc × exposure (k = 0,05). Các nâng cấp rẻ hơn mạng nơ-ron, rút từ van Gennip/Sörös:
  - (1) Quét vài giá trị độ dài vệt mờ và k quanh giá trị ước lượng. Hệ thống đã quét 2/3/4,5/6,5 px khi chưa biết exposure.
  - (2) Hiệu chỉnh độ dài PSF bằng cạnh finder pattern đã biết.
  - (3) Dùng Richardson–Lucy vài vòng hoặc TV-deconvolution khi Wiener gây ringing.
  Chưa có nguồn định lượng so Wiener với RL trên QR, cần đo nội bộ.
- Mạng kiểu NAFNet trên ROI 54 px phóng ×4 (khoảng 216²) có thể tốn khoảng 1/5 so với ảnh 512², nhưng vẫn ở mức trăm ms trên CPU. Chưa đo, và cần dữ liệu fine-tune riêng (QRData +40 điểm tỉ lệ đọc so với chỉ GoPro cho NAFNet).

### Gaps
- Không có benchmark tốc độ CPU công khai cho NAFNet/DeblurGAN trên patch nhỏ. Không có so sánh định lượng Wiener, RL và TV trên QR thật.

## (A) Nhị phân hóa và lấy mẫu lưới ô trực tiếp

### Takeaway
Ít tài liệu công khai riêng cho QR dưới 3 px/ô. Các hãng mô tả chung chung (Dynamsoft: chuỗi BinarizationModes/DeblurModes có ưu tiên; Halcon: `small_modules_robustness`). Nguyên lý sub-pixel đã được chứng minh với 1D (Halcon đọc phần tử dưới 1 px khi blur nhỏ). Bằng sáng chế US8150163 mô tả ước lượng bit ở độ phân giải sub-pixel.

### Cited Findings
- Dynamsoft áp DeblurModes lên vùng đã định vị để tạo ảnh nhị phân; có chế độ DM_BASED_ON_LOC_BIN (dựa trên nhị phân cục bộ) và DM_THRESHOLD_BINARIZATION. — [Dynamsoft DeblurMode](https://www.dynamsoft.com/capture-vision/docs/core/enums/barcode-reader/deblur-mode.html)
- Halcon sub-pixel bar code reader: phần tử dưới 1 px đọc được nếu blur nhỏ và mã xoay nhẹ. — [MVTec Developers Corner](https://www.mvtec.com/knowledge-base/developers-corner/article/introduction-to-new-sub-pixel-feature-of-bar-code-reader)
- US8150163: tìm kiếm sub-pixel để ước lượng bit barcode vượt độ phân giải ảnh, dùng được trên ảnh aliasing. — [Patsnap US8150163B2](https://eureka.patsnap.com/patent-US8150163B2)

### Inferences
- Ở 2,2–2,6 px/ô, lấy mẫu trung tâm ô từ ảnh xám nội suy (bilinear/bicubic) theo homography 4 góc, rồi phân ngưỡng từng ô theo histogram hai đỉnh, giữ được nhiều thông tin hơn so với phóng ×4 rồi để binarizer cục bộ của zxing xử lý. Chưa có nguồn định lượng; đây là suy luận từ nguyên lý.
- Giá trị xám mỗi ô có thể dùng làm "soft decision" để lật các ô kém tin cậy nhất rồi thử lại Reed–Solomon (giải mã với erasure). zxing-cpp không có API cho việc này, phải tự cài bộ giải RS. Không tìm thấy nguồn công khai dùng cách này cho QR.

### Gaps
- Không tìm thấy tài liệu/issue zxing-cpp về giới hạn PPM tối thiểu hay hành vi binarizer ở ô dưới 3 px. Không có số liệu Sauvola so với zxing HybridBinarizer trên QR nhỏ.

## (B) Tốc độ: thứ tự decoder, early-exit, song song; so sánh zxing-cpp, ZBar, Dynamsoft

### Takeaway
Không có benchmark độc lập so zxing-cpp/ZBar/Dynamsoft ở PPM thấp. Mọi benchmark tìm được đều do Dynamsoft (đối thủ thương mại) công bố. Theo các benchmark đó, Dynamsoft dẫn đầu, còn zxing-cpp yếu hơn ZBar trên ảnh thực tế tổng quát. Cơ chế early-exit kiểu ExpectedBarcodesCount của Dynamsoft khớp với chuỗi rẻ→đắt hệ thống đang dùng.

### Cited Findings
- Benchmark Python của Dynamsoft trên 170 ảnh thực tế: Dynamsoft 90,6%, PyZBar 71,2%, ZXing-Cpp 65,9%. Đây là số của vendor. — [Dynamsoft: ZXing vs ZBar vs Dynamsoft (Python)](https://www.dynamsoft.com/codepool/python-zxing-zbar-barcode.html)
- Benchmark QR của Dynamsoft (536 ảnh thực tế, 7 thư viện), cũng là số của vendor. — [Dynamsoft QR benchmark](https://www.dynamsoft.com/codepool/qr-code-reading-benchmark-and-comparison.html)
- Dynamsoft nói preset mặc định của họ đọc được mọi biến thể độ phân giải thấp, thiếu sáng, chói và mờ của Code 128 và QR. Tuy nhiên đó là dữ liệu tự tạo (tổng hợp), không phải ảnh thật. — [Dynamsoft: low-resolution, low-light, glare](https://www.dynamsoft.com/codepool/accurate-barcode-reader-low-resolution-low-light-glare.html)
- ExpectedBarcodesCount = N: dừng thử các chế độ khi đã thấy N mã. — [Dynamsoft ExpectedBarcodesCount](https://www.dynamsoft.com/barcode-reader/docs/core/parameters/reference/expected-barcodes-count.html)
- arXiv 2510.12098 định tuyến theo độ mờ (phương sai Laplacian): ảnh mờ nhẹ qua mạng nhẹ, mờ nặng qua mạng nặng. Cách này giảm khoảng 19% thời gian trung bình mà giữ nguyên 90% tỉ lệ đọc; định tuyến ngẫu nhiên chỉ đạt 72%. — [arXiv 2510.12098](https://arxiv.org/html/2510.12098v1)

### Inferences
- Áp dụng ý định tuyến cho `PassDecoder`: đo phương sai Laplacian hoặc độ tương phản ROI rồi bỏ qua các bước vô ích. Ví dụ ROI quá mờ thì bỏ zxing thẳng, đi ngay Wiener; ROI sắc thì không chạy Wiener. Cách này có thể cắt phần lớn 200–350 ms của detection thất bại. Ước lượng, cần đo.
- Song song: zxing-cpp và cv2 nhả GIL trong phần C++, nên thread pool theo từng ROI hoặc từng bước cascade có thể tăng thông lượng trên CPU nhiều lõi. Chưa kiểm chứng trong tài liệu tìm được; WeChat detector toàn cục không khóa (theo CLAUDE.md) là rủi ro khi chạy đa luồng.
- Hệ thống ghi zxing-only đọc 84% frame, thêm WeChat 99% frame sắc. Vậy chi phí thật nằm ở frame mờ hoặc thất bại. Ưu tiên tối ưu nhánh thất bại (fail fast) hơn nhánh thành công.

### Gaps
- Không có benchmark độc lập (không phải vendor) ở PPM 2–3 cho zxing-cpp, ZBar, WeChat và Dynamsoft. Cần tự đo trên dữ liệu hiện trường `data/field/raw`.

## (C/A) An toàn chống đọc sai: regex nội dung, kiểm tra vị trí, ECC, bỏ phiếu

### Takeaway
Ngành dùng bỏ phiếu đa frame (Dynamsoft mặc định 2/5 frame giống nhau). Hệ thống đã có quy tắc tương đương. Lỗ hổng lớn nhất hiện tại: **chưa lọc nội dung theo regex `^\d{12}#\d{12}$`**, dù định dạng đã chốt. Đây là biện pháp rẻ nhất và mạnh nhất còn thiếu.

### Cited Findings
- Dynamsoft MultiFrameResultCrossFilter: frameWindow 5, minConsistentFrames 2 (mặc định cho barcode). — [Dynamsoft CrossVerificationCriteria](https://www.dynamsoft.com/capture-vision/docs/mobile/programming/maui/api-reference/utility/cross-verification-criteria.md)
- Dynamsoft có cơ chế lọc theo định dạng và số lượng mã kỳ vọng (ExpectedBarcodesCount; lựa chọn định dạng). — [Dynamsoft barcode formats and count](https://github.com/dynamsoft-docs/barcode-reader-docs/blob/master/programming/features/barcode-formats-and-count.md)

### Inferences
- Thêm `code_pattern=r"^\d{12}#\d{12}$"` gần như loại hết đọc sai ngẫu nhiên. Mã 25 ký tự cố định cùng QR mức M có Reed–Solomon thì xác suất ra đúng định dạng mà sai nội dung rất thấp. Có thể cân nhắc nới quy tắc 2 lần đọc thành 1 lần đọc khi bước giải mã là zxing/WeChat chuẩn (không phải tái tạo từ `grid_sr`), để tăng tỉ lệ lượt đọc từ 74,6%. Cần đánh giá trên dữ liệu thật trước khi đổi, vì nội dung đọc sai vẫn có thể khớp regex.
- Kết quả từ bộ giải tái tạo (vẽ lại mã, ghép nhiều frame) rủi ro đọc sai cao hơn, nên giữ yêu cầu bỏ phiếu hoặc yêu cầu số lỗi RS đã sửa thấp. zxing-cpp có trả thông tin này hay không chưa được xác minh trong lần tìm này.

### Gaps
- Không tìm thấy tài liệu ngành về ngưỡng "% ECC đã dùng" để từ chối kết quả. Cognex/Keyence có thông số chất lượng mã (verification theo ISO 15415), nhưng không tìm được cách họ dùng nó để từ chối lượt đọc.
- Không tìm thấy số tỉ lệ đọc sai (misread rate) công bố của các hãng.
