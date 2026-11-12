# Motion-blur removal and blur-robust acquisition/decoding for QR / 2D codes on conveyors

Research note, 2026-11-06. Tooling caveat: WebSearch/WebFetch were unavailable in this session; sources were retrieved via the arXiv API, OpenAlex, Semantic Scholar and direct downloads of open-access PDFs (arXiv, Springer OA, Nature OA). Closed-access papers (Sörös 2015, Xu & McCloskey 2011, Pan 2014, Rioux 2019) are cited from their abstracts only; vendor application notes could not be retrieved (see Gaps). Every number below was read from the cited source text unless marked as an inference.

User context for interpretation: QR v1-L, ~2 px/module, CPU only, 8 ms exposure, current Wiener + linear kernel + up-to-8-frame averaging; 16/33 passes at 6 px (≈3 modules) blur, ~26–28/33 at 3 px (≈1.5 modules), semi-synthetic.

## 1. QR/barcode-specific blind deblurring (priors: binary, finder pattern, L0, KL)

### Takeaway
The strongest recent evidence (Zeng et al., arXiv Oct 2026, 955 real handheld photos) shows that a physics/model-based approach — estimate the motion trajectory from the code's known corners/function patterns, search candidates within measured tolerances, then do regularised linear inversion and verify by decoding — beats every fine-tuned deep network (93.1% vs 83.6% exact payload) and massively beats classic QR-prior regularisation methods (Van Gennip 17.1%, Pan et al. 20.3%). The key quantitative lesson for this project: at ~4 modules of constant-speed blur, the blur-length estimate must be within ~8–11% for decoding to succeed, so a coarse length sweep (2/3/4.5/6.5 px, ~1.4–1.5× steps) is too coarse at large blur.

### Cited Findings
- Zeng, Su, Xiong, Wang, Cai (arXiv 2610.34788, Oct 2026) "Decoding Motion-Blurred QR Codes: Motion-Parameter Error Tolerance and Model-Based Recovery": grey-box pipeline (two compact networks predict initial corner trajectory → tolerance-guided candidate search → alternating image-and-path fitting → regularised linear inversion) recovers the exact payload on 93.1% of 955 real handheld motion-blurred photos (4 phone models, 4 motion categories), vs 83.6% for the strongest fine-tuned network (NAFNet-32); decoding error rate reduced 16.4% → 6.9% (−58%), zero wrong strings accepted (acceptance requires agreement of three decoders). — [arXiv 2610.34788](https://arxiv.org/abs/2610.34788)
- Same paper, real-photo benchmark totals (exact / wrong / rejected out of 955): Ours 889 (93.1%); NAFNet-32 798 (83.6%); MIMO-UNet+ 782 (81.9%); EG-Restormer 704 (73.7%); Restormer 681 (71.3%); DeepDeblur 544 (57.0%); DeMoE 419 (43.9%); DeblurGAN-v2 245 (25.7%); Pan et al. 194 (20.3%); Van Gennip et al. 163 (17.1%). All networks were fine-tuned on the authors' QR synthetic generator; with released (non-QR) weights they recover only 12.1%–25.1% (NAFNet-32 12.1%, Restormer 25.1%, DeMoE 21.4%). — [arXiv 2610.34788](https://arxiv.org/abs/2610.34788)
- Same paper, stage ablation on 955 real photos: direct decoding 150 recovered (error 84.3%) → network trajectory 738 (22.7%) → trajectory search 836 (12.5%) → alternating fitting 889 (6.9%). — [arXiv 2610.34788](https://arxiv.org/abs/2610.34788)
- Same paper, tolerance laws (synthetic, 8 px/module renders): length tolerance shrinks as blur grows and is tightest at constant speed; at 4 modules of translation, constant-speed length tolerance drops from the ±80% scan limit to 8–11%; accelerating motion is much more forgiving (19–54% at speed ratio 2.1). Underestimating length is generally tolerated better than overestimating (e.g. 2-module translation at speed ratio 2.1: 54% under vs 29% over). Permitted direction error drops from 13° at 2 modules to 5° at 4 modules. Errors that are individually benign combine to prevent decoding (at T2 a 10% length overestimate narrows direction tolerance from 13°). Noise (σ 13–30% of full scale) changes length tolerance by only ~2%. — [arXiv 2610.34788](https://arxiv.org/abs/2610.34788)
- Same paper: runtime median 5.8 s per photo including decoding (90th percentile 33.8 s) on a single shared GPU; failures concentrate below 12 px/module (562 of 955 images but 63 of 66 failures). Cites Skurowski et al.: reliable QR detection needs roughly 3–3.5 px/module. — [arXiv 2610.34788](https://arxiv.org/abs/2610.34788)
- Van Gennip, Athavale, Gilles, Choksi (IEEE TIP 24(9) 2015; arXiv 2014): blind deblurring + denoising of QR using the known finder/required patterns to estimate the PSF, TV-regularisation; evaluated on synthetic codes with 8 px/module, motion blur lengths 3–19 px, readability tested with ZBar; results reported as readability maps over noise level, not a single rate. — [arXiv 1410.6333](https://arxiv.org/abs/1410.6333)
- Rioux, Scarvelis, Choksi, Hoheisel, Maréchal (IEEE TPAMI 2019/2021): blind deblurring of barcodes via Kullback–Leibler divergence, exploiting fixed symbology segments; shown on simulated highly blurred/noisy barcodes, plus one real out-of-focus camera image (proof of concept). — [DOI 10.1109/TPAMI.2019.2927311](https://doi.org/10.1109/tpami.2019.2927311)
- Sörös, Semmler, Humair, Hilliges (ISWC 2015) "Fast blur removal for wearable QR code scanners": blind blur estimation from salient code edges, alternating sharpening / blur estimation / decoding, with QR-specific constraints; checksum allows early termination and precludes false positives; authors state general blur-removal algorithms "perform poorly" on visual codes and are slow even on PCs. (Full text closed; quantitative results not retrieved.) — [DOI 10.1145/2802083.2808390](https://doi.org/10.1145/2802083.2808390)
- Pan, Hu, Su, Yang (CVPR 2014) "Deblurring Text Images via L0-Regularized Intensity and Gradient Prior": L0 prior on intensity and gradient for binary-like images, no explicit edge selection; widely used baseline (459 citations). Zeng 2026 measured it at 20.3% exact recovery on real QR photos. — [DOI 10.1109/CVPR.2014.371](https://doi.org/10.1109/cvpr.2014.371); [arXiv 2610.34788](https://arxiv.org/abs/2610.34788)
- Zhang, Yang, He et al. (arXiv 2609.23268, Sep 2026): blind deconvolution of binary/pattern images with a pixel-intensity constraint plus sparse gradient prior; kernel-estimation runtime (35×35 kernel) vs Pan et al.: Pan 13.28 / 42.07 / 94.23 s at 256² / 450² / 600² images; Wen et al. 12.60 / 20.37 / 31.33 s (non-blind step excluded). — [arXiv 2609.23268](https://arxiv.org/abs/2609.23268)
- Lv, Liu, Li, Yao (J. Comput. Appl. Math. 393, 2021) "Blind motion deconvolution for binary images" (numbers not retrieved). — [DOI 10.1016/j.cam.2021.113500](https://doi.org/10.1016/j.cam.2021.113500)

### Inferences
- The project's motion is near-constant-speed linear translation — exactly the regime with the tightest length tolerance (8–11% at 4 modules). At 6 px ≈ 3 modules, the sweep 4.5 → 6.5 px (+44%) likely skips the decodable basin; a finer sweep (~5–8% steps around the tracker estimate, biased toward slight underestimation) is the cheapest change suggested by this evidence.
- Zeng's best stages (search + fit, verified by decode) are conceptually close to what the project already has (velocity estimate + Wiener + decode check); the main delta is (a) finer, tolerance-guided candidate grids for length and direction, and (b) re-fitting length/direction by minimising re-blur residual on known function modules (finder patterns, timing patterns) before inversion.
- Their 5.8 s median GPU runtime includes perspective/rotation trajectories; a 1-D constant-velocity conveyor case reduces the search to length (and minor angle), which should be far cheaper — but no CPU timing was published.
- Classic QR-prior regularisation (Van Gennip, Pan L0) did poorly on real photos (17–20%), so implementing them is unlikely to beat a well-tuned Wiener + fine length search.

### Gaps
- Sörös 2015, Xu/Jia, Shi et al. and Rioux 2019 decode-rate numbers and runtimes were not retrievable (closed access, no search engine). No paper found that evaluates at ~2 px/module; Zeng renders ≥8 px/module and notes failures concentrate <12 px/module, so the tolerance numbers may be tighter at 2 px/module.
- "QR code deblurring via finder patterns" as a separately titled paper was not located; the finder-pattern PSF approach found is Van Gennip et al. 2015.

## 2. Non-blind deconvolution better than Wiener (RL, TV/L0, binary prior, multi-frame)

### Takeaway
Direct evidence comparing Wiener vs Richardson–Lucy / TV / binary-prior non-blind deconvolution specifically on QR decode rates was not found. The best available evidence (Zeng 2026) indicates that once the kernel is within tolerance, plain regularised linear inversion (conjugate gradients, Tikhonov-like) is enough to decode; kernel accuracy, not the inversion method, dominates.

### Cited Findings
- Zeng et al. 2026 use regularised linear inversion (conjugate gradients, λ = 10⁻³) as the final step; with the ground-truth trajectory, error rate on 100 synthetic images is 17% vs 23% for the full estimated pipeline and 69% for direct decoding, i.e. kernel error accounts for only a few points once inside tolerance. — [arXiv 2610.34788](https://arxiv.org/abs/2610.34788)
- Same paper: "several baseline outputs appear visually sharp and high-contrast yet still fail to decode, whereas our physically inverted reconstructions preserve the module structure". — [arXiv 2610.34788](https://arxiv.org/abs/2610.34788)
- Embree (arXiv 2505.16045, 2025, tutorial): Tikhonov-regularised least squares for 1-D UPC deblurring; illustrates that with 0.1%–1% relative noise unregularised inversion fails and regularisation is required. — [arXiv 2505.16045](https://arxiv.org/abs/2505.16045)
- Van Gennip 2015 thresholding detail: thresholding per block (module) vs per pixel was tested; per-pixel thresholding of the TV output gave better ZBar readability in their tests. — [arXiv 1410.6333](https://arxiv.org/abs/1410.6333)

### Inferences
- For a binary target, adding a bimodal/binary penalty or a few RL iterations after Wiener is plausible but unproven for QR decode rate; the larger lever is likely kernel length/angle accuracy and multi-frame data fusion.
- Multi-frame: averaging aligned blurred ROIs before Wiener (current approach) only improves SNR; jointly deconvolving N observations (each with its own kernel, e.g. sum of per-frame normal equations) is the standard multi-observation formulation, but no QR-specific quantitative study was found.

### Gaps
- No source found giving decode-rate comparisons Wiener vs RL vs TV vs binary-prior on QR codes; no multi-frame (burst) QR deconvolution study found. These would need in-house experiments on the existing 33-pass semi-synthetic set.

## 3. Deep-learning deblurring for QR (DeblurGAN-v2, NAFNet, Restormer, QR-specific)

### Takeaway
Fine-tuned general networks (NAFNet-32, MIMO-UNet+) reach ~82–84% on real QR photos; DeblurGAN-v2 only ~26%; untuned released weights 12–25%. QR-specific networks report 71–90% on their own small test sets, but runtimes are 0.23–0.9 s per image on GPU (CPU not reported), and they were trained on ≥8 px/module, heavily blurred phone images — not 2 px/module conveyor crops. CPU feasibility is unproven.

### Cited Findings
- Li, Guo, Li, Zhao (arXiv 2510.12098 2025; Sensors 26(15) 4879, 2026) ADNet / EG-Restormer: test set 150 motion-blurred QR (100 synthetic, 50 real); decoder ZBar. Decoding rate (pretrain GoPro / GoPro + QRData fine-tune): LENet 32.67% / 49.33%, NAFNet-32 40.67% / 81.33%, Restormer 50.00% / 88.67%, EG-Restormer 58.67% / 90.00%. Params / FLOPs (512²) / avg time: LENet 0.28 M / 3.87 G / 0.23 s; NAFNet-32 17.11 M / 64.44 G / 0.794 s; Restormer 26.13 M / 564.96 G / 0.838 s; EG-Restormer 26.13 M / 565.14 G / 0.910 s. ADNet (blur-severity routing by Laplacian variance) keeps 90% DR at 0.737 s (−19%). Hardware for timings not stated in the arXiv text. — [arXiv 2510.12098](https://arxiv.org/abs/2510.12098); code [github.com/leejianping/ADNet](https://github.com/leejianping/ADNet)
- Dong, Liu, Li, Ren, Xie (Int. J. Comput. Intell. Syst. 17:83, 2024) GAN + attention: ZBar recognition rate on 600 synthetic + 80 real blurred QR: unprocessed 14.56%, DeblurGAN 36.76%, DeblurGAN-v2 56.91%, SRN 67.35%, proposed 71.02% (+387% over baseline); proposed 0.55 s per code; hardware Xeon Gold 6230R + Tesla T4. (Param/FLOPs/time column alignment in the PDF table is ambiguous for the baselines.) — [Springer OA](https://doi.org/10.1007/s44196-024-00450-7)
- LCM-QRIR, lightweight causal Mamba (Sci. Rep. 2026): synthetic BQRCI dataset with mostly horizontal linear motion kernels, 75% of kernels 11–17 px; reports +1.1% recognition rate over second-best method; under fixed noise/illumination, all codes fail at kernel K ≥ 18 px and succeed at K < 18. — [Nature Sci. Rep.](https://doi.org/10.1038/s41598-026-49128-4)
- Earlier QR-specific nets referenced: Pu et al. 2019 doubly CNN (Multimed. Tools Appl. 78); Li et al. 2022 feature extraction + adaptive thresholding (Neurocomputing 493); Wang et al. 2019 GAN; Multi-residual GAN (SPIE 2022). — cited in [arXiv 2510.12098](https://arxiv.org/abs/2510.12098) and [OpenAlex record](https://doi.org/10.1117/12.2640025)
- Zeng 2026: fine-tuned NAFNet-32 83.6%, MIMO-UNet+ 81.9%, EG-Restormer 73.7%, DeblurGAN-v2 25.7% on 955 real photos (Section 1). — [arXiv 2610.34788](https://arxiv.org/abs/2610.34788)

### Inferences
- On a CPU at 2 px/module, a ROI of a v1 QR (21 modules + quiet zone ≈ 50–60 px) is tiny; a LENet-class model (0.28 M params, 3.87 GFLOPs at 512²) would cost roughly 3.87 × (64/512)² ≈ 0.06 GFLOPs on a 64×64 crop — plausibly a few ms on CPU. This is a scaling estimate, not a measurement.
- Networks trained on phone images with 8+ px/module will not transfer to 2 px/module; any DL route requires training on the project's own synthetic conveyor blur at native resolution.

### Gaps
- No paper reports CPU latency or results at ~2 px/module. No conveyor/industrial QR deblurring dataset with real-camera decode rates was found.

## 4. Acquisition-side methods (strobe, coded exposure, event cameras, line scan/TDI) and required exposure

### Takeaway
Shortening the effective exposure (strobe/flash synced to the camera) is the most direct fix: blur in modules = v · t / module size, so <0.5 module at 0.2–2 m/s needs tens of µs to a few ms depending on module size. Coded exposure (flutter shutter) has been demonstrated on 2D barcodes (Xu & McCloskey, WACV 2011) and makes the kernel invertible, but theory shows only a ≤1.17× RMSE gain over an optimal short snapshot when velocity is known. Line-scan/TDI with encoder sync removes motion blur by design.

### Cited Findings
- Xu & McCloskey (WACV 2011) "2D Barcode localization and motion deblurring using a flutter shutter camera": coded exposure "enables well-posed de-convolution and decoding over a wider range of velocities"; includes 2D barcode localisation under blur, a deblur quality metric, and motion-direction estimation from coded-exposure images; tested on real camera images. (Numbers not retrieved; closed access.) — [DOI 10.1109/WACV.2011.5711498](https://doi.org/10.1109/wacv.2011.5711498)
- Tendero / Morel line of theory (SIAM J. Imaging Sci. 2016): when relative velocity is a known constant, a flutter shutter cannot gain more than a factor 1.17 in RMSE over the optimal snapshot; gains appear only under a random velocity model. — [DOI 10.1137/15M1035872](https://doi.org/10.1137/15m1035872)
- TDI: a line-scan technique where charge is shifted in sync with object motion so each line is exposed repeatedly; readout speed is matched to object motion, turning motion into extra integration for low light. — [Wikipedia: Time delay and integration](https://en.wikipedia.org/wiki/Time_delay_and_integration)
- Event-camera / neuromorphic approaches exist for motion (e.g. arXiv 2605.17984 "See Silhouettes in Motion with Neuromorphic Vision") but no QR/2D-code reading evaluation was found. — [arXiv 2605.17984](https://arxiv.org/abs/2605.17984)

### Inferences (calculations, not from a source)
- Exposure needed for blur b (in modules): t = b · m / v, with m = module size. For b = 0.5 module (v in m/s = mm/ms):

  | module m | 0.2 m/s | 0.5 m/s | 1 m/s | 2 m/s |
  |---|---|---|---|---|
  | 0.25 mm | 625 µs | 250 µs | 125 µs | 62.5 µs |
  | 0.5 mm | 1.25 ms | 500 µs | 250 µs | 125 µs |
  | 1.0 mm | 2.5 ms | 1.0 ms | 500 µs | 250 µs |

- From the user's own numbers: 6 px blur ≈ 3 modules at 8 ms, so ≈0.375 module/ms; reaching 0.5 module needs ≈1.3 ms (≈6× shorter exposure); 3 px blur at 8 ms implies ≈2.7 ms for 0.5 module. With new lighting, compensating 6× less exposure needs ~6× more light or extra gain (≈+15.6 dB, adding noise). A strobe (LED overdrive, µs-scale pulse) synced to the Basler exposure-active/flash output gives the short effective exposure without losing brightness.
- Given Zeng's tolerance data, getting blur below ~1 module also makes any residual deconvolution far more forgiving of kernel-length errors (tolerance widens toward ±80% at small amplitude).

### Gaps
- No quantitative real-camera conveyor study of strobe vs deblur decode rates was found; coded-exposure barcode decode rates not retrieved; no QR evaluation for event cameras.

## 5. Vendor rules of thumb (Cognex, Basler, Teledyne, Zebra/Matrox, MVTec)

### Takeaway
Vendor application notes could not be retrieved in this session (vendor sites returned empty/blocked pages to direct fetches), so no sourced vendor rule (e.g. "max blur ≤ X module") can be reported. The only sourced resolution guideline found is ~3–3.5 px/module for reliable QR detection (Skurowski et al., as cited by Zeng 2026).

### Cited Findings
- "Reliable QR detection requires roughly 3 to 3.5 pixels per module" (Skurowski et al., cited) — [arXiv 2610.34788](https://arxiv.org/abs/2610.34788)

### Inferences
- The project's ~2 px/module is below that cited 3–3.5 px/module guideline before any blur; blur and sampling problems compound. Raising resolution (lens/working distance, ROI band) may matter as much as deblurring.

### Gaps
- Cognex DataMan, Basler, Teledyne DALSA, Zebra/Matrox and MVTec HALCON (find_data_code_2d) guidance on maximum blur in modules, and their exposure/strobe calculators, were not retrieved; the commonly quoted "blur < 1 pixel / < ½ module" rule remains unsourced here and should be verified directly from vendor documentation.
