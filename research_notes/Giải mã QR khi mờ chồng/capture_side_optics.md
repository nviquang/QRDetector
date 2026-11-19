# Capture-side and computational-imaging options against isotropic (optical) blur for conveyor QR reading

Geometry assumed throughout (from the brief): Basler a2A2840-48umBAS, 2.74 um pixels, 4 mm lens, working distance u ~ 1000 mm, label module ~1.55 mm (2.3 px x 0.673 mm/px), observed isotropic blur Gaussian sigma ~1 px, contrast ~50 gray levels, noise std ~2.5. Wavelength assumed 550 nm (white/green LED). Thin-lens formulas; all numbers marked "computed" are my own calculations from these assumptions, not from a source.

Formulas used (standard thin-lens / Edmund Optics conventions):
- Magnification m = f/(u - f); object-side pixel = p/m.
- Hyperfocal H = f^2/(N c) + f; DOF limits near = H u/(H + u), far = H u/(H - u), with c = acceptable blur-circle diameter on the sensor.
- Geometric defocus blur-circle diameter on sensor for an object at u' when focused at u0: b = (f^2/N) |1/u0 - 1/u'| (approx., u >> f). A uniform disk of diameter d has per-axis sigma ~ d/4.
- Diffraction: Airy disk diameter = 2.44 lambda N; Gaussian approximation sigma ~ 0.42 lambda N.
- Pixel aperture (100% fill box of 1 px) contributes sigma ~ 0.29 px. Independent blurs add in quadrature: sigma_tot^2 = sum sigma_i^2.

## Q1. Depth of field for 4 mm @ 1 m with 2.74 um pixels; what f-number; is sigma ~1 px defocus, lens MTF, glass, or vibration?

### Takeaway
With a 4 mm lens at 1 m, geometric depth of field is enormous (f/4 keeps the blur circle < 1 px from ~0.6 m to ~3.2 m), and a 50 mm label-height change produces < 0.2 px of defocus at any aperture; so label-height variation cannot explain sigma ~1 px. The observed blur is almost certainly lens resolution (MTF/aberrations, possibly off-axis or out-of-image-circle on a lens designed for a smaller sensor) plus diffraction if the iris is stopped down past ~f/5.6, plus pixel integration; a gross focus-setting error (lens focused at ~0.35-0.45 m or the iris wide open and focused at infinity) is the only defocus scenario that could reach sigma ~1 px, and that is easy to check.

### Cited Findings
- Camera: a2A2840-48umBAS uses Sony IMX546 (global shutter), 2.74 x 2.74 um pixels, 2/3" format, 7.78 x 7.78 mm sensor, 2840 x 2840 default resolution, C-mount, USB3 — [Basler docs](https://docs.baslerweb.com/a2a2840-48umbas); [Basler shop](https://www.baslerweb.com/en/shop/a2a2840-48umbas/)
- Edmund Optics: diffraction-limited minimum spot = 2.44 x lambda x (f/#); increasing f/# for DOF eventually blurs small detail by reaching the diffraction limit; "physics dictates it is impossible to have very high resolution over a large depth of field"; use working f/# rather than nominal f/# — [Edmund Optics, Lens Iris/Aperture Setting](https://www.edmundoptics.com/knowledge-center/application-notes/imaging/lens-iris-aperture-setting/); [Edmund Optics, DOF and Depth of Focus](https://www.edmundoptics.com/knowledge-center/application-notes/imaging/depth-of-field-and-depth-of-focus/) (pages returned 403 to direct fetch; content taken from search snippets)
- Edmund recommends shorter wavelengths to recover some resolution lost to diffraction — [Edmund Optics, Lens Iris/Aperture Setting](https://www.edmundoptics.com/knowledge-center/application-notes/imaging/lens-iris-aperture-setting/)
- Basler's own 4 mm 5 MP lens (C125-0418-5M-P) has a 7.3 mm image circle (1/2.5" format), F1.8-F22, designed for 230 lp/mm at 25% MTF in the center at full aperture for 2.2 um pixels, "at least 50% of resolution in image center" at 5.8 mm image diagonal, typical -18% barrel distortion, relative illumination at least 55%, optimum working distance 0.5 m — [Basler C125-0418-5M-P docs](https://docs.baslerweb.com/c125-0418-5m-p). Basler's shop lists it as suited to sensors up to 1/2" — [Basler shop](https://www.baslerweb.com/en/shop/basler-lens-c125-0418-5m-f4mm/)
- Basler 2/3" 5 MP lenses in the same family start at longer focal lengths (e.g., C23-0824-5M-P, 8 mm: MTF center 0.77 @ 90 lp/mm, 0.53 @ 140 lp/mm at F2.4) — [Basler C23-0824-5M-P docs](https://docs.baslerweb.com/c23-0824-5m-p) (via search snippet)

Computed numbers for the current setup (f = 4 mm, u = 1000 mm, c = 1 px = 2.74 um):
- m = 0.00402, object pixel = 0.682 mm/px (matches the measured 0.673 mm/px), sensor-width field of view ~1.94 m.
- DOF (blur circle <= 1 px): f/1.8: 765-1445 mm; f/2.8: 676-1918 mm; f/4: 594-3156 mm; f/5.6: 511 mm-~22 m; f/8: 423 mm-infinity.
- Defocus blur-circle diameter for a 50 mm height change at 1 m (focused at 1 m): 0.17 px at f/1.8, 0.11 px at f/2.8, 0.08 px at f/4. A glass stack or label height variation of tens of mm is therefore irrelevant for defocus with this lens. Even a 1 px-diameter disk is only sigma ~0.25 px.
- To get defocus sigma ~1 px (disk diameter ~4 px = 11 um) the lens would need to be focused at ~0.35 m (at f/2.8) or ~0.45 m (at f/1.8) while the label is at 1 m; focusing at infinity gives disk diameters of 3.3 px (f/1.8), 2.1 px (f/2.8), 1.5 px (f/4) i.e. sigma 0.8/0.5/0.37 px. So only a gross mis-focus with an open iris reproduces the observed blur.
- Diffraction (550 nm): Airy diameter 0.88 px (f/1.8), 1.37 px (f/2.8), 1.96 px (f/4), 2.74 px (f/5.6), 3.92 px (f/8), 5.39 px (f/11); Gaussian sigma 0.15 / 0.24 / 0.34 / 0.47 / 0.67 / 0.93 px. If the iris has been closed to f/11 "for depth of field", diffraction alone gives sigma ~0.93 px — essentially the observed value.
- Quadrature budget at f/4: sigma_tot = 1 px with pixel aperture 0.29 and diffraction 0.34 leaves sigma ~0.89 px for lens aberrations/misfocus/vibration, i.e. the lens itself would be the dominant term.
- Sensor Nyquist = 1/(2 x 2.74 um) = 182 lp/mm. If the installed lens is a 1/2.5"-class 4 mm lens (7.3 mm image circle) on this 2/3" sensor (7.78 mm square, ~11 mm diagonal), a full-width horizontal ROI band (7.78 mm wide) extends beyond the lens's specified image circle at both ends, where resolution and illumination are unspecified and much worse; even inside the circle, Basler only guarantees >= 50% of center resolution at 5.8 mm diagonal.
- Glass refraction: a plane-parallel plate of thickness t and index n ~1.5 in the path shifts focus by ~t(1 - 1/n) ~ t/3 (standard optics result, not separately sourced); for t = 10-20 mm this is 3-7 mm of object-side shift, which per the DOF numbers above is negligible. Labels lying on top of the glass are not imaged through it at all.
- Vibration: sigma ~1 px = 0.67 mm of relative camera-object motion during one exposure. With a short strobe/exposure (e.g., <= 0.5 ms), vibration at tens of Hz would need amplitudes well over a millimetre to matter; vibration typically shows up as directional (not isotropic) and frame-to-frame varying blur.

### Inferences
- The "defocus is hard to avoid" premise does not hold for this geometry: with a 4 mm lens, geometric DOF covers the entire plausible height range at any f-number. The isotropic blur is a resolution (MTF) problem, not a DOF problem, unless the lens is grossly mis-focused.
- Most likely contributors in order: (1) lens aberrations / MTF at 2.74 um, especially if a low-cost wide-angle or 1/2.5"-format lens is used on a 2/3" sensor and the ROI band includes the outer field; (2) diffraction if f/# >= 8; (3) misfocus (check by focusing on a Siemens star at 1 m with the iris wide open, then stopping down to f/4); (4) pixel integration (fixed, 0.29 px). Glass refraction and height variation are negligible; vibration is unlikely to be isotropic.
- Recommended aperture for the 4 mm lens: f/2.8-f/4 (diffraction sigma 0.24-0.34 px, DOF still ~0.6-1.9 m+). Do not go past f/5.6. Stopping down is not needed for DOF and costs light (each stop = 2x exposure), which works directly against the short exposure needed to kill motion blur.
- A quick diagnostic: measure sigma (edge-spread function on a printed knife edge or the label border) at the image center vs. at the band ends, and at f/2.8 vs f/8. If sigma grows toward the band ends → lens field performance/image circle; if it grows with f/# → diffraction; if uniform and independent of f/# → misfocus/lens center MTF.

### Gaps
- The exact lens model and iris setting in the field are not known; the 1/2.5"-image-circle concern applies only if a lens like the C125-0418-5M is installed. I found no published MTF for a 2/3"-rated 4 mm C-mount lens.
- No sourced measurement of IMX546 pixel MTF/crosstalk; 0.29 px box sigma is an idealization.
- Conveyor speed was not given, so vibration and exposure numbers are generic.

## Q2. Extended-depth-of-field optics: liquid lens / focus sweep, focal sweep + deconvolution, wavefront coding, Scheimpflug; commercial use in barcode readers

### Takeaway
EDOF techniques (liquid-lens refocus or sweep, focal-sweep + deconvolution, cubic-phase wavefront coding) are well established and used in commercial code readers, but they trade away peak MTF/SNR to gain depth range; since this geometry already has more DOF than needed, they would make the isotropic-blur problem worse, not better. They become relevant only after moving to a longer focal length (8-16 mm) where DOF shrinks to ~±50-150 mm.

### Cited Findings
- Focal sweep (Nagahara, Kuthirummal, Zhou, Nayar, ECCV 2008; TPAMI 33(1) 2011): translate the sensor along the optical axis during one exposure; the integrated PSF is nearly depth-invariant, so one deconvolution kernel restores the whole swept depth; claims extended DOF with a wide aperture and low noise — [Nagahara et al. ECCV 2008 PDF](https://stanford.edu/class/ee367/reading/EDOF_Eccv08.pdf); [mlanthology](https://mlanthology.org/eccv/2008/nagahara2008eccv-flexible)
- Wavefront coding (Dowski & Cathey, Applied Optics 1995): cubic phase plate at the aperture stop makes the OTF nearly identical across a depth range; digital restoration removes the blur; cost is reduced dynamic range / noise amplification in restoration — [Wavefront coding, Wikipedia](https://en.wikipedia.org/wiki/Wavefront_coding); [US6842297B2](https://patents.google.com/patent/US6842297)
- CDM Optics (Cathey, Dowski, Mercure) commercialized it; acquired by OmniVision in 2005 (TrueFocus mobile sensors) — [Wikipedia](https://en.wikipedia.org/wiki/Wavefront_coding). A 2002 trade article claimed "up to 1500%" more depth (vendor-era claim, unverified) — [MDDI](https://www.mddionline.com/new-technologies/digital-imaging-technology-extends-depth-of-field)
- 2D barcode scanner with wavefront coding (SPIE 2008): 7 mm EFL, f/6 design, simulated sharp working range ~80-355 mm — [SPIE 6837, 683711](https://nanophotonics.spiedigitallibrary.org/conference-proceedings-of-spie/6837/683711/Field-depth-extension-of-2D-barcode-scanner-based-on-wavefront/10.1117/12.756077.full). TU Delft project on wavefront coding in barcode imaging systems — [TU Delft](https://optics.tudelft.nl/index.php/optics-research-group/research/finished-projects/design-guideline-for-wavefront-coding-in-aperture-stop-lenses-separated-barcode-imaging-system/)
- Liquid lenses in readers: Cognex added liquid-lens autofocus to the DataMan 300; for presentation reading, tote scanning and small-package sorting the lens can sweep its full focal range (vendor claim) — [Automate.org](https://www.automate.org/vision/news/liquid-lens-optics-adds-autofocus-to-dataman-300-reader). Corning Varioptic example: a 6-mil code readable at 500 mm and 300 mm with refocus, but not with fixed focus; stopping down helps only marginally (vendor note) — [Automate Show](https://www.automateshow.com/exhibitor-news/corning-varioptic-liquid-lens-for-bar-code-reading-applications)
- Optotune ELM-12 (EL-16-40 based) 12 mm liquid-lens module: refocus within ~20 ms, optimized for ~1 m working distance (vendor-affiliated article) — [inVision](https://invision-news.de/?p=41878). Basler sells Optotune liquid lenses controllable through the camera SDK — [Basler liquid lenses](https://www.baslerweb.com/en-us/lenses/liquid-lenses/). Case study: toggling between two preset focus distances to read 2D codes at different heights — [1stVision](https://www.1stvision.com/machine-vision-solutions/?p=1265)
- Barcode patent: varying the focal length within one or more exposures to scan the full extended depth, then building an extended-depth image — [US 9411999](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/9411999). Cognex patent on extending DOF for 2D readers with moving objects using a variable lens and tilted optical path — [US 12356087](https://patents.justia.com/patent/12356087)
- Light-field barcode scanning (computational focal stack from one shot, avoids moving parts) — [U. Delaware LFBarcode](https://www.eecis.udel.edu/~xinqing/publications/LFBarcode/LFBarcode.pdf)
- Scheimpflug: tilting lens vs sensor rotates the focal plane; DOF becomes a wedge; used for slanted objects on conveyors; Basler states tilt does not raise theoretical DOF but keeps a slanted plane in focus — [Wikipedia](https://en.wikipedia.org/wiki/Scheimpflug_principle); [Schneider-Kreuznach](https://schneiderkreuznach.com/en/industrial-optics/knowledge-hub/scheimpflug-principle); [Basler Scheimpflug](https://www.baslerweb.com/en/use-cases/scheimpflug-imaging/)

Computed DOF for longer lenses at 1 m (c = 1 px, 550 nm):
- 6 mm: 0.454 mm/px, 3.4 px/module, FOV width 1.29 m; DOF f/2.8: 825-1270 mm; f/4: 767-1437 mm. 50 mm height error → 0.17 px blur disk at f/4.
- 8 mm: 0.340 mm/px, 4.6 px/module, FOV 0.97 m; DOF f/2.8: 893-1136 mm; f/4: 854-1206 mm; f/5.6: 807-1315 mm. 50 mm error → 0.31 px disk at f/4.
- 12 mm: 0.226 mm/px, 6.9 px/module, FOV 0.64 m; DOF f/4: 929-1082 mm; f/5.6: 904-1119 mm.
- 16 mm: 0.169 mm/px, 9.2 px/module, FOV 0.48 m; DOF f/5.6: 944-1064 mm.

### Inferences
- For a top-down camera over flat glass, Scheimpflug brings nothing (the object plane is already parallel to the sensor); it only matters if the camera is tilted to avoid specular glare from the glass.
- Wavefront coding and focal sweep deliberately make the PSF broader but depth-invariant; at 2.3 px/module with contrast ~50 and noise 2.5, the extra noise amplification in restoration is exactly the regime where current deblurring already fails. They are not a fix for the present problem.
- Even at 8 mm f/4, DOF (~±150 mm) easily covers glass thickness/stacking; at 12-16 mm, ±50-100 mm is still likely enough. A liquid lens with a height sensor (or two preset focus states) is the cheap insurance if a long lens is chosen and sheet stacking can exceed that.

### Gaps
- I could not confirm which current commercial fixed-mount readers (Zebra, Datalogic, Omron/Microscan) ship wavefront-coded or other passive EDOF optics; most current vendor material emphasizes liquid-lens autofocus. Vendor EDOF performance claims are unverified.
- No quantitative SNR penalty figures for focal-sweep/wavefront coding at our contrast/noise levels were extracted.

## Q3. Coded exposure / flutter shutter, strobe lighting, pulsed LEDs synchronized with exposure, polarizers for glass glare

### Takeaway
The highest-value capture-side change is a short, bright, synchronized LED strobe (overdriven pulse) so motion blur drops to ~1 px; coded exposure (flutter shutter, or equivalently a coded strobe pulse train within one exposure) is the fallback that makes residual motion blur invertible. Neither addresses the isotropic lens blur. Cross-polarization can remove glass glare but costs up to ~10x light, which conflicts with short exposures.

### Cited Findings
- Flutter shutter (Raskar, Agrawal, Tumblin, SIGGRAPH 2006): opening/closing the shutter in a pseudo-random binary sequence during the exposure converts the box-filter motion PSF (which has spectral zeros) into a broadband filter so deconvolution is well-posed; prototype used an external ferroelectric/LC shutter; about half the light is lost; PSF (motion extent) must be known/specified — [MERL TR2006-124](https://www.merl.com/publications/docs/TR2006-124.pdf); [MIT project page](https://web.media.mit.edu/~raskar/deblur/)
- Motion-freeze rule of thumb: target <= 1 px blur, achieved by short exposure, short strobe, or both; TI example: 0.01 mm object pixel at 3 m/s needs ~3 us strobe — [TI SSZT704](https://ti.com/lit/pdf/sszt704)
- Gardasoft-type controllers can overdrive LEDs to ~10x their continuous current for short pulses synchronized with the camera; trade press: high-brightness LEDs tolerate ~6-8x overcurrent at ~150 us pulse and 0.15% duty cycle (limits are LED- and duty-cycle-specific) — [Vision Systems Design](https://www.vision-systems.com/cameras-accessories/article/16739383/when-to-invest-in-led-strobe-controllers); [Quality Magazine](https://www.qualitymag.com/articles/89618-strobe-lighting-for-machine-vision)
- Cross-polarization (polarizer on light, analyzer on lens at 90°) suppresses specular reflections from glass/plastic; one vendor test showed ~10x light reduction (exposure 1 ms → 10 ms) on a reflective target; a single lens polarizer may suffice; works better on dielectrics (glass) than metals — [VA Imaging](https://va-imaging.com/en-us/blogs/machine-vision-knowledge-center/polarization-in-your-machine-vision-application); [Edmund Optics, Intro to Polarization](https://www.edmundoptics.com/knowledge-center/application-notes/optics/introduction-to-polarization/); [Vision Systems Design](https://www.vision-systems.com/cameras-accessories/article/16737367/optical-filters-reduce-glare-in-automotive-canister-machine-vision-inspection-application)

Computed for our geometry:
- Exposure for b px of motion blur: t = b x 0.673 mm / v. For b = 1 px: v = 0.5 m/s → 1.35 ms; 1 m/s → 0.67 ms; 2 m/s → 0.34 ms. The current 6-7 px blur implies the exposure is ~6.5x longer than the 1 px target at whatever the belt speed is.
- Light budget: going from 6.5 px to 1 px blur needs ~6.5x more light at the same aperture/gain; adding cross-polarizers (~2.5-10x loss) and stopping from f/2.8 to f/5.6 (4x) multiply on top. A strobe overdriven 5-10x roughly pays for the exposure reduction alone, not for polarizers plus stopping down as well.
- Coded exposure for our case: the motion direction and speed are already estimated by the tracker (vertical, velocity known), which removes the main practical drawback of the flutter shutter (needing the PSF). Implementation without an LC shutter: fire the LED as a pseudo-random pulse train within one camera exposure under dark ambient conditions (same effect as a fluttered shutter); ~50% duty cycle loses ~half the light versus a continuous pulse of the same total window.

### Inferences
- Priority: (1) strobed/overdriven LED synced to the camera trigger, exposure set to <= 1-1.5 px blur; this removes the motion component entirely and leaves the lens blur as the only problem, which is better posed for deconvolution (isotropic sigma 1 px alone at 2.3 px/module is still marginal, see Q4). (2) Coded strobe only if the light budget cannot reach ~1 px blur; it preserves invertibility for longer exposures but does nothing for isotropic blur.
- Glare: since the camera looks straight down onto glass, specular reflection of the lights is geometry-driven; placing lights off-axis (dark-field-ish, outside the specular cone) is cheaper in light than cross-polarization; use polarizers only if off-axis lighting is impossible.
- Ambient light must be much weaker than the strobe for coded or short strobes to work; shrouding may be needed.

### Gaps
- Belt speed, current exposure value and available LED power are unknown, so the light budget cannot be closed numerically.
- Did not verify whether the Basler ace 2 Basic supports multiple exposures within a frame; the coded-strobe approach avoids depending on it but I found no documented implementation for barcode reading.
- No source found applying flutter shutter specifically to industrial code reading.

## Q4. Is the 4 mm lens the bottleneck; what lens/magnification gives >= 3-4 px/module; vendor guidance on px/module

### Takeaway
Yes: 2.3 px/module is below every vendor minimum found for 2D codes on labels (2.5 PPE minimum, 3.5+ preferred), and the 4 mm lens is very likely the source of the sigma ~1 px blur. The most robust fix is more pixels per module: an 8 mm 2/3"-rated lens gives ~4.6 px/module but halves coverage to ~0.97 m (two cameras for ~1.9 m width); a 6 mm lens gives ~3.4 px/module with ~1.29 m coverage. At ~4.6 px/module, sigma ~1 px is a ~0.2-module blur, which standard decoders tolerate without deblurring.

### Cited Findings
- Omron (V460-H manual): 2D code on high-contrast label — 2.5 pixels per element (PPE) minimum, 3.5 PPE or more preferred; direct part marks 3.25 minimum, 4-6 preferred — [Omron V460-H manual (search snippet)](https://www.manualslib.com/manual/3258151/Omron-V460-H.html?page=50)
- Viziotix whitepaper: ~2 px/module recommended for Data Matrix with margin, decoder can work below (vendor claim) — [Viziotix whitepaper](https://www.viziotix.com/wp-content/uploads/2024/11/2024.11.14.How-to-Select-the-Best-Camera-for-Barcode-Scanning-Whitepaper-Viziotix.pdf)
- Cognex VisionPro ID tool: linear-code modules >= 1.6 px wide; postal codes >= 2.5 px; no 2D minimum found in that documentation — [Cognex VisionPro ID Tool](https://docs.cognex.com/vpro_950/web/EN/help/html/b5e68d1a-d0cd-4b1f-be49-e4c3c674b735.htm)
- Forum guidance cites 4-5 px/module for 2D codes (non-authoritative) — [Common Vision Blox forum](https://forum.commonvisionblox.com/t/max-size-of-datamatrix-code/307)
- Basler 4 mm C125-0418-5M-P is designed for 2.2 um pixels at center but only for a 7.3 mm image circle; 2/3" Basler 5 MP lenses begin at 8 mm (C23-0824-5M-P) — [Basler C125-0418-5M-P](https://docs.baslerweb.com/c125-0418-5m-p); [Basler C23-0824-5M-P](https://docs.baslerweb.com/c23-0824-5m-p)

Computed options (u = 1000 mm, module 1.55 mm, sensor 2840 px wide):
| Lens | mm/px | px/module | FOV width (full sensor) | Cameras for 1.9 m | DOF f/4 (c = 1 px) |
|---|---|---|---|---|---|
| 4 mm (current) | 0.68 | 2.3 | 1.94 m | 1 | 0.59-3.2 m |
| 6 mm | 0.45 | 3.4 | 1.29 m | 2 | 0.77-1.44 m |
| 8 mm | 0.34 | 4.6 | 0.97 m | 2 | 0.85-1.21 m |
| 12 mm | 0.23 | 6.9 | 0.64 m | 3 | 0.93-1.08 m |
- Alternatively keep the 4 mm field geometry but raise the camera? No: px/module depends on f/u, so lowering the camera to ~0.6 m with the 4 mm lens gives the same scale as 6.7 mm at 1 m but shrinks coverage identically and worsens off-axis angles.
- Line-scan alternative: px/module across the belt = sensor pixels / belt width; e.g., an 8k line-scan over 1.9 m gives ~0.23 mm/px (~6.7 px/module) across, with along-belt sampling set by line rate (needs encoder sync and strong line illumination). Cost and integration effort are much higher than a second area camera (no prices sourced).

### Inferences
- With blur sigma expressed in modules, 1 px at 2.3 px/module = 0.43 module (code essentially unreadable at contrast 50/noise 2.5), at 3.4 px/module = 0.29 module, at 4.6 px/module = 0.22 module. Moving to 6-8 mm attacks the problem at the root and also lowers motion blur in modules for the same exposure (motion blur in px rises proportionally, though, so the strobe/exposure must be shortened by the same factor: at 8 mm, 1 px = 0.34 mm, so t = 0.34 mm / v).
- A 2/3"-rated 6 or 8 mm lens (image circle >= 11 mm) at f/2.8-f/4 is the most likely single change to remove the isotropic sigma ~1 px; then verify with an edge-spread measurement.
- Two 8 mm cameras over the belt width (overlapping ~5-10%) with a shared strobe is the "best evidence" configuration: ~4.6 px/module meets the preferred Omron figure, DOF ±~150 mm at f/4, and the existing dual-camera app (`main_dual.py`) already handles two channels.
- If only one camera is allowed: 6 mm 2/3"-rated lens covers ~1.29 m at ~3.4 px/module (meets "preferred" ~3.5 roughly); whether 1.29 m suffices depends on where labels can lie on the glass.

### Gaps
- Belt width and label placement range are not stated, so the number of cameras is conditional.
- No Cognex or Keyence published 2D px/module minimum under motion was found; the Omron figure is the most authoritative vendor number located. No vendor gave a specific joint limit for motion blur + module size.
- No prices for 2/3" 6/8 mm lenses, additional ace 2 cameras, strobe controllers, or line-scan systems were sourced.
