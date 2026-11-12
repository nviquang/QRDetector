# Decoding QR codes at very low resolution (~1.5–3 px/module): super-resolution, model-based/soft decoding, limits

Research notes, 2026-11-06. Context: conveyor, grayscale, QR V1-L, ~1.8–2 px/module, CPU only. Current pipeline (zxing-cpp + warp + WeChat ± CNN/SR + 8-frame shift-and-add + Wiener) decodes ~51% of static ROIs.

Method note: the WebSearch/WebFetch tools failed in this session (model error), so sources were found through the arXiv API, the OpenAlex API, the GitHub API, Google Patents and direct downloads with curl. Paywalled full texts (IEEE GCCE, ICDAR 2011, MDPI Sensors HTML was blocked) were read only as abstracts. Numbers below come from the text I read. Anything I could not read is listed under Gaps.

---

## Q1. Super-resolution for barcodes/QR (single-image, multi-frame, structure-aware priors): what px/module, what decode gains?

### Takeaway
The most relevant published result is **multi-frame SR with a binary (and grid) constraint for QR, by Kato et al. (ICDAR 2011, extended 2013)**. It reached 98% recognition on real low-resolution video, +15.7 points over conventional multi-frame SR. The current shift-and-add + Wiener step is a weaker form of this idea because it has no binary/grid prior. For single-image SR, the strongest reproducible CPU result is **Mosaic-SR (ICIP 2025, Univ. Modena + Datalogic)**: about 1–4 ms per 128×128 crop on one CPU thread, raising zbar decodes at 1.0–1.6 PPM inputs from 2,336 (bicubic) to 3,714 out of 9,562. Generic CNN/GAN SR papers for QR mostly report synthetic results or omit the input px/module.

### Cited Findings
**Multi-frame / structure-aware SR (classical)**
- Kato, Deguchi, Takahashi, Ide (Murase lab), "Low Resolution QR-Code Recognition by Applying Super-Resolution Using the Property of QR-Codes", ICDAR 2011. Multi-frame SR (several LR frames → one HR image) with a **binary-pattern constraint**, because border pixels between black and white modules are ambiguous. Reports a **98% recognition rate, a 15.7% improvement over conventional SR**. The abstract gives no px/module figure. — [IEEE DOI 10.1109/ICDAR.2011.201 (abstract via OpenAlex)](https://doi.org/10.1109/icdar.2011.201)
- Kato, Takahashi, Deguchi, Ide, "Two-step Super-Resolution with Binary and Grid Constraints for Low Resolution QR-Code Recognition" (2013, Japanese journal paper, IRDB). Two SR stages, one tuned for **detection** and one for **decoding**. Uses **binary + grid constraints** in the SR objective and estimates the **PSF from the patterns every QR shares (finder/timing)**. On real video, it gives a high recognition rate on QR images too low-resolution to read as captured. The abstract has no numeric rate. — [IRDB record via OpenAlex search](https://api.openalex.org/works?search=Two-step%20Super-Resolution%20with%20Binary%20and%20Grid%20Constraints)
- Chinese 2015 paper (Computer and Digital Engineering), "QR-code Recognition Method in Super-resolution Image Synthesis Based on Maximum Likelihood". Phone video at low resolution, nonlinear fitting of each frame by maximum likelihood, then synthesis of a super-resolved barcode using the binary property of QR. The abstract has no numbers. — [OpenAlex record](https://api.openalex.org/works?search=QR-code%20Recognition%20Method%20in%20Super-resolution%20Image%20Synthesis%20Based%20on%20Maximum%20Likelihood)
- Yang, Liu, Gao, "Two-Dimensional Barcode Image Super-Resolution Reconstruction via Sparse Representation", ISCA 2013. Sparse-coding SR with Kirsch-gradient / edge-direction features. The abstract has no decode numbers. — [DOI 10.2991/isca-13.2013.55](https://doi.org/10.2991/isca-13.2013.55)

**Single-image learned SR for 2D barcodes**
- **Mosaic-SR** (Vezzali, Vorabbi, Grana, Bolelli; ICIP 2025; with Datalogic). 2× SR made of cascaded tiny fully-connected nets on 7×7 patches (1.2k / 3.8k / 14k parameters). It predicts per-patch uncertainty and refines only uncertain patches. Setup: BarBeR dataset, 1,366 QR/DataMatrix/Aztec crops of at least 3.2 PPM, bicubic-downsampled to **1.0–1.6 PPM** (HR targets 2.0–3.2 PPM), 9,562 LR/HR pairs, 128×128 grayscale, 4-fold CV. Decoder: pyzbar. Timing: single thread, AMD Threadripper Pro 5965WX and Raspberry Pi 3B+.
  - Results (number of decodes out of 9,562): **bicubic 2,336 (0.046 ms)**; Mosaic-SR fast setting 3,330 (0.88 ms PC / 23 ms RPi); mid setting 3,517 (1.7 ms / 44 ms); best setting **3,714 (4.2 ms / 110 ms)**. Baselines: ESPCN 3,596 (7.1 ms), FSRCNN 3,602 (13.5 ms), IMDN-RTC 3,695 (11 ms), QRCNN (Shindo) 3,488 (172 ms).
  - Without upscaling, **none** of the LR patches decoded.
  - Code and models are public (TFLite + a C++ im2col).
  - Caveats: synthetic downsampling, no motion blur, decoder is zbar rather than zxing.
  - — [Paper PDF](https://federicobolelli.it/pub_files/2025icip.pdf); [GitHub Henvezz95/Mosaic-SR](https://github.com/Henvezz95/Mosaic-SR); [BarBeR dataset](https://ditto.ing.unimore.it/barber/)
- Shindo et al., "Super Resolution for QR Code Images" (QRCNN / QRGAN, based on SRResNet/SRGAN but simplified), IEEE GCCE 2022. The abstract gives no decode-rate numbers. — [DOI 10.1109/GCCE56475.2022.10014154](https://doi.org/10.1109/gcce56475.2022.10014154)
- Tanaka, Tatsumi, Shindo, Watanabe, "Integrating QR Code Characteristics into Super-Resolution Method", GCCE 2024. The SR loss focuses on **module-centre regions** because the module-centre value carries the data. The abstract says effectiveness was confirmed by readability but gives no numbers. — [DOI 10.1109/GCCE62371.2024.10760486](https://doi.org/10.1109/gcce62371.2024.10760486)
- Sancar, "Reconstructing unreadable QR codes: a deep learning based super resolution strategy", PeerJ Computer Science 2025.
  - On **4,593 real-world scans that OpenCV QRCodeDetector could not decode**, EDSR / VDSR / ESPCN / SRCNN made **4,261 / 4,229 / 4,255 / 4,042** readable (about 88–93%).
  - On 2,899 simulated codes unreadable by WeChat, they made 2,891 / 2,884 / 2,433 / 2,560 readable.
  - Training used 16,000 synthetic codes.
  - Caveat: the baseline is OpenCV's weak QRCodeDetector, and px/module is not stated in the abstract.
  - — [DOI 10.7717/peerj-cs.2841](https://doi.org/10.7717/peerj-cs.2841)
- "QR Code Image Refinement by Deep Learning" (pix2pix), GCCE 2022: decodes a **5.2 cm QR photographed from 4 m**. No px/module or rate is given in the abstract. — [DOI 10.1109/GCCE56475.2022.10014313](https://doi.org/10.1109/gcce56475.2022.10014313)
- "Improvement of DeblurGAN for Low-Quality QR Codes", GCCE 2024. Logistics/factory motivation (reading from a distance, out-of-focus, low resolution). States that DeblurGAN/DeblurGAN-v2 are "not sufficient" for QR; no numbers in the abstract. — [DOI 10.1109/GCCE62371.2024.10760779](https://doi.org/10.1109/gcce62371.2024.10760779)
- YOLOv8 + Real-ESRGAN pipeline for obscure QR images (ICCCNT 2023). Claims improvement but has no px/module data in the abstract. Real-ESRGAN is excluded by the project's constraints anyway. — [DOI 10.1109/ICCCNT56998.2023.10307854](https://doi.org/10.1109/icccnt56998.2023.10307854)

**QR-specific deblurring (relevant because the conveyor adds motion blur)**
- **Zeng et al., "Decoding Motion-Blurred QR Codes: Motion-Parameter Error Tolerance and Model-Based Recovery"** (arXiv 2610.34788, Oct 2026, preprint).
  - Grey-box pipeline: two compact networks predict a corner trajectory, followed by tolerance-guided candidate search, alternating image-and-path fitting, and regularised linear inversion. Candidates are ranked by **known-module error**, the fraction of fixed function modules misclassified.
  - Real data: **955 handheld photos from 4 phones, 93.1% exact payload with 0 wrong strings**, vs NAFNet-32 at 83.6%, MIMO-UNet+ 81.9%, EG-Restormer 73.7%, Restormer 71.3%.
  - Stage ablation: direct decoding 150/955 → network trajectory 738 → search 836 → alternating fitting 889.
  - Its findings: **blur-length tolerance shrinks quickly as blur grows and is tightest at uniform speed**, which is exactly the conveyor case, and individually tolerable errors combine to cause failure.
  - Cost: **median 5.8 s per photo on GPU**, far too slow for the target.
  - Important caveat: synthetic renders used **≥8 px/module**, and the authors treat 3–3.5 px/module as a precondition. This is not a low-PPM method.
  - Inference code: [zengzhi2015/qr-deblur](https://github.com/zengzhi2015/qr-deblur). — [arXiv 2610.34788](https://arxiv.org/abs/2610.34788)
- Li et al., ADNet / EG-Restormer (arXiv 2510.12098, 2025). Edge-guided Transformer for QR motion deblur. Test set of 150 codes (100 synthetic, 50 real). EG-Restormer reaches about **90% decoding rate**, and ADNet matches it with average time cut from **0.910 s to 0.737 s**. GPU-class networks. — [arXiv 2510.12098](https://arxiv.org/abs/2510.12098); [GitHub leejianping/ADNet](https://github.com/leejianping/ADNet)
- Sörös, Semmler, Humair, Hilliges, "Fast blur removal for wearable QR code scanners", ISWC 2015. Blind blur estimation from the code's salient edges, alternating sharpening, blur estimation and **decoding**. The restored image is constrained by QR properties, and the **checksum allows early termination** and prevents false positives. PC + Android implementations; the abstract gives no rates. — [DOI 10.1145/2802083.2808390](https://doi.org/10.1145/2802083.2808390)
- van Gennip, Athavale, Gilles, "A Regularization Approach to Blind Deblurring and Denoising of QR Barcodes", IEEE TIP 2015. Uses the **known function patterns** for blind deblurring with TV-type regularisation, then ZBar. — [DOI 10.1109/TIP.2015.2432675](https://doi.org/10.1109/tip.2015.2432675); [arXiv 1410.6333](https://arxiv.org/abs/1410.6333)
- Choksi, van Gennip, Oberman, "Anisotropic TV regularized L1 approximation and denoising/deblurring of 2D bar codes", Inverse Problems & Imaging 2011. Gives **explicit regimes** (fidelity parameter vs smallest length scale) in which the perfect barcode is the exact minimiser; solved as a linear program. — [DOI 10.3934/ipi.2011.5.591](https://doi.org/10.3934/ipi.2011.5.591)
- Chen et al., IEEE Sensors J. 2021. Out-of-focus kernel estimated from an edge prior, then Wiener; aimed at warehouse, logistics and automated production. No numbers in the abstract. — [DOI 10.1109/JSEN.2021.3085568](https://doi.org/10.1109/jsen.2021.3085568)

**Open-source repos (unvetted, small)**
- [zhongzhengli13/QRSuperResolutionNet-for-qrcode](https://github.com/zhongzhengli13/QRSuperResolutionNet-for-qrcode) (RRDB + SE GAN, 18★, 2026)
- [PsVenom/QR-code-enhancement-using-SRGANs](https://github.com/PsVenom/QR-code-enhancement-using-SRGANs) (36★, 2022)
- [cby0730/barcode-service](https://github.com/cby0730/barcode-service) (YOLOv8 + PAN SR, CPU/OpenVINO)
- [benedikthoward/ENPH459-Super-Resolution](https://github.com/benedikthoward/ENPH459-Super-Resolution) (UBC capstone: barcode decoding from optically beam-shifted images, i.e. multi-frame sub-pixel SR)

All found via the GitHub API search; none reports benchmarked px/module.

**WeChat SR internals (why it adds little)**
- In OpenCV wechat_qrcode, the SR net runs only on the **2.0 scale** of the scale list {1.0, 2.0, 0.5}, which is used when the crop is <320 px, and only if sqrt(w·h) < `sr_max_size`. Otherwise bicubic ×2 is used. It is a generic 2× SR applied to the crop. — [wechat_qrcode.cpp](https://github.com/opencv/opencv_contrib/blob/4.x/modules/wechat_qrcode/src/wechat_qrcode.cpp); [super_scale.cpp](https://github.com/opencv/opencv_contrib/blob/4.x/modules/wechat_qrcode/src/scale/super_scale.cpp)

### Inferences
- The pipeline's 8-frame shift-and-add + Wiener step is essentially "conventional multi-frame SR". Kato 2011 reports that **adding a binary constraint** to multi-frame SR gave +15.7 points on real video. Adding the grid constraint and a PSF estimated from function patterns (Kato 2013) goes further. Replacing plain averaging with a reconstruction on the known module grid (estimate one value per module from all frames' sub-pixel samples, under a binary/two-level prior) is the closest literature-backed upgrade.
- Mosaic-SR is the only published barcode SR that fits the CPU budget comfortably (<5 ms per 128×128 crop on one thread). It was trained exactly in the 1.0–1.6 → 2.0–3.2 PPM regime. Retraining on the user's own sharp frames (downsample + motion blur) is cheap, and the code is public. The reported gain is relative to bicubic + zbar, so the gain over zxing-cpp at ~2 PPM is unknown.
- At 1.8–2 PPM the user is above the Mosaic-SR input range (1.0–1.6) but below the 3–3.5 PPM practical decoding threshold (Q3). The main problem may be **blur + noise at 2 PPM** rather than sampling alone.

### Gaps
- No paper found that reports decode rate vs px/module for **multi-frame** SR on a moving conveyor with known sub-pixel motion. Kato's abstracts give no PPM.
- Full texts of the Kato ICDAR 2011, Shindo GCCE 2022/2024 and DeblurGAN-QR GCCE 2024 papers were not accessible (paywall). Their PPM and test conditions are unknown.
- No diffusion-model SR paper specific to QR at low PPM was found in arXiv/OpenAlex queries.

---

## Q2. Model-based / soft decoding (grid fitting with a binary prior, ML/Bayesian module estimation, RS erasures, brute force)

### Takeaway
Industrial vendors do this. **Cognex patent US11151346B2** decodes under-resolved 2D symbols at **<1 px/module (e.g. 0.8 PPM)** by fitting the module grid, modelling each pixel as a causal function of overlapping modules, and testing only *valid combinations* of neighbouring modules iteratively. The academic precedent is **Gallo & Manduchi's ML deformable-template decoding for 1D barcodes (TPAMI 2011)**, which avoids binarisation. For QR V1-L, erasure decoding matters a lot: the code is (26,19) with only 2 correctable errors per ISO, but RS can correct up to n−k = 7 erasures (2E+S ≤ 7). No open-source QR library exposing soft or erasure decoding was found.

### Cited Findings
- **Cognex, "Methods and apparatus for decoding under-resolved symbols", US11151346B2** (priority 2014-10-09).
  - Spatial mapping from a contiguous subset of the module grid to the pixel grid.
  - "Causal relationships" between each module and the pixels.
  - Tests the **set of valid combinations of neighbouring module values** against the pixels and fills in module values iteratively, which cuts the search far below 2^n.
  - Claims decoding of 1D and **2D symbols "under one pixel per module, such as 0.8 pixels per module"**.
  - Context stated: common decoders "require … at least 2 pixels per module", and edge-based decoders "tend to start failing between 1.3 and 1.5 PPM" for 1D scan lines.
  - No decode-rate numbers in the parts read.
  - — [Google Patents US11151346B2](https://patents.google.com/patent/US11151346B2/en)
  - Companion: Cognex US10699089B2 "Decoding barcodes" (1D character-unit grid + sampling coefficients). — [Google Patents US10699089B2](https://patents.google.com/patent/US10699089B2/en)
- **Gallo & Manduchi, "Reading 1D Barcodes with Mobile Phones Using Deformable Templates", IEEE TPAMI 2011.**
  - Argues that "early commitment" (binarise first) is why readers fail under blur, noise and low resolution.
  - Uses **gray-level ML estimation per digit with deformable templates**, then enforces spatial coherence.
  - Outperforms competing algorithms on UPC-A images from five databases.
  - 400–500 ms on a Nokia N95 for VGA.
  - — [DOI 10.1109/TPAMI.2010.229](https://doi.org/10.1109/tpami.2010.229)
- **Reed–Solomon erasure arithmetic**: an RS(n,k) code corrects ⌊(n−k)/2⌋ errors at unknown positions, or up to n−k erasures at known positions, or any mix with **2E + S ≤ n − k**. RS decoders can use "side information" about unreliable positions; the CD's CIRC flags uncorrectable inner blocks as erasures for the outer code. — [Wikipedia: Reed–Solomon error correction](https://en.wikipedia.org/wiki/Reed%E2%80%93Solomon_error_correction)
- **QR V1-L specifics**: one block of 26 codewords (19 data + 7 EC). ISO/IEC 18004 reserves p = 3 EC codewords for misdecode detection in 1-L, so the standard designation is **(26,19,2), i.e. only 2 byte errors corrected** (7.7%). Erasures need only one EC byte each. — [Wikipedia: QR code (citing ISO/IEC 18004 §7.5)](https://en.wikipedia.org/wiki/QR_code); 1-L = 19 data + 7 EC codewords — [Thonky error-correction table](https://www.thonky.com/qr-code-tutorial/error-correction-table)
- Soft-decision RS decoding in communications: GMD (Generalized Minimum Distance) and SISO decoders for RS are standard. — [Tadesse et al., Sci. Rep. 2025](https://doi.org/10.1038/s41598-025-13672-2). Koetter–Vardy soft-decision decoding has been adapted to reconstruct an RS codeword from **K independent noisy copies**, which maps directly onto "several frames of the same tag". — [Singhvi, Kiah, Yaakobi, ISIT 2026](https://doi.org/10.1109/isit62367.2026.11653901)
- Sörös et al. 2015 use the **QR checksum as the stopping criterion** inside an iterative restoration–decode loop, which also prevents false positives. — [DOI 10.1145/2802083.2808390](https://doi.org/10.1145/2802083.2808390). Zeng et al. 2026 rank candidate restorations by **known function-module error**, use agreement across three decoders, and report 0 wrong strings out of 955. — [arXiv 2610.34788](https://arxiv.org/abs/2610.34788)
- Kato 2013 estimates the PSF from patterns common to all QR codes (finder/timing), which is a model-based use of known modules. — [OpenAlex record](https://api.openalex.org/works?search=Two-step%20Super-Resolution%20with%20Binary%20and%20Grid%20Constraints)
- Open-source: [ETHANTANE-XIN/qr-erasure-bench](https://github.com/ETHANTANE-XIN/qr-erasure-bench) (2026, 0★) decodes scribbled or redacted modules as RS erasures (browser tool + CLI). It is aimed at occlusion, not low resolution, and is unvetted. A zxing-cpp PR adding a "generic RS implementation for prime and extended Galois fields" exists (#1123, 2026). I did not verify whether zxing-cpp exposes erasure positions in its public API. — [zxing-cpp PR #1123](https://github.com/zxing-cpp/zxing-cpp/pull/1123)
- zxing-cpp recently added "scored fusion of all function patterns" for sampling short rMQR symbols (PR #1135, 2026), a move toward model-based grid fitting inside zxing-cpp. — [zxing-cpp PR #1135](https://github.com/zxing-cpp/zxing-cpp/pull/1135)

### Inferences
- For V1-L, standard hard decoding fails as soon as about 3 of 26 bytes are wrong. Any soft decoder that can **mark the 3–7 least-confident codewords as erasures** (GMD/Chase-style: try erasing the k least reliable bytes for k = 0…7, check consistency) raises the correction budget up to 3.5×. Since the user's failed module-grid reader did not use erasures or confidences, this specific combination remains untested.
- Using up to 7 erasures consumes the 3 misdecode-protection bytes, so the false-positive risk rises. Multi-frame agreement (already used: 2 identical reads) and function-pattern consistency are the natural guards, as in Sörös 2015 and Zeng 2026.
- Format information is 15 bits (BCH) with only 32 valid words. ML selection over 32 candidates using soft module values is trivial. Version is fixed at 1, and module positions follow a fixed 21×21 grid, so only about 26×8 data/EC modules are unknown.
- A Cognex-style "valid combinations" or Viterbi-like search is feasible on CPU for 21×21 = 441 modules if done row-by-row with a small PSF (at 2 PPM a pixel touches at most 2×2 modules, plus blur along the motion direction).
- Multi-frame soft combining (sum per-module log-likelihoods across frames, then erasure-decode) is the coding-theory analogue of the user's frame stacking, and it maps onto the K-noisy-copies RS reconstruction setting.

### Gaps
- No peer-reviewed paper was found that implements soft-decision or erasure RS decoding for QR images and reports decode-rate gains vs PPM. Search queries returned only generic RS literature. This appears to be an open gap or kept proprietary (Cognex, Datalogic).
- Whether zxing-cpp's QR decoder enforces the ISO p=3 reservation (2 vs 3 correctable errors for 1-L) was not verified.
- The Cognex patent text read contains no quantitative decode rates.

---

## Q3. Theoretical/empirical minimum px/module and its dependence on blur, noise and EC level

### Takeaway
Across several sources the practical floor for off-the-shelf decoders is **about 3–3.5 px/module (Skurowski et al., Sensors 2022)**. Industrial edge-based 1D decoders start failing at **1.3–1.5 PPM**, and the commonly cited requirement is **≥2 PPM** (Cognex patent). Model-based methods claim **0.8 PPM** (Cognex) or 1.0–1.6 PPM inputs made decodable by SR (Mosaic-SR). The user at 1.8–2 PPM with motion blur and EC-L is squarely in the regime where generic decoders are unreliable.

### Cited Findings
- **Skurowski, Nurzyńska, Pawlyta, Cyran, "Performance of QR Code Detectors near Nyquist Limits", Sensors 22(19):7230, 2022.**
  - Simulation of QR scanning near Shannon/Nyquist limits, with MTF modelled as Gaussian low-pass based on real devices.
  - Three public decoders were tested on decode-only and locate+decode tasks.
  - Finding: **"for practical decoding, the QR-code module should be no smaller than 3–3.5 pixels, regardless of MTF characteristics"**.
  - ZBar is best in practical tasks. OpenCV is worst overall, but in borderline or **below-Nyquist** cases OpenCV still decodes some codes where the others fail.
  - Synthetic simulation.
  - — [DOI 10.3390/s22197230](https://doi.org/10.3390/s22197230)
- Cognex US11151346B2 states that typical 1D/2D decoding techniques require **at least 2 PPM**, edge-based decoders fail at **1.3–1.5 PPM**, and the patented method works **below 1 PPM (0.8 PPM)**. — [Google Patents](https://patents.google.com/patent/US11151346B2/en)
- Mosaic-SR: LR crops at **1.0–1.6 PPM decode 0 times without upscaling** (zbar), and some become decodable after 2× SR (Q1 numbers). — [Paper PDF](https://federicobolelli.it/pub_files/2025icip.pdf)
- Zeng et al. 2026 cite Skurowski for the 3–3.5 PPM threshold and render at **≥8 PPM**. Their tolerance study shows **blur-length tolerance shrinks rapidly with blur amplitude and is tightest under uniform-speed motion**. — [arXiv 2610.34788](https://arxiv.org/abs/2610.34788)
- Choksi & van Gennip derive regimes, in terms of fidelity parameter vs the smallest bar-code length scale and blur-kernel support, where TV-regularised deblurring provably returns the exact 2D bar code. — [DOI 10.3934/ipi.2011.5.591](https://doi.org/10.3934/ipi.2011.5.591); 1D analogue — [arXiv 0910.2494](https://arxiv.org/abs/0910.2494)
- EC level: V1-L tolerates 2 byte errors (7.7%) per ISO; ~7% recovery for level L. — [Wikipedia: QR code](https://en.wikipedia.org/wiki/QR_code)

### Inferences
- With uniform conveyor motion, the measured blur (2–6.5 px tested in the pipeline) is comparable to or larger than the module size (2 px). Zeng's tolerance law says Wiener with a mis-estimated length fails easily. Estimating blur length per tag by search, scored by function-module error, should help more than a fixed list of lengths.
- Hardware levers from the literature: Mosaic-SR notes that low-resolution sensors with larger pixels allow shorter exposures and less motion blur. The underlying trade-off is between PPM and exposure/blur.

### Gaps
- No source gives a closed-form minimum PPM as a function of (blur, noise, EC level) for QR. Skurowski varies MTF but not EC level (not confirmed; full text not read because MDPI HTML was blocked).

---

## Q4. End-to-end deep-learning QR decoders (predict modules/bits directly)

### Takeaway
There is almost nothing. The only learning-based "QR decoding" paper found (Yoda, Kawamoto, Kera, arXiv 2025) learns the mapping from **module bits to text** with a Transformer. It exceeds the RS correction limit by learning text priors (domain names), which does not help with arbitrary tag payloads, and it is not an image→bits low-resolution decoder. No image→module CNN with published low-PPM accuracy vs zxing/WeChat was found.

### Cited Findings
- Yoda, Kawamoto, Kera, "Learning Moderately Input-Sensitive Functions: A Case Study in QR Code Decoding", arXiv 2506.20305 (2025). The authors call it "the first learning-based QR code decoding".
  - Transformers decode even beyond the theoretical EC limit by learning the structure of embedded text (domain names from the Tranco top-1M + English words). They generalise partly to other languages and random strings.
  - The model **ignores EC bits and relies on data bits**.
  - Success varies by mask pattern (e.g. 92.8% for mask 1 vs 49.1% for mask 2; average 68.3% in one setting).
  - Synthetic corruption, not camera images.
  - — [arXiv 2506.20305](https://arxiv.org/abs/2506.20305)
- EgoQR (Meta, arXiv 2410.05497, 2024). Detection + "enhanced decoding" for wearable egocentric images (motion blur, wide FoV). **+34% read rate vs an existing SOTA reader** on an egocentric dataset. Designed for on-device low power. Abstract only; method details and PPM not given. — [arXiv 2410.05497](https://arxiv.org/abs/2410.05497)
- Mosaic-SR's patch-MLP predicts 2×2 HR pixels plus an uncertainty from a 7×7 LR patch. The same structure could predict per-module probabilities instead (inference, not in the paper). — [Paper PDF](https://federicobolelli.it/pub_files/2025icip.pdf)

### Inferences
- A small CNN/MLP trained to output **P(module = black)** for each of the 21×21 modules (given a warped ROI and optionally multiple frames), feeding an erasure-aware RS decoder, is unexplored in the literature. It would combine Q2 and Q4, and training data is easy to synthesise (render V1-L codes, downsample to 1.8–2 PPM, add motion blur and noise).

### Gaps
- No published image→bits QR decoder with accuracy vs zxing/WeChat at ≤3 PPM was found.

---

## Q5. CPU practicality (50–300 ms per ROI) and code availability

### Takeaway
CPU-feasible and open: **Mosaic-SR** (≈1–4 ms per 128×128 crop, one thread, code + models public). Classical model-based approaches (Kato multi-frame SR with binary/grid prior, van Gennip TV deblurring, Sörös iterative blur estimation, Cognex-style valid-combination search, RS erasure decoding) are likely CPU-feasible at QR V1 size but have no public code, except the 1D/TV research code. Deep deblurring (EG-Restormer/ADNet ~0.7–0.9 s; Zeng et al. median 5.8 s on GPU) is too slow.

### Cited Findings
- Mosaic-SR: 0.88 / 1.69 / 4.22 ms on a Threadripper (single thread), 23 / 44 / 110 ms on a Raspberry Pi 3B+; QRCNN 172 ms on PC; TFLite + SIMD im2col; code public. — [Paper PDF](https://federicobolelli.it/pub_files/2025icip.pdf); [GitHub](https://github.com/Henvezz95/Mosaic-SR)
- ADNet: avg 0.737 s, EG-Restormer 0.910 s (hardware per paper; network class needs GPU). — [arXiv 2510.12098](https://arxiv.org/abs/2510.12098)
- Zeng et al.: median 5.8 s per photo, 90th percentile 33.8 s, on GPU; inference code public. — [arXiv 2610.34788](https://arxiv.org/abs/2610.34788); [GitHub zengzhi2015/qr-deblur](https://github.com/zengzhi2015/qr-deblur)
- Gallo & Manduchi ML template decoding: 400–500 ms for a VGA frame on a 2008 Nokia N95, including localisation. — [DOI 10.1109/TPAMI.2010.229](https://doi.org/10.1109/tpami.2010.229)
- Sörös et al.: fast blind deblur with PC + Android implementations, described as outperforming existing methods in speed. — [DOI 10.1145/2802083.2808390](https://doi.org/10.1145/2802083.2808390)

### Inferences
- Candidates in rough order of literature support × CPU fit:
  1. Multi-frame reconstruction on the module grid with a binary prior (Kato-style).
  2. Soft module probabilities + RS erasure/GMD decoding with multi-frame soft combining.
  3. Mosaic-SR retrained on conveyor data as a pre-step before zxing.
  4. Blur-length search scored by function-module error (Zeng-style, classical part only).

### Gaps
- No code found for the Kato multi-frame binary/grid-constrained SR, the Cognex method, or any QR erasure-aware decoder for low resolution.
