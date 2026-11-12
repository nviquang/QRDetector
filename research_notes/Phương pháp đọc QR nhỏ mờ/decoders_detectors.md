# QR decoders and detectors for hard cases (small ~2 px/module, blur, low contrast, many codes)

Research notes, 2026-11-06. Method note: the WebSearch/WebFetch tools failed in this session (model error), so sources were fetched directly with curl (vendor pages, GitHub raw, arXiv API, OpenAlex API, PyPI JSON). The MVTec site refused connections; the HALCON documentation was read through the Wayback Machine (HALCON 23.11 docs). Cognex, Matrox/Zebra, Sick and Scandit spec pages could not be retrieved (login or JS walls); see the Gaps sections.

## 1. Published benchmarks: which decoders read the most hard codes, and vendor-stated minimum module size

### Takeaway
The only reproducible multi-library QR benchmark is the BoofCV dataset (536 images, 1,232 QR codes, 16 categories). On it, a vendor-run 2026 update puts Dynamsoft first (84.75%), then BoofCV (60.69%) and OpenCV WeChat (48.89%), with ZXing Java (31.87%) and ZBar (38.95%) behind. In the blurred category Dynamsoft scores 67.7%, WeChat 46.2%, BoofCV 38.5% and ZXing 21.5%. No public benchmark tests zxing-cpp 2.x/3.x against these libraries, and none isolates the ~2 px/module case. Among the vendor-stated minimums found, HALCON's is the clearest: its parameter range goes down to 1 px/module, but MVTec recommends 3–4 px.

### Cited Findings
**BoofCV independent study (Peter Abeles, V3, updated 19 Mar 2019; author's own library included, so not neutral)**
- Libraries evaluated: BoofCV 0.33, OpenCV 4.0.1, Quirc (Feb 2018), ZBar 0.10, ZXing 3.3.3 (Java). The categories are blurred, brightness, bright spots, close, curved, damaged, glare, high version, lots, monitor, nominal, non-compliant, pathological, perspective, rotated and shadows. Scoring is F-measure with a loose 10% overlap match, and each category carries equal weight. — [BoofCV Performance:QrCode](https://boofcv.org/index.php?title=Performance:QrCode)
- Conclusions: "No library dominates all categories". BoofCV is best or a close second everywhere except non-compliant and pathological codes. ZBar beats ZXing in most categories. OpenCV 4.0's scanner "needs a lot of work" and could detect only one QR per image. ZXing was run with TRY_HARDER because its default detection rate was low. — [BoofCV Performance:QrCode](https://boofcv.org/index.php?title=Performance:QrCode)
- Runtime: ignoring "lots", ZXing was fastest. Including "lots", BoofCV was fastest by a large margin. ZBar was slowest and about 20x slower than BoofCV on "lots". The per-category numbers are published only as charts, so I could not extract them as text. — [BoofCV Performance:QrCode](https://boofcv.org/index.php?title=Performance:QrCode)

**Dynamsoft extension of the BoofCV dataset (vendor-run; by Lihang Xu; page "Updated Nov 06, 2026"; Intel i5-10400, browser harness; detection counted at >20% polygon overlap)**
- Versions: Dynamsoft DBR 11.6.5000, Scandit 6.16 (measured in 2021; Scandit's current release is 8.4.0), Aspose 13.9, BoofCV 0.43.1, ZXing 3.5.1 (Java, not zxing-cpp), pyzbar 0.1.9, and OpenCV 4.7.0.72 WeChat. — [Dynamsoft QR benchmark](https://www.dynamsoft.com/codepool/qr-code-reading-benchmark-and-comparison.html)
- Reading rate (%) by category:

| Category | Dynamsoft | BoofCV | ZXing | ZBar | WeChat | Scandit(2021) | Aspose |
|---|---|---|---|---|---|---|---|
| blurred | 67.69 | 38.46 | 21.54 | 35.38 | 46.15 | 33.85 | 36.92 |
| brightness | 81.18 | 78.82 | 52.94 | 50.59 | 23.53 | 52.94 | 51.76 |
| bright_spots | 41.24 | 27.84 | 20.62 | 19.59 | 24.74 | 8.25 | 29.9 |
| close | 95 | 100 | 5 | 12.5 | 67.5 | 22.5 | 25 |
| curved | 75 | 56.67 | 31.67 | 35 | 43.33 | 31.67 | 36.67 |
| damaged | 60.47 | 16.28 | 20.93 | 25.58 | 30.23 | 27.91 | 27.91 |
| glare | 84.91 | 32.08 | 20.75 | 35.85 | 58.49 | 43.4 | 20.75 |
| high_version | 97.3 | 40.54 | 5.41 | 27.03 | 18.92 | 78.38 | 35.14 |
| lots | 100 | 99.76 | 82.86 | 18.1 | 0 | 14.52 | 97.14 |
| monitor | 100 | 82.35 | 0 | 0 | 94.12 | 11.76 | 5.88 |
| nominal | 93.59 | 89.74 | 53.85 | 66.67 | 71.79 | 64.1 | 65.38 |
| noncompliant | 96.15 | 3.85 | 15.38 | 50 | 76.92 | 61.54 | 11.54 |
| pathological | 95.65 | 43.48 | 34.78 | 65.22 | 91.3 | 0 | 78.26 |
| perspective | 68.57 | 80 | 37.14 | 42.86 | 42.86 | 65.71 | 34.29 |
| rotations | 99.25 | 96.24 | 42.11 | 48.87 | 32.33 | 99.25 | 69.17 |
| shadows | 100 | 85 | 65 | 90 | 60 | 90 | 95 |
| **average** | **84.75** | **60.69** | **31.87** | **38.95** | **48.89** | **44.11** | **45.04** |

  — [Dynamsoft QR benchmark](https://www.dynamsoft.com/codepool/qr-code-reading-benchmark-and-comparison.html)
- Mean time per image: Dynamsoft 116 ms, BoofCV 105 ms, ZBar 157 ms, ZXing 180 ms, Aspose 346 ms, WeChat 758 ms, Scandit 1400 ms. Per-image JSON results and the runner are published, so the numbers can be audited. — [Dynamsoft QR benchmark](https://www.dynamsoft.com/codepool/qr-code-reading-benchmark-and-comparison.html)
- Note: WeChat reads 0% in "lots". In this test it fails when many codes are visible at once. — [Dynamsoft QR benchmark](https://www.dynamsoft.com/codepool/qr-code-reading-benchmark-and-comparison.html)

**Vendor-stated module size limits**
- HALCON `find_data_code_2d`: `module_size_min` is the "Minimum size of the modules in the image in pixels". Its range is 1–100. The default is 6 in standard mode, 2 in enhanced mode and 1 in maximum mode. MVTec notes that "for optimal reading performance a module size of at least 3-4 pixels is recommended". — [HALCON 23.11 set_data_code_2d_param (archived)](https://web.archive.org/web/2024/https://www.mvtec.com/doc/halcon/2311/en/set_data_code_2d_param.html)
- OpenCV `QRCodeDetectorAruco` (OpenCV 4.8+): `minModuleSizeInPyramid` is "The minimum allowed pixel size of a QR module in the smallest image in the image pyramid, default 4.f". Other parameters are maxRotation (default π/12), maxPenalties (default 0.4) and maxColorsMismatch (default 0.2). — [OpenCV objdetect.hpp](https://raw.githubusercontent.com/opencv/opencv/4.x/modules/objdetect/include/opencv2/objdetect.hpp)
- WeChat QR (opencv_contrib): it adds a "lighten super-resolution CNN model for QR code, called QRSR" specifically "to improve the performance of tiny QR code". It also adds an SSD/MobileNetV2-like CNN detector, area-based finder-pattern detection, and "trying more binarization methods" built on top of zxing-cpp. — [wechat_qrcode README](https://raw.githubusercontent.com/opencv/opencv_contrib/4.x/modules/wechat_qrcode/README.md)

### Inferences
- The user's measured ordering (union of decoders ~51%, zxing alone ~25%, WeChat CNN+SR adding little) matches the "blurred" column: the open-source tools sit at 21–46% there, while Dynamsoft reaches 68%. This is the strongest available evidence that a commercial engine could recover a meaningful share of the failed ROIs. It is not proof, because the dataset is phone imagery, not ~2 px/module industrial frames.
- WeChat's SR is trained for phone-scale "tiny" codes. Its weak gain at 2 px/module is consistent with HALCON's guidance that below 3–4 px a reader needs special handling, not just upsampling.
- The benchmark used ZXing Java 3.5.1. zxing-cpp 2.x/3.x has a different, improved detector, so the 31.87% figure should not be taken as zxing-cpp's score.

### Gaps
- No public benchmark tests zxing-cpp 2.x/3.x on the BoofCV dataset, and none tests at a controlled ~2 px/module.
- I found no independent (non-vendor) benchmark that includes Dynamsoft, HALCON, Cognex, Matrox/Zebra Aurora, Sick or Scandit 7/8.
- I could not retrieve vendor-stated minimum module sizes for Cognex (DataMan / VisionPro ID), Matrox/Zebra Aurora Imaging Library, Sick or Scandit; their pages were behind logins or JavaScript. Values I remember (e.g. "~1.5–2 px/module" claims) are not reported here because I could not verify them.
- The BoofCV per-category numbers exist only as chart images on the page.

## 2. Commercial SDKs usable from Python on Windows CPU: licensing and low-resolution / deblur modes

### Takeaway
Dynamsoft and HALCON both ship official Python wheels that run on Windows x64 CPU. Each documents controls aimed at this problem. Dynamsoft offers DeblurModes (including a neural-network deblur and a "DataMatrixQRCodeDeblur" model) and BarcodeScaleModes, which upsample by powers of 2 until a target module size is reached. HALCON offers `small_modules_robustness='high'` together with module_size_min, and module_gap settings. Both are licensed commercially: Dynamsoft by annual quote, HALCON by development plus runtime licenses. A 30-day Dynamsoft trial makes an on-site A/B test cheap.

### Cited Findings
- Dynamsoft Python packages: `dynamsoft-barcode-reader-bundle` 11.6.5000 and `dynamsoft-capture-vision-bundle` 3.6.5000 (uploaded 2026-10-29) ship `win_amd64` wheels. — [PyPI dbr bundle](https://pypi.org/pypi/dynamsoft-barcode-reader-bundle/json), [PyPI DCV bundle](https://pypi.org/pypi/dynamsoft-capture-vision-bundle/json)
- Dynamsoft `DeblurModes` (DecodeBarcodesStage) candidate modes: DM_DIRECT_BINARIZATION, DM_THRESHOLD_BINARIZATION, DM_GRAY_EQUALIZATION, DM_SMOOTHING, DM_MORPHING, DM_DEEP_ANALYSIS, DM_SHARPENING, DM_BASED_ON_LOC_BIN, DM_SHARPENING_SMOOTHING, DM_NEURAL_NETWORK, DM_SKIP. DM_NEURAL_NETWORK takes a `ModelNameArray` whose candidates include "DataMatrixQRCodeDeblur". — [Dynamsoft DeblurModes](https://www.dynamsoft.com/capture-vision/docs/core/parameters/reference/barcode-reader-task-settings/deblur-modes.html)
- Dynamsoft `BarcodeScaleModes` (BSM_AUTO, BSM_LINEAR_INTERPOLATION) takes `ModuleSizeThreshold` and `TargetModuleSize`. When the module size is below the threshold, "the barcode image will be enlarged by a scale factor of N (the value of N is a power of 2) till N * modulesize >= TargetModuleSize". — [Dynamsoft BarcodeScaleModes](https://www.dynamsoft.com/capture-vision/docs/core/parameters/reference/barcode-reader-task-settings/barcode-scale-modes.html)
- Dynamsoft pricing is quote-based. The quote form asks for annual scan volume, device count and vCPUs used for barcode reading "per year". A 30-day free trial is offered. — [Dynamsoft store/quote](https://www.dynamsoft.com/store/dynamsoft-barcode-reader/), [Dynamsoft QR benchmark](https://www.dynamsoft.com/codepool/qr-code-reading-benchmark-and-comparison.html)
- HALCON Python: `mvtec-halcon` 26050.0.0 (2026-05-19) provides "Native Python language bindings for MVTec HALCON". It requires an installed HALCON runtime and license. — [PyPI mvtec-halcon](https://pypi.org/pypi/mvtec-halcon/json)
- HALCON `small_modules_robustness`: setting it to 'high' "increases the likelihood of being able to decode data codes with very small module sizes". `module_size_min` should then be set to the expected size. It "can significantly increase the internal memory usage", and "the maximal accepted image size is bisected". The default is 'low'. — [HALCON set_data_code_2d_param (archived)](https://web.archive.org/web/2024/https://www.mvtec.com/doc/halcon/2311/en/set_data_code_2d_param.html)
- HALCON `module_gap_min/max` ('no'/'small'/'big'): the QR default is 'small', or 'big' in enhanced mode. `contrast_tolerance` 'high' improves robustness to strong local contrast variation, and 'any' runs both algorithms. `default_parameters` selects standard_recognition, enhanced_recognition or maximum_recognition. — [HALCON set_data_code_2d_param (archived)](https://web.archive.org/web/2024/https://www.mvtec.com/doc/halcon/2311/en/set_data_code_2d_param.html)
- Open-source alternative: BoofCV is available to Python through `pyboof` 0.43.1 (Py4J, Apache-2.0, last released 2023-06-01; needs a JVM). — [PyPI pyboof](https://pypi.org/pypi/pyboof/json)

### Inferences
- For this pipeline (ROIs already cropped by qrdet), the cheapest experiment is to feed the same failed ROIs to two configurations. The first is Dynamsoft with BarcodeScaleModes (threshold around 4, target around 6–8) plus DeblurModes including DM_NEURAL_NETWORK and DM_DEEP_ANALYSIS. The second is HALCON QR with `default_parameters='maximum_recognition'`, `small_modules_robustness='high'` and `module_size_min=1` or `2`. Count the extra reads over the union of the current decoders.
- HALCON's "image size bisected" warning favours passing small ROIs rather than full 2448-wide bands. The current architecture already does this.

### Gaps
- No public per-device or per-vCPU price was found for Dynamsoft or HALCON. Cognex VisionPro (Windows/.NET; no official Python wheel found) and Scandit (no PyPI package; mainly mobile/web/Linux SDKs) were not verified for Windows Python CPU use.
- No vendor publishes a decode rate at ~2 px/module for these modes.

## 3. Detecting small QR codes in large images without merging adjacent codes

### Takeaway
The standard tools are tiling/slicing (SAHI: +5–7 AP from slicing at inference alone, +13–15 AP with slicing-aided fine-tuning), segmentation-based detectors built for ultra-high-resolution images, and dense-object YOLO variants for barcodes. Merged adjacent tags are usually an NMS/IoU or mask-resolution problem. qrdet exposes `nms_iou` (default 0.3) and `conf_th` (0.5). Finder-pattern detectors (BoofCV, OpenCV Aruco) never merge two codes, because each code is assembled from its own three finder patterns. This makes them a natural way to split a merged box.

### Cited Findings
- SAHI (Akyon et al., 2022): slicing-aided inference raised AP by 6.8%, 5.1% and 5.3% for FCOS, VFNet and TOOD on VisDrone/xView. Adding slicing-aided fine-tuning raised AP by 12.7%, 13.4% and 14.5% cumulatively. It is integrated with YOLOv5, Detectron2 and MMDetection. — [arXiv 2202.06934](http://arxiv.org/abs/2202.06934)
- Ultra-high-resolution barcode detection (ICIP 2021): a modified RPN plus a Y-Net segmentation network on images larger than 10k×10k ran end to end in 16 ms. It was 2.5x faster than YOLOv4 and 5.9x faster than Mask R-CNN, with +5.5% and +47.1% mAP respectively, on a synthetic dataset. — [Fast, Accurate Barcode Detection in UHR Images, ICIP 2021](https://doi.org/10.1109/icip42928.2021.9506134)
- YOLO-Barcode (Computer Optics, 2024) "copes well with a large number of densely spaced barcodes". On ZVZ-real it reaches F1 98.6% against 88.9% for the earlier segmentation-based DilatedModel, and is 4x faster. — [YOLO-Barcode](https://doi.org/10.18287/2412-6179-co-1424)
- Universal Barcode Detector via Semantic Segmentation (ICDAR 2019) reaches a detection rate of 0.995 on the ArTe-Lab 1D Medium dataset. — [Zharkov & Zagaynov, ICDAR 2019](https://doi.org/10.1109/icdar.2019.00139)
- BarBeR (Vezzali et al., ICPR 2024 / EAAI 2025) is an open benchmark of 8,748 annotated barcode images (1D and 2D). It includes YOLO, RT-DETR, Detectron2 and classical localizers such as Sörös & Flörkemeier's blur-resistant joint 1D/2D localizer, along with the BaFaLo fast segmentation method. — [EAAI 2025 abstract](https://doi.org/10.1016/j.engappai.2025.110259), [BarBeR README](https://raw.githubusercontent.com/Henvezz95/BarBeR/main/README.md)
- qrdet API: `QRDetector(model_size='s', conf_th=0.5, nms_iou=0.3)`. The README says to "Increase this number if you find problems with duplicated detections". — [qrdet README](https://raw.githubusercontent.com/Eric-Canas/qrdet/main/README.md); latest PyPI release 2.5 (2024-06-15), [PyPI qrdet](https://pypi.org/pypi/qrdet/json)
- Multi-QR localization from finder patterns, plus perspective-distortion identification from edge directions and projections, is reported as "computationally efficient, works well for low-resolution images". — [J. Imaging 2020, 6(7):67](https://doi.org/10.3390/jimaging6070067)
- EgoQR (Meta, 2024) is a detection plus enhanced-decoding pipeline for high-resolution, wide-FOV images with motion blur. It reports a "34% improvement in reading the code compared to an existing state of the art QR code readers". — [arXiv 2410.05497](http://arxiv.org/abs/2410.05497)
- MU R-CNN (2019) is instance segmentation for QR tags in Industry 4.0. It is motivated by Mask R-CNN failing to guarantee complete masks on textured, low-quality QR tags. — [Future Internet 11(9):197](https://doi.org/10.3390/fi11090197)

### Inferences
- When qrdet merges two tags, three fixes are cheap. (a) Lower `nms_iou` and prefer the mask over the box. Splitting the mask with connected components or a distance transform separates touching instances that NMS keeps as one box. (b) Run a finder-pattern detector (OpenCV Aruco, BoofCV) inside each large box. Three-finder-pattern groups define individual codes and their quads. (c) Reject or split boxes whose aspect ratio or area exceeds what one tag can be. Option (c) conflicts with the project rule against size filtering for variable-length tags, so a two-code split test is safer than a hard size gate.
- SAHI-style tiling mainly helps recall on tiny objects. At imgsz 1600 on a 2448-wide band, objects are already near native resolution, so tiling is unlikely to fix merging and costs more inference.

### Gaps
- I found no paper that specifically measures adjacent-QR merging rates or evaluates de-merging methods for QR.
- I found no published comparison of YOLO detection recall versus QR module size (px/module).

## 4. Academic work 2018–2026 on robust QR decoding (binarization, deblurring, geometry), with numbers

### Takeaway
Recent numeric gains come mainly from QR-specific deblurring. A 2026 grey-box motion-parameter recovery method decodes 93.1% of 955 handheld motion-blurred photos, against 83.6% for the best fine-tuned deblurring network. Edge-guided Transformer deblurring (ADNet, 2025) also helps. QR-tailored adaptive binarization (illumination equalization) reaches 78–99% recognition with WeChat/zxing. Most papers use phone imagery at larger module sizes than 2 px, and many GAN-deblurring papers report no comparable decode rates.

### Cited Findings
- Motion-blurred QR recovery (arXiv, Oct 2026) studies how accurately the motion must be known. Tolerances shrink as blur grows and are tightest under uniform speed. Errors in length, direction and speed profile interact. The proposed grey-box pipeline predicts the corner trajectory with two compact networks, runs a tolerance-guided candidate search, alternates image and path fitting, then applies regularised linear inversion. It recovers the exact payload on 93.1% of 955 handheld motion-blurred photos (4 phone models, 4 motion categories), against 83.6% for the strongest fine-tuned deblurring network, a 58.0% cut in decoding error. — [arXiv 2610.34788](http://arxiv.org/abs/2610.34788)
- ADNet / EG-Restormer (arXiv, Oct 2025) embeds an Edge-Guided Attention Block (explicit edge priors) in a Transformer for QR motion deblurring. A lightweight LENet handles mild blur, and the system selects the network adaptively by blur severity. The authors claim state-of-the-art decoding rate; the numbers are not in the abstract. Code: github.com/leejianping/ADNet. — [arXiv 2510.12098](http://arxiv.org/abs/2510.12098)
- Fast adaptive binarization via dynamic illumination equalization (Electronics, 2023) locates finder patterns with edge enhancement, then equalizes illumination. It reports recognition rates of 78.26–98.75% across strong-light, weak-light and shadow cases with WeChat and ZXing decoders, at 0.0164 s per image. It targets logistics sorting. — [Electronics 12(19):4134](https://doi.org/10.3390/electronics12194134)
- Adaptive binarization for warehouse sorting (Sensors, 2019) selects the block window for local thresholding adaptively, guided by the QR structure, to handle uneven illumination in real time. The abstract claims superiority without giving numbers. — [Sensors 19(24):5466](https://doi.org/10.3390/s19245466)
- GAN deblurring plus a modified local adaptive threshold using integral images (IEEE CASE, 2020) targets motion-blurred QR. The abstract gives no numbers. — [CASE 2020](https://doi.org/10.1109/case48305.2020.9216945)
- GAN plus attention (WGAN-div, ECA) motion-deblur QR recognition (IJCIS, 2024) reports "significant improvements" in time and recognition accuracy on GoPro and a self-built QR set. The abstract gives no numbers. — [IJCIS 2024](https://doi.org/10.1007/s44196-024-00450-7)
- An embedded YOLOv3 plus GAN-deblur QR system on Xilinx ZYNQ (IEEE MultiMedia, 2024) addresses Gaussian blur with a relative-entropy loss. — [IEEE MultiMedia 2024](https://doi.org/10.1109/mmul.2024.3459003)
- Survey context: Deep Learning in Barcode Recognition, a systematic review (IEEE Access, 2022). — [IEEE Access 2022](https://doi.org/10.1109/access.2022.3143033)

### Inferences
- The 2026 result favours model-based inversion with a known motion path, rather than blind CNN deblurring, when the motion is constrained. A conveyor is the best case for this: the direction is known, speed is roughly constant, and exposure is known. The project's Wiener filter driven by tracked velocity is a simple form of the same idea. The paper's finding that tolerances are "tightest under uniform speed" implies that blur length (velocity × exposure) must be estimated precisely. That supports sweeping a few candidate lengths around the estimate, as the project already does with 2/3/4.5/6.5 px.
- The binarization papers target uneven lighting at normal module sizes. At ~2 px/module the limit is sampling and blur, not lighting. Adaptive-binarization gains (up to 98.75%) should therefore not be expected to carry over.

### Gaps
- I found no paper reporting decode rate as a function of px/module below 3 px for any method.
- Sauvola/Wolf versus CNN binarization comparisons specific to QR, with numbers, were not found within the time budget.
- Full-text decode-rate tables for ADNet and the GAN papers were not retrieved; only abstracts were read.
- zxing-cpp 3.1.1 (PyPI, 2026-07-29, win_amd64 wheel available) has no published cross-library benchmark — [PyPI zxing-cpp](https://pypi.org/pypi/zxing-cpp/json).
