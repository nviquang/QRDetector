# Field imaging requirements for QR reading (0.6 m × 1.6–1.8 m area, camera at 1 m)

> Research-condition note (2026-11-06): in this session the WebSearch tool did not work (model error) and WebFetch failed on most vendor sites (socket hang-up). Only pages that could be fetched directly with curl are cited below: DENSO WAVE (qrcode.com, the QR inventor), Wikipedia (QR code, Data Matrix, Depth of field) and Edmund Optics (DOF application note). **No Cognex, Keyence, SICK, Zebra, Datalogic, Basler, Teledyne or MVTec page could be retrieved**, so vendor px/module numbers are listed under *Gaps* as unverified recollection, not as findings. All numeric examples marked "Inference" are my own arithmetic from the stated formulas and the project's parameters. Check them before treating them as fact.

## 1. Minimum pixels per module (vendor and standard guidance)

### Takeaway
The only primary guidance retrieved (DENSO WAVE) says the module must be larger than the reader's resolution, and printed with at least 4 printer dots per module. Sampling theory puts the hard floor at 2 px/module. At 2 px/module (lab: ~51% of static ROIs decoded) the decoder is working at that floor, so a field design should target ≥3 px/module, and preferably 4, to leave margin for blur and phase misalignment.

### Cited Findings
- DENSO WAVE: "Each scanner has its own readable module size limit. The scanner resolution represents this limit." Their example: a 600 dpi, 4-dot module is 0.17 mm, so a scanner resolution finer than 0.17 mm is needed. Source type: inventor's how-to page, undated (living page). — [DENSO WAVE, Point for setting the module size](https://www.qrcode.com/en/howto/cell.html)
- DENSO WAVE recommends that each printed module be made of 4 or more printer dots for stable operation. Example: 300 dpi × 5 dots = 0.42 mm per module. More dots per module reduce the effect of print-width and feed-speed fluctuation, axis distortion and blurring. — [DENSO WAVE](https://www.qrcode.com/en/howto/cell.html)
- DENSO WAVE: "The larger the module is, the more stable and easier to read … It is recommended that QR Code symbols be printed as large as possible within the available printing area." — [DENSO WAVE](https://www.qrcode.com/en/howto/cell.html)
- Data Matrix can be read with only a 20% contrast ratio (Wikipedia citing an industry source). — [Wikipedia, Data Matrix](https://en.wikipedia.org/wiki/Data_Matrix)

### Inferences
- **Sampling floor.** By the Nyquist criterion a module pattern (period = 2 modules) needs ≥2 samples per module even when perfectly aligned. With arbitrary sub-pixel phase, an optical PSF of about 1 px and motion blur, many modules at 2 px/module become mid-grey mixed pixels. This is consistent with the lab result: 2 px/module gave ~51% static decode.
- Working targets for the field, derived from the above. They agree with typical industry practice but are **not vendor-verified here**:
  - ≥4 px/module: "reliable" target. Leaves room for 1–1.5 px of blur and perspective.
  - 3 px/module: "acceptable/marginal". Needs good focus and less than about 0.5 module of blur.
  - 2 px/module: absolute floor, current lab condition. Needs super-resolution or multi-frame fusion, which `PassDecoder` already does.
  - Below 2 px/module: not decodable by sampling.
- Printing: the label printer must give ≥4 dots/module (DENSO). For a 1.9 mm module, a 203 dpi printer gives 15 dots/module, which is no constraint. Print quality therefore does not limit the module sizes discussed here; the camera does.

### Gaps
- Could not retrieve vendor documents. Recollections, **unverified**:
  - Cognex DataMan material is often quoted as about 1.5–2 px/module minimum (Data Matrix) and 3–5 px/module recommended for QR.
  - Keyence SR series quotes minimum "cell size" in mm for each model and distance, not in px.
  - The HALCON `find_data_code_2d` default `module_size_min` is in the low single-digit px, and the "enhanced/maximum" recognition modes allow smaller modules.
  - The report writer should verify these before quoting them.
- ISO/IEC 18004 (QR), ISO/IEC 15415 (2D print-quality grading: aperture, symbol contrast, modulation, axial non-uniformity, grid non-uniformity, unused EC) and ISO/IEC 29158 (AIM DPM) are paywalled. No public summary with px/module numbers was fetched. Note: ISO 15415 grades the *printed symbol*. It does not set a camera px/module minimum.
- GS1 General Specifications X-dimension tables were not retrieved.

## 2. Resolution arithmetic: mm/px, module size and QR size, lens and depth of field

### Takeaway
With the current ~2856 px across 1.6–1.8 m (0.56–0.63 mm/px), a version 1 QR needs modules of about 1.7–1.9 mm (QR ≈ 36–40 mm, ≈ 49–55 mm with quiet zone) for 3 px/module. For 4 px/module it needs 2.2–2.5 mm modules (QR ≈ 47–53 mm, ≈ 65–73 mm with quiet zone). A 12–25 MP sensor brings a 3 px/module v1 QR down to about 20–28 mm. The 1 m distance across a 1.8 m width means an ~84° field angle, so wide-angle distortion and corner fall-off become algorithm concerns.

### Cited Findings
- A QR version V has 4V+17 modules per side: version 1 = 21×21, version 40 = 177×177. — [DENSO WAVE, version page](https://www.qrcode.com/en/about/version.html); [Wikipedia, QR code](https://en.wikipedia.org/wiki/QR_code)
- QR requires a quiet zone of 4 modules on all sides. DENSO's worked example: v3 (29 modules) × 0.254 mm = 7.366 mm, plus 8 modules of margin = 9.398 mm square. — [DENSO WAVE, code area](https://www.qrcode.com/en/howto/code.html)
- Approximate depth of field: DOF ≈ 2·N·c·u²/f², where N = f-number, c = acceptable circle of confusion, u = subject distance and f = focal length. DOF scales linearly with N and c, with the square of distance, and inversely with the square of focal length. — [Wikipedia, Depth of field](https://en.wikipedia.org/wiki/Depth_of_field)
- Edmund Optics: DOF can only be quantified for a given detail size or spatial frequency. Smaller details need higher frequency and give less DOF. There is more usable DOF beyond best focus than in front of it. Lower f/# means less DOF. With high pixel counts (especially line scan with low f/#), focus alignment becomes critical. — [Edmund Optics, Depth of Field and Depth of Focus (application note)](https://www.edmundoptics.com/knowledge-center/application-notes/imaging/depth-of-field-and-depth-of-focus/)

### Inferences
**Core formulas** (all lengths in mm):
- Object pixel size: `p = FOV_width / N_px`
- Module needed: `m = k · p`, where k = target px/module
- QR side: `S = (4V+17)·m`. Footprint with quiet zone: `(4V+25)·m`
- Lens focal length (thin lens): `f ≈ WD · w_sensor / (FOV + w_sensor) ≈ WD · w_sensor / FOV`, where `w_sensor = N_px × pixel_pitch`

**Current camera, 2856 px:**

| FOV width | mm/px | m @2 px | m @3 px | m @4 px | v1 QR @3 px (with QZ) | v1 QR @4 px (with QZ) |
|---|---|---|---|---|---|---|
| 1.6 m | 0.560 | 1.12 | 1.68 | 2.24 | 35.3 (48.7) | 47.1 (65.0) |
| 1.8 m | 0.630 | 1.26 | 1.89 | 2.52 | 39.7 (54.8) | 52.9 (73.1) |

**Higher-resolution sensors**, full width across 1.8 m. Widths are typical for those sensor classes (12 MP 4096, 20 MP 5472, 25 MP ≈5120–5328, 45 MP ≈8192, 65 MP 9344); verify against the chosen datasheet.

| Sensor | width px | mm/px (1.8 m) | m @3 px | v1 QR @3 px | v1 QR @4 px |
|---|---|---|---|---|---|
| current | 2856 | 0.630 | 1.89 | 39.7 | 52.9 |
| 12 MP | 4096 | 0.439 | 1.32 | 27.7 | 36.9 |
| 20 MP | 5472 | 0.329 | 0.99 | 20.7 | 27.6 |
| 25 MP | 5120 | 0.352 | 1.05 | 22.1 | 29.5 |
| 45 MP | 8192 | 0.220 | 0.66 | 13.8 | 18.5 |
| 65 MP | 9344 | 0.193 | 0.58 | 12.1 | 16.2 |

(At 1.6 m, multiply by 0.889.)

**Inverse view (fixed label size):** a 25 mm v1 QR (1.19 mm/module) on the current camera gives 1.9–2.1 px/module, which is the current lab regime. Reaching 3 px/module at 25 mm needs ≤0.40 mm/px, which means ≥4500 px across 1.8 m.

**Sensor aspect and band:** 1.8 × 0.6 m is 3:1. A 4:3 sensor spanning 1.8 m covers about 1.35 m in the other axis, so a horizontal ROI band is efficient. Band height in object space = rows × mm/px. For example, 768 rows × 0.63 = 484 mm.

**Lens at WD = 1 m:**
- Half-angle across width = atan(0.9/1.0) ≈ 42°, so the full horizontal field is about 84°.
- Example: w_sensor = 2856 × 3.45 µm ≈ 9.9 mm gives f ≈ 5.5 mm. A 14 mm (4096 × 3.45 µm) sensor gives f ≈ 7.8 mm.
- At this angle:
  - Natural vignetting cos⁴(42°) ≈ 0.31, so the corners get about 30% of center illumination before lens/lighting compensation.
  - Short-focal-length machine-vision lenses typically show noticeable barrel distortion. Module pitch therefore varies across the field, and module grids at the edges are curved.
  - Objects above the belt are magnified by `WD/(WD−h)`. A 300 mm tall box gives 1/0.7 = 1.43× larger modules but also shifts focus by 300 mm.
- Algorithm consequence: the decoder must tolerate position-dependent scale (±40%), perspective/keystone (codes viewed at up to ~42° obliquity on box sides) and edge darkening. Undistortion with a calibrated lens model is worth adding before sampling the grid.

**DOF example** (same formula, plus hyperfocal `H = f²/(N·c)`, near `= H·u/(H+u)`, far `= H·u/(H−u)`), with f = 8 mm, pitch 3.45 µm, c = 1 px = 3.45 µm, u = 1000 mm:
- N = 4: H ≈ 4.64 m, sharp from about 0.82 m to 1.28 m.
- N = 2.8: about 0.87–1.18 m.
- With c = 2 px, DOF roughly doubles, but 2 px of defocus blur equals one whole module at 2 px/module. **At low px/module the acceptable circle of confusion must be ≤1 px, so DOF budget and px/module budget trade off directly.**

**Diffraction limit** (standard Airy formula, not fetched): spot diameter ≈ 2.44·λ·N ≈ 1.34·N µm at 550 nm.
- At N = 8 this is ≈10.7 µm ≈ 3 px of 3.45 µm, which destroys 2–3 px/module codes.
- Keep N ≤ ~4 for 3.45 µm pixels and ≤ ~2.8 for 2.4 µm pixels.
- Small-pixel high-MP sensors therefore cannot be stopped down to gain DOF.

### Gaps
- Exact pixel pitch and sensor of the current Basler (2856 px band) was not identified.
- Lens distortion figures for specific 5–8 mm C-mount lenses were not retrieved.
- No Basler/Teledyne lens calculator page was fetched.

## 3. How industrial systems cover wide conveyors

### Takeaway
Wide belts are normally covered by one of the following: several area-scan cameras side by side with overlap, one high-resolution area-scan camera (12–65 MP), or a line-scan camera triggered by a conveyor encoder. Parcel tunnels combine several of these for multi-side reading. Line scan removes motion blur in the travel direction by construction but needs very intense line lighting. No sourced price or resolution data could be retrieved in this session.

### Cited Findings
- Edmund Optics notes that line-scan setups with large arrays and low f/# demand careful alignment between object, lens and sensor, because depth of focus shrinks as pixel count grows. — [Edmund Optics](https://www.edmundoptics.com/knowledge-center/application-notes/imaging/depth-of-field-and-depth-of-focus/)

### Inferences
**Multi-camera area scan.** n cameras each cover `FOV/n + overlap`. The overlap must be ≥ the largest code footprint so that every code is wholly inside at least one view. Example: 2 × 2856 px over 1.8 m with a 70 mm overlap gives about 0.33 mm/px, so a v1 QR at 3 px/module is about 21 mm. This doubles px/module without changing the sensor and gives a narrower field angle (≈24° half-angle at 1 m), which also reduces distortion and vignetting. The project already has a two-camera app (`main_dual.py`) with cross-camera merging over 30 s.

**Line scan with encoder.**
- Required line rate: `f_line = v / p_along`. For p = 0.63 mm: v = 2 m/s needs 3.2 kHz. For an 8k line over 1.8 m (0.22 mm): 2 m/s needs 9.1 kHz.
- Exposure is ≤ 1/f_line (≤110 µs in the latter case), so blur in the travel direction is ≤1 px automatically, but light demand is high.
- Encoder triggering keeps square pixels when belt speed varies.
- For the algorithm, line-scan images have no inter-frame motion. Multi-frame fusion becomes irrelevant, but per-row jitter and speed errors cause aspect-ratio errors that the decoder must tolerate.

**Single high-MP area scan.**
- Simplest optics, but more data per frame. At 25 MP mono, 8 bit, 10 fps that is 250 MB/s.
- Detection on CPU-only hardware at that size is costly. The project's GPU measurements were 190 ms for 2448×2048 on a GTX 1650 and 980 ms on CPU.
- A band/ROI readout or tiling is needed.

**Frame rate needed for area scan** (code must appear whole in at least F frames):
- Formula: `fps ≥ F · v / (L_along − S_code)`, where L_along = along-travel coverage of the band.
- Example: L = 484 mm (768-row band), S = 55 mm, v = 1 m/s, F = 3 (multi-frame `PassDecoder` wants ≥2 confirming reads) gives fps ≥ 7.
- At 2 m/s, fps ≥ 14.

### Gaps
- No tunnel-system documents (SICK, Cognex, Datalogic, Vitronic), line-scan rates or price data could be retrieved. Do not quote costs from these notes.

## 4. Lighting, exposure and motion blur at conveyor speed

### Takeaway
Blur in modules is `v·t/m`. Keeping blur ≤0.5 module with ~1.9 mm modules needs t ≤ 4.7 ms at 0.2 m/s and ≤0.47 ms at 2 m/s. The demo's current default exposure of 12.9 ms gives about 4 px (≈2 modules at 2 px/module) of blur even at 0.2 m/s. Pulsed or overdriven LED strobes or much higher gain are needed. The resulting light deficit (noise) and glare from glossy labels are what the decoder will actually face.

### Cited Findings
- Data Matrix is readable at 20% contrast (useful when strobe light or glare reduces contrast). — [Wikipedia, Data Matrix](https://en.wikipedia.org/wiki/Data_Matrix)
- (No lighting vendor note on strobe/overdrive pulse widths, polarization or dome lighting could be fetched.)

### Inferences
**Formulas:**
- blur_px = `v·t/p`
- blur_modules = `v·t/m`
- max exposure for blur ≤ b modules: `t ≤ b·m/v`
- for ≤ b px: `t ≤ b·p/v`

The project already computes blur length = velocity × measured seq/s × exposure, consistent with this.

**Max exposure for ≤0.5 module blur, m = 1.89 mm** (3 px/module at 0.63 mm/px):

| v (m/s) | 0.2 | 0.5 | 1.0 | 2.0 |
|---|---|---|---|---|
| t_max | 4.7 ms | 1.9 ms | 0.95 ms | 0.47 ms |
| ≤1 px blur (p = 0.63 mm) | 3.2 ms | 1.26 ms | 0.63 ms | 0.32 ms |

With p = 0.33 mm (two cameras or 20 MP), all values roughly halve.

**Current setting:** 12.9 ms at 0.2 m/s gives a blur of 2.58 mm = 4.1 px at 0.63 mm/px. At 2 m/s it is 25.8 mm = 41 px. Going from 12.9 ms to 0.5–1 ms needs 13–26× more light, which is +22 to +28 dB of gain if done with gain alone. That multiplies shot and read noise, so the decoder sees low-SNR images unless a strobe supplies the light. Overdriven LED strobes (pulse widths in the tens of µs to about 1 ms) are the standard industrial answer; this is not sourced in this session.

**Algorithm implications:**
- With short exposure plus strobe, residual blur is ≤0.5 module, and the Wiener/multi-frame deblur path is rarely needed. Noise and low contrast dominate instead, so denoising, frame averaging and adaptive binarization matter more.
- With long exposure (no strobe), blur is several px along the travel direction, so the Wiener deconvolution with known velocity and exposure that `PassDecoder` already implements becomes central.
- Glossy labels and lamination: specular hot spots saturate modules. Cross-polarization or diffuse/dome or off-axis lighting is the usual fix. Otherwise the decoder must handle locally saturated regions; the existing "% clipped" status metric is relevant.
- An 84° field also causes uneven illumination (cos⁴ ≈ 0.31 at the corners) unless the lighting compensates. Use a local or adaptive threshold, not a global one.

### Gaps
- Specific vendor numbers were not retrieved:
  - Gardasoft/Smart Vision Lights overdrive factors
  - CCS/Advanced Illumination guidance on dome/polarized lighting for labels
  - Cognex/Keyence "max line speed vs exposure" tables
- Strobe power needed for 1.8 m-wide coverage at 1 m is not estimated; this needs a lighting vendor's irradiance data.

## 5. Symbol design choices: EC level, version, quiet zone, Data Matrix vs QR

### Takeaway
Version 1-L can correct only about 2 codewords (out of 26). A single smudged area of about 16 modules defeats it, so moving to M/Q/H (or a larger module in the same footprint) directly raises readability. Data Matrix needs only a 1-module quiet zone versus QR's 4. For short payloads it therefore fits much larger modules in the same label area and tolerates 20% contrast.

### Cited Findings
- QR v1 (21×21) at level L holds at most 19 data bytes and uses a (26,19) Reed–Solomon code that corrects 2 codeword errors (Wikipedia's notation "(26,19,2)"). — [Wikipedia, QR code](https://en.wikipedia.org/wiki/QR_code)
- Error-correction levels recover approximately L 7%, M 15%, Q 25% and H 30% of codewords. DENSO: Q or H for dirty factory environments, L for clean environments with lots of data, and "Typically, Level M (15%) is most frequently selected". Raising the level increases symbol size for the same data. — [DENSO WAVE, error correction](https://www.qrcode.com/en/about/error_correction.html); [Wikipedia](https://en.wikipedia.org/wiki/QR_code)
- RS correction needs 2 EC codewords per corrected codeword. — [DENSO WAVE](https://www.qrcode.com/en/about/error_correction.html)
- Wikipedia notes that whether a damaged code reads in practice depends heavily on *where* the damage is. Finder or format damage defeats it regardless of EC. — [Wikipedia](https://en.wikipedia.org/wiki/QR_code)
- Version and data choice: pick the smallest version whose capacity at the chosen EC level fits the data. DENSO's example is 100 characters at level M → v3; 50 alphanumeric at M → v3, because v2-M holds only 38. — [DENSO version](https://www.qrcode.com/en/about/version.html); [DENSO code area](https://www.qrcode.com/en/howto/code.html)
- Data Matrix ECC 200 sizes run from 10×10 to 144×144, plus rectangular 8×18 to 16×48. A 16×16 symbol carries 12 data bytes and 12 EC bytes, correcting up to 6 byte errors. ECC 200 can reconstruct data with 30% damage if the symbol can still be located. Readable at 20% contrast. — [Wikipedia, Data Matrix](https://en.wikipedia.org/wiki/Data_Matrix)

### Inferences
**Footprint comparison** for a fixed label square of side A, with quiet zones included:
- QR v1 uses 21 + 8 = 29 modules, so module = A/29.
- Data Matrix 16×16 with a 1-module quiet zone uses 18 modules, so module = A/18, which is **1.6× larger modules**. The 1-module DM quiet zone is from ISO/IEC 16022 as commonly reproduced and was not fetched here.
- At the same label size on the current camera, 2 px/module QR would become about 3.2 px/module DM. The cost is capacity: 12 data bytes (DM 16×16) versus 19 bytes (QR 1-L).
- Even if QR is kept, **shrinking the printed quiet zone is not an option**, but making the code fill the label is. A QR whose modules are 29/21 of the label share is optimal.

**EC per v1 level.** From the ISO 18004 table as commonly reproduced; only the L row is verified above:
- L: 19 data / 7 EC → corrects 2
- M: 16 / 10 → 4
- Q: 13 / 13 → 6
- H: 9 / 17 → 8 codewords

Each codeword is 8 modules, so H tolerates about 4× more misread modules than L, but holds less than half the data (9 bytes). If the payload fits in ≤13–16 bytes, v1-M/Q is free robustness. Otherwise, use v2-M/Q (25 modules) with larger modules where label size allows.

**For the decoder:**
- With L, a low ratio of errors to correct means near-perfect module sampling is required. That is why 2 px/module with blur yields about 50%.
- Higher EC lets the algorithm accept noisier binarizations and lowers the value of exotic deblurring.
- Since the tracker already requires 2 identical reads, false positives from higher-EC "lucky" decodes stay controlled.

**Printing:** keep ≥4 printer dots per module (DENSO); for mm-scale modules this is easy. Matte stock avoids specular glare.

### Gaps
- Benchmarks comparing Data Matrix and QR decode rates at equal px/module (for example zxing-cpp or libdmtx at 1.5–3 px/module) were not found; the zxing-cpp README has no such data.
- ISO/IEC 16022 and 18004 tables were not fetched directly.
- GS1 recommendations on X-dimension for logistics 2D codes were not retrieved.
