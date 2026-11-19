# Learning-based restoration / direct decoding of strongly blurred, low-resolution QR codes

Scope reminder (our case): QR v2-L, 25x25 modules, ~2.3 px/module (~57 px code), vertical motion blur 6-7 px (~2.6-3 modules) convolved with Gaussian sigma ~1 px (~0.43 module), contrast ~50 DN, noise sigma ~2.5 (SNR of the module contrast ~20), 20-150 frames/pass, GTX 1650, off-line budget <= 30 s/pass. Research budget was limited (~17 tool calls); several primary PDFs (Springer, MDPI, Springer MTAP) were paywalled/403 and could only be characterised from abstracts or citing papers — flagged below.

## Q1. Which QR/barcode deblurring / SR networks exist, what blur and resolution did they test, and how did they compare to baselines?

### Takeaway
The published QR-specific learning work (CNN, GAN, Transformer) is almost entirely single-frame, image-to-image restoration on synthetic motion blur of comparatively large codes, decoded afterwards by ZBar/ZXing; none of the papers I could read reports blur length in modules, px/module, or results at ~2 px/module with combined motion+defocus. The best-documented recent result (EG-Restormer, 2025) reaches 90% ZBar decode on a 150-image test set, only 1.3 pp above a generic Restormer, so "QR-specific" networks so far beat generic deblurrers by small margins and have never been benchmarked against strong classical/multi-frame QR solvers.

### Cited Findings
- **EG-Restormer / LENet / ADNet (Li et al., arXiv 2510.12098, Oct 2025)**: adds an Edge-Guided Attention Block (explicit edge prior) to Restormer for severe blur; a 0.28 M-param lightweight LENet for mild blur; ADNet routes by Laplacian-variance threshold. — [arXiv HTML](https://arxiv.org/html/2510.12098v1)
  - Data: "QRData" = 1,822 synthetic QR images with non-uniform motion kernels (1,521 train / 301 test); evaluation set 150 images (100 synthetic + 50 real) with no separate real/synthetic breakdown; GoPro used for pre-training. Kernel sizes, QR versions, module px and noise are **not reported**. — [arXiv HTML](https://arxiv.org/html/2510.12098v1)
  - Decode rate with ZBar after GoPro pre-train + QRData fine-tune: EG-Restormer 90.00%, Restormer 88.67%, NAFNet-32 81.33%, LENet 49.33%; ADNet 90% vs random routing 72%. Baselines are only generic deblurring nets — no QR-specific or classical baselines. — [arXiv HTML](https://arxiv.org/html/2510.12098v1)
  - Cost at 512x512: LENet 0.28 M params / 3.87 GFLOPs / 0.23 s; NAFNet-32 17.1 M / 64 G / 0.79 s; Restormer 26.1 M / 565 G / 0.84 s; EG-Restormer 26.1 M / 565 G / 0.91 s; ADNet avg 0.737 s; hardware not stated. — [arXiv HTML](https://arxiv.org/html/2510.12098v1)
  - Later preprint version reports +8.67 pp (GoPro-only training) and +1.33 pp (after QRData fine-tune) over baseline, 19% latency reduction for ADNet. — [search summary of arXiv 2510.12098](https://arxiv.org/pdf/2510.12098); an aggregator's "+12.7%, 28 FPS" claim does not match the paper and should be ignored. — [emergentmind](https://www.emergentmind.com/papers/2510.12098)
  - Code: https://github.com/leejianping/ADNet (licence not stated in paper); SOTAVerified lists it as not yet reproduced. — [arXiv HTML](https://arxiv.org/html/2510.12098v1); [sotaverified](https://sotaverified.org/papers/251012098)
- **Earlier CNN/GAN QR deblurring cited by Li et al.**: Pu et al. dual-CNN framework for reversing 2D-barcode degradation; Li et al. (Neurocomputing 2022) encoder-decoder with ResBlocks + adaptive thresholding for motion blur and uneven illumination; Dong et al. GAN + attention for motion-blurred QR; Wang et al. GAN motion deblurring. Li et al. criticise these as adapting general deblurring models without QR-specific priors, and note the earlier dual-CNN needed a manually specified blur kernel at training. — [arXiv HTML](https://arxiv.org/html/2510.12098v1); [arXiv PDF](https://arxiv.org/pdf/2510.12098)
  - Attribution conflict: one 2026 paper attributes GAN methods to "Pu et al. [16]", others attribute the dual-CNN to Pu; the GAN+attention paper (Springer IJCIS, s44196-024-00450-7) is credited to Xie in a CVPR 2026 supplement, not Dong. — [Springer](https://link.springer.com/article/10.1007/s44196-024-00450-7); [CVPR 2026 supp.](https://openaccess.thecvf.com/content/CVPR2026F/supplemental/Kumar_Tap_Scan_Exploit_CVPRF_2026_supplemental.pdf)
  - A review in the same Springer paper states that DL QR deblurring methods still show artifacts, unclear edge outlines, overly complex models and long training. — [Springer](https://link.springer.com/article/10.1007/s44196-024-00450-7)
- **"Quick response barcode deblurring via doubly convolutional neural network"** (Multimedia Tools & Applications, 2018, DOI 10.1007/s11042-018-5802-2): CNN reported to outperform model-based deblurring on practically blurred QR images; full text not accessible. — [Bohrium summary](https://www.bohrium.com/paper-details/quick-response-barcode-deblurring-via-doubly-convolutional-neural-network/813052478747574274-2728)
- **Gs-DeblurGANv2 (Multimedia Systems, 2024)**: lightweight DeblurGANv2 for QR, PSNR 25.21 dB / SSIM 0.87 on a self-made dataset; evaluated mainly on image metrics and speed, not decode rate. — [Bohrium](https://www.bohrium.com/paper-details/gs-deblurganv2-a-qr-code-deblurring-algorithm-based-on-lightweight-network-structure/978112017191665665-2812)
- **GAN deblur + modified local adaptive thresholding (CASE 2020)**: qualitative "performs well" on motion-blurred QR. — [HIT scholar](https://scholar.hit.edu.cn/en/publications/a-new-qr-code-recognition-method-using-deblurring-and-modified-lo/)
- **Pix2Pix cGAN for damaged 1D/QR codes (Muallim et al., CMES 143(3), 2025)**: QR decode 14% -> 99% on training data but only 15% -> 68% on validation (1D: 7% -> 73% train) — a large train/val gap on synthetic data. — [TechScience CMES](https://www.techscience.com/CMES/v143n3/62816)
- **BARGAIN (CODS-COMAD 2024)**: SR network for (1D) barcodes with an edge-preserving loss; ~11.27% decode-accuracy gain over SOTA SR methods. — [AMiner](https://aminer.org/pub/659b7349939a5f4082ed98ec/bargain-a-super-resolution-technique-to-gain-high-resolution-images-for-barcodes)
- **EgoQR (Meta, arXiv 2410.05497, 2024)**: QR reading on wearable images; overall +34% reads vs an existing SOTA reader; per a search summary of the PDF, its decoder uses an SR model trained on ~700k simulated LR/HR QR patch pairs (camera-noise simulation) which added +2.6% decode success. (PDF too large to fetch; the 700k/2.6% figures are from a search snippet only.) — [arXiv abs](https://arxiv.org/abs/2410.05497); [arXiv PDF](https://arxiv.org/pdf/2410.05497)
- **Multi-scale edge-guided real-time deblurring for barcode/QR/Data Matrix (MDPI Electronics 14(7):1298, 2025)** exists; full text blocked (403), numbers unknown. — [MDPI](https://mdpi.com/2079-9292/14/7/1298)
- **Electronics 13(10):1873 (2024)**: 2D-barcode restoration with recurrent feature reasoning + structural fusion attention (inpainting/damage oriented). — [MDPI](https://www.mdpi.com/2079-9292/13/10/1873)
- **WeChat QR (OpenCV contrib)**: two Caffe CNNs — a detector and a super-resolution model "to enlarge small codes"; input rescaled by default to 160,000 px area. No training details or blur robustness figures published in the docs. — [OpenCV 4.8 docs](https://docs.opencv.org/4.8.0/d5/d04/classcv_1_1wechat__qrcode_1_1WeChatQRCode.html); [OpenCV 5 docs](https://docs.opencv.org/5.0/extra_modules/wechat_qrcode.html)
- **Industry patents (secondary evidence)**: US12131224B1 — decode, on failure run a DL restoration model (GAN or diffusion named in claims) and retry. — [Google Patents](https://patents.google.com/patent/US12131224); Cognex-style "decoding under-resolved symbols" patents test valid module combinations using module-pixel relationships for codes with few px/module. — [USPTO 10599902](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/10599902)

### Inferences
- Our degradation (blur extent ~2.6-3 modules plus sigma ~0.43 module, 2.3 px/module) is almost certainly harsher than the "severe" cases in the academic QR deblurring sets, which use full-size codes on 256-512 px patches; no paper demonstrates decoding at ~2 px/module with blur spanning several modules.
- The academic image-to-image nets were all evaluated against generic deblurrers, not against multi-frame classical solvers with binary priors like ours, so "how far beyond classical" is essentially unmeasured in the literature; we would have to measure it ourselves on our synthetic simulator.
- The EG-Restormer vs Restormer gap (1.3 pp) suggests architecture matters less than training on the right degradation distribution — supporting a strategy of training a modest network on our own exact simulator.

### Gaps
- No public numbers on WeChat SR model size, training data, or when it triggers (source `super_scale.cpp` not checked).
- Could not access Dong/Xie GAN (Springer), MDPI 14(7):1298, or the 2018 MTAP doubly-CNN paper for blur lengths and decode rates.
- No Dynamsoft/Scandit quantitative claims on blur at ~2 px/module were found in this pass.

## Q2. Per-module probability ("soft bits") prediction + Reed-Solomon / soft-decision decoding; structure-aware networks

### Takeaway
I found no peer-reviewed paper that predicts per-module probabilities from blurred QR images and feeds them into erasure/soft-decision Reed-Solomon; the closest are patents (NN-flagged erasures for RS) and a French paper classifying noisy QR images directly. This is an open niche that matches our known geometry (25x25 grid, fixed function patterns) well.

### Cited Findings
- A patent ("Erasure-based QR decoding", USPTO 12524638) describes a network predicting which modules are in error and a correction engine using erasure-based Reed-Solomon. — [USPTO](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/12524638)
- A barcode patent (USPTO 12008431) uses an NN intensity map as a decode fallback, with RS error correction, noting the intensity map is more stable than module centroids. — [USPTO](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/12008431)
- Leygonie et al. (RFIAP 2022, arXiv 2307.10677) train a deep classifier on noisy QR codes (health-pass data) and compare against a deterministic decoder; the abstract does not give the per-module design or numbers. — [arXiv](https://arxiv.org/abs/2307.10677)
- CNNs beat RBF nets and MLPs for classifying 2D matrix codes and their rotations (comparative study, 2023). — [PMC10532761](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC10532761/)
- Cognex-style patents decode under-resolved symbols by testing consistent module combinations given the module-to-pixel relationship (a structured, non-learned analogue of per-module inference). — [USPTO 10599902](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/10599902)

### Inferences
- For v2-L (from the QR spec, not from a source found here): 44 codewords, 34 data + 10 EC in one block, so RS can correct up to 5 symbol errors or up to 10 erasures (or 2e+f <= 10). A module classifier giving calibrated probabilities lets us mark the ~least-confident codewords as erasures (doubling correction power) and/or run list/Chase-style decoding (flip the k least-reliable bits, check RS + format + content regex `^\d{14}#\d{12}$`). The fixed content structure (byte mode header, length 27, digits + '#') is an additional very strong prior: most data bits are constrained to ASCII '0'-'9', which a constrained search can exploit.
- A grid-aligned network is natural for us: rectify each frame with the homography from finder patterns (we already warp), sample a fixed canvas (e.g. 25 modules x 4 px = 100x100 or keep native 57x57 with known sub-pixel offset), and output a 25x25 logit map. Function patterns/timing/format areas are known and can be masked from the loss or fed as an extra input channel. Since blur is vertical and only ~3 modules long, a network with receptive field ~7x3 modules suffices; a few hundred k parameters should be enough (e.g. LENet-scale 0.28 M ran 0.23 s on 512x512 per Q1).
- Training targets are exact (we render the bits), so cross-entropy on module bits is the right loss rather than pixel L1/PSNR — this directly optimises what RS needs, unlike the image-restoration papers.

### Gaps
- No published benchmark of soft-decision/erasure RS decoding of QR with learned reliabilities; gain must be estimated by our own simulation.

## Q3. Multi-frame / burst networks and physics-informed (unrolled) deconvolution with known PSF

### Takeaway
No QR-specific burst network was found, but general frameworks fit our setting: deep unfolding (USRNet) and feature-space Wiener (Deep Wiener Deconvolution) take the known PSF as input and generalise across kernel/noise levels with one model; burst SR/deblur networks can align and fuse many frames. For a 25x25 binary target, a simpler multi-frame module classifier (frames registered by known velocity, stacked as channels or pooled) is likely more practical than adapting generic burst models.

### Cited Findings
- **USRNet (Zhang, Van Gool, Timofte, CVPR 2020)**: unrolls MAP with half-quadratic splitting into alternating data (closed-form, uses the given kernel) and learned prior modules; one model handles different scale factors, blur kernels and noise levels; scale factor 1 gives non-blind deblurring; code at github.com/cszn/USRNet. — [arXiv 2003.10428](https://arxiv.org/pdf/2003.10428); [CVPR paper](https://openaccess.thecvf.com/content_CVPR_2020/papers/Zhang_Deep_Unfolding_Network_for_Image_Super-Resolution_CVPR_2020_paper.pdf)
- **Deep Wiener Deconvolution (Dong, Roth, Schiele, NeurIPS 2020 oral)**: explicit Wiener deconvolution in a learned feature space with known kernel, plus multi-scale refinement; estimates noise level adaptively so one model covers various noise levels; reviewers noted it is limited to uniform blur (fine for us: spatially uniform PSF over a 57 px code). — [arXiv 2103.09962](https://arxiv.org/abs/2103.09962v1); [NeurIPS reviews](https://proceedings.neurips.cc/paper_files/paper/2020/file/0b8aff0438617c055eb55f0ba5d226fa-Review.html)

### Inferences
- Because our PSF is parametric and measurable (motion length from speed x exposure, direction vertical, plus Gaussian sigma ~1), a non-blind unrolled model conditioned on (L, sigma) — USRNet-style with an x1 scale and a binary-ish prior — is the most "physics-respecting" option and should transfer to real data better than blind GANs. The classical failure at sigma >= 0.8 is consistent with the combined PSF's MTF having near-zeros/low gain near the module frequency (0.43 cycles/px at 2.3 px/module); a learned prior on the 25x25 binary grid can fill in what Wiener cannot, but only where multi-frame SNR permits — no network recovers frequencies that are fully destroyed in every frame.
- Multi-frame gain: with 20-150 frames, sub-pixel phase diversity (the code moves ~ known px/frame) acts like multi-frame SR; averaging N registered frames improves SNR by sqrt(N) (≈4.5-12x). A practical design: register each frame's crop to the code grid (homography + velocity), feed a fixed number K (e.g. 8-16) of frames — or a permutation-invariant mean/max pooling over per-frame features — into the module classifier. This mirrors burst-SR designs (align, fuse, decode) while staying tiny.
- General burst SR/deblur models (e.g. Bhat et al. Deep Burst SR, BIPNet, Burstormer) are designed for RGB photos at 4x and are heavy; I did not verify their details in this pass and they are probably overkill for 57 px binary codes.

### Gaps
- Did not retrieve primary sources for burst networks (DBSR, BIPNet, Burstormer) — sizes/licences unverified here.
- No paper found applying deep unfolding or burst fusion to barcodes specifically.

## Q4. Synthetic-to-real gap, simulation practice, model size / inference on modest GPUs

### Takeaway
QR papers simulate blur with synthetic (often non-uniform) motion kernels, pre-train on GoPro, and evaluate on small mixed sets without separate real-data results; the Pix2Pix study shows a stark synthetic train/val gap (99% vs 68%). Our advantage is a precisely known forward model; the main risks are mis-modelled PSF (defocus shape, rolling/global shutter, label print quality, paper texture/glare, gamma/nonlinearity) rather than network capacity. Model cost is not a constraint for 57 px crops.

### Cited Findings
- EG-Restormer: two-stage transfer (GoPro pre-train -> QRData fine-tune), augmentation by flips/rotations/shuffling; 50 of 150 test images real but not reported separately. GoPro-only training gave ~8.67 pp lower decode than QR-specific fine-tune per preprint. — [arXiv HTML](https://arxiv.org/html/2510.12098v1); [arXiv PDF](https://arxiv.org/pdf/2510.12098)
- Pix2Pix barcode restoration: QR decode 99% on train vs 68% on validation (synthetic) — overfitting/generalisation gap. — [TechScience CMES](https://www.techscience.com/CMES/v143n3/62816)
- EgoQR SR trained on ~700k simulated LR/HR QR patch pairs with camera-noise simulation (search-snippet level evidence). — [arXiv PDF](https://arxiv.org/pdf/2410.05497)
- Sizes/latency: LENet 0.28 M params, 0.23 s at 512x512; Restormer-class 26 M params, ~0.8-0.9 s at 512x512 (hardware unspecified). — [arXiv HTML](https://arxiv.org/html/2510.12098v1)
- Deep Wiener model handles varying noise with one model via adaptive noise estimation. — [arXiv 2103.09962](https://arxiv.org/abs/2103.09962v1)

### Inferences
- Compute: a 57x57 (or 100x100 rectified) crop is ~1/25-1/80 of a 512x512 patch; even a Restormer-sized net would run in tens of ms per frame on a GTX 1650, and a 0.3-2 M-param grid classifier over 16 stacked frames would take a few ms on GPU and well under a second on CPU — comfortably inside the 30 s background budget and the existing `qr/solvers` spawn-process architecture.
- Domain randomisation to apply when rendering: motion length L in [4, 9] px with ±10% error vs. the measured value, small angle jitter (±3°); Gaussian sigma in [0.5, 1.5] px plus optionally disc/defocus kernels; sub-pixel grid phase and slight perspective/rotation residual after homography (±0.3 px corner error); contrast 30-80 DN, offset/illumination gradient, gamma; Gaussian + Poisson noise around sigma 2.5; print effects (dot gain/ink spread ±15% module width, paper texture, missing ink specks); JPEG-free (we record uncompressed). Train with conditioning inputs (L, sigma estimate) if using a non-blind design.
- Validation on real data: the static capture with known codes gives labelled crops; real conveyor passes without ground truth can still be scored by "RS decodes + content matches regex + consistent across frames" (self-consistency), and decoded passes become pseudo-labels for fine-tuning (semi-supervised loop).
- Main failure modes to expect on real data (by analogy with the cited gaps): hallucinated valid-looking modules (GAN/diffusion priors can output a *different* valid code) — mitigated by predicting soft bits and requiring RS success with few corrections plus the content regex; mismatch in defocus PSF shape; frame registration error.

### Gaps
- No paper reported performance as a function of px/module or blur-to-module ratio, so there is no external evidence of where learned methods break at ~2.3 px/module.
- No diffusion-model QR restoration paper with decode-rate numbers was found (only a patent claim naming diffusion as an option).

## Q5. Open-source code/models usable as a starting point

### Takeaway
Usable code exists for generic restoration backbones (USRNet, Restormer/NAFNet family, ADNet for QR) and the WeChat CNN models in OpenCV contrib; no open-source QR module-classifier or soft-RS decoder was found, so the most promising pipeline would be custom but small.

### Cited Findings
- ADNet/EG-Restormer/LENet QR deblurring code: https://github.com/leejianping/ADNet (licence not stated in the paper; check repo). — [arXiv HTML](https://arxiv.org/html/2510.12098v1)
- USRNet code: github.com/cszn/USRNet. — [arXiv 2003.10428](https://arxiv.org/pdf/2003.10428)
- WeChat QR CNN detector + SR models ship with OpenCV contrib (`wechat_qrcode`, Apache-2.0 like OpenCV contrib), Caffe format (our repo uses ONNX conversions). — [OpenCV docs](https://docs.opencv.org/4.8.0/d5/d04/classcv_1_1wechat__qrcode_1_1WeChatQRCode.html)
- Deep Wiener Deconvolution (NeurIPS 2020) — public paper; code availability not verified here. — [NeurIPS](https://neurips.cc/virtual/2020/poster/16944)

### Inferences
- Recommended order of experiments for us (inference, not from a source): (1) train a tiny multi-frame grid classifier (rectified K-frame stack -> 25x25 logits) purely on our simulator, decode with hard bits + erasures of least-confident codewords + content-regex-constrained search; measure on synthetic sweeps (L 6-8 px, sigma 0.8-1.4) vs the current ComboBC solver; (2) if insufficient, try a non-blind unrolled restoration (USRNet with scale 1 conditioned on the PSF) before decoding; (3) generic GAN/Transformer deblurring (EG-Restormer) only as a baseline — they are single-frame, image-space and unproven at our resolution.
- Hard information limit check worth running first: compute, for our PSF+noise and N frames, the Bayes-optimal per-module error rate on synthetic data (e.g. by the classifier itself trained to convergence); if module error after fusion is > ~10% (≈ > 5 codeword errors / 44), no learned method can decode v2-L reliably, and the hardware lever (shorter exposure / strobe, larger label or EC level M/Q) is mandatory.

### Gaps
- Licences of ADNet repo and Deep Wiener code unverified.
- No Dynamsoft/Scandit/Cognex documentation with quantitative claims was found in this pass; vendor marketing about "AI deblur" remains unquantified.
