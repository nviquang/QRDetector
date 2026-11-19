# Chiếu sáng buồng tối và cài đặt thu ảnh cho tem QR 32 mm trên kính tấm (2 × Basler a2A2840-48umBAS, ống kính 4 mm)

Phạm vi: thiết kế đèn trong buồng tối dài 60 cm và cấu hình camera. Phần cứng cố định (camera, ống kính 4 mm, tem 32 mm version 2 mức M, băng 3,25 m, 80–120 mm/s, Jetson Nano hoặc PC chỉ CPU) không được bàn lại.

Quy ước: "(tính)" là con số tôi tự tính từ công thức quang học chuẩn và thông số có nguồn. Nó không phải số đo, phải kiểm lại trên camera thật. Mọi dữ kiện khác đều có nguồn.

Hình học dùng xuyên suốt (tính): cảm biến rộng 2856 × 2,74 µm = 7,83 mm. Để phủ W = 1,55 m với f = 4 mm thì cần khoảng cách H ≈ 4 × 1550 / 7,83 ≈ 0,79 m, tức 0,543 mm/px và 2,36 px/ô (ô 1,28 mm). Nửa góc nhìn ngang là atan(775/792) ≈ 44°. Dải ROI 1072 dòng × 0,543 mm ≈ 582 mm dọc băng (±291 mm, nửa góc ≈ 20°). Góc dải ROI có bán kính ảnh √(3,91² + 1,47²) ≈ 4,18 mm, tức ≈ 46° so với trục.

---

## 1. Exposure, lượng ánh sáng cần, nhiễu/gain, strobe so với đèn liên tục, đồng bộ hai camera

### Takeaway
Cảm biến là Sony IMX546 (2/3", global shutter, QE ≈ 66 %, nhiễu tối 2,4 e⁻, giếng 9,8 ke⁻). Ở exposure 2,5 ms, f/2,8, không gain, cần khoảng 4–8 klux trên tem ở tâm ảnh (tính) để trắng đạt ~200/255. Mép ảnh cần 2–4 lần mức đó do suy giảm cos⁴ của ống kính góc rộng. Đây là mức sáng gấp 10–30 lần đèn văn phòng nhưng làm được bằng LED. Strobe overdrive cho tới ~5 lần cường độ (số của nhà bán) ở duty ≤10 %, đủ để hạ exposure xuống 1 ms. Hai camera dùng chung một xung trigger cho đèn.

### Cited Findings
- a2A2840-48umBAS dùng Sony IMX546-AAMJ-C, CMOS global shutter, định dạng 2/3" (đường chéo hiệu dụng 11,1 mm), pixel 2,74 µm, 2856 × 2848, ngàm C, USB 3.0 5 Gbit/s. Tốc độ 44,6 fps ở cài đặt mặc định, 48,4 fps khi tắt Device Link Throughput Limit. Có 1 ngõ vào opto, 2 GPIO (tải tối đa 50 mA), trigger cứng/mềm/free-run. Tính năng ghi trên trang: Line Noise Reduction, Data Chunks, Timestamp, Sequencer, Image ROI, Multiple ROI, Binning, Timer, PGI Feature Set — [Basler docs a2A2840-48umBAS](https://docs.baslerweb.com/a2a2840-48umbas). Lưu ý: đề bài ghi "1/1.2"", nhưng Basler ghi 2/3".
- Theo trang shop Basler (tiếng Nhật), EMVA 1288: QE 65,9 % (điển hình) ở ~541 nm, nhiễu tối 2,4 e⁻, giếng bão hòa 9,8 ke⁻ — [Basler shop JP](https://www.baslerweb.com/ja-jp/shop/a2a2840-48umbas/). Một đại lý ghi 65,3 % / 2,5 e⁻ / 9,8 ke⁻ — [Machine Vision Store](https://machinevisionstore.com/catalog/details/22067). Tài liệu tổng quan EMVA của Basler nói các phép đo làm ở 545 nm — [Basler EMVA Data Overview](https://cdn.graftek.com/system/files/13429/original/Basler_EMVA_Data_Overview.pdf).
- Phương pháp tính ngân sách ánh sáng: lấy quang thông tới mỗi pixel (phụ thuộc f-number, kích thước pixel, độ phản xạ vật), đổi ra photon/s, nhân QE và thời gian phơi sáng. Lux là đại lượng theo mắt người, nên dùng irradiance (W/m²) cho cảm biến. SNR shot-noise = √Ne — [Bodkin Design](https://www.bodkindesign.com/?p=12886); [Vision Systems Design: photons per lumen](https://vision-systems.com/cameras-accessories/article/55330759/how-many-photons-are-there-in-a-lumen); [CCS radiant vs luminous quantities](https://www.ccs-grp.com/guide/theory-light-color/06_radiant-quantities-luminous-quantities-3.html).
- Công thức vệt mờ: vệt (px) = tốc độ × exposure × (số px / FOV) — [Quality Magazine](https://www.qualitymag.com/articles/98039-machine-vision-technologies-adapt-for-higher-speeds-evolving-needs).
- Đèn overdrive Smart Vision Lights (LSR, LM75, ODL300) có hai chế độ, liên tục hoặc OverDrive strobe. Duty tối đa 10 % (giới hạn nhiệt). Strobe dài tối đa 50 ms (LSR, LM75) tới 125 ms (ODL300). Tần số tối đa 4 kHz hoặc 1/duty. Chỉnh cường độ bằng tín hiệu 0–10 V hoặc 1–10 V. ODL300 nói "sáng gấp tới 5 lần" đèn linear thường, nhưng không định nghĩa mốc so sánh (**marketing**) — [ODL300 datasheet](https://downloads.machinevisiondirect.com/wp-content/uploads/SVL/ODL300/ODL300_Datasheet.pdf); [LSR datasheet](https://cdn.shopify.com/s/files/1/0264/1297/4177/files/LSR_Datasheet.R.4.040422.pdf); [LM75](https://cdn.shopify.com/s/files/1/0264/1297/4177/files/LM75_Datasheet.pdf); [Machine Vision Direct: SVL OverDrive](https://machinevisiondirect.com/blogs/news/svl-overdrive). Công thức duty = thời gian strobe / (strobe + nghỉ) — [LM45 datasheet](https://cdn.shopify.com/s/files/1/0603/8129/8903/files/LM45_Datasheet.pdf).
- Đồng bộ đèn với ace 2: Basler hướng dẫn dùng hai timer. Line 1 (trigger cứng) khởi động Timer 1 (delay ≥ thời gian LED lên sáng, duration < exposure) và Timer 2 (delay 0, duration = delay Timer 1 + exposure). Frame Start lấy nguồn Timer 1 Active. Line 2 đặt Output với Line Source = Timer 2 Active để bật đèn. Mục đích là tránh ảnh tối khi exposure ngắn (<100 µs) vì LED cần thời gian lên sáng. Bài không nêu thông số điện của GPIO và cách nối bộ điều khiển strobe — [Basler: sync light source ace 2/boost R](https://docs.baslerweb.com/knowledge/how-to-synchronize-a-light-source-with-a-basler-ace2-or-boost-r-camera). Với camera global shutter, Flash Window không có hoặc tương đương Exposure Active. Chọn tín hiệu bằng LineSelector + LineSource — [Basler Line Source](https://docs.baslerweb.com/line-source).

### Inferences
- **Exposure (tính):** vệt mờ ≤0,25 ô = 0,32 mm, nên ở 120 mm/s exposure ≤ 2,67 ms. 2,5 ms cho 0,30 mm = 0,55 px = 0,23 ô; 1,0 ms cho 0,22 px. Vệt 10–20 px trong các bản ghi AE trước đây tương ứng 5,4–10,9 mm di chuyển, tức exposure khoảng 45–90 ms ở 120 mm/s. AE hoàn toàn không dùng được.
- **Ngân sách sáng ở tâm ảnh (tính):** chọn trắng ≈ 200/255 ở Mono8, gain 0 dB. Giả sử thang 8 bit ≈ giếng 9,8 ke⁻ (cần kiểm trên camera vì Basler có thể ánh xạ khác), cần khoảng 7.700 e⁻, tức ≈ 12.800 photon ở QE 0,6. Irradiance ảnh E_ảnh = E_vật × ρ × T / (4N²), suy giảm thêm cos⁴θ ngoài trục. Ở 555 nm, 1 lm·s ≈ 4,1·10¹⁵ photon; pixel 7,5·10⁻¹² m². Từ đó cần E_ảnh × t ≈ 0,42 lux·s, tức ~170 lux trên cảm biến ở 2,5 ms. Với ρ = 0,8 (giấy trắng), T = 0,9, N = 2,8: E_vật ≈ 7 klux. Đèn LED trắng cho khoảng gấp đôi số photon mỗi lumen so với 555 nm đơn sắc, nhưng QE ở hai đầu phổ thấp hơn, nên ước 4–8 klux. Ở f/4 gấp đôi (8–15 klux). Ở exposure 1 ms gấp 2,5 lần nữa.
- **Mép ảnh (tính):** cos⁴(44°) ≈ 0,27 và cos⁴(46°) ≈ 0,23 ở góc dải ROI. Ống kính thật thường đỡ hơn cos⁴ lý thuyết nhưng vẫn nên giả định chỉ còn 30–50 % ở mép. Như vậy hoặc tăng chiếu sáng ở hai mép (bố trí LED dày hơn hoặc nghiêng về mép), hoặc chấp nhận gain/khuếch đại số theo bản đồ flat-field (SNR mép thấp hơn).
- **Nhiễu và gain (tính):** ở 7.700 e⁻, SNR shot-noise ≈ 88 (39 dB). Nếu ánh sáng chỉ đủ 1/4 và bù bằng +12 dB gain thì 1.925 e⁻ cho SNR ≈ 44. Nhiễu đọc 2,4 e⁻ không đáng kể. Với QR 2,2–2,4 px/ô, giới hạn chính là MTF/vệt mờ và độ tương phản chứ không phải nhiễu. Vì vậy gain +6 đến +12 dB chấp nhận được nếu thiếu sáng, nhưng **luôn ưu tiên exposure ngắn hơn gain thấp hơn**.
- **Strobe hay liên tục:** ở 15 fps với 2,5 ms, duty = 3,75 % (≤10 %), nên chạy overdrive được. Ở 1 ms và 40 fps vẫn ≤10 %. Đèn liên tục đơn giản hơn (không cần dây trigger, hai camera không cần đồng bộ) nhưng tốn nhiệt và chỉ cho 1× cường độ. Nếu đèn liên tục thì phải điều khiển bằng dòng DC, không dùng PWM tần số thấp: PWM vài trăm Hz với exposure 2,5 ms làm độ sáng dao động giữa các frame (suy luận, chưa có nguồn).
- **Hai camera chung một đèn strobe:** đưa một xung từ bộ phát (hoặc từ GPIO camera A qua Timer) vào Line 1 (opto) của cả hai camera, và vào ngõ trigger của bộ điều khiển strobe. GPIO chỉ 50 mA nên không cấp nguồn LED trực tiếp. Theo hướng dẫn Basler, nếu dùng trigger ngoài thì đặt delay exposure bằng Timer để LED kịp lên sáng. Như vậy hai camera chụp cùng lúc, cùng một xung sáng, và không camera nào phơi sáng lúc đèn tắt.

### Gaps
- Không tìm được đường cong QE số của IMX546 theo bước sóng, nên chưa chọn được giữa LED trắng, xanh lá hay đỏ theo số liệu. Không có dải gain/exposure chính thức của bản BAS trên trang đã đọc.
- Không có số cd/m² hoặc lux thực của các tấm LED/đèn bar cụ thể ở khoảng cách 0,8 m. Cần đo bằng lux kế, hoặc chụp thử thẻ trắng ở 2,5 ms.
- Ánh xạ e⁻ → DN của Mono8 ở gain 0 trên a2A2840 chưa xác minh. Đo bằng cách chụp thẻ trắng, tăng exposure tới bão hòa.

---

## 2. Chiếu sáng riêng cho kính: phản xạ gương, đèn khuếch tán/dome, góc thấp, phân cực chéo, nền dưới kính, đồng đều trên 1,6 m

### Takeaway
Kính phản xạ ~4 % mỗi mặt (~8 % cả tấm), như một gương yếu. Với ống kính 4 mm nhìn ±44° và dải ROI dài gần bằng buồng 60 cm, gần như mọi điểm trên trần và vách buồng đều hiện ra trong ảnh qua phản xạ. Vì vậy không thể "đặt đèn ngoài nón phản xạ" ở phía trên. Có hai chiến lược khả thi:
- (A) trần đen nhám, đèn góc thấp ở hai đầu buồng, dải ROI ngắn hơn buồng một chút: kính hiện đen, tem trắng sáng (dark-field-like);
- (B) cả trần là một mặt phát sáng khuếch tán đồng đều ("cloudy day"): phản xạ thành lớp màng đều 4–8 %, không có đốm chói.

Phân cực chéo về nguyên lý cắt được phản xạ kính, nhưng mất ~6–8 lần ánh sáng (tính). Nó cũng làm lộ vân ứng suất của kính cường lực, và hiệu quả kém đều trên trường nhìn ±44°. Chỉ nên là phương án thử.

### Cited Findings
- Kính soda-lime float điển hình phản xạ 4 % ở mỗi mặt, chiết suất ≈ 1,52 — [NGA FM05-12 (2023)](https://www.glass.org/sites/default/files/2023-07/FM05-12_2023_Physical_Mechanical_Properties_Typical_Soda_Lime_Float_Glass.pdf). Tổng phản xạ một tấm là 2R/(1+R) ≈ 7,8 % ở góc vuông góc — [glassproperties.com](https://glassproperties.com/reflection). Phản xạ bề mặt tăng khi góc tới tăng — [NRC CBD-60](https://web.mit.edu/parmstr/Public/NRCan/CanBldgDigests/cbd060_e.html).
- Dome cho chiếu sáng gần như không phản xạ trên vật bóng, nhưng dome và tunnel có lỗ cho camera nhìn qua, tạo đốm tối ở giữa vật phản xạ mạnh. Dome và đèn đồng trục thường cần khoảng làm việc nhỏ. Đèn đồng trục hay dùng cho kính phẳng (ví dụ Keyence kiểm mép kính) — [vision-doctor: diffuse incident light](https://www.vision-doctor.com/en/illumination-techniques/diffuse-incident-light.html); [Keyence lighting basics](https://www.keyence.com/products/vision/vision-sys/resources/vision-sys-resources/basics-of-lighting-selection.jsp).
- Flat dome là tấm phẳng có lỗ camera ở giữa, nên rộng gấp khoảng 2 lần FOV. Bề mặt càng cong và bóng thì đèn càng phải to. CCS bán cỡ tới 300 × 300 mm, Wenglor LFD tới 400 × 400 mm — [Vision Systems Design: flat dome](https://www.vision-systems.com/lighting-optics/article/14182971/flat-dome-lights-tame-reflections-and-shadows-in-machine-vision); [Wenglor flat dome](https://www.wenglor.com/en/en/Illumination-Technology/Flat-Dome-Lights/c/cxmCID211483). Dome dạng tunnel có cửa vào/ra để vật đi qua trên băng (LDDLIGHT IQD) — [ThomasNet](https://news.thomasnet.com/fullstory/dome-lights-suit-conveyor-based-machine-vision-systems-568299).
- Phân cực chéo: một polarizer trên đèn, một trên ống kính xoay 90°, chặn phản xạ gương. Polarizer lý tưởng giảm ánh sáng không phân cực còn một nửa. Ánh sáng đã phân cực theo định luật Malus I₀cos²θ — [Edmund Optics: Introduction to polarization](https://www.edmundoptics.com/knowledge-center/application-notes/optics/introduction-to-polarization/). Phân cực chéo làm giảm tổng cường độ, phải tăng exposure hoặc tăng đèn. Với phản xạ góc thấp, một polarizer trên đèn không đủ vì đó là vấn đề hình học — [VA Imaging](https://va-imaging.com/en-us/blogs/machine-vision-knowledge-center/polarization-in-your-machine-vision-application). Ghi chú cũ có thêm: dời đèn lệch trục nên thử trước khi thêm polarizer — [1stVision](https://www.1stvision.com/machine-vision-solutions/?p=5197).
- Kính cường lực có vân ngũ sắc (iridescence/anisotropy) khi nhìn dưới ánh sáng phân cực, do ứng suất không đều sinh ra lúc tôi. Đây là đặc tính vốn có, không phải lỗi. Máy quét anisotropy của Viprotron dùng chính hiện tượng này (LED đỏ, kính lọc phân cực tròn) — [SAFTI: anisotropy scanners](https://safti.com/articles/mitigating-the-menace-anisotropy-scanners-aid-fabricators-to-improve-aesthetics/); [glassonweb: anisotropy measurement](https://www.glassonweb.com/article/anisotropy-measurement-architectural-glass). Nguồn là bài báo ngành và tài liệu của chính nhà bán.
- Patent Saint-Gobain đọc mã trên tấm kính đang chạy: camera line-scan + chiếu sáng **dark-field**, đèn có thể đặt giữa các con lăn (cách nhau <400 mm), chụp nhiều lần các phần khác nhau của mã, kích chụp theo chuyển động đo được — [US9767334B2](https://patents.google.com/patent/US9767334B2/en). Mã trong patent là mã khắc, khác tem giấy.

### Inferences
- **Hình học phản xạ (tính):** camera ở cao H nhìn điểm P trên mặt kính cách trục x thì nhìn thấy qua phản xạ một vật ở độ cao h, cách trục x(1 + h/H). Ở h = H (trần ngang camera), vùng trần lộ qua phản xạ là ±1,55 m ngang × ±0,58 m dọc. Ở sát mặt kính (h nhỏ), dọc băng vẫn là ±291(1 + h/H) mm, mà buồng chỉ dài ±300 mm. Kết luận: **mọi nguồn sáng ở phía trên, trong buồng 60 cm, đều lộ thành đốm chói ở đâu đó trong dải 1072 dòng**. Để giấu đèn phải làm một trong hai việc: (i) rút dải ROI ngắn lại, ví dụ 800–900 dòng ≈ 435–490 mm, để đèn bar nằm ở hai đầu buồng, thấp (h ≈ 5–10 cm) và ngoài vùng ±(ROI/2)(1 + h/H); hoặc (ii) đặt đèn ngay ngoài miệng buồng, có rèm che.
- **Chiến lược A, dark-field góc thấp + trần đen (khuyến nghị thử trước):** trần và vách sơn đen nhám. Hai đèn bar chạy hết 3,25 m, đặt thấp ở hai đầu buồng, chiếu xiên dọc băng. Kính chỉ phản chiếu trần đen nên tối; tem giấy khuếch tán ánh sáng xiên nên sáng. Viền trắng/quiet zone của tem trên nền đen giúp detector. Phản xạ gương của lớp phủ bóng trên tem (nếu có) đi ra xa camera. Nhược điểm (tính): độ rọi dọc băng không đều. Với đèn ở y = ±0,3 m, h = 0,1 m, điểm gần đèn sáng gấp khoảng 4–5 lần điểm giữa. Bù bằng cách hướng chùm hẹp sang phía xa, hoặc dựa vào việc tem đi qua cả dải nên chắc chắn có frame ở vùng sáng vừa (thời gian tem ở trong dải 4,6–6,9 s). Phải chọn exposure để vùng sáng nhất không cháy. Theo chiều ngang, bar dài đều cả 3,25 m nên đồng đều tốt hơn.
- **Chiến lược B, trần phát sáng khuếch tán "cloudy day":** toàn bộ trần 3,25 × 0,6 m là LED sau tấm khuếch tán, có hai lỗ camera, vách trắng hoặc cũng phát sáng. Phản xạ của kính là màng đều khoảng 4–8 % độ chói trần, không có đốm. Tương phản tem (tính): trắng ρ ≈ 0,8, đen ≈ 0,05, cộng màng bóng ~0,05, cho tương phản Michelson ~0,79 thay vì 0,88. Chấp nhận được. Lỗ camera tạo một đốm tối nhỏ ngay dưới camera. Hệ số góc nhìn (form factor) của trần 1,6 × 0,6 m nhìn từ điểm dưới tâm ở 0,8 m ≈ 0,3 (tính), nên E ≈ π·L·0,3. Để đạt 6 klux cần độ chói trần ≈ 6.000 cd/m², ở mức cao cho tấm LED liên tục, nên có thể phải dùng strobe. Ở hai mép băng, trần chỉ vươn thêm vài cm nên độ rọi tụt còn khoảng một nửa, cộng với cos⁴ của ống kính. Phải nối vách phát sáng xuống gần mặt kính và tăng mật độ LED ở mép.
- **Phân cực chéo với kính:** phản xạ gần vuông góc giữ phân cực nên bị chặn tốt. Nhưng (a) phim polarizer thường truyền ~40 % ánh sáng không phân cực (chưa có nguồn số cụ thể), nên hai lần cộng với tem làm khử phân cực chỉ còn khoảng 1/6–1/8 ánh sáng. Ngân sách 4–8 klux thành 25–60 klux (tính). (b) Với mặt phẳng nhìn ±44–54°, mặt phẳng tới thay đổi theo phương vị nên độ dập kém đều ở các góc ảnh. Góc ảnh 54° gần góc Brewster của kính (≈56,7° với n = 1,52, tính), nơi phản xạ chủ yếu là phân cực s. (c) Phản xạ từ mặt dưới đi qua kính cường lực hai lần, bị lưỡng chiết làm đổi phân cực, nên lọt qua analyzer thành vân (theo nguồn về iridescence). Lớp phủ PET trên tem cũng có thể lưỡng chiết. Vì vậy chỉ thử nếu A và B thất bại.
- **Nền dưới kính:** tem dán mặt trên và đục nên bản thân mã không bị ảnh hưởng. Qua kính trong suốt sẽ thấy con lăn hoặc băng; với chiến lược A, ánh sáng xiên xuyên kính chiếu sáng con lăn thành các vạch sáng ở nền. Nên kiểm tra detector có báo nhầm không. Không đổi được con lăn, nhưng có thể sơn đen nhám các chi tiết cố định trong buồng (khung, máng).
- Độ dày kính (3–19 mm) làm khoảng cách đổi ≤2,4 % (≤19/790 mm, tính), nên px/ô và nét gần như không đổi.

### Gaps
- Không tìm được đèn thương mại dạng flat dome hay tunnel rộng 3,25 m. Cỡ lớn nhất tìm thấy là 400 × 400 mm (Wenglor), nên buồng phải tự chế: LED dải hoặc bar + tấm khuếch tán, hoặc ghép nhiều đèn linear.
- Không có số truyền qua thực của phim polarizer LED, và không có tài liệu đo hiệu quả phân cực chéo trên kính ở trường nhìn rộng.
- Chưa biết tem có lớp phủ bóng hay mờ, chưa biết loại kính (cường lực hay float, phủ low-E). Low-E có thể phản xạ mạnh hơn 4 %; chưa có nguồn.

---

## 3. Ống kính 4 mm trên cảm biến 2/3": méo, tối góc, px/ô ở mép, MTF, khẩu độ, lấy nét, hiệu chuẩn

### Takeaway
Với ống kính rectilinear, mặt phẳng song song cảm biến được ảnh với tỉ lệ mm/px **đồng đều**. Px/ô ở mép chỉ giảm do méo thùng: méo −3 % ở mép làm độ phóng đại cục bộ theo bán kính giảm khoảng 9 % (tính), từ 2,36 xuống ~2,15 px/ô. Dải ROI chỉ cần vòng ảnh ≥8,4 mm. Khẩu độ nên chọn f/2,8 (thử f/4): độ sâu trường ảnh ~0,6 m đã thừa, nhiễu xạ ở f/5,6 trở lên làm giảm MTF ở tần số ô. Không cần undistort toàn ảnh để giải mã.

### Cited Findings
- Không tìm được datasheet ống kính 4 mm, 2/3", ≥5–8 MP từ Computar, Kowa, Fujinon, Basler trong lần tìm này. Tham khảo cùng họ ống 2/3" tiêu cự 8 mm: méo từ 0,01 % (Computar M0828-MPX) tới −6,2 % (Kowa LM8JC); Basler C23-0824-5M-P méo 1,87 % thiết kế cho pixel 3,4 µm, 147 lp/mm; Basler C23-0816-2M −4,8 % (thùng) — [Computar M0828-MPX](https://1stvision.com/lens/computar/dataman/M0828-MPX_en.pdf); [Kowa LM8JC](https://www.kowa-lenses.com/LM8JC-2-3-8mm-MP-C-Mount-Lens/10222); [Basler C23-0824-5M-P](https://docs.baslerweb.com/c23-0824-5m-p). Keyence CA-LHR8 (8,5 mm, 2/3") méo TV 0,31 %, 200 lp/mm ở tâm và 140 lp/mm ở rìa — [Keyence CA-LHR8](https://www.keyence.com/products/vision/vision-sys/ca-l/models/ca-lhr8/). Tamron M23FM08 thiết kế cho pixel 2,5 µm "tới 90 % chiều cao ảnh" — [cctvvideo](https://cctvvideo.com/tamron-m23fm08-2-3-machine-vision-fixed-focal-lens-8mm).
- Đường chéo hiệu dụng cảm biến 11,1 mm (2/3") — [Basler docs](https://docs.baslerweb.com/a2a2840-48umbas).
- Tăng f-number thì tăng độ sâu trường ảnh nhưng cần nhiều sáng hơn — [Bodkin Design](https://www.bodkindesign.com/?p=12886).

### Inferences
- **Vòng ảnh (tính):** toàn cảm biến cần ≥11,1 mm, nhưng dải 2856 × 1072 chỉ cần ≥8,4 mm. Một ống 4 mm cho 1/1,8" (vòng ~8,9 mm) có thể đủ cho dải nếu đặt dải ở giữa cảm biến. Phải đặt ROI offset Y căn giữa (≈ dòng 888–1960).
- **Px/ô ở mép (tính):** ống rectilinear lý tưởng ánh xạ x = f·X/Z, nên mặt kính nằm ngang (song song cảm biến) có mm/px như nhau ở mọi điểm và tem ở mép không bị co ngắn phối cảnh. Đây là lý do **không nên nghiêng camera**. Méo thùng dạng D(r) = k·r² làm độ phóng đại theo bán kính dr'/dr = 1 + 3k·r², gấp khoảng 3 lần méo danh nghĩa. Méo −3 % ở mép thì px/ô theo bán kính còn ≈ 2,36 × 0,91 ≈ 2,15; theo phương tiếp tuyến chỉ giảm 3 %, tức ô thành hình chữ nhật nhẹ. Méo −5 % thì ≈ 2,0 px/ô theo bán kính. Đây là lý do nên chọn ống méo thấp và đo méo thực.
- **Tối góc:** ngoài cos⁴ (xem mục 1), ống 4 mm thường có tối góc cơ học nếu vòng ảnh vừa sát. Đóng khẩu một nấc giảm tối góc cơ học nhưng không giảm cos⁴.
- **MTF và khẩu độ (tính, nhiễu xạ ở 550 nm):** Nyquist pixel 2,74 µm là 182 lp/mm. Tần số cơ bản của ô xen kẽ ở 2,36 px/ô là 1 chu kỳ/4,7 px ≈ 77 lp/mm (0,42 Nyquist). MTF nhiễu xạ tại 77 lp/mm: f/2,8 ≈ 0,85; f/4 ≈ 0,79; f/5,6 ≈ 0,70; f/8 ≈ 0,58. Tại Nyquist: 0,65 / 0,51 / 0,33 / 0,10. Vết Airy: f/2,8 ≈ 3,8 µm (1,4 px), f/4 ≈ 5,4 µm (2 px). Ống góc rộng mở hết cỡ thường kém ở mép do quang sai, nên điểm ngọt dự kiến là f/2,8–f/4. Thử cả hai bằng bảng Siemens star ở tâm và mép rồi chọn.
- **Độ sâu trường ảnh (tính):** m ≈ 4/786 ≈ 0,0051, vòng nhòe 1 px (2,74 µm), DOF ≈ 2Nc/m² ≈ 217·N mm. f/2,8 ≈ 0,6 m, f/4 ≈ 0,87 m. Độ dày kính và độ võng băng không đáng kể. Có thể mở lớn để tiết kiệm sáng mà không lo mất nét.
- **Lấy nét:** đặt bảng nét (Siemens star hoặc QR in 1,28 mm/ô) trên một tấm kính dày trung bình ở độ cao mặt trên kính, lấy nét ở tâm, kiểm mép, rồi khóa vít vòng nét và vòng khẩu (rung băng chuyền làm xê dịch).
- **Hiệu chuẩn và undistort:** pipeline hiện warp từng QR theo homography (`qr/corrector.py`). Trong 54 px của một tem, méo gần như affine, nên **không cần remap toàn ảnh để giải mã**. Chỉ cần hiệu chuẩn (bảng ô cờ, OpenCV) nếu muốn quy đổi tọa độ sang mm trên băng hoặc ghép vùng chồng hai camera. Khi đó chỉ undistort các điểm góc, rẻ hơn remap 3 MP mỗi frame trên Jetson Nano. Chưa có số đo thời gian remap trên Nano.

### Gaps
- Chưa có datasheet ống 4 mm thực tế dự án đang dùng (vòng ảnh, méo, MTF, tối góc). Đây là thông số quyết định px/ô ở mép và lượng sáng cần ở mép. Cần lấy datasheet hoặc đo bằng ảnh bảng ô cờ.

---

## 4. Cài đặt camera: ROI, Mono8/10/12, USB3 cho hai camera trên Jetson Nano/PC, fps, trigger, timestamp, PGI

### Takeaway
Dùng Mono8, dải ROI 2856 × ~1072 căn giữa (hoặc ngắn hơn nếu cần giấu đèn), không binning. Tắt AE/AG, exposure cố định 1–2,5 ms, gain cố định thấp. Chọn 8–15 fps theo khả năng xử lý: tem nằm trong dải 4,6–6,9 s nên 5 fps đã có hơn 20 frame. Băng thông hai camera chỉ ~90 MB/s ở 15 fps, rất xa giới hạn USB3 kể cả qua một root port của Jetson Nano. Bản BAS gần như chắc chắn không có PGI; nếu thấy có thì để trung tính.

### Cited Findings
- Có Image ROI, Multiple ROI, Binning, Data Chunks, Timestamp, Sequencer, Timer. 44,6 fps mặc định, 48,4 fps khi tắt Device Link Throughput Limit ở toàn khung — [Basler docs a2A2840-48umBAS](https://docs.baslerweb.com/a2a2840-48umbas).
- PGI (sharpness, denoise) **không hỗ trợ** trên các bản ace 2 Basic mono theo bảng của Basler (ví dụ a2A1920-51gmBAS, a2A2448-23gmBAS: "PGI Feature Set not supported"). Chỉ bản PRO có Noise Reduction và Improved Sharpness — [Basler PGI feature set](https://docs.baslerweb.com/pgi-feature-set). **Mâu thuẫn:** trang sản phẩm a2A2840-48umBAS lại liệt kê "PGI Feature Set" — [Basler docs a2A2840-48umBAS](https://docs.baslerweb.com/a2a2840-48umbas). Phần bảng tôi đọc được bị cắt, chưa thấy dòng của a2A2840-48umBAS. Trên camera mono có PGI, mặc định là trung tính (ảnh gốc giữ nguyên từng bit) — [Basler PGI](https://www.baslerweb.com/en/learning/pgi).
- Jetson: các camera cắm chung một root hub USB3 chia nhau băng thông. Jetson Nano 4GB có người không mở được quá 2 camera USB3 cùng lúc, NVIDIA cho là giới hạn phần cứng. Hub phải là USB3 — [NVIDIA forum: insufficient bandwidth multiple USB cameras](https://forums.developer.nvidia.com/t/insufficient-bandwidth-when-using-multiple-usb-cameras/232422); [NVIDIA forum: four USB3 cameras on Nano](https://forums.developer.nvidia.com/t/can-i-use-four-usb-3-0-cameras-on-nvidia-jetson-nano-board-without-loosing-speed-of-video-streaming/185709). Device Link Throughput Limit để chia băng thông giữa các camera — [FLIR app note](https://flir.com/support-center/iis/machine-vision/application-note/usb-3.1-multiple-camera-setup). Basler có tài liệu đo băng thông tối đa của các host controller USB3 (chưa đọc được số) — [Basler AW00126010000](https://assets-ctf.baslerweb.com/dg51pdwahxgw/4N0SupZ9UpIdxerGU2bXoL/3feef7a06f126ab852eaf3f69997aedf/AW00126010000_USB3.0_Host_Controllers_Max_Bandwidth.pdf).

### Inferences
- **Mono8 hay Mono10/12 (tính):** ở ~7.700 e⁻ cho 200 DN thì 1 DN ≈ 38 e⁻. Nhiễu shot σ ≈ 88 e⁻ ≈ 2,3 DN, lớn hơn nhiều so với nhiễu lượng tử hóa 8 bit (0,29 DN). Ở gain +12 dB tỉ lệ này không đổi. Mono10/12 không cải thiện độ chính xác dưới pixel đáng kể, nhưng tăng gấp 1,5–2 lần băng thông và bộ nhớ, và pipeline OpenCV/zxing/WeChat đều dùng 8 bit. **Chọn Mono8.** Ngoại lệ: nếu bị thiếu sáng nặng (trắng chỉ ~40 DN) thì nên tăng gain analog chứ không phải đổi sang 12 bit.
- **Băng thông (tính):** 2856 × 1072 × 1 B = 3,06 MB/frame. 15 fps là 46 MB/s mỗi camera, hai camera 92 MB/s. 30 fps là 184 MB/s tổng. Đều dưới mức thực tế ~350–400 MB/s của một kênh USB3 5 Gbit/s (con số thực tế này chưa có nguồn đã kiểm). Jetson Nano bản gốc dồn các cổng USB3 qua một hub vào một root port nên vẫn đủ. Đặt Device Link Throughput Limit mỗi camera ≈ 40–45 % để chúng không tranh nhau.
- **fps (tính):** dải 582 mm, tem 32 mm (cộng quiet zone) thì tem nằm trọn trong dải trong (582 − 42)/120 ≈ 4,5 s ở 120 mm/s và ≈ 6,8 s ở 80 mm/s. Ở 10 fps tem di chuyển 12 mm ≈ 22 px mỗi frame, có ~45–68 frame mỗi lượt. Giới hạn thật là thời gian xử lý trên Jetson Nano/CPU, không phải camera. Đặt fps cố định (AcquisitionFrameRate) bằng nhịp mà pipeline tiêu thụ được, để không tốn băng thông và nhiệt.
- **Trigger:** nếu dùng strobe thì trigger cứng một xung chung vào Line 1 hai camera (mục 1). Nếu đèn liên tục thì free-run với fps cố định là đủ. Photo-eye/encoder chưa được xác nhận và không bắt buộc: nhiều frame mỗi lượt cùng PassTracker đã thay vai trò kích chụp theo vị trí.
- **Timestamp và chunk:** bật Data Chunks (Timestamp, Frame/Trigger counter nếu có) để đo vận tốc lượt chính xác. Vận tốc hiện tính theo seq/s đo được. Đồng hồ timestamp của hai camera USB không đồng bộ với nhau; trigger chung mới là cách đồng bộ.
- **Tắt mọi xử lý tự động:** ExposureAuto = Off, GainAuto = Off. PGI/Sharpness/Noise Reduction để trung tính nếu có, vì sharpening tạo viền vọng gây hại cho ô 2 px. Line Noise Reduction chưa rõ tác dụng, cần thử A/B. Không dùng binning (mất độ phân giải). Không dùng Multiple ROI trừ khi muốn cắt hai dải.

### Gaps
- Chưa có fps tối đa của a2A2840-48umBAS ở ROI cao 1072 dòng; dự kiến cao hơn 48 fps nhiều nhưng chưa có số. Chưa có dải gain và exposure tối thiểu của bản BAS.
- Chưa xác minh a2A2840-48umBAS có Gamma, Sharpness, PGI hay không (mâu thuẫn tài liệu). Cần mở pylon Viewer để kiểm.

---

## 5. Chồng lấn hai camera

### Takeaway
Với W = 1,6 m mỗi camera, tổng 3,2 m < 3,25 m nên không có chồng lấn mà còn hở 5 cm. Muốn mọi tem (xoay bất kỳ) nằm trọn trong ít nhất một camera, chồng lấn phải ≥ ~60 mm, cộng biên an toàn thì ~100 mm. Khi đó mỗi camera phải phủ ≈ 1,675 m (H ≈ 0,86 m, ~2,2 px/ô). Nếu không, phải xác nhận kính không bao giờ nằm sát mép băng.

### Cited Findings
- QR cần quiet zone 4 ô — [qr-code-generator.com](https://www.qr-code-generator.com/blog/data-matrix-vs-qr-codes).
- Không tìm được nguồn bên ngoài về quy tắc chồng lấn cho đầu đọc mã nhiều camera; phần dưới là tính toán.

### Inferences
- **Kích thước cần chứa (tính):** tem 32 mm (giả sử là kích thước mã, chưa gồm quiet zone 4 × 1,28 = 5,1 mm mỗi bên, tổng ≈ 42 mm). Xoay 45° chiếm 42 × √2 ≈ 60 mm theo chiều ngang. Pipeline hiện bỏ QR chạm mép ảnh, nên tem phải nằm trọn trong một ảnh. Chồng lấn tối thiểu ≈ 60 mm, khuyến nghị 80–100 mm vì ở mép ảnh tối góc nặng và px/ô thấp nhất.
- **Phủ (tính):** 2W − chồng = 3,25 m. Với chồng 100 mm thì W = 1,675 m, H ≈ 4 × 1675/7,83 ≈ 0,86 m, 0,587 mm/px, 2,18 px/ô (trước méo). Như vậy vượt nhẹ giới hạn 1,5–1,6 m đặt ra. Phương án thay thế là đo dải mà kính thực sự chiếm trên băng: nếu có thanh dẫn biên chừa ≥ 30–50 mm thì W = 1,6 m với chồng ~50 mm ở giữa là vừa đủ.
- Nếu muốn tận dụng lề ngang cảm biến, căn hai camera sao cho mép ngoài ảnh chỉ vượt mép băng vài cm. Phần ảnh ngoài băng là vùng tối góc nhất nên không phí.
- Hai camera phải chung một buồng và một chiến lược đèn. Vùng chồng ở giữa nhận ánh sáng ở góc nghiêng ngược nhau từ hai camera; với chiến lược B (trần khuếch tán) điều này không sao; với A (bar xiên dọc băng) cũng đối xứng.

### Gaps
- Chưa biết kính có thể nằm sát mép băng tới đâu, và 32 mm là kích thước mã hay kích thước tem (gồm viền).

---

## 6. Sản phẩm và hệ thống thực tế tương tự

### Takeaway
Không có đèn thương mại cỡ 3,25 m × 0,6 m dạng dome; các hệ thực tế dùng đèn linear/bar ghép (thường có chế độ overdrive strobe), flat dome tối đa ~400 mm, hoặc tunnel dome cho vật nhỏ. Ngành kính đọc mã trên tấm đang chạy bằng dark-field và nhiều lần chụp (patent Saint-Gobain); đầu đọc logistics dùng đèn xung. Các khẳng định hiệu năng của nhà bán là marketing.

### Cited Findings
- Smart Vision Lights ODL300/LSR/LM75: đèn linear overdrive, duty ≤10 %, "sáng gấp tới 5 lần" (**marketing**, không định nghĩa mốc) — [ODL300](https://downloads.machinevisiondirect.com/wp-content/uploads/SVL/ODL300/ODL300_Datasheet.pdf); [SVL ODL300 product](https://smartvisionlights.com/products/odl300/).
- Flat dome CCS tới 300 × 300 mm, Wenglor LFD tới 400 × 400 mm; nên rộng khoảng 2× FOV — [Vision Systems Design](https://www.vision-systems.com/lighting-optics/article/14182971/flat-dome-lights-tame-reflections-and-shadows-in-machine-vision); [Wenglor](https://www.wenglor.com/en/en/Illumination-Technology/Flat-Dome-Lights/c/cxmCID211483). Wenglor có ghi chú ứng dụng chiếu sáng đồng đều mã 1D/2D trên thùng hàng (chưa đọc nội dung) — [Wenglor app](https://www.wenglor.com/en/Homogeneous-Illumination-of-1D-and-2D-Codes-on-Boxes/a/326).
- LDDLIGHT IQD: dome dạng tunnel có cửa vào/ra lớn cho vật đi trên băng — [ThomasNet](https://news.thomasnet.com/fullstory/dome-lights-suit-conveyor-based-machine-vision-systems-568299).
- Saint-Gobain US9767334B2: đọc mã trên tấm kính đang chạy bằng camera line-scan, chiếu dark-field (đèn giữa các con lăn), nhiều lần chụp, kích theo chuyển động — [Google Patents](https://patents.google.com/patent/US9767334B2/en). Có thêm các patent đọc mã trên kính bằng mạng nơ-ron và đọc qua cạnh tấm khi xếp chồng — [USPTO 12086681](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/12086681); [EP3105706B1](https://data.epo.org/gpi/EP3105706B1).
- Viprotron: máy quét anisotropy inline cho kính cường lực, dùng LED đỏ và kính lọc phân cực tròn (tài liệu nhà bán) — [glassonweb](https://www.glassonweb.com/article/anisotropy-measurement-architectural-glass).
- Datalogic AV7000 (đầu đọc line-scan logistics) dùng đèn xung PLS, bản 12k phủ 1.600 mm (từ ghi chú cũ) — [Datalogic AV7000](https://www.datalogic.com/eng/products/industrial-automation/fixed-industrial-barcode-readers/av7000-pd-709.html). Đây là thiết bị khác loại phần cứng cố định, chỉ để tham khảo cách chiếu sáng.

### Inferences
- Buồng tối nên tự chế từ các module linear LED có đầu vào strobe (loại SVL/CCS/Effilux), ghép chạy hết 3,25 m, kèm bộ điều khiển dòng có trigger. Đây là cách gần nhất với sản phẩm thương mại có sẵn.
- Cách tiếp cận dark-field + nhiều lần chụp trong ngành kính khớp với chiến lược A và với kiến trúc đa frame (`PassDecoder`) hiện có.

### Gaps
- Không tìm được nguồn cụ thể về cách các hệ đọc tunnel logistics (SICK, Cognex) chiếu sáng; cũng không tìm được tài liệu ứng dụng của Effilux, Metaphase, Advanced Illumination, CCS cho buồng rộng >1 m hoặc cho kính phẳng. Không có số liệu so sánh khách quan giữa dark-field và cloudy-day trên kính có tem giấy; phải thử bằng mẫu thật trên một đoạn buồng 1 m.
