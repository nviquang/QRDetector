# Model-based (non-learning) decoding of QR codes under compound blur (motion box + defocus) at low resolution

Scope of these notes: QR v2-L, ~2.3 px/module, 6–7 px vertical box motion blur convolved with isotropic Gaussian (σ≈0.8–1.2 px) or disk defocus, contrast ~50 gray levels, noise σ≈2.5, 20–150 frames per pass. Generic motion deblurring, binary grid reconstruction and Mosaic-SR were covered elsewhere and are not repeated. Sections marked "our calculation" are small simulations run for this note (scripts in the session scratchpad). They are not published results.

## 1. Which papers/methods address QR/barcode deblurring with defocus + motion, and at what blur/SNR?

### Takeaway
No published QR/barcode method was found that handles *compound* motion + defocus at ~2 px/module. Every QR-specific paper tests Gaussian-only or motion-only blur, at 3–8+ px/module, and usually without noise or with very large noise. The benchmark closest to our case is a 2026 arXiv paper on motion-blurred QR codes. On real photos it reports Pan et al. (L0) at 20.3% and van Gennip et al. at 17.1%, against 93.1% for its own forward-model fitting. It names coupled defocus as unmodelled and as a cause of its failures.

### Cited Findings
- **van Gennip, Athavale, Gilles, Choksi (IEEE TIP 2015).** Pipeline: weighted-TV-flow denoising, then kernel estimation by comparing the known upper-left finder pattern with the denoised corner (no parametric blur model), then TV deconvolution, then a global threshold, then ZBar. The module is **8 px**. Blur is a Gaussian (fspecial size 3–11, large std, so the kernel is effectively truncated to the window) or motion of length **{3, 7, 11, 15, 19} px**, i.e. 0.4–2.4 modules. Noise types: Gaussian, uniform, salt-and-pepper, speckle. Readability is the ZBar success rate over 10 noise realisations. Per-pixel thresholding was read better by ZBar than per-module averaging. Compound blur was not tested. — [arXiv 1410.6333](https://arxiv.org/pdf/1410.6333)
- **Rioux, Scarvelis, Choksi, Hoheisel, Maréchal (IEEE TPAMI 43(1), 2021): "Blind Deblurring of Barcodes via Kullback-Leibler Divergence".** Method: maximum entropy on the mean, with a *symbolic prior* (each module is Bernoulli on {0,1}), solved via the Fenchel–Rockafellar dual with scipy L-BFGS. QR codes were upscaled ×3, so a module is 3×3 px. In the **noiseless** case the method first fails at these kernel widths (in px, i.e. ÷3 for modules), against ZBar on the raw blurred image:
  - non-blind, Gaussian: 29–35 px, ZBar 5–5.8;
  - non-blind, motion: 31–66 px, ZBar 6.6–7;
  - blind, Gaussian: **9–10.6 px**;
  - blind, motion: 25–34 px.

  Gaussian blur is harder than motion blur of the same kernel width ("Gaussian … l² points … vs l points"). Noisy results are only in the supplementary figures. One real out-of-focus phone image is shown. No compound blur. Runtime is not tabulated; the authors say unoptimised Python/L-BFGS is the bottleneck. — [Rioux et al. PDF](https://www.math.mcgill.ca/rchoksi/pub/KL.pdf)
- **Liu, Du, Xu (Pattern Recognition Letters 111, 2018).** QR blind deconvolution with a binary-characteristic term plus an L0 regulariser, solved by alternating minimisation with auxiliary variables. Only the abstract was accessible; no blur/SNR numbers verified. — [Semantic Scholar](https://www.semanticscholar.org/paper/QR-codes-blind-deconvolution-algorithm-based-on-and-Liu-Du/19aadc6a1c7cf04cc5276ade5ec4b4cd56d3d7a8), [ADS](https://ui.adsabs.harvard.edu/abs/2018PaReL.111..117L/abstract)
- **Wang, Chen, Ren (2024, Springer LNCS chapter).** A "Local Extremum Intensity" prior for blind QR deblurring. The claim of better restoration than generic SOTA was not verified numerically. — [Springer](https://link.springer.com/chapter/10.1007/978-981-97-1417-9_19)
- **Motion-blurred QR decoding (arXiv 2610.34788, 2026).** This is the strongest recent evidence for forward-model fitting over deconvolve-then-decode.
  - Data: 955 handheld photos.
  - Exact-match results: model-based trajectory search plus alternating fitting **93.1%** (0 wrong strings, 66 rejected); best network NAFNet-32 83.6%; **Pan et al. (L0) 20.3%**; **van Gennip et al. 17.1%**.
  - Inversion: regularised (BᵀB+λI)⁻¹Bᵀ by conjugate gradients, λ=10⁻³, at most 40 iterations, on linearised intensities.
  - Runtime: median 5.8 s, 90th percentile 33.8 s per photo on one GPU.
  - Resolution: renders use ≥8 px/module. 63 of the 66 real-photo rejections are below 12 px/module.
  - Defocus was disabled in the tolerance tests. Of 100 synthetic images, 17 fail even with the ground-truth trajectory, which the authors partly attribute to "unmodelled defocus". Coupled defocus is listed as future work.

  — [arXiv 2610.34788](https://arxiv.org/html/2610.34788)
- **Iwen, Santosa, Ward (SIAM J. Imaging Sci. 6(1), 2013), 1-D UPC.** Symbol-based greedy fitting of codeword templates to the blurred signal, instead of deblurring. Results:
  - Guarantee regime: Gaussian blur width ≤ minimal bar width, i.e. **σ ≤ 0.425 X** (X = narrowest bar). Noise ceiling per block ≈ αr(e^(−σ) − 1.2σ), giving ≤0.144·αr at σ=0.425.
  - Empirically tolerates noise of about 0.25× the signal norm with an accurate σ̂. Examples at σ=0.45–0.75 decode about 80% (α=1) and about 60% (α=0.25).
  - At low noise, only a moderate decline even when |σ̂−σ|≈σ.
  - O(m) cost, under 1 s. Simulations only.

  — [arXiv 1210.7009](https://ar5iv.arxiv.org/html/1210.7009)
- **Esedoglu (Inverse Problems 20, 2004), "Blind deconvolution of bar code signals".** Gaussian kernel with unknown width and amplitude, TV-regularised variational problem, plus a uniqueness result: noiseless signal ⇒ unique bar code. Two regularisation parameters must be tuned. — [Esedoglu PDF](https://dept.math.lsa.umich.edu/~esedoglu/Papers_Preprints/barcodes_esedoglu.pdf) (summarised via search snippets; full text not read)
- A heuristic quoted in barcode literature: once the blur radius exceeds about half the bar width, the radius cannot be estimated from the image and the code cannot be read. This is a rule of thumb for edge-based readers, not a bound. — [Iwen et al. search context / arXiv 1210.7009](https://arxiv.org/pdf/1210.7009)
- **Generic binary/text priors.** Pan et al.'s L0 intensity+gradient prior is the usual QR baseline, and it performs poorly on real blurred QR (20.3% above). — [arXiv 2610.34788](https://arxiv.org/html/2610.34788)
- **A recent arXiv preprint** on binary/pattern image blind deconvolution with pixel-intensity constraints and a sparse-gradient prior includes a QR test image. Its ID/date looked unusual in the search results and it was not verified. — [arXiv 2609.23268](https://arxiv.org/pdf/2609.23268)

### Inferences
- Measured in modules, our case is (motion 6.5 px ≈ 2.8 modules) ⊗ (σ 1.2 px ≈ 0.52 module; FWHM ≈ 1.2 modules). That is outside the 1-D guarantee regime of Iwen et al. (σ ≤ 0.425 X) on the defocus axis alone, and within the motion range van Gennip et al. tested, but at 3.5× fewer px/module and with compound blur. No paper validates this regime. Treat all published success rates as non-transferable.
- The consistent message across van Gennip, Rioux, Iwen and arXiv 2610.34788 is that structure-constrained fitting (symbol/finder prior, codeword templates, forward model + decoder acceptance) beats deblur-then-threshold by a large margin. The gain comes from the prior, not from a better deconvolution filter.

### Gaps
- No paper found with QR results under motion ⊗ Gaussian/disk blur, at ≤3 px/module, with stated noise σ. The Liu 2018 and Wang 2024 numbers could not be accessed.
- The Schrier 2015 UMN thesis on the resolution/noise needed to decode barcodes in camera scanners was not readable (HTTP 403). — [UMN conservancy](https://conservancy.umn.edu/bitstream/handle/11299/175329/Schrier_umn_0130E_16096.pdf%3Bsequence%3D1)

## 2. PSF estimation for compound blur, and sensitivity of decoding to PSF error

### Takeaway
Published joint estimators of motion length + defocus radius are old (GRNN regression, cepstrum/spectral methods) and assume larger blur and higher SNR. For QR, the practical route is to fit the parametric PSF (box length L, σ or disk radius) to the *known* function patterns (finder, timing, separators) in the forward model. Our calculation shows that **σ errors of 0.2–0.4 px and module-pitch errors of ~1% create systematic model errors comparable to the 2.5-gray noise**. Multi-frame averaging cannot remove these errors, so PSF/grid precision, not noise, becomes the limit once frames are stacked.

### Cited Findings
- Joint defocus+motion parameter identification: motion length and defocus radius estimated from the jointly blurred image with a generalized regression neural network, simulated on the Brno QR database. The paper notes that earlier joint-blur work assumed the motion PSF was known. — [Springer CSI Trans. ICT 2014](https://link.springer.com/article/10.1007/s40012-014-0039-3)
- Defocus-only QR: the disk radius is estimated from QR step edges (edge spread), then Wiener restoration. — [Chen et al. 2021](https://rgu-repository.worktribe.com/preview/1369604/CHEN%202021%20Fast%20restoration.pdf)
- Motion-only QR: the PSF is estimated from the spectrum ("improved twice Fourier transform"), with fractional-order regularised deblurring. — [Yu et al., IET Image Processing 2019](https://ietresearch.onlinelibrary.wiley.com/doi/10.1049/iet-ipr.2018.5792)
- van Gennip et al. estimate a *non-parametric* kernel by matching the known upper-left finder pattern. Earlier work used the L-shaped finder pattern to estimate the Gaussian σ. — [arXiv 1410.6333](https://arxiv.org/pdf/1410.6333)
- **Sensitivity (motion only, ≥8 px/module), arXiv 2610.34788:**
  - Constant speed, 4-module translation: length tolerance falls to **8–11%**.
  - Direction tolerance shrinks from 13° (2 modules) to 5° (4 modules).
  - Underestimating the length is tolerated more than overestimating it: 54% vs 29% at 2 modules with speed ratio 2.1.
  - A 10% length overestimate cuts the direction tolerance from 13° to 8°.
  - Their search grid uses length scale 0.70–1.35 in 0.05 steps.

  — [arXiv 2610.34788](https://arxiv.org/html/2610.34788)
- 1-D barcodes (Iwen et al.): error bound B(σ=0.425, σ̂) is 0.345 / 0.065 / 0.161 / 0.307 / 0.589 for σ̂ = 0.2 / 0.4 / 0.5 / 0.6 / 0.8. Underestimating or overestimating σ by 0.2 roughly multiplies the error term by 2.5–5. — [arXiv 1210.7009](https://ar5iv.arxiv.org/html/1210.7009)
- **Our calculation** (not published). Random 25×25 pattern, 2.3 px/module, contrast 50, true PSF = box 6.5 px vertical ⊗ Gaussian σ=1.2, ×10 supersampled then pixel-integrated. RMS difference of the predicted image versus the true one, over an 80×80 px canvas of which the QR is ~55%, so per-QR-pixel values are ~1.35× higher:

  | Wrong model parameter | RMS error (gray) |
  |---|---|
  | σ = 1.0 | 0.90 |
  | σ = 0.8 | **1.89** |
  | L = 6.0 or 7.0 | 0.40 |
  | grid offset 0.2 px, vertical | 0.45 |
  | grid offset 0.2 px, horizontal | 0.74 |
  | module pitch +0.9% (2.32 vs 2.3) | **1.38** |

  For comparison, noise σ is 2.5 per frame, which falls to 0.35 after averaging 50 frames.

### Inferences
- With compound blur, the decoder is more sensitive to **σ (defocus) and module pitch** than to motion length. L errors of ±0.5 px cost <0.5 gray RMS, while a 0.4 px σ error costs ~1.9 gray. Our solvers search σ ∈ {0.45..1.2}; a coarse σ grid or σ fixed per frame could explain failure at σ ≥ 0.8. Recommend a finer σ grid (Δσ ≤ 0.1), or continuous σ fitted jointly with grid pitch/affine on the finder + timing patterns, using all frames (the PSF is the same across the pass if focus is constant).
- **Disk vs Gaussian.** Real lens defocus at this level is close to Gaussian once pixel aperture and lens aberrations are included, but a disk PSF has MTF zeros (first zero at f ≈ 0.61/R). Fit both shapes and keep the one with lower residual on the function patterns. This is unverified for our camera; a quick test is to fit the ESF of the finder's outer edge horizontally, where there is no motion blur, and compare residuals.
- **Separable estimation.** Motion blur is purely vertical, so a horizontal edge profile (vertical edges of the finder/timing) measures defocus + pixel aperture only. Vertical edge profiles then measure box ⊗ defocus with defocus already known. Unlike blind estimation, this decouples the two parameters. Exposure uncertainty enters only through L, which matters least (above).
- Cepstrum/spectral motion-length estimation needs many periods of blur. On a ~57 px QR with L≈6.5, spectral zeros at f=k/6.5 are hard to locate at 3 gray signal, so it is not recommended over fitting known patterns. This is an inference; no paper tested it at this scale.

### Gaps
- No published sensitivity numbers for σ error in 2-D QR decoding at ~2 px/module. Our numbers are a model-mismatch proxy, not decode-rate measurements.
- The accuracy of joint (L, σ) estimation from finder patterns at SNR ≈ 20:1 (50/2.5) has not been reported anywhere found.

## 3. Decoding directly in the measurement domain: ML/MAP module classification, message passing, soft-decision RS, known bits

### Takeaway
No academic QR paper was found that does full ML/BP decoding with soft Reed–Solomon. The closest evidence is an open-source reader (go-qr PR #186), one of the 1-D barcode papers, and the 2026 forward-model paper. go-qr's neighbour-aware least-squares module classifier, with per-module LLRs and GMD-style erasure decoding, lifts blurred-photo reads from 73.3% to 82.2%. Simulation shows that erasing all check bytes is dangerous: wrong codewords were accepted in >99% of unrecoverable blocks without a 2-byte margin. Our minimum-distance calculation suggests that, with an exactly known forward model, sequence/ML detection has a large per-frame margin even at box 6.5 ⊗ σ 1.2. Model accuracy and the detector, not the noise, are the bottleneck.

### Cited Findings
- **go-qr PR #186** (open-source project write-up, not peer-reviewed).
  - Classifier: function-pattern modules are used as pilots. Per window, it does a least-squares fit of luminance on the module's own darkness, the darkness of its **8 neighbours** and a constant, which captures blur/contrast/ISI. Modules are re-decided given their neighbours for 3 iterations. Reliability is the LLR of the two values; a codeword's reliability is that of its weakest module.
  - Decoding: hard decisions first, then erase the 2, 4, … least reliable codewords (Forney GMD), gated by ≥75% of function-pattern modules being correct.
  - Results on the BoofCV set (536 photos): 78.4% → 80.6% overall; **blurred 73.3% → 82.2%**; glare 58.0% → 68.0%. Cost about +1% on most decode benchmarks.
  - Safeguards: the misdecode-protection codewords (ISO 18004 Table 9) are never used in soft attempts; a 2-byte-per-block margin is always kept; at least one valid data segment is required. Over ~3 M random grids, no false decode through the soft path.

  — [go-qr PR #186](https://github.com/piglig/go-qr/pull/186)
- **go-qr PR #185.** Errors-and-erasures RS decoding, valid when 2e + s ≤ n − k. Erasing up to full redundancy with uninformative reliabilities produced wrong codewords in >99% of version-4+ blocks. — [go-qr PR #185](https://github.com/piglig/go-qr/pull/185)
- Successive errors-and-erasures (GMD-type) soft-decision decoding of RS codes is established theory. — [ResearchGate: Soft-decision decoding of RS codes using successive error-and-erasure decoding](https://www.researchgate.net/publication/224356431_Soft-Decision_Decoding_of_Reed-Solomon_Codes_Using_Successive_Error-and-Ersure_Decoding)
- 1-D analogue of measurement-domain decoding: Iwen et al. fit codeword templates directly to the blurred signal, never deblurring, and get recovery guarantees. — [arXiv 1210.7009](https://ar5iv.arxiv.org/html/1210.7009)
- Rioux et al. place a Bernoulli (symbolic) prior directly on module values. With the symbolic prior, the noiseless blind cut-off widths (UPC-A) are 75–77 px, against ~19 px for a uniform prior. That is ~4× from the prior alone. — [Rioux et al. PDF](https://www.math.mcgill.ca/rchoksi/pub/KL.pdf)
- arXiv 2610.34788 accepts a result only when two decoders agree, and reports 0 wrong strings out of 955. Its ablation shows direct decoding at 84.3% error, a network trajectory at 22.7%, trajectory search at 12.5% and alternating fitting at 6.9%. Iterative re-fitting of the forward model is the step that matters. — [arXiv 2610.34788](https://arxiv.org/html/2610.34788)
- **Our calculation: minimum error-event distance** (not published). Pixel-domain Euclidean distance between predicted images of two module patterns, brute force over all {−1,0,+1} error patterns in a 4×3-module window, contrast 50 gray, 2.3 px/module:

  | PSF | Single-module flip | Minimum error event | Worst pattern |
  |---|---|---|---|
  | no blur | 92.5 | 92.5 | single flip |
  | box 6.5 | 57.3 | 41.3 | vertical pair |
  | Gaussian σ 1.2 | — | 51.5 | 2×2 checker |
  | box 6.5 ⊗ σ 0.8 | 47.5 | 31.6 | — |
  | box 6.5 ⊗ σ 1.2 | 40.4 | **24.7** | 2×2 checker |
  | box 9.2 ⊗ σ 0.8 | — | 22.3 | — |

  Pair-wise error probability ≈ Q(d/2σ_n). With σ_n = 2.5, d/2σ_n ≈ 5 even in the worst case, i.e. an error-event probability of about 3×10⁻⁷ per event per frame *if the model is exact and detection is joint (MLSE/MAP)*.

### Inferences
- The failure at σ ≥ 0.8 is very likely not an information limit of a single frame. It is (a) model mismatch (σ, pitch, registration; section 2), and/or (b) a sub-optimal detector. Wiener/RL plus per-module least squares behaves like linear equalisation: it amplifies noise at frequencies where the box ⊗ Gaussian MTF is ~6%, whereas joint detection uses the full error-event distance. Caveat: the 4×3 window excludes long periodic error patterns. For a pattern at the module-alternation frequency, the distance grows like |H(f)|·contrast·√(pixels) ≈ 0.06·50·√(5.3·n_modules), which still reaches ~24 gray-L2 at n≈12 modules. Very long error events near an MTF zero can be smaller, and the window does not capture them.
- **A practical ML/MAP detector for v2 (25×25)**:
  - Model: the PSF is box(L,vertical) ⊗ G(σ), so the vertical support spans about 4 modules and the horizontal about 2. A column-wise Viterbi / trellis over module rows (state = the 3 previous module rows in a narrow strip) is exponential in strip width, so it is infeasible for full rows. Practical alternatives are:
    - (i) iterative ICM/"turbo" equalisation as in go-qr: decide each module given its neighbours' current soft values, 3–10 sweeps;
    - (ii) loopy belief propagation on the 25×25 grid with pairwise/higher-order factors from the forward model;
    - (iii) a continuous relaxation (box-constrained least squares or a Bernoulli/MEM prior as in Rioux) followed by LLRs from the residual change when each module is flipped.

    All of these are cheap at 625 variables (well under 1 s in numpy per iteration over all frames).
  - Multi-frame: the per-frame log-likelihoods add, provided each frame has its own sub-pixel registration. Average only after registration in the module domain; pixel averaging blurs further.
- **Known bits for QR v2-L with byte-mode 27-byte payload "14 digits # 12 digits":**
  - All function patterns: finders, separators, timing, the alignment pattern at (18,18) for v2, and the dark module.
  - The format information (15 bits, ×2 copies; only 8 valid patterns for EC level L, one per mask). Detecting the mask by ML over 8 hypotheses using both copies is very robust.
  - Mode indicator 0100 (byte) and an 8-bit count = 27.
  - For each digit byte the high nibble is 0011; the '#' byte (0x23) is at a fixed position (byte 15); terminator 0000.
  - v2-L holds 34 data codewords and 2 bytes + 4 bits are used by the header, so data = 27 bytes plus header; the remaining bytes are known pad 0xEC/0x11 after terminator alignment.

  Roughly: header 12 bits + 26×4 known nibble bits + 8 bits for '#' + terminator/pad. That is about 130–150 of the 272 data bits (~50%) known a priori. These count arithmetics are an inference from the ISO 18004 structure and should be checked against our encoder. Known data bits can be fixed in the MAP detector (forcing the modules) and used as additional pilots for σ/grid fitting. In RS decoding they are known codeword *symbols* only where a whole byte is known (the '#', pad bytes, the count byte), so they act as erasure-free anchors; partially known bytes reduce the candidate list in list/Chase decoding (e.g. 16 candidates per digit byte instead of 256, actually 10 valid digits).
- **Soft RS for v2-L.** 44 codewords in one block, 10 EC, so e_max=5 by 2e ≤ 10. The ISO misdecode-protection value p for v2-L is believed to be 2, so a safe e_max is about 4 (from memory, not verified here; check ISO 18004 Table 9). Chase-type decoding with digit constraints (each digit byte has only 10 valid values) plus a content-pattern check (^\d{14}#\d{12}$) provides a strong extra validity check that hard RS lacks. Koetter–Vardy-style list decoding could exceed (n−k)/2. Given the miscorrection risk shown by go-qr, require a content-pattern match and multi-frame agreement.

### Gaps
- No peer-reviewed QR paper found that combines a forward-model likelihood, BP/turbo equalisation and soft RS (Koetter–Vardy/GMD). The go-qr evidence is a project write-up on BoofCV photos, not compound-blur synthetic data.
- No QR paper was found that quantifies the gain from known content bits (digit nibbles, pad bytes).

## 4. Theoretical limits: information/CRB near MTF zeros, number of frames, sub-pixel shift diversity

### Takeaway
No published Cramér–Rao or information-theoretic bound specific to *binary* QR patterns under blur was found. The general super-resolution CRB literature (Milanfar group; Felzenszwalb box-deconvolution) shows that box blur is non-invertible for general signals but that sparse/structured signals can be recovered exactly. For our parameters the module fundamental (0.217 cycles/px) sits near the **peak of the first sidelobe** of a 6.5 px box, which is fortunate (|H| ≈ 0.22, with sign inversion). Sub-pixel shifts between frames do *not* move the box zeros. Only a change in blur length (exposure or speed) does that.

### Cited Findings
- Felzenszwalb, "Deconvolution with a Box" (2024): convolution with a box is generally not invertible, but sparse signals can be reconstructed exactly with convex optimisation, with a tight bound that matches an information-theoretic limit (abstract only). — [arXiv 2407.11685](https://arxiv.org/abs/2407.11685)
- Litterio, Felzenszwalb et al., "Super-Resolution with Structured Motion" (2025): pseudo-random camera motion during exposure lets a single low-resolution motion-blurred image reconstruct a sparse high-resolution target via convex optimisation (simulated data plus a stage-mounted camera). The authors' future-work discussion proposes varying the effective box size to remove Fourier zeros. — [arXiv 2505.15961](https://arxiv.org/abs/2505.15961); [search summary](https://www.themoonlight.io/review/super-resolution-with-structured-motion)
- Milanfar-group CRB analysis of super-resolution: treats registration, reconstruction and restoration as joint parametric estimation, and argues that much earlier work quantified the ill-posedness of deblurring rather than true SR limits. — [Robinson & Milanfar PDF](https://users.soe.ucsc.edu/%7emilanfar/publications/journal/SRPerformanceFinal.pdf)
- Multiframe SR with spatial (registration) uncertainty: a CRB-type bound that, for known translations, scales with resolution factor / number of images. — [arXiv 1411.0564](https://arxiv.org/pdf/1411.0564)
- Multi-image SR combining sub-pixel shift and relative defocus blur as cues, with a CRB evaluation (ICIP 2007). — [Unpaywall record](https://unpaywall.org/10.1109%2FICIP.2007.4379992)
- Rioux et al.: the symbolic (binary) prior extends noiseless blind cut-off widths ~4× over a uniform prior. This is empirical support that the binary constraint carries much of the information. — [Rioux et al. PDF](https://www.math.mcgill.ca/rchoksi/pub/KL.pdf)

### Inferences (our calculation unless cited)
- **MTF at the module fundamental**, f = 1/4.6 = 0.217 cycles/px:
  - box 6.5 px: sinc(1.41) ≈ **−0.22** (contrast inverted);
  - box 6.0: −0.20; box 7.0: −0.21;
  - Gaussian σ=1.2: exp(−2π²σ²f²) ≈ 0.26; σ=0.8: 0.55;
  - pixel aperture: ≈ 0.93.

  Combined 6.5 ⊗ 1.2 gives ≈ 0.053 (matching the brief's ~6%). Box zeros fall at f = k/L, i.e. 0.154 and 0.308 cycles/px for L=6.5. **Dangerous lengths** are L ≈ 4.6 px (1 period) and L ≈ 9.2 px (2 periods), where the fundamental is zeroed. For the 6–7 px range the fundamental is near a sidelobe maximum (|sinc| peaks at x≈1.43, f≈0.22 for L=6.5). If line speed rises so that L approaches 9 px, readability should collapse faster than a smooth MTF trend suggests. Exposure should be chosen to keep L away from k·4.6 px, not just "as short as possible".
- **Frames needed.** If the decoder is limited by *noise*, the effective noise after N registered frames is 2.5/√N: 0.56 at N=20 and 0.25 at N=100. A combined fundamental signal of ~3 gray (brief's estimate) then has per-frequency SNR ≈ 5 at N=20 and 12 at N=100. Our error-event distances (section 3) say a single frame already has margin with joint detection and an exact model. So stacking frames mainly helps a *linear* (Wiener/LS) pipeline. The systematic model errors in section 2 (0.4–1.9 gray RMS) do **not** shrink with N. Beyond N≈10–20, effort is better spent on σ/pitch/registration accuracy than on more frames.
- **Sub-pixel shift diversity.** Each frame sees the label at a different vertical sub-pixel phase. This helps with *pixel-sampling* aliasing (2.3 px/module is near Nyquist for the module pattern: 0.217 cycles/px against a Nyquist of 0.5, so the fundamental is fine, but harmonics at 0.43 and 0.65 alias). It does **not** change the box or Gaussian MTF, so zeros stay put. Diversity in the zeros would require different blur lengths per frame, i.e. exposure dithering frame to frame (a coded-exposure-lite strategy), or varying belt speed. Exposure dithering (e.g. alternating L≈5 and L≈7.5 px) is the cheapest hardware change that guarantees no common zeros near the module frequency. This is an inference; the "vary box size to remove zeros" idea appears as future work in Litterio et al.
- **Per-module-pixel budget.** At 2.3 px/module, each module covers ~5.3 px per frame, and the pixel-aperture MTF loss is small (0.93). The binding constraints are the optical/motion MTF product and model accuracy, not sampling.

### Gaps
- No CRB/information bound for discrete-valued (binary) 2-D patterns under box ⊗ Gaussian blur was found. Our minimum-distance numbers are a union-bound proxy over a limited error-pattern window, not a proof.
- No published quantification of how many frames are needed for QR under compound blur. Runtime of a multi-frame ML/BP detector at 625 modules × 20–150 frames is not reported anywhere. Our estimate (well under 30 s on CPU) is an inference.
