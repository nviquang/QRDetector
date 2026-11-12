# Tăng tốc decode QR bằng GPU + vẽ quad đúng — Implementation Plan

> **Tài liệu lịch sử:** ghi theo cấu hình tại thời điểm viết (camera MindVision 2448 × 2048, tem 25 mm, khoảng 0,43 mm/px). Thông số hiện tại: `README.md`, mục Thông số hiện trường và tem.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Chạy detect YOLO trên GPU NVIDIA của máy, không decode lại những QR đã đọc chắc, đếm kết quả theo lượt QR đi qua băng, và vẽ khung quad bám đúng QR trên màn hình kể cả khi băng đang chạy.

**Architecture:**
- `QRDetector` tự chọn `cuda:0` khi có CUDA, và trả thêm đường bao mask.
- Các decoder trả về 4 góc QR. Pipeline quy đổi 4 góc này về tọa độ ảnh gốc, nên khi đọc được QR thì quad vẽ ra chính xác. Khi không đọc được, quad lấy hình chữ nhật xoay nhỏ nhất bao mask.
- `PassReader` (`solution/qr/pass_reader.py`) đứng giữa `DecodeWorker` và pipeline, theo dõi QR qua các frame bằng `PassTracker`. Nó bỏ cascade cho lượt đã đọc chắc, đo thời gian từng bước, và tạo `Overlay` gồm quad, trạng thái, vận tốc và seq.
- UI vẽ overlay sau khi đã dịch theo vận tốc tới frame đang hiển thị, và bỏ overlay đã quá cũ.

**Tech Stack:** Python 3.11, PyTorch 2.14.1 (**chuyển từ `+cpu` sang `+cu126`**), ultralytics 8.4 / qrdet 2.5 (YOLOv8-seg), zxing-cpp 3.1, OpenCV 5 (WeChat), PyQt5 5.15, `unittest`.

**Spec:** `solution/DE_XUAT_KHAC_PHUC.md` mục 3 "Tốc độ xử lý", và yêu cầu người dùng ngày 31/10: (1) tận dụng GPU của máy, (2) sửa lỗi quad vẽ lệch.

---

## Bối cảnh đã kiểm tra (31/10)

### Phần cứng và môi trường
- CPU AMD Ryzen 5 5500U (6 luồng torch). **GPU NVIDIA GeForce GTX 1650, 4 GB** (Turing sm_75), driver 595.79, hỗ trợ CUDA tới 13.2. Ngoài ra có Radeon tích hợp, không dùng.
- **`torch 2.14.1+cpu`**, nên `torch.cuda.is_available() == False`: YOLO hiện chạy 100% trên CPU, GPU đứng yên.
- Có sẵn wheel CUDA cho đúng phiên bản: `torch==2.14.1+cu126` / `torchvision==0.29.1+cu126` (mỗi wheel torch khoảng 2,6 GB). Bản `cu130` cũng có, nhưng không có `cu128`. Chọn **cu126** vì nó hỗ trợ sm_75 và driver hiện tại chạy được.
- OpenCV cài từ pip không có CUDA, nên WeChat CNN vẫn chạy CPU. Plan này không đụng tới phần đó.

### Thời gian (CPU, 14 ảnh `images/*.bmp` 2448×2048)
| Cấu hình | detect | scan (detect + cascade) | frame đọc được |
|---|---|---|---|
| Toàn khung, `imgsz=1280` | 772 ms | 1124 ms | 12/14 |
| Dải 2448×768, `imgsz=1280` | 463 ms | 566 ms | 9/14* |
| Toàn khung, `imgsz=640` | 195 ms | — | 0/14 |

\* Dải y=1024..1792 cắt mất các QR ở y≈1914–1940.

- Detect chiếm 70–85% thời gian, và đây là phần chuyển được sang GPU.
- Cascade tốn 1–15 ms khi đọc được ngay, nhưng **200–350 ms cho mỗi detection không đọc được**. Phần này chạy trên CPU. Khi detect đã lên GPU, đây sẽ là phần tốn thời gian nhất, nên việc bỏ cascade cho QR đã đọc chắc (Task 4) càng quan trọng hơn.
- Không hạ `imgsz` (ở 640 mất hết detection). Không dùng zxing quét toàn khung (chỉ đọc được 1/14 ảnh).
- Chưa đo được tốc độ trên GPU vì chưa cài torch CUDA. Task 0 cài, Task 7 đo.

### Nguyên nhân quad vẽ lệch (đã kiểm chứng bằng ảnh)
Đã vẽ thử trên 25 detection của ảnh mẫu, so sánh quad đang dùng (`padded_quad_xy` của qrdet) với 4 góc do decoder trả về:

1. **Quad lấy từ mask segmentation độ phân giải thấp.** YOLOv8-seg sinh mask ở 1/4 kích thước đầu vào. Với `imgsz=1280` trên ảnh 2448 px, mỗi điểm mask tương ứng khoảng 7,6 px ảnh gốc, nên QR 60 px chỉ còn khoảng 8×8 điểm mask. Polygon có 11–90 điểm răng cưa. `QuadrilateralFitter` khớp tứ giác lên polygon đó: độ lệch góc so với 90° có trung vị **8°**, tệ nhất **45°** (thành hình diều). Bật `retina_masks=True` chỉ giảm trung vị xuống 5,6°, trường hợp tệ nhất vẫn 46°.
2. **Code đang chọn `padded_quad_xy`**, là tứ giác *nới rộng* để bao trọn mọi điểm polygon. Chỉ cần một chỗ lồi ra (ngón tay, vùng lóa, mép tem) là một góc bị kéo dài ra. Thường quad to hơn QR khoảng 15–20%, có lúc gấp đôi.
3. **QR nằm sát mép ảnh** bị cắt mask, nên quad thành gần như tam giác.
4. **Quad bị trễ thời gian.** `on_display_tick` vẽ `_last_detections` (kết quả của frame đã decode, cũ khoảng 0,6–1,1 s) lên *frame mới nhất*. Ở 30 cm/s và 0,43 mm/px, QR đi được khoảng 700 px/s, nên quad lệch hàng trăm px so với QR thật. Ngoài ra quad cũ vẫn còn vẽ sau khi QR đã rời khung, và vẫn vẽ khi frame đổi kích thước (bật dải ROI).
5. Quad lệch còn làm bước warp trong cascade (bước 2) kém hiệu quả. Plan này **không đổi** quad dùng cho warp để tránh làm giảm tỷ lệ đọc; Task 7 đo để quyết định sau.

**Cách sửa đã kiểm chứng:**
- **4 góc do decoder trả về** (zxing `Barcode.position`, WeChat `detectAndDecode` points) khớp chính xác với QR trên cả 12/12 ảnh mẫu đọc được, và sai số 0 px trên ảnh tổng hợp. Lưu ý phải trừ phần viền đệm `16 × scale` px mà `upscale_gray` thêm vào trước khi chia cho scale; nếu không, quad lệch về phía dưới bên phải khoảng 16 px.
- Khi không đọc được: dùng `cv2.minAreaRect(polygon_xy)`, luôn là hình chữ nhật và không bao giờ thành hình diều.
- Về độ trễ: dịch quad theo vận tốc của lượt (px/seq, lấy từ tracker) cho bằng chênh lệch seq; bỏ quad cũ hơn 100 seq (khoảng 2 s ở 50 fps) và quad thuộc frame khác kích thước.

### Mục tiêu định lượng
FOV dọc băng hiện tại ≈ 1053 mm. Ở 30 cm/s, mỗi QR nằm trong khung khoảng 3,4 s. Muốn ≥5 lần thử thì mỗi frame phải xử lý xong trong **≤ 680 ms**. Nếu sau này đổi quang học sang 0,25 mm/px thì mục tiêu là **≤ 390 ms**. Với GPU, mục tiêu đặt ra là đạt mức ≤ 390 ms ngay cả ở cấu hình này.

## Global Constraints

- Chỉ sửa trong `solution/` (không sửa `production/`, `Demo/`, `offline/`). Tracker được **copy** sang `solution/qr/tracker.py`.
- Không thêm `basicsr`/`realesrgan`. **Thay đổi môi trường duy nhất** là đổi torch/torchvision sang bản `+cu126` (Task 0). Không cài thêm thư viện nào khác.
- App phải **vẫn chạy được khi không có CUDA** (máy khác, driver lỗi): detector tự quay về `cpu` và ghi cảnh báo vào log.
- `half=False` (FP16) là mặc định. GTX 16xx từng có lỗi FP16; chỉ bật khi Task 7 cho thấy kết quả giống hệt FP32.
- Đầu vào QR luôn là BGR `np.ndarray` contiguous. `CameraManager` giữ nguyên API public. `ImprovePipeline.scan()` và `ImprovePipeline.decode()` giữ nguyên chữ ký và kết quả.
- `torch`/`qr` phải được import **trước** PyQt5 (tránh `WinError 1114`), kể cả trong test. Điều này càng quan trọng khi dùng torch CUDA vì nó nạp nhiều DLL hơn.
- Chuỗi hiển thị trên UI và trong log bằng tiếng Việt.
- `.venv` không có `pytest`. Test chạy bằng `unittest` từ thư mục `solution/`.
- **Bộ test đầy đủ** (chạy ở bước cuối mỗi task, từ `solution/`; module nào chưa tạo thì bỏ khỏi lệnh). **Giữ đúng thứ tự**: các module nạp gói `qr` thật (torch) phải đứng trước các module import PyQt5.
  ```bash
  ../.venv/Scripts/python.exe -m unittest tests.test_detector_device tests.test_pipeline_api tests.test_tracker tests.test_pass_reader tests.test_decode_worker tests.test_camera_diagnostics tests.test_camera_recording tests.test_color_pipeline tests.test_conveyor_mode tests.test_logging_setup tests.test_recording tests.test_recording_ui tests.test_display
  ```
  Kèm theo: `../.venv/Scripts/python.exe tests/test_small_qr.py`, kỳ vọng `[PASS] … >= 12/14`.

## Review Focus

1. **Máy không có CUDA, hoặc torch CUDA không nạp được** → app vẫn chạy bằng CPU, log ghi rõ, UI hiện "CPU". (Task 1: `test_cuda_requested_without_cuda_falls_back_to_cpu`)
2. **Camera mở lại khiến `seq` quay về số nhỏ, hoặc frame đổi kích thước** → đóng hết lượt cũ, và không vẽ quad cũ lên frame mới. (Task 4: `test_backwards_frame_index_closes_open_passes`, `test_shape_change_closes_open_passes`; Task 5: `test_overlay_from_other_shape_is_not_drawn`)
3. **Nhãn bị thay tại chỗ, hoặc lần đọc đầu bị sai** → cứ 5 lần bỏ qua lại đọc kiểm tra một lần; lượt đã mâu thuẫn thì không bỏ qua nữa. (Task 4: `test_recheck_detects_changed_content`, `test_conflicting_reads_never_skip`)
4. **QR nằm sát mép ảnh hoặc mask méo** → quad hiển thị vẫn là tứ giác hợp lý (góc decoder, hoặc hình chữ nhật xoay nhỏ nhất), không thành hình diều hay tam giác. (Task 2: `test_display_quad_*`)
5. **Đóng app trong lúc worker đang warm-up hoặc decode dở trên GPU** → `stop()` không flush tracker khi thread còn sống, và không treo quá thời gian chờ. (Task 5: `test_stop_skips_flush_while_thread_alive`)

---

## File Structure

| File | Trách nhiệm |
|---|---|
| `.venv` (môi trường) | torch/torchvision `+cu126` (Task 0) |
| `solution/README.md` (sửa) | Hướng dẫn cài torch CUDA và cách khôi phục |
| `solution/qr/detector.py` (sửa) | `resolve_device()`, chọn thiết bị và FP16, `warmup()`, `Detection.polygon_xy` |
| `solution/qr/decoder.py` (sửa) | `read_zxing_gray` / `read_wechat_gray` trả `(text, 4 góc)`; các hàm `decode_*_gray` cũ trở thành wrapper |
| `solution/qr/preprocessor.py` (sửa) | `UPSCALE_PAD_PER_SCALE`, `roi_bounds()` |
| `solution/qr/corrector.py` (sửa) | `warp_matrix()` (dùng chung cho `warp_qr`), `display_quad()` |
| `solution/qr/improved_pipeline.py` (sửa) | Inject detector; tham số `device`/`half`; `Decoded(text, corners)`; `decode_detection()`; `warmup()`; `device` |
| `solution/qr/tracker.py` (mới) | `PassTracker` copy từ offline, thêm `match()` và `Track.votes` |
| `solution/qr/pass_reader.py` (mới) | `PassReader`, `FrameResult`, `Overlay` |
| `solution/qr/__init__.py` (sửa) | Export `Decoded`, `FrameResult`, `Overlay`, `PassReader` |
| `solution/ui/main_window.py` (sửa) | `DecodeWorker` dùng `PassReader` (warm-up trong thread); `draw_overlays()`; `frame_to_qimage()`; nhãn hiện thiết bị, ms từng bước, số lượt |
| `solution/tests/qr_fixtures.py` (mới) | Ảnh QR tổng hợp, `Detection` giả |
| `solution/tests/test_detector_device.py`, `test_pipeline_api.py`, `test_tracker.py`, `test_pass_reader.py`, `test_decode_worker.py`, `test_display.py` (mới) | Test đơn vị |
| `solution/tests/test_camera_diagnostics.py`, `test_recording_ui.py`, `test_conveyor_mode.py` (sửa) | Stub `qr` mới và test nhãn |
| `solution/tests/bench_decode.py` (mới) | Đo CPU/GPU, dải/toàn khung, video |
| `solution/CLAUDE.md`, `solution/DE_XUAT_KHAC_PHUC.md` (sửa) | Kiến trúc mới, kết quả đo |

---

### Task 0: Cài torch CUDA cho GTX 1650

Thay đổi môi trường, không có code. **Phải làm trước mọi task khác**, vì Task 1 và Task 7 cần GPU để kiểm chứng.

**Files:**
- Modify: `solution/README.md` (mục "## 2. Python environment", chèn ngay trước "### Chạy")

- [ ] **Step 1: Lưu lại danh sách gói hiện tại để có thể khôi phục**

Run (từ gốc repo):
```bash
.venv/Scripts/python.exe -m pip freeze > tmp/requirements-before-cuda.txt
```
`tmp/` đã nằm trong `.gitignore`.

- [ ] **Step 2: Cài torch/torchvision bản CUDA 12.6**

Cần cắm sạc và có mạng ổn định (khoảng 2,6 GB).
```bash
.venv/Scripts/python.exe -m pip install "torch==2.14.1+cu126" "torchvision==0.29.1+cu126" --index-url https://download.pytorch.org/whl/cu126
```
Expected: `Successfully installed torch-2.14.1+cu126 torchvision-0.29.1+cu126` (có thể kèm vài gói phụ thuộc).

- [ ] **Step 3: Kiểm tra GPU**

```bash
.venv/Scripts/python.exe -c "import torch; print(torch.__version__, torch.cuda.is_available(), torch.cuda.get_device_name(0)); x = torch.ones(1000, 1000, device='cuda'); print(float((x @ x).sum()))"
```
Expected: `2.14.1+cu126 True NVIDIA GeForce GTX 1650` và `1000000000.0`.

- [ ] **Step 4: Kiểm tra thứ tự nạp DLL (WinError 1114) và test hiện có**

Run (từ `solution/`):
```bash
../.venv/Scripts/python.exe -c "import qr; import PyQt5.QtWidgets; import torch; print('ok', torch.cuda.is_available())"
```
Expected: `ok True`.
Sau đó chạy bộ test đầy đủ (chỉ gồm các module đang có) và `tests/test_small_qr.py`. Kỳ vọng: kết quả giống hệt trước khi cài, vì code chưa dùng GPU.
Cuối cùng chạy `../.venv/Scripts/python.exe main.py`. Cửa sổ phải mở được; đóng lại là xong.

- [ ] **Step 5: Nếu Step 3 hoặc Step 4 lỗi thì khôi phục**

```bash
.venv/Scripts/python.exe -m pip install "torch==2.14.1+cpu" "torchvision==0.29.1+cpu" --index-url https://download.pytorch.org/whl/cpu
```
Dừng plan và báo lỗi kèm output. Các task sau vẫn đúng trên CPU nhưng không đạt mục tiêu tốc độ.

- [ ] **Step 6: Ghi hướng dẫn vào `solution/README.md`**

Chèn ngay trước dòng `### Chạy`:

````markdown
### GPU NVIDIA (khuyến nghị)

Detect QR (YOLO) chạy trên GPU NVIDIA nếu torch có CUDA; không có CUDA thì tự chạy CPU (chậm hơn nhiều).
Máy lab: GTX 1650 4 GB, driver ≥ 560. Thay torch bản CPU bằng bản CUDA 12.6 (~2,6 GB):

```bash
.venv\Scripts\python.exe -m pip install "torch==2.14.1+cu126" "torchvision==0.29.1+cu126" --index-url https://download.pytorch.org/whl/cu126
.venv\Scripts\python.exe -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
```

Quay lại bản CPU: cùng lệnh với `+cpu` và `--index-url https://download.pytorch.org/whl/cpu`.
Thiết bị đang dùng hiện trên nhãn "Decode" (GPU/CPU) và trong log (`qr_detector device=…`).
````

- [ ] **Step 7: Commit**

```bash
git add solution/README.md
git commit -m "docs(solution): hướng dẫn cài torch CUDA cho detect QR trên GPU"
```

---

### Task 1: `QRDetector` chạy trên GPU, trả thêm polygon mask

**Files:**
- Modify: `solution/qr/detector.py`
- Create: `solution/tests/test_detector_device.py`

**Interfaces:**
- Produces:
  - `Detection(bbox_xyxy, quad_xy, confidence, polygon_xy=None)`. `polygon_xy` có dạng `(N, 2)` float32 hoặc `None`.
  - `resolve_device(requested: str, cuda_available: bool) -> str`
  - `QRDetector(model_size="s", conf_th=0.5, imgsz=640, device="auto", half=False)`; property `device -> str`; `warmup(shape=(768, 2448)) -> None`
  - Logger `"solution.qr"`: lúc khởi tạo ghi INFO `qr_detector device=… half=… imgsz=… gpu=…`; khi buộc phải chạy CPU ghi WARNING `Không có CUDA — detector chạy CPU thay cho …`.

- [ ] **Step 1: Viết test (fail)**

`solution/tests/test_detector_device.py`:

```python
"""Chọn thiết bị cho detector + kiểm tra GPU thật (bỏ qua nếu máy không có CUDA).

Chạy (từ solution/):  python -m unittest tests.test_detector_device
"""
import glob
from pathlib import Path
import sys
import unittest

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import torch  # noqa: E402
from qr.detector import Detection, QRDetector, resolve_device  # noqa: E402

SAMPLES = sorted(glob.glob(str(ROOT.parent / "images" / "*.bmp")))[:3]


class ResolveDeviceTests(unittest.TestCase):
    def test_auto_picks_cuda_when_available(self):
        self.assertEqual(resolve_device("auto", True), "cuda:0")
        self.assertEqual(resolve_device("auto", False), "cpu")

    def test_cuda_requested_without_cuda_falls_back_to_cpu(self):
        with self.assertLogs("solution.qr", "WARNING"):
            self.assertEqual(resolve_device("cuda:0", False), "cpu")

    def test_explicit_device_is_kept(self):
        self.assertEqual(resolve_device("cpu", True), "cpu")
        self.assertEqual(resolve_device("cuda:0", True), "cuda:0")

    def test_detection_polygon_defaults_to_none(self):
        det = Detection(np.zeros(4, np.float32), np.zeros((4, 2), np.float32), 0.9)
        self.assertIsNone(det.polygon_xy)


@unittest.skipUnless(SAMPLES, "thiếu ảnh mẫu ../images/*.bmp")
class RealDetectorTests(unittest.TestCase):
    def test_detections_carry_mask_polygon(self):
        det = QRDetector(conf_th=0.3, imgsz=1280, device="cpu").detect(cv2.imread(SAMPLES[0]))[0]
        self.assertGreaterEqual(len(det.polygon_xy), 3)

    @unittest.skipUnless(torch.cuda.is_available(), "máy không có CUDA")
    def test_gpu_finds_same_qrs_as_cpu(self):
        cpu = QRDetector(conf_th=0.3, imgsz=1280, device="cpu")
        gpu = QRDetector(conf_th=0.3, imgsz=1280, device="auto")
        self.assertTrue(gpu.device.startswith("cuda"))
        gpu.warmup()
        for path in SAMPLES:
            img = cv2.imread(path)
            a, b = cpu.detect(img), gpu.detect(img)
            self.assertEqual(len(a), len(b), path)
            for da, db in zip(sorted(a, key=lambda d: d.bbox_xyxy[0]), sorted(b, key=lambda d: d.bbox_xyxy[0])):
                np.testing.assert_allclose(da.bbox_xyxy, db.bbox_xyxy, atol=3.0)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `../.venv/Scripts/python.exe -m unittest tests.test_detector_device -v`
Expected: `ImportError: cannot import name 'resolve_device'`.

- [ ] **Step 3: Viết lại `solution/qr/detector.py`**

```python
"""Bước 1: Phát hiện QR bằng qrdet (YOLOv8-seg) — chạy GPU NVIDIA nếu torch có CUDA."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import torch
from qrdet import QRDetector as _QRDetector
# qrdet.detect() không cho chỉnh imgsz → gọi thẳng model YOLO và dùng lại helper của qrdet
from qrdet.qrdet import _prepare_input, _yolo_v8_results_to_dict

logger = logging.getLogger("solution.qr")


@dataclass
class Detection:
    bbox_xyxy: np.ndarray   # [x1, y1, x2, y2] float32
    quad_xy: np.ndarray     # (4, 2) float32 — padded quad của qrdet, dùng cho warp trong cascade
    confidence: float
    polygon_xy: np.ndarray | None = None   # (N, 2) đường bao mask — nguồn quad hiển thị khi chưa đọc được


def resolve_device(requested: str, cuda_available: bool) -> str:
    """'auto' → 'cuda:0' nếu có CUDA, ngược lại 'cpu'. Yêu cầu cuda mà không có → 'cpu' + cảnh báo."""
    if requested == "auto":
        return "cuda:0" if cuda_available else "cpu"
    if requested.startswith("cuda") and not cuda_available:
        logger.warning("Không có CUDA — detector chạy CPU thay cho %s", requested)
        return "cpu"
    return requested


class QRDetector:
    def __init__(self, model_size: str = "s", conf_th: float = 0.5, imgsz: int = 640,
                 device: str = "auto", half: bool = False):
        """
        imgsz:  cạnh ảnh đưa vào YOLO. Mặc định qrdet là 640 — frame 2448×2048 bị thu nhỏ ~4 lần,
                QR ~60px còn ~15px và bị bỏ sót. imgsz=1280 giữ QR nhỏ đủ lớn để phát hiện.
        device: "auto" (GPU nếu có), "cpu" hoặc "cuda:N".
        half:   FP16 — chỉ có tác dụng trên GPU; tắt mặc định vì GTX 16xx từng lỗi FP16.
        """
        self._detector = _QRDetector(model_size=model_size, conf_th=conf_th)
        self._conf_th = conf_th
        self._imgsz = imgsz
        self._device = resolve_device(device, torch.cuda.is_available())
        self._half = half and self._device.startswith("cuda")
        gpu = torch.cuda.get_device_name(self._device) if self._device.startswith("cuda") else "-"
        logger.info("qr_detector device=%s half=%s imgsz=%d gpu=%s",
                    self._device, self._half, imgsz, gpu)

    @property
    def device(self) -> str:
        return self._device

    def warmup(self, shape: tuple[int, int] = (768, 2448)):
        """Detect một lần trên ảnh đen — lần đầu trên GPU mất vài giây (nạp kernel CUDA)."""
        self.detect(np.zeros((shape[0], shape[1], 3), np.uint8))

    def detect(self, image_bgr: np.ndarray) -> list[Detection]:
        """Nhận ảnh BGR, trả về danh sách Detection (có thể rỗng)."""
        image = _prepare_input(source=image_bgr, is_bgr=True)
        predictions = self._detector.model.predict(
            source=image, conf=self._conf_th, iou=self._detector._nms_iou, imgsz=self._imgsz,
            device=self._device, half=self._half, max_det=100, agnostic_nms=True, verbose=False,
        )
        raw = _yolo_v8_results_to_dict(results=predictions[0], image=image)
        results = []
        for d in raw:
            # ưu tiên padded_quad_xy để bao trọn QR khi warp; fallback về quad_xy
            quad = d.get("padded_quad_xy", d.get("quad_xy"))
            if quad is None:
                continue
            polygon = d.get("polygon_xy")
            results.append(Detection(
                bbox_xyxy=d["bbox_xyxy"].astype(np.float32),
                quad_xy=quad.astype(np.float32),
                confidence=float(d["confidence"]),
                polygon_xy=None if polygon is None else np.asarray(polygon, np.float32),
            ))
        return results
```

- [ ] **Step 4: Chạy test, xác nhận pass**

Run: `../.venv/Scripts/python.exe -m unittest tests.test_detector_device -v`
Expected: `Ran 6 tests … OK`. Sau Task 0 không có test nào bị skip. Nếu `test_gpu_finds_same_qrs_as_cpu` lệch bbox hơn 3 px, ghi lại độ lệch thực tế và báo trước khi nới ngưỡng.

- [ ] **Step 5: Bộ test đầy đủ + `test_small_qr.py`, rồi commit**

`test_small_qr.py` lúc này chạy trên GPU (vì mặc định là `auto`). Kỳ vọng vẫn ≥12/14 và thời gian trung bình mỗi frame giảm rõ.

```bash
git add solution/qr/detector.py solution/tests/test_detector_device.py
git commit -m "perf(solution/qr): detect QR trên GPU CUDA (tự về CPU nếu không có), trả polygon mask"
```

---

### Task 2: Decoder trả góc QR; pipeline trả `Decoded`; quad hiển thị đúng

**Files:**
- Modify: `solution/qr/decoder.py` (các hàm `decode_zxing_gray`, `decode_wechat_gray`)
- Modify: `solution/qr/preprocessor.py` (`upscale_gray`, `crop_roi_gray`)
- Modify: `solution/qr/corrector.py` (`warp_qr`)
- Modify: `solution/qr/improved_pipeline.py` (toàn bộ phần cascade và class)
- Modify: `solution/qr/__init__.py`
- Create: `solution/tests/qr_fixtures.py`, `solution/tests/test_pipeline_api.py`

**Interfaces:**
- Consumes: `Detection.polygon_xy`, `QRDetector(device=, half=)`, `QRDetector.device`, `QRDetector.warmup()` (Task 1).
- Produces:
  - `read_zxing_gray(gray) -> tuple[str, np.ndarray] | None` và `read_wechat_gray(gray, use_cnn=False) -> tuple[str, np.ndarray] | None`. Mảng góc có dạng `(4, 2)` float32, theo thứ tự vòng, trong tọa độ của `gray`.
  - `UPSCALE_PAD_PER_SCALE = 16`; `roi_bounds(shape, bbox_xyxy, margin=0.25) -> tuple[int, int, int, int]`
  - `warp_matrix(detection, out_size) -> np.ndarray (3×3)`; `display_quad(det, corners=None) -> np.ndarray (4, 2) float32`
  - `Decoded(text: str, corners: np.ndarray)` (dataclass, góc trong tọa độ ảnh gốc)
  - `ImprovePipeline(model_size="s", conf_th=0.3, imgsz=1280, roi_margin=0.25, detector=None, device="auto", half=False)`; `decode_detection(image_bgr, det) -> Decoded | None`; `warmup(shape=(768, 2448))`; property `device -> str`
  - `tests.qr_fixtures.frame_with_qrs(items, shape=(600, 900), scale=4)`, `detection_at(cx, cy, size=60.0)`, `symbol_corners(x, y, scale=4)`

- [ ] **Step 1: Tạo fixture**

`solution/tests/qr_fixtures.py`:

```python
"""Ảnh QR tổng hợp và Detection giả cho test — không cần camera hay model YOLO."""

import cv2
import numpy as np

from qr.detector import Detection

_BORDER_MODULES = 2      # QRCodeEncoder của OpenCV đệm 2 ô trắng mỗi phía (25×25 cho QR 21 ô)


def qr_image(text: str, scale: int = 4) -> np.ndarray:
    """QR xám (đã gồm viền trắng của encoder) phóng ``scale`` lần, giữ cạnh sắc."""
    code = cv2.QRCodeEncoder.create().encode(text)
    return cv2.resize(code, None, fx=scale, fy=scale, interpolation=cv2.INTER_NEAREST)


def symbol_corners(x: int, y: int, text: str = "000000585545", scale: int = 4) -> np.ndarray:
    """4 góc ngoài của ký hiệu QR (không gồm viền trắng) khi đặt qr_image ở góc trái-trên (x, y)."""
    size = qr_image(text, scale).shape[0]
    b = _BORDER_MODULES * scale
    return np.array([[x + b, y + b], [x + size - b, y + b], [x + size - b, y + size - b],
                     [x + b, y + size - b]], np.float32)


def frame_with_qrs(items, shape=(600, 900), scale=4):
    """Frame BGR nền trắng; ``items`` = [(text, (x, y))] với (x, y) là góc trái-trên.

    Trả (frame, detections) — Detection thứ i bao đúng ảnh QR thứ i (quad = polygon = khung ảnh QR).
    """
    frame = np.full((shape[0], shape[1], 3), 255, np.uint8)
    detections = []
    for text, (x, y) in items:
        code = qr_image(text, scale)
        h, w = code.shape
        frame[y:y + h, x:x + w] = code[..., None]
        quad = np.array([[x, y], [x + w, y], [x + w, y + h], [x, y + h]], np.float32)
        detections.append(Detection(bbox_xyxy=np.array([x, y, x + w, y + h], np.float32),
                                    quad_xy=quad, confidence=0.9, polygon_xy=quad.copy()))
    return frame, detections


def detection_at(cx: float, cy: float, size: float = 60.0) -> Detection:
    """Detection vuông cạnh ``size`` tâm (cx, cy) — dùng khi chỉ cần vị trí, không cần ảnh."""
    r = size / 2
    quad = np.array([[cx - r, cy - r], [cx + r, cy - r], [cx + r, cy + r], [cx - r, cy + r]],
                    np.float32)
    return Detection(bbox_xyxy=np.array([cx - r, cy - r, cx + r, cy + r], np.float32),
                     quad_xy=quad, confidence=0.9, polygon_xy=quad.copy())
```

- [ ] **Step 2: Viết test (fail)**

`solution/tests/test_pipeline_api.py`:

```python
"""API pipeline: inject detector, decode_detection trả Decoded (text + 4 góc), quad hiển thị.
Không cần YOLO.

Chạy (từ solution/):  python -m unittest tests.test_pipeline_api
"""
from pathlib import Path
import sys
import unittest

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from qr import Decoded, ImprovePipeline  # noqa: E402
from qr.corrector import display_quad  # noqa: E402
from qr.decoder import read_wechat_gray, read_zxing_gray  # noqa: E402
from qr.detector import Detection  # noqa: E402
from qr.improved_pipeline import _warp_zxing_step  # noqa: E402
from qr.preprocessor import UPSCALE_PAD_PER_SCALE, upscale_gray  # noqa: E402
from tests.qr_fixtures import frame_with_qrs, qr_image, symbol_corners  # noqa: E402


class FakeDetector:
    def __init__(self, detections):
        self.detections = detections
        self.calls = 0

    def detect(self, image_bgr):
        self.calls += 1
        return list(self.detections)


def assert_corners(test, got, expected, tol=2.0):
    """Mỗi góc kỳ vọng có một góc trả về cách ≤ tol px (không ràng buộc thứ tự bắt đầu)."""
    for e in expected:
        test.assertLessEqual(float(np.min(np.linalg.norm(got - e, axis=1))), tol, (got, expected))


class DecoderCornerTests(unittest.TestCase):
    def setUp(self):
        self.gray = np.full((300, 300), 255, np.uint8)
        q = qr_image("000000585545")
        self.gray[50:50 + q.shape[0], 60:60 + q.shape[1]] = q
        self.expected = symbol_corners(60, 50)

    def test_zxing_returns_symbol_corners(self):
        text, corners = read_zxing_gray(self.gray)
        self.assertEqual(text, "000000585545")
        assert_corners(self, corners, self.expected)

    def test_wechat_returns_symbol_corners(self):
        text, corners = read_wechat_gray(self.gray)
        self.assertEqual(text, "000000585545")
        assert_corners(self, corners, self.expected)

    def test_upscale_pad_constant_matches_upscale_gray(self):
        up = upscale_gray(self.gray, 3)
        self.assertEqual(up.shape[0], 300 * 3 + 2 * UPSCALE_PAD_PER_SCALE * 3)


class PipelineApiTests(unittest.TestCase):
    def test_scan_uses_injected_detector(self):
        frame, dets = frame_with_qrs([("000000585545", (100, 100))])
        detector = FakeDetector(dets)
        results, found = ImprovePipeline(detector=detector).scan(frame)
        self.assertEqual(results, ["000000585545"])
        self.assertEqual(found, dets)
        self.assertEqual(detector.calls, 1)

    def test_decode_detection_maps_corners_back_to_frame(self):
        frame, (det,) = frame_with_qrs([("000000585545", (130, 90))])
        hit = ImprovePipeline(detector=FakeDetector([])).decode_detection(frame, det)
        self.assertIsInstance(hit, Decoded)
        self.assertEqual(hit.text, "000000585545")
        assert_corners(self, hit.corners, symbol_corners(130, 90))

    def test_warp_step_maps_corners_back_through_homography(self):
        frame, (det,) = frame_with_qrs([("000000585545", (200, 150))])
        hit = _warp_zxing_step(frame, det, None, np.zeros(2, np.float32))
        self.assertEqual(hit.text, "000000585545")
        assert_corners(self, hit.corners, symbol_corners(200, 150), tol=3.0)

    def test_decode_detection_reads_only_its_own_qr(self):
        frame, (_, second) = frame_with_qrs([("000000000001", (50, 50)),
                                             ("000000000002", (500, 300))])
        hit = ImprovePipeline(detector=FakeDetector([])).decode_detection(frame, second)
        self.assertEqual(hit.text, "000000000002")

    def test_decode_detection_on_blank_area_returns_none(self):
        frame = np.full((400, 400, 3), 255, np.uint8)
        quad = np.array([[100, 100], [160, 100], [160, 160], [100, 160]], np.float32)
        det = Detection(np.array([100, 100, 160, 160], np.float32), quad, 0.9)
        self.assertIsNone(ImprovePipeline(detector=FakeDetector([])).decode_detection(frame, det))


class DisplayQuadTests(unittest.TestCase):
    def test_display_quad_prefers_decoder_corners(self):
        corners = np.array([[1, 2], [3, 2], [3, 4], [1, 4]], np.float32)
        det = Detection(np.zeros(4, np.float32), np.zeros((4, 2), np.float32), 0.9)
        np.testing.assert_array_equal(display_quad(det, corners), corners)

    def test_display_quad_from_jagged_polygon_is_rectangle(self):
        # polygon răng cưa + một điểm lồi (kiểu ngón tay) — padded quad của qrdet thành hình diều
        poly = np.array([[100, 100], [160, 98], [162, 160], [130, 175], [99, 161]], np.float32)
        det = Detection(np.array([99, 98, 162, 175], np.float32), np.zeros((4, 2), np.float32), 0.9,
                        polygon_xy=poly)
        quad = display_quad(det)
        self.assertEqual(quad.shape, (4, 2))
        for i in range(4):          # mọi góc vuông
            a, b, c = quad[i - 1], quad[i], quad[(i + 1) % 4]
            cos = float(np.dot(a - b, c - b) / (np.linalg.norm(a - b) * np.linalg.norm(c - b)))
            self.assertLess(abs(cos), 1e-3)

    def test_display_quad_without_polygon_uses_bbox(self):
        det = Detection(np.array([10, 20, 70, 90], np.float32), np.zeros((4, 2), np.float32), 0.9)
        np.testing.assert_array_equal(display_quad(det),
                                      np.array([[10, 20], [70, 20], [70, 90], [10, 90]], np.float32))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Chạy test, xác nhận fail**

Run: `../.venv/Scripts/python.exe -m unittest tests.test_pipeline_api -v`
Expected: `ImportError: cannot import name 'Decoded' from 'qr'`.

- [ ] **Step 4: Sửa `solution/qr/decoder.py`**

Thay hai hàm `decode_zxing_gray` và `decode_wechat_gray` bằng:

```python
def _zxing_corners(barcode) -> np.ndarray:
    p = barcode.position
    return np.array([[p.top_left.x, p.top_left.y], [p.top_right.x, p.top_right.y],
                     [p.bottom_right.x, p.bottom_right.y], [p.bottom_left.x, p.bottom_left.y]],
                    np.float32)


def read_zxing_gray(gray: np.ndarray) -> tuple[str, np.ndarray] | None:
    """zxing-cpp binarizer LocalAverage — rất nhanh (~1ms) trên ROI đã upscale.

    Trả (nội dung, 4 góc QR (4, 2) trong tọa độ ``gray``) hoặc None.
    """
    for b in zxingcpp.read_barcodes(gray, formats=zxingcpp.BarcodeFormat.QRCode, try_rotate=True):
        if b.valid and b.text:
            return b.text, _zxing_corners(b)
    return None


def decode_zxing_gray(gray: np.ndarray) -> str | None:
    hit = read_zxing_gray(gray)
    return hit[0] if hit else None
```

và (đặt sau `_get_wechat_cnn_detector`):

```python
def read_wechat_gray(gray: np.ndarray, use_cnn: bool = False) -> tuple[str, np.ndarray] | None:
    """WeChatQRCode một lần (không xoay — WeChat tự xử lý hướng). use_cnn=True dùng CNN + SR.

    Trả (nội dung, 4 góc QR (4, 2) trong tọa độ ``gray``) hoặc None.
    """
    detector = _get_wechat_cnn_detector() if use_cnn else _get_wechat_detector()
    if detector is None:
        return None
    try:
        texts, points = detector.detectAndDecode(gray)
    except Exception:
        return None
    for text, pts in zip(texts, points):
        if text:
            return text, np.asarray(pts, np.float32).reshape(4, 2)
    return None


def decode_wechat_gray(gray: np.ndarray, use_cnn: bool = False) -> str | None:
    hit = read_wechat_gray(gray, use_cnn)
    return hit[0] if hit else None
```

- [ ] **Step 5: Sửa `solution/qr/preprocessor.py`**

Thay `crop_roi_gray` và `upscale_gray` bằng:

```python
UPSCALE_PAD_PER_SCALE = 16   # upscale_gray đệm viền (UPSCALE_PAD_PER_SCALE × scale) px mỗi phía


def roi_bounds(shape, bbox_xyxy: np.ndarray, margin: float = 0.25) -> tuple[int, int, int, int]:
    """bbox nới thêm margin × cạnh dài, kẹp trong ảnh — (x1, y1, x2, y2) nguyên."""
    h, w = shape[:2]
    x1, y1, x2, y2 = bbox_xyxy
    m = margin * max(x2 - x1, y2 - y1)
    return (int(max(0, x1 - m)), int(max(0, y1 - m)),
            int(min(w, x2 + m)), int(min(h, y2 + m)))


def crop_roi_gray(image_bgr: np.ndarray, bbox_xyxy: np.ndarray, margin: float = 0.25) -> np.ndarray:
    """Cắt bbox (nới thêm margin × cạnh dài) từ ảnh gốc độ phân giải đầy đủ, trả về ảnh xám."""
    x1, y1, x2, y2 = roi_bounds(image_bgr.shape, bbox_xyxy, margin)
    roi = image_bgr[y1:y2, x1:x2]
    return cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY) if roi.ndim == 3 else roi
```

```python
def upscale_gray(gray: np.ndarray, scale: int, pad_per_scale: int = UPSCALE_PAD_PER_SCALE) -> np.ndarray:
    """Upscale bicubic rồi đệm viền replicate (pad_per_scale × scale px) để giữ Quiet Zone."""
    up = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    pad = pad_per_scale * scale
    return cv2.copyMakeBorder(up, pad, pad, pad, pad, cv2.BORDER_REPLICATE)
```

Nếu `upscale_gray` đang nằm sau `crop_roi_gray` thì đặt `UPSCALE_PAD_PER_SCALE` lên đầu file, ngay sau phần import.

- [ ] **Step 6: Sửa `solution/qr/corrector.py`**

Thay `warp_qr` bằng hai hàm dưới đây, và thêm `display_quad` vào cuối file:

```python
def warp_matrix(detection: Detection, out_size: int = _DEFAULT_SIZE) -> np.ndarray:
    """Ma trận perspective đưa quad của detection về hình vuông out_size × out_size."""
    src = _order_points(detection.quad_xy)
    dst = np.array([
        [0, 0],
        [out_size - 1, 0],
        [out_size - 1, out_size - 1],
        [0, out_size - 1],
    ], dtype=np.float32)
    return cv2.getPerspectiveTransform(src, dst)


def warp_qr(
    image_bgr: np.ndarray,
    detection: Detection,
    out_size: int = _DEFAULT_SIZE,
    pad_px: int = 0,
) -> np.ndarray:
    """Warp perspective vùng QR về ảnh vuông out_size x out_size (tuỳ chọn đệm Quiet Zone viền trắng)."""
    warped = cv2.warpPerspective(image_bgr, warp_matrix(detection, out_size), (out_size, out_size),
                                 flags=cv2.INTER_LANCZOS4)
    if pad_px > 0:
        return add_quiet_zone(warped, pad_px=pad_px)
    return warped


def display_quad(detection: Detection, corners: np.ndarray | None = None) -> np.ndarray:
    """Quad để VẼ lên màn hình.

    Ưu tiên 4 góc decoder trả về (khớp QR chính xác). Chưa đọc được → hình chữ nhật xoay nhỏ nhất bao
    mask: padded quad của qrdet khớp trên mask thô (~8×8 điểm cho QR 60px) nên hay thành hình diều /
    to hơn QR. Không có mask → bbox.
    """
    if corners is not None:
        return np.asarray(corners, np.float32)
    poly = detection.polygon_xy
    if poly is not None and len(poly) >= 3:
        return cv2.boxPoints(cv2.minAreaRect(np.asarray(poly, np.float32))).astype(np.float32)
    x1, y1, x2, y2 = (float(v) for v in detection.bbox_xyxy)
    return np.array([[x1, y1], [x2, y1], [x2, y2], [x1, y2]], np.float32)
```

- [ ] **Step 7: Viết lại `solution/qr/improved_pipeline.py`**

Giữ nguyên docstring module hiện tại và thêm một đoạn vào cuối docstring:

```
Mỗi bước trả ``Decoded`` gồm cả 4 góc QR quy về tọa độ ảnh gốc (trừ viền đệm của upscale_gray, chia
scale, cộng gốc ROI; bước warp đi ngược qua homography) — UI vẽ quad bằng góc này thay cho padded quad.
```

Phần code sau docstring:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import cv2
import numpy as np

from .corrector import add_quiet_zone, warp_matrix, warp_qr
from .decoder import read_wechat_gray, read_zxing_gray
from .detector import Detection, QRDetector
from .preprocessor import UPSCALE_PAD_PER_SCALE, clahe, roi_bounds, stretch_contrast, upscale_gray

_WARP_SIZE = 256
_WARP_PAD = 32


@dataclass
class Decoded:
    text: str
    corners: np.ndarray   # (4, 2) float32 — 4 góc QR trong tọa độ ảnh gốc, thứ tự vòng


Reader = Callable[[np.ndarray], "tuple[str, np.ndarray] | None"]


def _roi_step(preprocess: Callable[[np.ndarray], np.ndarray], scale: int, read: Reader):
    pad = UPSCALE_PAD_PER_SCALE * scale

    def step(image_bgr: np.ndarray, det: Detection, roi_gray: np.ndarray,
             origin: np.ndarray) -> Decoded | None:
        hit = read(upscale_gray(preprocess(roi_gray), scale))
        if hit is None:
            return None
        text, pts = hit
        return Decoded(text, ((pts - pad) / scale + origin).astype(np.float32))
    return step


def _warp_zxing_step(image_bgr: np.ndarray, det: Detection, roi_gray: np.ndarray,
                     origin: np.ndarray) -> Decoded | None:
    warped = cv2.cvtColor(warp_qr(image_bgr, det, out_size=_WARP_SIZE), cv2.COLOR_BGR2GRAY)
    hit = read_zxing_gray(add_quiet_zone(warped, pad_px=_WARP_PAD))
    if hit is None:
        return None
    text, pts = hit
    back = np.linalg.inv(warp_matrix(det, _WARP_SIZE))
    corners = cv2.perspectiveTransform((pts - _WARP_PAD).reshape(-1, 1, 2).astype(np.float32), back)
    return Decoded(text, corners.reshape(4, 2).astype(np.float32))


def _identity(gray: np.ndarray) -> np.ndarray:
    return gray


_CASCADE = (
    _roi_step(_identity, 4, read_zxing_gray),
    _warp_zxing_step,
    _roi_step(clahe, 4, read_wechat_gray),
    _roi_step(stretch_contrast, 4, lambda g: read_wechat_gray(g, use_cnn=True)),
    _roi_step(_identity, 3, lambda g: read_wechat_gray(g, use_cnn=True)),
)


class ImprovePipeline:
    def __init__(
        self,
        model_size: str = "s",
        conf_th: float = 0.3,
        imgsz: int = 1280,
        roi_margin: float = 0.25,
        detector=None,
        device: str = "auto",
        half: bool = False,
    ):
        """detector: object có ``detect(image_bgr) -> list[Detection]`` — mặc định QRDetector (YOLO,
        GPU nếu có); test truyền detector giả để không phải nạp model."""
        self._detector = detector if detector is not None else QRDetector(
            model_size=model_size, conf_th=conf_th, imgsz=imgsz, device=device, half=half)
        self._roi_margin = roi_margin

    # ── public ────────────────────────────────────────────────────────────────

    @property
    def device(self) -> str:
        return getattr(self._detector, "device", "cpu")

    def warmup(self, shape: tuple[int, int] = (768, 2448)):
        """Chạy detect một lần để lần đầu trên GPU không rơi vào frame thật."""
        self._detector.warmup(shape)

    def detect(self, image_bgr: np.ndarray) -> list[Detection]:
        """Chỉ chạy bước detect — dùng để vẽ quad không cần decode."""
        return self._detector.detect(image_bgr)

    def decode(self, image_bgr: np.ndarray) -> list[str]:
        """
        Nhận ảnh BGR (np.ndarray H×W×3 uint8), trả về list nội dung QR (có thể rỗng).
        """
        results, _ = self.scan(image_bgr)
        return results

    def scan(self, image_bgr: np.ndarray) -> tuple[list[str], list[Detection]]:
        """Detect 1 lần, trả về (list nội dung QR, list Detection TẤT CẢ — dùng để vẽ quad)."""
        detections = self._detector.detect(image_bgr)
        if not detections:
            return [], []

        results: list[str] = []
        for det in detections:
            hit = self.decode_detection(image_bgr, det)
            if hit:
                results.append(hit.text)
        return results, detections

    def decode_detection(self, image_bgr: np.ndarray, det: Detection) -> Decoded | None:
        """Chạy cascade cho MỘT detection, trả nội dung + 4 góc QR (tọa độ ảnh gốc) hoặc None."""
        x1, y1, x2, y2 = roi_bounds(image_bgr.shape, det.bbox_xyxy, self._roi_margin)
        roi = image_bgr[y1:y2, x1:x2]
        if roi.size == 0:
            return None
        roi_gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY) if roi.ndim == 3 else roi
        origin = np.array([x1, y1], np.float32)
        for step in _CASCADE:
            hit = step(image_bgr, det, roi_gray, origin)
            if hit:
                return hit
        return None
```

`device` dùng `getattr` vì detector inject vào (fake trong test) có thể không có thuộc tính `device`.

- [ ] **Step 8: Export trong `solution/qr/__init__.py`**

```python
from .detector import Detection, QRDetector
from .improved_pipeline import Decoded, ImprovePipeline

__all__ = ["Detection", "QRDetector", "Decoded", "ImprovePipeline"]
```

- [ ] **Step 9: Chạy test, xác nhận pass**

Run: `../.venv/Scripts/python.exe -m unittest tests.test_pipeline_api -v`
Expected: `Ran 11 tests … OK`.
Nếu `test_warp_step_maps_corners_back_through_homography` lệch hơn 3 px, kiểm tra lại thứ tự hai phép: phải trừ `_WARP_PAD` trước, rồi mới nhân với ma trận nghịch đảo.

- [ ] **Step 10: Hồi quy, rồi commit**

Run: `../.venv/Scripts/python.exe tests/test_small_qr.py`. Expected: vẫn ≥12/14, vì thứ tự cascade không đổi.
Chạy bộ test đầy đủ.

```bash
git add solution/qr/decoder.py solution/qr/preprocessor.py solution/qr/corrector.py solution/qr/improved_pipeline.py solution/qr/__init__.py solution/tests/qr_fixtures.py solution/tests/test_pipeline_api.py
git commit -m "fix(solution/qr): quad hiển thị lấy từ góc decoder hoặc minAreaRect của mask thay cho padded quad lệch"
```

---

### Task 3: `PassTracker` trong solution: copy, thêm `match()` và `Track.votes`

**Files:**
- Create: `solution/qr/tracker.py`
- Create: `solution/tests/test_tracker.py`

**Interfaces:**
- Produces:
  - `Observation(center: tuple[float, float], size: float, text: str | None = None)`, mutable dataclass
  - `Track`: các trường `track_id, first_frame, last_frame, center, size, velocity, observations, texts: Counter`; các property `text -> str | None`, `votes -> int`, `conflicting -> bool`
  - `PassTracker(max_gap=5, gate_px=400.0, gate_sizes=3.0)`; `match(frame_idx, observations) -> dict[int, Track]` (không thay đổi trạng thái); `update(frame_idx, observations) -> list[Track]`; `finish() -> list[Track]`

- [ ] **Step 1: Viết test (fail)**

`solution/tests/test_tracker.py`. Năm test đầu copy từ `offline/tests/test_tracker.py`, bốn test sau là test mới:

```python
"""PassTracker — gom detection qua các frame thành lượt QR. Không cần model/camera.

Chạy (từ solution/):  python -m unittest tests.test_tracker
"""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from qr.tracker import Observation, PassTracker  # noqa: E402


def _run(tracker, frames):
    done = []
    for idx, obs in frames:
        done += tracker.update(idx, obs)
    return done + tracker.finish()


class PassTrackerTests(unittest.TestCase):
    def test_one_qr_crossing_is_one_pass(self):
        frames = [(i, [Observation((100 + 45 * i, 500), 60, "A" if i in (5, 9) else None)])
                  for i in range(40)]
        passes = _run(PassTracker(), frames)
        self.assertEqual(len(passes), 1)
        self.assertEqual(passes[0].text, "A")
        self.assertEqual(passes[0].observations, 40)

    def test_two_labels_side_by_side_stay_separate(self):
        frames = [(i, [Observation((100 + 45 * i, 500), 60, "A"),
                       Observation((100 + 45 * i, 700), 60, "B")]) for i in range(20)]
        passes = sorted(_run(PassTracker(), frames), key=lambda t: t.track_id)
        self.assertEqual([p.text for p in passes], ["A", "B"])
        self.assertFalse(any(p.conflicting for p in passes))

    def test_gap_longer_than_max_gap_splits_passes(self):
        frames = [(i, [Observation((500, 500), 60)]) for i in range(5)]
        frames += [(i, [Observation((500, 500), 60)]) for i in range(20, 25)]
        self.assertEqual(len(_run(PassTracker(max_gap=5), frames)), 2)

    def test_short_dropout_is_bridged_by_velocity(self):
        frames = [(i, [Observation((100 + 45 * i, 500), 60)]) for i in range(10)]
        frames += [(i, []) for i in range(10, 13)]
        frames += [(i, [Observation((100 + 45 * i, 500), 60)]) for i in range(13, 20)]
        self.assertEqual(len(_run(PassTracker(max_gap=5), frames)), 1)

    def test_conflicting_reads_flagged_and_majority_wins(self):
        frames = [(i, [Observation((100 + 10 * i, 500), 60, t)]) for i, t in enumerate("AABA")]
        (track,) = _run(PassTracker(), frames)
        self.assertEqual(track.text, "A")
        self.assertTrue(track.conflicting)

    # ── mới trong solution ──

    def test_match_does_not_mutate_tracks(self):
        tracker = PassTracker()
        tracker.update(0, [Observation((100, 500), 60, "A")])
        matched = tracker.match(1, [Observation((130, 500), 60)])
        self.assertEqual(list(matched), [0])
        self.assertEqual(matched[0].observations, 1)
        self.assertEqual(matched[0].last_frame, 0)
        self.assertEqual(matched[0].center, (100, 500))

    def test_match_ignores_stale_tracks(self):
        tracker = PassTracker(max_gap=5)
        tracker.update(0, [Observation((100, 500), 60, "A")])
        self.assertEqual(tracker.match(10, [Observation((100, 500), 60)]), {})

    def test_match_pairs_same_as_update(self):
        tracker = PassTracker()
        tracker.update(0, [Observation((100, 200), 60, "A"), Observation((100, 600), 60, "B")])
        obs = [Observation((140, 600), 60), Observation((140, 200), 60)]
        matched = {i: t.track_id for i, t in tracker.match(1, obs).items()}
        tracker.update(1, obs)
        self.assertEqual(matched, {0: 1, 1: 0})
        self.assertEqual(sorted(t.observations for t in tracker.finish()), [2, 2])

    def test_votes_is_count_of_majority_text(self):
        tracker = PassTracker()
        for i, t in enumerate(["A", None, "A", "B"]):
            tracker.update(i, [Observation((100 + 10 * i, 500), 60, t)])
        (track,) = tracker.finish()
        self.assertEqual((track.text, track.votes), ("A", 2))
        self.assertEqual(PassTracker()._start(0, Observation((0, 0), 60)).votes, 0)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `../.venv/Scripts/python.exe -m unittest tests.test_tracker -v`
Expected: `ModuleNotFoundError: No module named 'qr.tracker'`.

- [ ] **Step 3: Tạo `solution/qr/tracker.py`**

```python
"""Gom detection qua các frame thành "lượt" — mỗi lượt là một QR đi qua khung hình một lần.

Copy từ offline/qr/tracker.py (không import chéo giữa hai app), thêm ``match()`` để hỏi trước
detection sẽ ghép vào track nào mà không đổi trạng thái — PassReader dùng để bỏ cascade cho QR
đã đọc chắc. Ghép tham lam theo khoảng cách từ vị trí dự đoán (tâm + vận tốc × số frame) tới
tâm detection mới. Lượt kết thúc khi mất dấu quá ``max_gap`` frame. Kết quả đọc của lượt là nội
dung decode xuất hiện nhiều nhất.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

import numpy as np


@dataclass
class Observation:
    center: tuple[float, float]
    size: float
    text: str | None = None


@dataclass
class Track:
    track_id: int
    first_frame: int
    last_frame: int
    center: tuple[float, float]
    size: float
    velocity: tuple[float, float] = (0.0, 0.0)   # px / frame
    observations: int = 1
    texts: Counter = field(default_factory=Counter)

    def predict(self, frame_idx: int) -> tuple[float, float]:
        dt = frame_idx - self.last_frame
        return (self.center[0] + self.velocity[0] * dt, self.center[1] + self.velocity[1] * dt)

    @property
    def text(self) -> str | None:
        """Nội dung đọc được nhiều nhất trong lượt (None nếu chưa frame nào decode được)."""
        return self.texts.most_common(1)[0][0] if self.texts else None

    @property
    def votes(self) -> int:
        """Số lần đọc ra nội dung ``text`` (0 nếu chưa đọc được)."""
        return self.texts.most_common(1)[0][1] if self.texts else 0

    @property
    def conflicting(self) -> bool:
        """Lượt có hơn một nội dung khác nhau — dấu hiệu đọc sai hoặc ghép nhầm hai QR."""
        return len(self.texts) > 1


class PassTracker:
    def __init__(self, max_gap: int = 5, gate_px: float = 400.0, gate_sizes: float = 3.0):
        """
        max_gap:    số frame (theo chỉ số frame gốc) được phép mất dấu trước khi đóng lượt.
        gate_px:    khoảng cách tối đa (px) từ vị trí dự đoán khi track chưa có vận tốc.
        gate_sizes: khi đã có vận tốc, cổng = gate_sizes × kích thước QR (dự đoán đã bù chuyển động).
        """
        self.max_gap = max_gap
        self.gate_px = gate_px
        self.gate_sizes = gate_sizes
        self._active: list[Track] = []
        self._next_id = 0

    def match(self, frame_idx: int, observations: list[Observation]) -> dict[int, Track]:
        """Observation thứ i sẽ ghép vào track nào nếu gọi ``update`` ngay — không đổi trạng thái."""
        live = [t for t in self._active if frame_idx - t.last_frame <= self.max_gap]
        return {oi: live[ti] for ti, oi in self._pairs(live, frame_idx, observations)}

    def update(self, frame_idx: int, observations: list[Observation]) -> list[Track]:
        """Ghép observation của frame ``frame_idx`` vào các track, trả về các lượt vừa kết thúc."""
        # Đóng track mất dấu quá lâu TRƯỚC khi ghép — tránh nối QR xuất hiện lại vào lượt cũ.
        finished = [t for t in self._active if frame_idx - t.last_frame > self.max_gap]
        self._active = [t for t in self._active if frame_idx - t.last_frame <= self.max_gap]
        pairs = self._pairs(self._active, frame_idx, observations)
        for ti, oi in pairs:
            self._extend(self._active[ti], frame_idx, observations[oi])
        used_o = {oi for _, oi in pairs}
        for oi, obs in enumerate(observations):
            if oi not in used_o:
                self._active.append(self._start(frame_idx, obs))
        return finished

    def finish(self) -> list[Track]:
        """Đóng mọi lượt còn mở (gọi khi hết video)."""
        finished, self._active = self._active, []
        return finished

    def _pairs(self, tracks: list[Track], frame_idx: int,
               observations: list[Observation]) -> list[tuple[int, int]]:
        """Ghép tham lam (chỉ số track, chỉ số observation) theo khoảng cách tăng dần trong cổng."""
        candidates = []
        for ti, track in enumerate(tracks):
            px, py = track.predict(frame_idx)
            moving = track.observations > 1
            gate = self.gate_sizes * max(track.size, 1.0) if moving else self.gate_px
            for oi, obs in enumerate(observations):
                d = float(np.hypot(obs.center[0] - px, obs.center[1] - py))
                if d <= gate:
                    candidates.append((d, ti, oi))
        used_t, used_o, pairs = set(), set(), []
        for _, ti, oi in sorted(candidates):
            if ti in used_t or oi in used_o:
                continue
            used_t.add(ti)
            used_o.add(oi)
            pairs.append((ti, oi))
        return pairs

    def _start(self, frame_idx: int, obs: Observation) -> Track:
        track = Track(self._next_id, frame_idx, frame_idx, obs.center, obs.size)
        self._next_id += 1
        if obs.text:
            track.texts[obs.text] += 1
        return track

    @staticmethod
    def _extend(track: Track, frame_idx: int, obs: Observation):
        dt = max(1, frame_idx - track.last_frame)
        vx = (obs.center[0] - track.center[0]) / dt
        vy = (obs.center[1] - track.center[1]) / dt
        if track.observations > 1:   # làm mượt vận tốc, tránh nhảy theo nhiễu detect
            vx = 0.5 * (vx + track.velocity[0])
            vy = 0.5 * (vy + track.velocity[1])
        track.velocity = (vx, vy)
        track.center = obs.center
        track.size = 0.7 * track.size + 0.3 * obs.size
        track.last_frame = frame_idx
        track.observations += 1
        if obs.text:
            track.texts[obs.text] += 1
```

- [ ] **Step 4: Chạy test, xác nhận pass**

Run: `../.venv/Scripts/python.exe -m unittest tests.test_tracker -v`
Expected: `Ran 9 tests … OK`.

- [ ] **Step 5: Bộ test đầy đủ rồi commit**

```bash
git add solution/qr/tracker.py solution/tests/test_tracker.py
git commit -m "feat(solution/qr): PassTracker gom detection theo lượt, thêm match() và votes"
```

---

### Task 4: `PassReader`: bỏ cascade cho QR đã đọc chắc, đo thời gian, tạo overlay

**Files:**
- Create: `solution/qr/pass_reader.py`
- Modify: `solution/qr/__init__.py`
- Create: `solution/tests/test_pass_reader.py`

**Interfaces:**
- Consumes: `ImprovePipeline.detect`, `.decode_detection -> Decoded | None`, `.warmup` (Task 2); `display_quad` (Task 2); `PassTracker`, `Observation`, `Track` (Task 3).
- Produces:
  - `Overlay(quad_xy: np.ndarray, ok: bool, velocity: tuple[float, float], seq: int, shape: tuple[int, int])`; `Overlay.at(seq, shape, max_age) -> np.ndarray | None`
  - `FrameResult(detections, texts, overlays, skipped, detect_ms, cascade_ms, finished=[])`; property `results -> list[str]`
  - `PassReader(pipeline, tracker=None, min_votes=2, recheck_every=5)`. Tracker mặc định là `PassTracker(max_gap=100)`, đơn vị là seq.
  - `PassReader.process(image_bgr, frame_idx) -> FrameResult`; `flush() -> list[Track]`; `warmup() -> None`
  - Logger `"solution.qr"`: mỗi lượt kết thúc ghi INFO `pass_finished id=… text=… votes=… observations=… conflicting=…`.

**Quy tắc bỏ cascade:** một detection được bỏ qua khi track ghép với nó có `votes >= min_votes`, **không** `conflicting`, và đã bỏ liên tiếp ít hơn `recheck_every` lần. Lần tiếp theo sau đó vẫn decode để kiểm tra lại, rồi bộ đếm về 0. Detection bị bỏ lấy `text` từ `track.text`, **không** cộng phiếu, và quad hiển thị lấy từ `display_quad(det)` (hình chữ nhật xoay nhỏ nhất của mask). Frame có `frame_idx` nhỏ hơn frame trước, hoặc kích thước ảnh khác frame trước, sẽ đóng hết lượt đang mở trước khi xử lý.

**Vận tốc của overlay** là `track.velocity` của lượt đã ghép (px/seq, tính trước khi cập nhật). QR mới xuất hiện có vận tốc `(0, 0)`.

- [ ] **Step 1: Viết test (fail)**

`solution/tests/test_pass_reader.py`:

```python
"""PassReader — detect, ghép lượt, bỏ cascade QR đã đọc chắc, overlay. Pipeline giả, không cần YOLO.

Chạy (từ solution/):  python -m unittest tests.test_pass_reader
"""
from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from qr.improved_pipeline import Decoded  # noqa: E402
from qr.pass_reader import Overlay, PassReader  # noqa: E402
from qr.tracker import PassTracker  # noqa: E402
from tests.qr_fixtures import detection_at  # noqa: E402

IMG = np.zeros((768, 2448, 3), np.uint8)
CORNERS = np.array([[1, 1], [9, 1], [9, 9], [1, 9]], np.float32)


class FakePipeline:
    """detect(): trả lần lượt từng phần tử ``frames``; decode_detection(): trả lần lượt ``answers``
    (str → Decoded với CORNERS, None → không đọc được; hết danh sách thì lặp phần tử cuối)."""

    def __init__(self, frames, answers):
        self.frames = list(frames)
        self.answers = list(answers)
        self.decode_calls = 0
        self.warmed = False

    def warmup(self):
        self.warmed = True

    def detect(self, image_bgr):
        return self.frames.pop(0)

    def decode_detection(self, image_bgr, det):
        self.decode_calls += 1
        text = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        return Decoded(text, CORNERS) if text else None


def moving(n, y=300, start=100, step=45):
    """n frame, mỗi frame một QR chạy ``step`` px/frame theo x."""
    return [[detection_at(start + step * i, y)] for i in range(n)]


class PassReaderTests(unittest.TestCase):
    def test_confirmed_track_skips_cascade_and_reuses_text(self):
        pipe = FakePipeline(moving(3), ["A"])
        reader = PassReader(pipe)
        results = [reader.process(IMG, i) for i in range(3)]
        self.assertEqual(pipe.decode_calls, 2)
        self.assertEqual((results[2].skipped, results[2].texts, results[2].results), (1, ["A"], ["A"]))

    def test_recheck_every_n_skips(self):
        pipe = FakePipeline(moving(8), ["A"])
        reader = PassReader(pipe, recheck_every=5)
        for i in range(8):
            reader.process(IMG, i)
        self.assertEqual(pipe.decode_calls, 3)   # frame 0, 1 đọc; 2–6 bỏ qua; 7 đọc kiểm tra

    def test_recheck_detects_changed_content(self):
        pipe = FakePipeline(moving(9), ["A", "A", "B"])
        reader = PassReader(pipe, recheck_every=5)
        for i in range(9):
            reader.process(IMG, i)
        self.assertEqual(pipe.decode_calls, 4)   # 0, 1, 7 (ra B → mâu thuẫn), 8 không còn bỏ qua
        (track,) = reader.flush()
        self.assertTrue(track.conflicting)

    def test_conflicting_reads_never_skip(self):
        pipe = FakePipeline(moving(5), ["A", "B", "A", "A", "A"])
        reader = PassReader(pipe)
        for i in range(5):
            reader.process(IMG, i)
        self.assertEqual(pipe.decode_calls, 5)

    def test_unreadable_qr_is_never_skipped(self):
        pipe = FakePipeline(moving(4), [None])
        reader = PassReader(pipe)
        for i in range(4):
            self.assertEqual(reader.process(IMG, i).results, [])
        self.assertEqual(pipe.decode_calls, 4)
        (track,) = reader.flush()
        self.assertIsNone(track.text)

    def test_new_qr_beside_confirmed_one_is_still_decoded(self):
        frames = moving(3) + [[detection_at(100 + 45 * 3, 300), detection_at(100, 600)]]
        pipe = FakePipeline(frames, ["A", "A", "B"])
        reader = PassReader(pipe)
        for i in range(3):
            reader.process(IMG, i)
        result = reader.process(IMG, 3)
        self.assertEqual(pipe.decode_calls, 3)
        self.assertEqual(result.texts, ["A", "B"])
        self.assertEqual(result.skipped, 1)

    def test_backwards_frame_index_closes_open_passes(self):
        pipe = FakePipeline([[detection_at(100, 300)]] * 3, ["A"])
        reader = PassReader(pipe)
        reader.process(IMG, 100)
        reader.process(IMG, 101)
        result = reader.process(IMG, 5)          # camera mở lại → seq bắt đầu lại
        self.assertEqual([t.text for t in result.finished], ["A"])
        self.assertEqual(result.skipped, 0)
        self.assertEqual(pipe.decode_calls, 3)

    def test_shape_change_closes_open_passes(self):
        pipe = FakePipeline([[detection_at(100, 300)]] * 3, ["A"])
        reader = PassReader(pipe)
        reader.process(IMG, 1)
        reader.process(IMG, 2)
        result = reader.process(np.zeros((2048, 2448, 3), np.uint8), 3)
        self.assertEqual(len(result.finished), 1)
        self.assertEqual(result.skipped, 0)

    def test_gap_finishes_pass_and_logs_it(self):
        pipe = FakePipeline([[detection_at(100, 300)], [detection_at(100, 300)], []], ["A"])
        reader = PassReader(pipe, PassTracker(max_gap=5))
        reader.process(IMG, 0)
        reader.process(IMG, 1)
        with self.assertLogs("solution.qr", "INFO") as logs:
            result = reader.process(IMG, 20)
        self.assertEqual([t.text for t in result.finished], ["A"])
        self.assertIn("pass_finished", logs.output[0])
        self.assertIn("text=A", logs.output[0])

    def test_flush_returns_open_passes_and_timings_are_reported(self):
        pipe = FakePipeline(moving(1), ["A"])
        reader = PassReader(pipe)
        result = reader.process(IMG, 0)
        self.assertGreaterEqual(result.detect_ms, 0.0)
        self.assertGreaterEqual(result.cascade_ms, 0.0)
        self.assertEqual([t.text for t in reader.flush()], ["A"])
        self.assertEqual(reader.flush(), [])

    def test_warmup_is_forwarded_to_pipeline(self):
        pipe = FakePipeline([], ["A"])
        PassReader(pipe).warmup()
        self.assertTrue(pipe.warmed)

    # ── overlay ──

    def test_overlay_uses_decoder_corners_when_read(self):
        pipe = FakePipeline(moving(1), ["A"])
        (ov,) = PassReader(pipe).process(IMG, 7).overlays
        np.testing.assert_array_equal(ov.quad_xy, CORNERS)
        self.assertEqual((ov.ok, ov.seq, ov.shape, ov.velocity), (True, 7, (768, 2448), (0.0, 0.0)))

    def test_overlay_of_unread_or_skipped_qr_uses_mask_rectangle(self):
        pipe = FakePipeline(moving(3), ["A", "A"])
        reader = PassReader(pipe)
        reader.process(IMG, 0)
        reader.process(IMG, 1)
        (ov,) = reader.process(IMG, 2).overlays         # bỏ cascade → không có góc decoder
        self.assertTrue(ov.ok)
        self.assertEqual(ov.quad_xy.shape, (4, 2))
        self.assertAlmostEqual(float(ov.quad_xy[:, 0].mean()), 100 + 45 * 2, delta=1.0)
        self.assertEqual(ov.velocity, (45.0, 0.0))

    def test_overlay_at_shifts_by_velocity_and_expires(self):
        ov = Overlay(CORNERS.copy(), True, (5.0, -1.0), seq=10, shape=(768, 2448))
        np.testing.assert_allclose(ov.at(14, (768, 2448), max_age=100), CORNERS + [20.0, -4.0])
        self.assertIsNone(ov.at(14, (2048, 2448), max_age=100))   # khác kích thước frame
        self.assertIsNone(ov.at(200, (768, 2448), max_age=100))   # quá cũ
        self.assertIsNone(ov.at(5, (768, 2448), max_age=100))     # seq lùi (camera mở lại)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `../.venv/Scripts/python.exe -m unittest tests.test_pass_reader -v`
Expected: `ModuleNotFoundError: No module named 'qr.pass_reader'`.

- [ ] **Step 3: Tạo `solution/qr/pass_reader.py`**

```python
"""PassReader: đọc QR theo lượt trên luồng frame liên tục (băng chuyền).

Mỗi frame: detect một lần → ghép detection vào lượt (PassTracker) → chỉ chạy cascade cho QR chưa
đọc chắc. Cascade (CPU) tốn 200–350 ms cho mỗi detection không đọc được — QR đã có ``min_votes``
lần đọc giống nhau thì dùng lại kết quả của lượt, cứ ``recheck_every`` lần bỏ qua lại đọc kiểm tra
một lần (phòng nhãn bị thay tại chỗ). Mỗi detection kèm một Overlay để UI vẽ quad: góc decoder nếu
đọc được, ngược lại hình chữ nhật xoay của mask; kèm vận tốc lượt để bù độ trễ khi vẽ lên frame mới.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

import numpy as np

from .corrector import display_quad
from .detector import Detection
from .tracker import Observation, PassTracker, Track

logger = logging.getLogger("solution.qr")


@dataclass
class Overlay:
    quad_xy: np.ndarray                  # (4, 2) tọa độ trong frame ``seq``
    ok: bool                             # có nội dung (đọc được hoặc lấy từ lượt đã đọc chắc)
    velocity: tuple[float, float]        # px / seq của lượt (0 nếu QR mới)
    seq: int
    shape: tuple[int, int]

    def at(self, seq: int, shape: tuple[int, int], max_age: int) -> np.ndarray | None:
        """Quad dịch theo vận tốc tới frame ``seq``; None nếu khác kích thước frame, seq lùi hoặc quá cũ."""
        age = seq - self.seq
        if shape != self.shape or age < 0 or age > max_age:
            return None
        return self.quad_xy + np.array(self.velocity, np.float32) * age


@dataclass
class FrameResult:
    detections: list[Detection]
    texts: list[str | None]          # song song detections: từ cascade, hoặc từ lượt đã đọc chắc
    overlays: list[Overlay]          # song song detections
    skipped: int                     # số detection bỏ cascade nhờ lượt đã đọc chắc
    detect_ms: float
    cascade_ms: float
    finished: list[Track] = field(default_factory=list)   # lượt vừa kết thúc

    @property
    def results(self) -> list[str]:
        return [t for t in self.texts if t]


def _observation(det: Detection) -> Observation:
    x1, y1, x2, y2 = (float(v) for v in det.bbox_xyxy)
    return Observation(((x1 + x2) / 2, (y1 + y2) / 2), max(x2 - x1, y2 - y1))


class PassReader:
    def __init__(self, pipeline, tracker: PassTracker | None = None,
                 min_votes: int = 2, recheck_every: int = 5):
        """
        pipeline:      có ``detect``, ``decode_detection`` và ``warmup`` (ImprovePipeline).
        tracker:       mặc định max_gap=100 theo seq camera (~2 s ở 50 fps) — frame được decode
                       cách nhau cỡ (thời gian decode × fps) seq.
        min_votes:     số lần đọc giống nhau để coi lượt là đọc chắc.
        recheck_every: số lần bỏ cascade liên tiếp trước khi đọc kiểm tra lại.
        """
        self._pipeline = pipeline
        self._tracker = tracker if tracker is not None else PassTracker(max_gap=100)
        self._min_votes = min_votes
        self._recheck_every = recheck_every
        self._skips: dict[int, int] = {}         # track_id → số lần bỏ cascade liên tiếp
        self._last_idx: int | None = None
        self._shape: tuple[int, int] | None = None

    def warmup(self):
        self._pipeline.warmup()

    def process(self, image_bgr: np.ndarray, frame_idx: int) -> FrameResult:
        finished: list[Track] = []
        shape = image_bgr.shape[:2]
        if self._last_idx is not None and (frame_idx < self._last_idx or shape != self._shape):
            finished += self._close(self._tracker.finish())   # camera mở lại / đổi ROI
        self._last_idx, self._shape = frame_idx, shape

        t0 = time.perf_counter()
        detections = self._pipeline.detect(image_bgr)
        t1 = time.perf_counter()
        observations = [_observation(d) for d in detections]
        matched = self._tracker.match(frame_idx, observations)
        texts: list[str | None] = []
        overlays: list[Overlay] = []
        skipped = 0
        for i, det in enumerate(detections):
            track = matched.get(i)
            velocity = track.velocity if track is not None else (0.0, 0.0)
            if track is not None and self._can_skip(track):
                self._skips[track.track_id] = self._skips.get(track.track_id, 0) + 1
                text, quad = track.text, display_quad(det)
                skipped += 1
            else:
                if track is not None:
                    self._skips[track.track_id] = 0
                hit = self._pipeline.decode_detection(image_bgr, det)
                text = hit.text if hit else None
                quad = display_quad(det, hit.corners if hit else None)
                observations[i].text = text
            texts.append(text)
            overlays.append(Overlay(quad, text is not None, velocity, frame_idx, shape))
        t2 = time.perf_counter()
        finished += self._close(self._tracker.update(frame_idx, observations))
        return FrameResult(detections, texts, overlays, skipped,
                           (t1 - t0) * 1000.0, (t2 - t1) * 1000.0, finished)

    def flush(self) -> list[Track]:
        """Đóng mọi lượt đang mở (dừng decode / đóng app)."""
        self._last_idx = self._shape = None
        return self._close(self._tracker.finish())

    def _can_skip(self, track: Track) -> bool:
        return (track.votes >= self._min_votes and not track.conflicting
                and self._skips.get(track.track_id, 0) < self._recheck_every)

    def _close(self, tracks: list[Track]) -> list[Track]:
        for t in tracks:
            self._skips.pop(t.track_id, None)
            logger.info("pass_finished id=%d text=%s votes=%d observations=%d conflicting=%s",
                        t.track_id, t.text, t.votes, t.observations, t.conflicting)
        return tracks
```

- [ ] **Step 4: Export trong `solution/qr/__init__.py`**

```python
from .detector import Detection, QRDetector
from .improved_pipeline import Decoded, ImprovePipeline
from .pass_reader import FrameResult, Overlay, PassReader

__all__ = ["Detection", "QRDetector", "Decoded", "ImprovePipeline",
           "FrameResult", "Overlay", "PassReader"]
```

- [ ] **Step 5: Chạy test, xác nhận pass**

Run: `../.venv/Scripts/python.exe -m unittest tests.test_pass_reader -v`
Expected: `Ran 14 tests … OK`.
Nếu `test_recheck_every_n_skips` ra 2 hoặc 4 lần decode, kiểm tra `_can_skip`: phép so sánh phải là `< recheck_every`, và chỉ reset bộ đếm khi thực sự decode.

- [ ] **Step 6: Bộ test đầy đủ rồi commit**

```bash
git add solution/qr/pass_reader.py solution/qr/__init__.py solution/tests/test_pass_reader.py
git commit -m "feat(solution/qr): PassReader bỏ cascade QR đã đọc chắc, đo detect/cascade, overlay bù vận tốc"
```

---

### Task 5: Nối vào `DecodeWorker` và UI: warm-up, nhãn, vẽ quad bù độ trễ

**Files:**
- Modify: `solution/ui/main_window.py`
- Modify: `solution/tests/test_camera_diagnostics.py:154-155`, `solution/tests/test_recording_ui.py:23-24` (stub `qr`)
- Modify: `solution/tests/test_conveyor_mode.py` (`LatestQrLabelTests`)
- Create: `solution/tests/test_decode_worker.py`, `solution/tests/test_display.py`

**Interfaces:**
- Consumes: `PassReader`, `FrameResult`, `Overlay` (Task 4); `ImprovePipeline.device` (Task 2).
- Produces:
  - `DecodeWorker(pipeline)`: các signal `done(list, list)` = `(results, overlays)`, `stats(dict)` với key `detect_ms`, `cascade_ms`, `skipped`, `passes(list)`, `failed(str)`; `submit(frame, seq) -> bool`. Warm-up GPU chạy ở đầu thread worker.
  - `QUAD_MAX_AGE_SEQ = 100`; `draw_overlays(frame_bgr, overlays, seq, max_age=QUAD_MAX_AGE_SEQ, thickness=2) -> np.ndarray`
  - `MainWindow.on_decode_stats(stats)`, `MainWindow.on_passes_done(tracks)`, `MainWindow.lbl_passes`, `MainWindow._overlays` (thay cho `_last_detections`)
  - Định dạng nhãn: `lbl_stat` = `"Decode: {n} lần · {GPU|CPU} · detect {d:.0f} ms · cascade {c:.0f} ms"`, thêm `" · bỏ qua {k}"` khi k > 0. `lbl_passes` = `"Lượt QR: {đọc}/{tổng} đọc được · mâu thuẫn {m}"`.

- [ ] **Step 1: Cập nhật stub `qr` trong hai test UI có sẵn**

`solution/tests/test_camera_diagnostics.py`: thay dòng `qr.ImprovePipeline = type("UnusedPipeline", (), {})` bằng:

```python
qr.ImprovePipeline = type("UnusedPipeline", (), {"device": "cpu"})
qr.PassReader = type("UnusedReader", (), {"__init__": lambda self, *a, **k: None,
                                           "warmup": lambda self: None,
                                           "flush": lambda self: []})
```

`solution/tests/test_recording_ui.py`, ngay sau dòng `qr.ImprovePipeline = Mock()`:

```python
        qr.PassReader = Mock()
        qr.PassReader.return_value.flush.return_value = []
```

- [ ] **Step 2: Viết test worker (fail)**

`solution/tests/test_decode_worker.py`:

```python
"""DecodeWorker dùng PassReader: signal kết quả/thời gian/lượt, warm-up, flush khi dừng.

Chạy (từ solution/):  python -m unittest tests.test_decode_worker
"""
import importlib.util
import os
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch

import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# qr (torch) PHẢI import trước PyQt5 — xem solution/CLAUDE.md
from qr.improved_pipeline import Decoded  # noqa: E402
from qr.pass_reader import PassReader  # noqa: E402
from tests.qr_fixtures import detection_at  # noqa: E402

_manager = types.ModuleType("camera.camera_manager")
_manager.CameraManager = Mock()
_qr = types.ModuleType("qr")
_qr.ImprovePipeline = Mock()
_qr.PassReader = PassReader
_spec = importlib.util.spec_from_file_location("ui._decode_worker_test", ROOT / "ui" / "main_window.py")
window_module = importlib.util.module_from_spec(_spec)
with patch.dict(sys.modules, {"camera.camera_manager": _manager, "qr": _qr}):
    _spec.loader.exec_module(window_module)

FRAME = np.zeros((768, 2448, 3), np.uint8)


class FakePipeline:
    def __init__(self, fail=False):
        self.fail = fail
        self.warmups = 0

    def warmup(self):
        self.warmups += 1

    def detect(self, image_bgr):
        if self.fail:
            raise RuntimeError("detect hỏng")
        return [detection_at(100, 300)]

    def decode_detection(self, image_bgr, det):
        return Decoded("A", det.quad_xy)


class DecodeWorkerTests(unittest.TestCase):
    def make(self, pipeline):
        worker = window_module.DecodeWorker(pipeline)
        worker.stop()                    # dừng thread nền — test gọi _process trực tiếp
        self.done, self.stats, self.passes, self.failed = [], [], [], []
        worker.done.connect(lambda r, o: self.done.append((r, o)))
        worker.stats.connect(self.stats.append)
        worker.passes.connect(self.passes.append)
        worker.failed.connect(self.failed.append)
        return worker

    def test_thread_warms_up_pipeline_first(self):
        pipe = FakePipeline()
        self.make(pipe)
        self.assertEqual(pipe.warmups, 1)

    def test_process_emits_results_overlays_and_stage_stats(self):
        worker = self.make(FakePipeline())
        worker._process(FRAME, 1)
        (results, overlays), = self.done
        self.assertEqual(results, ["A"])
        self.assertEqual([(o.ok, o.seq) for o in overlays], [(True, 1)])
        self.assertEqual(set(self.stats[0]), {"detect_ms", "cascade_ms", "skipped"})

    def test_failure_emits_failed_and_no_result(self):
        worker = self.make(FakePipeline(fail=True))
        worker._process(FRAME, 1)
        self.assertEqual(self.failed, ["detect hỏng"])
        self.assertEqual(self.done, [])

    def test_stop_flushes_open_passes_when_thread_finished(self):
        worker = self.make(FakePipeline())
        worker._process(FRAME, 1)
        worker._process(FRAME, 2)
        worker.stop()
        (tracks,) = self.passes
        self.assertEqual([t.text for t in tracks], ["A"])

    def test_stop_skips_flush_while_thread_alive(self):
        worker = self.make(FakePipeline())
        worker._process(FRAME, 1)
        worker._thread = Mock()
        worker._thread.is_alive.return_value = True
        worker.stop()
        self.assertEqual(self.passes, [])

    def test_submit_keeps_seq_with_frame(self):
        worker = self.make(FakePipeline())
        self.assertTrue(worker.submit(FRAME, 7))
        self.assertEqual(worker._pending[1], 7)
        self.assertFalse(worker.submit(FRAME, 8))     # đang có frame chờ → bỏ


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Viết test vẽ overlay (fail)**

`solution/tests/test_display.py` (Task 6 sẽ bổ sung thêm test vào file này):

```python
"""Vẽ quad lên frame hiển thị: bù vận tốc, bỏ quad cũ/khác kích thước; chuyển frame → QImage.

Chạy (từ solution/):  python -m unittest tests.test_display
"""
from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from qr.pass_reader import Overlay  # noqa: E402  (torch trước PyQt5)
from tests import test_camera_diagnostics as fake  # noqa: E402  (stub mvsdk/qr + import ui)

draw_overlays = fake.window_module.draw_overlays

SQUARE = np.array([[50, 50], [90, 50], [90, 90], [50, 90]], np.float32)
GREEN, RED = (0, 255, 0), (0, 0, 255)


class DrawOverlayTests(unittest.TestCase):
    def setUp(self):
        self.frame = np.zeros((200, 300, 3), np.uint8)

    def test_quad_is_shifted_by_velocity_to_current_seq(self):
        ov = Overlay(SQUARE, True, (5.0, 0.0), seq=10, shape=(200, 300))
        vis = draw_overlays(self.frame, [ov], seq=14)
        self.assertEqual(tuple(vis[70, 70]), GREEN)       # cạnh trái mới: 50 + 5 × 4
        self.assertEqual(tuple(vis[70, 50]), (0, 0, 0))   # cạnh trái cũ không còn vẽ
        self.assertEqual(tuple(self.frame[70, 70]), (0, 0, 0))   # không vẽ đè frame gốc

    def test_unread_qr_is_red(self):
        vis = draw_overlays(self.frame, [Overlay(SQUARE, False, (0.0, 0.0), 3, (200, 300))], seq=3)
        self.assertEqual(tuple(vis[70, 50]), RED)

    def test_overlay_from_other_shape_is_not_drawn(self):
        ov = Overlay(SQUARE, True, (0.0, 0.0), seq=3, shape=(2048, 2448))
        self.assertIs(draw_overlays(self.frame, [ov], seq=3), self.frame)

    def test_stale_overlay_is_not_drawn(self):
        ov = Overlay(SQUARE, True, (0.0, 0.0), seq=3, shape=(200, 300))
        self.assertIs(draw_overlays(self.frame, [ov], seq=3 + 101, max_age=100), self.frame)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 4: Thêm test nhãn UI (fail)**

Trong `solution/tests/test_conveyor_mode.py`, thêm `import types` vào đầu file (và `import numpy as np` nếu chưa có), rồi thêm vào class `LatestQrLabelTests`:

```python
    def test_stats_label_shows_device_and_stage_timings(self):
        self.window.on_decode_done(["A"], [])
        self.window.on_decode_stats({"detect_ms": 61.4, "cascade_ms": 32.0, "skipped": 1})
        self.assertEqual(self.window.lbl_stat.text(),
                         "Decode: 1 lần · CPU · detect 61 ms · cascade 32 ms · bỏ qua 1")
        self.window.on_decode_stats({"detect_ms": 70.0, "cascade_ms": 5.0, "skipped": 0})
        self.assertEqual(self.window.lbl_stat.text(), "Decode: 1 lần · CPU · detect 70 ms · cascade 5 ms")

    def test_pass_counter_counts_read_and_conflicting(self):
        self.assertEqual(self.window.lbl_passes.text(), "Lượt QR: 0/0 đọc được · mâu thuẫn 0")
        T = types.SimpleNamespace
        self.window.on_passes_done([T(text="A", conflicting=False), T(text=None, conflicting=False),
                                    T(text="B", conflicting=True)])
        self.assertEqual(self.window.lbl_passes.text(), "Lượt QR: 2/3 đọc được · mâu thuẫn 1")

    def test_display_tick_submits_frame_with_seq(self):
        frame = np.zeros((48, 64, 3), np.uint8)
        self.window.cbx_decode.setChecked(True)
        self.window.spin_n.setValue(1)
        with unittest.mock.patch.object(self.window.mgr, "latest_frame", return_value=(frame, 10)), \
                unittest.mock.patch.object(self.window.worker, "submit", return_value=True) as submit:
            self.window.on_display_tick()
        submit.assert_called_once_with(frame, 10)
```

Chuỗi "CPU" đến từ stub `UnusedPipeline.device = "cpu"` (Step 1).

- [ ] **Step 5: Chạy test, xác nhận fail**

Run: `../.venv/Scripts/python.exe -m unittest tests.test_decode_worker tests.test_display tests.test_conveyor_mode -v`
Expected: lỗi `AttributeError` với `stats`/`_process`/`draw_overlays`/`on_decode_stats`/`lbl_passes`.

- [ ] **Step 6: Sửa `solution/ui/main_window.py`: import, `draw_overlays`, `DecodeWorker`**

Đổi dòng import `from qr import ImprovePipeline` thành `from qr import ImprovePipeline, PassReader`.
Trong docstring đầu file, đổi `- Thêm panel Kết quả QR: decode mỗi N frame trên thread riêng,` thành `- Thêm panel Kết quả QR: decode mỗi N frame trên thread riêng qua PassReader (theo lượt, GPU nếu có),`.

Đặt hàm và hằng dưới đây ngay trước `# ── Decode worker`:

```python
QUAD_MAX_AGE_SEQ = 100   # quad cũ hơn ~2 s (50 fps) thì thôi vẽ — tránh khung "ma" khi QR đã đi qua


def draw_overlays(frame_bgr: np.ndarray, overlays, seq: int,
                  max_age: int = QUAD_MAX_AGE_SEQ, thickness: int = 2) -> np.ndarray:
    """Vẽ quad lên BẢN SAO frame (trả nguyên frame nếu không có gì để vẽ).

    Kết quả decode đến từ frame cũ hơn frame đang hiển thị (decode mất hàng trăm ms trong khi băng
    chạy ~700 px/s) → dịch quad theo vận tốc lượt tới ``seq``; bỏ quad của frame khác kích thước
    (đổi ROI) hoặc quá cũ. Xanh = đã có nội dung, đỏ = chưa đọc được.
    """
    shape = frame_bgr.shape[:2]
    quads = [(o.at(seq, shape, max_age), o.ok) for o in overlays]
    quads = [(q, ok) for q, ok in quads if q is not None]
    if not quads:
        return frame_bgr
    vis = frame_bgr.copy()
    for quad, ok in quads:
        pts = np.round(quad).astype(np.int32).reshape((-1, 1, 2))
        cv2.polylines(vis, [pts], isClosed=True, color=(0, 255, 0) if ok else (0, 0, 255),
                      thickness=thickness)
    return vis
```

Thay toàn bộ class `DecodeWorker`:

```python
class DecodeWorker(QObject):
    """Thread riêng gọi PassReader.process(). submit() fail khi đang bận."""

    done = pyqtSignal(list, list)   # (results, overlays)
    stats = pyqtSignal(dict)        # detect_ms, cascade_ms, skipped
    passes = pyqtSignal(list)       # list[Track] — lượt QR vừa kết thúc
    failed = pyqtSignal(str)

    def __init__(self, pipeline: ImprovePipeline, parent=None):
        super().__init__(parent)
        self._reader = PassReader(pipeline)
        self._lock = threading.Lock()
        self._pending: tuple[np.ndarray, int] | None = None
        self._busy = False
        self._stop = False
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def submit(self, frame: np.ndarray, seq: int) -> bool:
        with self._lock:
            if self._busy or self._pending is not None:
                return False   # đang bận → bỏ qua frame này
            self._pending = (frame, seq)
            return True

    @property
    def busy(self) -> bool:
        with self._lock:
            return self._busy or self._pending is not None

    def stop(self):
        self._stop = True
        self._thread.join(timeout=5)
        if self._thread.is_alive():
            return              # còn đang warm-up/decode dở → không đụng tracker từ thread khác
        finished = self._reader.flush()
        if finished:
            self.passes.emit(finished)

    def _loop(self):
        try:
            self._reader.warmup()   # lần detect đầu trên GPU mất vài giây — làm ở đây, không chặn UI
        except Exception as e:
            self.failed.emit("Warm-up lỗi: {}".format(e))
        while not self._stop:
            with self._lock:
                job, self._pending = self._pending, None
                self._busy = job is not None
            if job is None:
                threading.Event().wait(0.02)
                continue
            try:
                self._process(*job)
            finally:
                with self._lock:
                    self._busy = False

    def _process(self, frame: np.ndarray, seq: int):
        try:
            r = self._reader.process(frame, seq)
        except Exception as e:  # decode lỗi → bỏ frame này, chạy tiếp
            self.failed.emit(str(e))
            return
        self.done.emit(r.results, r.overlays)
        self.stats.emit({"detect_ms": r.detect_ms, "cascade_ms": r.cascade_ms,
                         "skipped": r.skipped})
        if r.finished:
            self.passes.emit(r.finished)
```

- [ ] **Step 7: Sửa `MainWindow`**

1. Trong `__init__`, sau `self.worker.failed.connect(self.on_decode_failed)`:
   ```python
           self.worker.stats.connect(self.on_decode_stats)
           self.worker.passes.connect(self.on_passes_done)
   ```
2. Trong khối khởi tạo thành viên, đổi `self._last_detections = []` thành `self._overlays = []`, rồi thêm ngay sau `self.decode_count = 0`:
   ```python
           self._device_label = "GPU" if str(self.pipeline.device).startswith("cuda") else "CPU"
           self._passes_total = 0
           self._passes_read = 0
           self._passes_conflict = 0
   ```
3. Tìm mọi chỗ còn dùng `_last_detections` (hiện ở các dòng khoảng 553, 686, 689, 724) và đổi sang `_overlays`. Dòng reset khoảng 553 thành `self._overlays = []`.
4. Trong `_setup_qr_panel`, thay đoạn `row2` bằng:
   ```python
           row2 = QHBoxLayout()
           self.lbl_latest = QLabel("QR mới nhất: —", self.qr_group)
           self.lbl_latest.setStyleSheet("font-weight: bold;")
           row2.addWidget(self.lbl_latest, 1)
           row.addLayout(row2)

           row3 = QHBoxLayout()
           self.lbl_stat = QLabel("Decode: 0 lần", self.qr_group)
           self.lbl_passes = QLabel("Lượt QR: 0/0 đọc được · mâu thuẫn 0", self.qr_group)
           row3.addWidget(self.lbl_stat)
           row3.addStretch(1)
           row3.addWidget(self.lbl_passes)
           row.addLayout(row3)
   ```
5. Trong `on_display_tick`: đổi `if self.worker.submit(frame):` thành `if self.worker.submit(frame, seq):`. Sau đó thay đoạn từ `vis = frame` tới **trước** dòng `rgb = cv2.cvtColor(vis, cv2.COLOR_BGR2RGB)` bằng:
   ```python
           label_w, label_h = self.ui.label_image.width(), self.ui.label_image.height()
           vis = frame
           if self.cbx_quad.isChecked() and self._overlays:
               # nét dày theo tỷ lệ thu nhỏ để còn thấy sau khi resize về khung hiển thị
               thickness = max(2, 2 * frame.shape[1] // max(1, label_w))
               vis = draw_overlays(frame, self._overlays, seq, thickness=thickness)
   ```
   (`label_h` sẽ được dùng ở Task 6.)
6. `on_decode_done(self, results, detections)`: đổi tên tham số thành `overlays`, và đổi `self._last_detections = detections` thành `self._overlays = overlays`. Phần còn lại giữ nguyên.
7. Thêm hai slot ngay sau `on_decode_done`:
   ```python
       def on_decode_stats(self, stats):
           skipped = " · bỏ qua {}".format(stats["skipped"]) if stats["skipped"] else ""
           self.lbl_stat.setText("Decode: {} lần · {} · detect {:.0f} ms · cascade {:.0f} ms{}".format(
               self.decode_count, self._device_label, stats["detect_ms"], stats["cascade_ms"], skipped))

       def on_passes_done(self, tracks):
           """Đếm lượt QR đi qua (một QR chạy qua khung = một lượt) — read rate thật trên băng."""
           self._passes_total += len(tracks)
           self._passes_read += sum(1 for t in tracks if t.text)
           self._passes_conflict += sum(1 for t in tracks if t.conflicting)
           self.lbl_passes.setText("Lượt QR: {}/{} đọc được · mâu thuẫn {}".format(
               self._passes_read, self._passes_total, self._passes_conflict))
   ```

Màu quad giờ đi theo từng overlay (`ok`) thay vì `_latest_qr_hits`. Giữ nguyên `_latest_qr_hits` vì nhãn "QR mới nhất" và test hiện có vẫn dùng nó.

- [ ] **Step 8: Chạy test, xác nhận pass**

Run: `../.venv/Scripts/python.exe -m unittest tests.test_decode_worker tests.test_display tests.test_conveyor_mode tests.test_recording_ui tests.test_camera_diagnostics -v`
Expected: OK. `test_decode_worker` có 6 test, `test_display` có 4 test.

- [ ] **Step 9: Kiểm tra trên app thật**

Run (từ `solution/`): `../.venv/Scripts/python.exe main.py`. Mở camera, áp dụng chế độ băng chuyền có dải, bật decode và "Vẽ quad", đưa QR qua.
Expected:
- Nhãn hiện **GPU**, và detect vài chục đến khoảng 150 ms (CPU là 460–770 ms).
- Quad **xanh ôm khít QR** khi đọc được, và vẫn bám QR khi QR đang di chuyển. Quad đỏ là hình chữ nhật, không thành hình diều.
- Quad biến mất khoảng 2 s sau khi QR rời khung, và không còn quad cũ sau khi bấm áp dụng dải.
- `lbl_passes` tăng sau mỗi QR đi qua; `logs/camera.log` có dòng `qr_detector device=cuda:0` và `pass_finished`.

Nếu không có camera: chạy `bench_decode.py` (Task 7) thay thế, và ghi rõ là chưa kiểm tra trên app thật.

- [ ] **Step 10: Bộ test đầy đủ rồi commit**

```bash
git add solution/ui/main_window.py solution/tests/test_decode_worker.py solution/tests/test_display.py solution/tests/test_conveyor_mode.py solution/tests/test_recording_ui.py solution/tests/test_camera_diagnostics.py
git commit -m "feat(solution/ui): decode theo lượt qua PassReader, warm-up GPU, quad bù độ trễ, nhãn thiết bị/ms/lượt"
```

---

### Task 6: Hiển thị: thu nhỏ bằng OpenCV trước khi đổi màu

Hiện `on_display_tick` chạy ở 30 Hz trên GUI thread: `cvtColor` ảnh 5 MP, rồi `QImage.copy()`, rồi `QPixmap.scaled(SmoothTransformation)`. Phần cascade và tiền xử lý vẫn chạy trên CPU, nên GUI thread không được chiếm CPU vô ích.

**Files:**
- Modify: `solution/ui/main_window.py` (thêm `frame_to_qimage`; cuối `on_display_tick`)
- Modify: `solution/tests/test_display.py`

**Interfaces:**
- Produces: `frame_to_qimage(frame_bgr, max_w, max_h) -> QImage`. Thu nhỏ giữ tỷ lệ cho vừa khung, không phóng to; khi `max_w <= 0` hoặc `max_h <= 0` thì giữ nguyên kích thước.

- [ ] **Step 1: Viết test (fail)**

Thêm vào `solution/tests/test_display.py`. Import đặt cạnh các import hiện có, `frame_to_qimage = …` đặt dưới dòng `draw_overlays = …`, class đặt trước `if __name__`:

```python
from PyQt5.QtGui import QColor  # noqa: E402

frame_to_qimage = fake.window_module.frame_to_qimage


class FrameToQImageTests(unittest.TestCase):
    def test_large_frame_fits_target_keeping_aspect(self):
        img = frame_to_qimage(np.zeros((2048, 2448, 3), np.uint8), 800, 600)
        self.assertLessEqual(img.width(), 800)
        self.assertLessEqual(img.height(), 600)
        self.assertAlmostEqual(img.width() / img.height(), 2448 / 2048, delta=0.01)

    def test_small_frame_is_not_upscaled(self):
        img = frame_to_qimage(np.zeros((100, 200, 3), np.uint8), 800, 600)
        self.assertEqual((img.width(), img.height()), (200, 100))

    def test_zero_target_size_keeps_original_size(self):
        img = frame_to_qimage(np.zeros((100, 200, 3), np.uint8), 0, 0)
        self.assertEqual((img.width(), img.height()), (200, 100))

    def test_bgr_converted_to_rgb(self):
        frame = np.zeros((2048, 2448, 3), np.uint8)
        frame[..., 0] = 255                      # BGR xanh dương
        color = QColor(frame_to_qimage(frame, 400, 300).pixel(10, 10))
        self.assertEqual((color.red(), color.green(), color.blue()), (0, 0, 255))
```

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `../.venv/Scripts/python.exe -m unittest tests.test_display -v`
Expected: `AttributeError: module … has no attribute 'frame_to_qimage'`.

- [ ] **Step 3: Thêm hàm vào `solution/ui/main_window.py`**

Đặt ngay trước `QUAD_MAX_AGE_SEQ`:

```python
def frame_to_qimage(frame_bgr: np.ndarray, max_w: int, max_h: int) -> QImage:
    """Thu nhỏ bằng OpenCV (INTER_AREA) về khung hiển thị TRƯỚC khi đổi màu — GUI thread không
    phải xử lý ảnh 5MP ở 30 Hz (tranh CPU với cascade). Không phóng to; khung 0 → giữ nguyên."""
    h, w = frame_bgr.shape[:2]
    if max_w > 0 and max_h > 0:
        scale = min(max_w / w, max_h / h)
        if scale < 1.0:
            frame_bgr = cv2.resize(frame_bgr, (max(1, int(w * scale)), max(1, int(h * scale))),
                                   interpolation=cv2.INTER_AREA)
    rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    h, w = rgb.shape[:2]
    return QImage(rgb.data, w, h, rgb.strides[0], QImage.Format_RGB888).copy()
```

- [ ] **Step 4: Dùng hàm trong `on_display_tick`**

Thay toàn bộ đoạn từ `rgb = cv2.cvtColor(vis, cv2.COLOR_BGR2RGB)` đến hết method bằng:

```python
        self.ui.label_image.setPixmap(QPixmap.fromImage(frame_to_qimage(vis, label_w, label_h)))
```

- [ ] **Step 5: Chạy test, xác nhận pass**

Run: `../.venv/Scripts/python.exe -m unittest tests.test_display tests.test_conveyor_mode -v`
Expected: OK. `test_display` có 8 test.

- [ ] **Step 6: Bộ test đầy đủ, kiểm tra trên app, rồi commit**

Nếu có camera: ảnh không méo tỷ lệ, quad vẫn nhìn rõ, "Capture fps" không giảm.

```bash
git add solution/ui/main_window.py solution/tests/test_display.py
git commit -m "perf(solution/ui): thu nhỏ frame bằng OpenCV trước khi hiển thị, giảm tải GUI thread"
```

---

### Task 7: Bench CPU/GPU và ghi kết quả

**Files:**
- Create: `solution/tests/bench_decode.py`
- Modify: `solution/DE_XUAT_KHAC_PHUC.md` (mục 3, thêm "Kết quả đo")
- Modify: `solution/CLAUDE.md`

**Interfaces:**
- Consumes: `ImprovePipeline(imgsz=, device=, half=)`, `.device`, `.warmup` (Task 1–2); `PassReader`, `PassTracker` (Task 3–4).

- [ ] **Step 1: Viết script**

`solution/tests/bench_decode.py`:

```python
"""Đo tốc độ đọc QR theo từng bước (detect / cascade) và đếm lượt — ảnh mẫu hoặc video quay từ app.

Chạy (từ solution/):
  python tests/bench_decode.py                              # ../images/*.bmp, GPU nếu có
  python tests/bench_decode.py --device cpu                 # so sánh với CPU
  python tests/bench_decode.py --band 1024 768              # cắt dải như chế độ băng chuyền
  python tests/bench_decode.py --half                       # thử FP16 (chỉ GPU)
  python tests/bench_decode.py --video recordings/<phiên>/video.avi --every 5
Warm-up model chạy trước, không tính vào thống kê.
"""

from __future__ import annotations

import argparse
import glob
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from qr import ImprovePipeline, PassReader  # noqa: E402
from qr.tracker import PassTracker  # noqa: E402


def _frames(args):
    if args.video:
        cap = cv2.VideoCapture(args.video)
        idx = 0
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if idx % args.every == 0:
                yield idx, frame
            idx += 1
        cap.release()
    else:
        for i, path in enumerate(sorted(glob.glob(os.path.join(ROOT, "..", "images", "*.bmp")))):
            yield i * 1000, cv2.imread(path)     # cách nhau > max_gap → mỗi ảnh là lượt riêng


def _pct(values, q):
    return float(np.percentile(values, q)) if values else 0.0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--video", help="file video (AVI quay từ app)")
    ap.add_argument("--every", type=int, default=1, help="chỉ xử lý mỗi N frame của video")
    ap.add_argument("--band", type=int, nargs=2, metavar=("Y", "H"), help="cắt dải hàng [Y, Y+H)")
    ap.add_argument("--imgsz", type=int, default=1280)
    ap.add_argument("--device", default="auto", help="auto / cpu / cuda:0")
    ap.add_argument("--half", action="store_true", help="FP16 (chỉ có tác dụng trên GPU)")
    ap.add_argument("--max-frames", type=int, default=0, help="0 = không giới hạn")
    args = ap.parse_args()

    pipeline = ImprovePipeline(imgsz=args.imgsz, device=args.device, half=args.half)
    pipeline.warmup((args.band[1], 2448) if args.band else (2048, 2448))
    reader = PassReader(pipeline, PassTracker(max_gap=max(100, 3 * args.every)))
    rows, passes = [], []
    for idx, frame in _frames(args):
        if frame is None:
            continue
        if args.band:
            y, h = args.band
            frame = np.ascontiguousarray(frame[y:y + h])
        t = time.perf_counter()
        r = reader.process(frame, idx)
        rows.append((r.detect_ms, r.cascade_ms, (time.perf_counter() - t) * 1000.0,
                     len(r.detections), len(r.results), r.skipped))
        passes += r.finished
        if args.max_frames and len(rows) >= args.max_frames:
            break
    passes += reader.flush()
    if not rows:
        sys.exit("Không có frame nào (kiểm tra --video hoặc thư mục ../images).")

    print(f"device={pipeline.device} half={args.half} imgsz={args.imgsz} band={args.band}")
    for name, col in (("detect", 0), ("cascade", 1), ("tổng", 2)):
        vals = [row[col] for row in rows]
        print(f"{name:8s} mean={np.mean(vals):7.0f} ms  p50={_pct(vals, 50):7.0f}  p95={_pct(vals, 95):7.0f}")
    print(f"frame={len(rows)}  frame đọc được={sum(1 for row in rows if row[4])}  "
          f"detection={sum(row[3] for row in rows)}  bỏ cascade={sum(row[5] for row in rows)}")
    print(f"lượt={len(passes)}  đọc được={sum(1 for p in passes if p.text)}  "
          f"mâu thuẫn={sum(1 for p in passes if p.conflicting)}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Đo CPU và GPU, toàn khung và dải**

Run (từ `solution/`), từng lệnh một:
```bash
../.venv/Scripts/python.exe tests/bench_decode.py --device cpu
```
```bash
../.venv/Scripts/python.exe tests/bench_decode.py
```
```bash
../.venv/Scripts/python.exe tests/bench_decode.py --band 1024 768
```
```bash
../.venv/Scripts/python.exe tests/bench_decode.py --band 1024 768 --half
```
Expected:
- CPU toàn khung: tổng mean khoảng 1100 ms, frame đọc được ≥12/14 (khớp số đo cũ, sai số ±15%).
- GPU: dòng đầu in `device=cuda:0`. Frame đọc được **bằng** CPU (±1). Detect mean **≤ 1/3** của CPU.
- GPU ở dải: tổng mean **≤ 390 ms** (mục tiêu cho quang học 0,25 mm/px).
- `--half`: chỉ giữ FP16 nếu frame đọc được và số detection **giống hệt** FP32 *và* detect nhanh hơn ≥20%. Nếu đạt, đổi mặc định `half=True` trong `ImprovePipeline` thành một commit riêng kèm số đo; nếu không đạt, giữ `False`.

Nếu GPU ở dải vượt 390 ms: dừng lại, ghi số đo, báo lại kèm phân tích phần nào tốn nhất (detect hay cascade). Không hạ `imgsz`.

- [ ] **Step 3: Chạy trên video thật (nếu có)**

Run: `../.venv/Scripts/python.exe tests/bench_decode.py --video recordings/<phiên>/video.avi --every 10 --max-frames 300`
Expected: `bỏ cascade` > 0 khi QR nằm trong khung qua nhiều frame; `mâu thuẫn` = 0. Hai phiên quay ngày 20/10 là cảnh tĩnh; nếu chưa có video băng chạy thì ghi rõ "chưa có video băng chạy" (mục 4 của đề xuất sẽ quay bổ sung).

- [ ] **Step 4: Ghi kết quả vào `solution/DE_XUAT_KHAC_PHUC.md`**

Cuối mục 3 (trước `---` của mục 4), thêm khối dưới đây và thay `…` bằng số đo thật:

```markdown
### Kết quả đo sau khi sửa (bench_decode.py, GTX 1650)

| Cấu hình | Thiết bị | detect mean | cascade mean | tổng mean / p95 | frame đọc được |
|---|---|---|---|---|---|
| Toàn khung 2448×2048 | CPU | … ms | … ms | … / … ms | …/14 |
| Toàn khung 2448×2048 | GPU | … ms | … ms | … / … ms | …/14 |
| Dải 2448×768 (y=1024) | GPU | … ms | … ms | … / … ms | …/14 |
| Dải, FP16 | GPU | … ms | … ms | … / … ms | …/14 |
| Video … (every 10) | GPU | … ms | … ms | … / … ms | … (bỏ cascade …) |

FP16: giữ / không giữ vì … . Ở 30 cm/s: khoảng … lần thử/lượt với FOV hiện tại, khoảng … với 0,25 mm/px (mục tiêu ≥5).
Quad hiển thị: lấy từ góc decoder hoặc minAreaRect của mask, bù vận tốc lượt; quad dùng cho warp chưa đổi.
```

- [ ] **Step 5: Cập nhật `solution/CLAUDE.md`**

Trong khối kiến trúc, sau dòng `improved_pipeline.py   → ImprovePipeline`, thêm:

```
  tracker.py             → PassTracker: gom detection qua frame thành lượt (copy từ offline/, thêm match())
  pass_reader.py         → PassReader: detect → ghép lượt → bỏ cascade QR đã đọc chắc (≥2 phiếu, kiểm tra lại mỗi 5 lần) → ms + Overlay
```

Thay câu **Luồng:** bằng:

```
**Luồng:** capture thread → copy frame sở hữu độc lập, RGB/mono chuyển thành BGR 3 kênh → `latest_frame` (frame cũ bị drop) → mỗi N frame `DecodeWorker.submit(frame, seq)` (bận thì bỏ; thread worker warm-up GPU trước) → `PassReader.process` → signal `done` (results + Overlay), `stats` (ms detect/cascade), `passes` (đếm lượt, log `pass_finished`). Hiển thị: `draw_overlays` dịch quad theo vận tốc lượt tới seq hiện tại, bỏ quad cũ >100 seq hoặc khác kích thước frame; `frame_to_qimage` resize OpenCV trước khi đổi màu.
```

Thêm vào mục **ImprovePipeline**:

```
Detect chạy GPU CUDA nếu có (`device="auto"`, torch `+cu126`; không có CUDA → CPU + cảnh báo log), FP16 tắt mặc định. Mỗi bước cascade trả `Decoded(text, corners)` — 4 góc QR quy về ảnh gốc (trừ viền đệm `UPSCALE_PAD_PER_SCALE × scale`, chia scale, cộng gốc ROI; bước warp đi ngược homography). Quad hiển thị = `display_quad()`: góc decoder, nếu chưa đọc được thì `minAreaRect(polygon_xy)`; KHÔNG dùng `padded_quad_xy` để vẽ (mask YOLO thô ~8×8 điểm cho QR 60px → quad méo tới 45°). `padded_quad_xy` vẫn dùng cho warp.
```

Thêm vào dòng "Test pipeline offline không cần camera": `` và `python tests/bench_decode.py [--device cpu] [--band Y H] [--half] [--video …]` để đo tốc độ``.

- [ ] **Step 6: Bộ test đầy đủ rồi commit**

```bash
git add solution/tests/bench_decode.py solution/DE_XUAT_KHAC_PHUC.md solution/CLAUDE.md
git commit -m "test(solution): bench_decode CPU/GPU theo lượt; ghi kết quả đo và kiến trúc mới"
```

---

## Ngoài phạm vi (có lý do)

- **Đổi quad dùng cho warp** (bước 2 của cascade) sang minAreaRect hoặc góc khác: có thể tăng tỷ lệ đọc nhưng cũng có thể làm giảm. Cần so sánh bằng `bench_decode.py` trên video băng thật trước khi làm, nên để thành plan riêng.
- **OpenVINO / ONNX Runtime**: đã có GPU NVIDIA với CUDA, OpenVINO lại tối ưu cho phần cứng Intel. Chỉ xem lại nếu phải chạy trên máy không có GPU NVIDIA.
- **TensorRT**: có thể nhanh hơn CUDA PyTorch, nhưng phải export theo đúng kích thước đầu vào, phải phân phối thêm engine, và GTX 1650 chỉ có 4 GB. Chỉ cân nhắc khi Task 7 không đạt mục tiêu.
- **WeChat CNN trên GPU**: OpenCV cài từ pip không có CUDA; muốn có phải tự build OpenCV. Nhờ bỏ cascade cho QR đã đọc chắc (Task 4), phần này đã giảm tải.
- **Cắt dải bằng phần mềm khi chạy toàn khung**, **zxing toàn khung thay YOLO**, **nhiều process decode**: lý do như bản plan trước. Chế độ dải sensor đã cho cùng lợi ích; zxing chỉ đọc được 1/14 ảnh ở 2,8 px/ô; GPU chỉ có một nên chạy thêm process không tăng tổng tốc độ.
- **Chỉ chạy YOLO khi có QR mới vào khung** (theo dấu QR cũ bằng cascade quanh vị trí dự đoán): để dành nếu Task 7 vẫn chưa đủ nhanh.
