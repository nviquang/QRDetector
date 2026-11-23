# Bỏ gõ mã vào ô đang chọn, gửi mã qua API báo cáo tấm — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Gỡ toàn bộ chức năng "Gõ mã vào ô đang chọn" và thay đường gửi server cũ (`PUT {upload_base_url}/{mã}`) bằng `POST /api/v1/production/camera/product-item-reports` ký `X-App-Token` + `X-Api-Key`, cấu hình lấy từ `.env`.

**Architecture:** Giữ nguyên `ScanUploader` (hàng đợi, chống trùng 30 s, thử lại, bật/tắt) nhưng đổi hàm gửi: `send(text)` thay cho `send(url)`. Hàm gửi mới là `ReportClient` (urllib, không thêm thư viện) tính chữ ký mỗi lần gọi và ánh xạ mã HTTP theo bảng mục 5.2 của tài liệu. Cấu hình `BASE_URL`, `APP_TOKEN_SECRET`, `API_KEY` đọc từ `.env` ở gốc repo bằng parser nhỏ trong `demo_ui/api_config.py`; thiếu thì app vẫn chạy, ô **Gửi mã lên server** bị vô hiệu hóa.

**Tech Stack:** Python 3 stdlib (`hmac`, `hashlib`, `json`, `urllib.request`), PyQt5, unittest.

**Spec:** `camera-integration.md` (gốc repo) + yêu cầu người dùng 23/11/2026.

## Global Constraints

- Endpoint: `POST {BASE_URL}/api/v1/production/camera/product-item-reports`, header `Content-Type: application/json`, `X-App-Token`, `X-Api-Key`, body `{"productItemCode": "<mã QR nguyên văn>"}`.
- `X-App-Token = hex(HMAC_SHA256(APP_TOKEN_SECRET, f"{ts}\nPOST\n/api/v1/production/camera/product-item-reports"))`, `ts = now_ms // 60000 * 60000`, hex chữ thường, **tính lại mỗi lần gửi kể cả lần thử lại**.
- Vector kiểm tra: secret `test-secret`, ts `1763631180000` → `5b0b785e50ed64bdcfa810bf3b57a9622097f6a14412a9318ec93f20b5233a2b` (đã chạy thử, khớp).
- Tên biến trong `.env` là `BASE_URL`, `APP_TOKEN_SECRET`, `API_KEY` (tài liệu gọi secret là `APP_SECRET`; dùng tên trong `.env`). Biến môi trường của tiến trình ghi đè `.env`.
- Không bao giờ ghi `APP_TOKEN_SECRET`, `API_KEY` hay `X-App-Token` vào log, status bar, tooltip hay file cấu hình JSON.
- Timeout 10 s. Thử lại chỉ khi mất mạng/timeout/`5xx`/body không phải JSON; `400/401/403/404` không thử lại. `200` là thành công, `warning` khác rỗng vẫn là thành công.
- Không thêm dependency (`python-dotenv`, `requests`) vào `requirements.txt`.
- `ReplaySettings.upload_enabled` vẫn mặc định `False`.
- `main.py` (app test camera) trước giờ chỉ có gõ phím, không có uploader: sau thay đổi nó không xuất mã ra đâu cả; KHÔNG thêm API vào `main.py` trong plan này.
- File cấu hình cũ còn `keyboard_output_enabled`/`upload_base_url` phải nạp được (trường lạ bị bỏ qua, mất ở lần lưu sau — hành vi sẵn có của `AppSettings.from_dict`).

## Review Focus

1. **Đồng hồ máy lệch** → server trả `403 invalid X-App-Token`; người dùng phải thấy thông báo có chữ "kiểm tra giờ máy", không thử lại vô ích. (Task 2, `test_403_message_hints_clock`)
2. **`.env` thiếu hoặc thiếu một biến** → app khởi động bình thường, ô gửi bị vô hiệu hóa, tooltip nêu tên biến thiếu, không crash. (Task 3, `test_missing_env_disables_upload_switch`)
3. **Proxy trả HTML (502/504) hoặc body rỗng** → coi là lỗi tạm thời, thử lại, thread gửi không chết. (Task 2, `test_non_json_5xx_is_transient`)
4. **Mã chứa `#`, khoảng trắng, Unicode** → gửi nguyên văn trong JSON, không URL-encode như đường cũ. (Task 2, `test_body_sends_code_verbatim`)
5. **`BASE_URL` có `/` ở cuối** → URL không có `//api`, chữ ký vẫn ký đúng đường dẫn `/api/...`. (Task 2, `test_trailing_slash_in_base_url`)

---

### Task 1: Gỡ chức năng gõ mã vào ô đang chọn

**Files:**
- Delete: `ui/keyboard_output.py`, `tools/try_keyboard_output.py`, `tests/test_keyboard_output.py`, `tests/test_keyboard_apps.py`
- Modify: `ui/main_window.py` (tham số `keyboard_typer`, signal `keyboard_status`, `cbx_keyboard` ~dòng 310-316, `on_reads_done`/`on_keyboard_status` ~861-868, `stop()` ở closeEvent ~588)
- Modify: `demo_ui/main_window.py` (import `KeyboardTyper`, tham số/doc `keyboard_typer`, `keyboard_status`, `cbx_keyboard` ~486-491, nạp/lưu ~311-326, `on_keyboard_toggled`, `stop` ~642, `on_reads_done` ~776-778, `on_keyboard_status` ~802)
- Modify: `demo_ui/dual_window.py` (tương tự: ~195, 198-213, 260-265, 318-320, 328-329, 343-345, 372-373, 584-585, 652-654, 671-672)
- Modify: `demo_ui/workspace.py` (bỏ `lbl_keyboard` ~244-249 và `set_keyboard_status` ~344-348)
- Modify: `demo_ui/app_settings.py` (bỏ trường + validator `keyboard_output_enabled`)
- Modify: `main.py`, `main_demo.py`, `main_basler.py`, `main_dual.py`, `main_replay.py` (bỏ import và đối số `keyboard_typer=KeyboardTyper()`)
- Modify tests: `tests/test_demo_conveyor.py` (xóa `KeyboardSwitchTests`, import `FakeKeyboard`/`KeyboardTyper`), `tests/test_replay_manager.py:200` (bỏ dòng `keyboard_output_enabled`)

**Interfaces:**
- Produces: `ui.MainWindow()` không tham số; `demo_ui.MainWindow(settings_path=None, uploader=None, camera=..., settings_cls=..., tray=False)`; `DualWindow(settings_path=None, uploader=None, cameras=None, pipeline=None)`. Signal `DecodeWorker.reads` của `ui/` **giữ lại** (demo dùng).

- [ ] **Step 1: Chuyển test còn giá trị.** Chép `BaseWorkerReadsTests` từ `tests/test_keyboard_apps.py` sang cuối `tests/test_demo_conveyor.py` (đổi docstring: "DecodeWorker của ui/ phát `reads` cho lượt vừa đọc chắc"), rồi xóa 4 file ở mục Delete.
- [ ] **Step 2: Thêm test cấu hình cũ.** Trong `tests/test_demo_conveyor.py`:

```python
class LegacySettingsTests(unittest.TestCase):
    def test_old_keyboard_and_url_fields_are_ignored(self):
        s = AppSettings.from_dict({"keyboard_output_enabled": True,
                                   "upload_base_url": "https://old.example", "decode_every_n": 7})
        self.assertEqual(s.decode_every_n, 7)
        self.assertNotIn("keyboard_output_enabled", asdict(s))
```

- [ ] **Step 3: Chạy, xác nhận fail.** `python -m unittest tests.test_demo_conveyor -v` → `LegacySettingsTests` FAIL (`keyboard_output_enabled` còn trong `asdict`).
- [ ] **Step 4: Gỡ code** theo danh sách Modify. `ui/main_window.py` không còn nối `worker.reads` tới slot nào (xóa `on_reads_done` nếu chỉ dùng cho gõ phím). Không để lại `self.keyboard_typer = None`.
- [ ] **Step 5: Kiểm tra không còn tham chiếu.** `git grep -n -i "keyboard" -- "*.py"` → không còn kết quả (trừ chữ trong comment không liên quan, nếu có thì xóa).
- [ ] **Step 6: Chạy cả bộ test.** `python -m unittest discover -s tests -t . -p "test_*.py"` → PASS (bỏ qua test chậm/thiếu dữ liệu vốn đã skip trước đó).
- [ ] **Step 7: Commit** `refactor: bỏ chức năng gõ mã vào ô đang chọn`.

---

### Task 2: `ApiConfig` + `ReportClient` + `ScanUploader` gửi theo mã

**Files:**
- Create: `demo_ui/api_config.py`, `tests/test_api_config.py`
- Modify: `demo_ui/scan_uploader.py` (bỏ `DEFAULT_BASE_URL`, `build_url`, `http_put`, tham số `base_url`)
- Modify: `tests/test_scan_uploader.py` (bỏ `BuildUrlTests`; fake `send` nhận `text`; thêm `ReportClientTests`)
- Create: `.env.example` (3 dòng `BASE_URL=`, `APP_TOKEN_SECRET=`, `API_KEY=`, không giá trị)

**Interfaces:**
- Produces (`demo_ui/api_config.py`):
  - `ENV_PATH: Path = ROOT / ".env"`, `REQUIRED_KEYS = ("BASE_URL", "APP_TOKEN_SECRET", "API_KEY")`
  - `@dataclass(frozen=True) class ApiConfig: base_url: str; app_secret: str; api_key: str` — `__repr__` che secret/key (`field(repr=False)`).
  - `read_env_file(path: Path) -> dict[str, str]`: đọc `utf-8-sig`; bỏ dòng trống/`#`; bỏ tiền tố `export `; tách ở `=` đầu tiên; strip khoảng trắng và một cặp nháy `'`/`"` bao ngoài; file không tồn tại → `{}`.
  - `load_api_config(path: Path = ENV_PATH, environ: Mapping[str, str] = os.environ) -> tuple[ApiConfig | None, list[str]]`: giá trị = `environ` nếu khác rỗng, không thì file; trả `(None, [tên thiếu])` nếu thiếu/rỗng; `BASE_URL` không bắt đầu `http://`/`https://` tính là thiếu.
- Produces (`demo_ui/scan_uploader.py`):
  - `REPORT_PATH = "/api/v1/production/camera/product-item-reports"`
  - `make_app_token(secret: str, method: str, path: str, now_ms: int) -> str`
  - `TransientError(message)`, `PermanentError(message)` — `str(exc)` là thông báo hiển thị được.
  - `class ReportClient: __init__(self, config: ApiConfig, timeout: float = 10.0, now_ms=lambda: int(time.time() * 1000), opener=urllib.request.urlopen)`; `__call__(self, code: str) -> str` trả `warning` ("" nếu không có).
  - `UploadStatus` thêm trường `last_error: str | None = None` (cuối dataclass).
  - `ScanUploader(send, maxsize=500, dedup_ttl=30.0, max_retries=3, on_status=None, monotonic=..., sleep=..., autostart=True)` — `send(text) -> str | None`; không còn mặc định cho `send`.

Ánh xạ trong `ReportClient.__call__` (đọc `error` từ body JSON nếu có, không thì `"HTTP {code}"`):

| Tình huống | Kết quả |
|---|---|
| 200, body JSON | trả `body.get("warning") or ""` |
| 400/401/404 | `PermanentError(error)` |
| 403 | `PermanentError(error + " — kiểm tra giờ máy")` nếu `error == "invalid X-App-Token"`, không thì `PermanentError(error)` |
| 408, 429, ≥500, `URLError`/`OSError`/timeout, body 200 không phải JSON | `TransientError(...)` |
| mã 4xx khác | `PermanentError(error)` |

`ScanUploader._process`: khi thành công log `upload_ok text=%s warning=%s`; khi lỗi lưu `str(exc)` vào `last_error` của `UploadStatus`. Không log header.

- [ ] **Step 1: Viết test `tests/test_api_config.py`:**
  - `test_reads_keys_quotes_comments_bom`: file `﻿# c\nBASE_URL="https://x.test/"\nexport API_KEY=k\nAPP_TOKEN_SECRET='s'\n` → `ApiConfig("https://x.test/", "s", "k")`, missing `[]`.
  - `test_environment_overrides_file`: `environ={"API_KEY": "env"}` → `api_key == "env"`.
  - `test_missing_file_reports_all_keys`: → `(None, ["BASE_URL", "APP_TOKEN_SECRET", "API_KEY"])`.
  - `test_empty_value_and_bad_url_count_as_missing`: `BASE_URL=ftp://x`, `API_KEY=` → missing chứa `"BASE_URL"`, `"API_KEY"`.
  - `test_repr_hides_secrets`: `"s3cret" not in repr(cfg)` và `"k3y" not in repr(cfg)`.
- [ ] **Step 2: Viết test `ReportClientTests` trong `tests/test_scan_uploader.py`** với `opener` giả ghi lại `Request` và trả response giả (hoặc ném `urllib.error.HTTPError(url, code, msg, hdrs, io.BytesIO(body))`), `now_ms=lambda: 1763631234567`:
  - `test_signature_vector`: `make_app_token("test-secret", "POST", REPORT_PATH, 1763631180000) == "5b0b785e50ed64bdcfa810bf3b57a9622097f6a14412a9318ec93f20b5233a2b"`.
  - `test_request_shape`: method `POST`, URL `https://x.test/api/v1/production/camera/product-item-reports`, header `X-api-key == "k"`, `X-app-token == make_app_token("s", "POST", REPORT_PATH, 1763631180000)`, `Content-type == "application/json"`, timeout 10.
  - `test_trailing_slash_in_base_url`: base `https://x.test/` → URL không chứa `//api`.
  - `test_body_sends_code_verbatim`: code `"12 #34é"` → `json.loads(req.data) == {"productItemCode": "12 #34é"}`.
  - `test_returns_warning`: body `{"status":"REPORTED","warning":"Tấm đã được quét trước đó, số lần quét đã tăng"}` → trả đúng chuỗi đó.
  - `test_404_is_permanent_with_server_message`: body `{"error":"Không tìm thấy tấm"}` → `PermanentError`, `str(exc) == "Không tìm thấy tấm"`.
  - `test_403_message_hints_clock`: body `{"error":"invalid X-App-Token"}` → `PermanentError`, `"kiểm tra giờ máy" in str(exc)`.
  - `test_500_and_network_are_transient`: 500 → `TransientError`; opener ném `urllib.error.URLError("down")` → `TransientError`.
  - `test_non_json_5xx_is_transient`: 502 với body `b"<html>"` → `TransientError`, `str(exc) == "HTTP 502"`.
  - `test_token_recomputed_each_call`: `now_ms` trả 60000 rồi 120000 → hai request có `X-App-Token` khác nhau.
- [ ] **Step 3: Sửa test `UploaderTests` hiện có:** `make()` không truyền `base_url`; kỳ vọng `sent == ["A"]` thay cho URL; thêm `test_failure_status_carries_server_error`: `send` ném `PermanentError("Không tìm thấy tấm")` → `UploadStatus` cuối có `last_ok is False`, `last_error == "Không tìm thấy tấm"`.
- [ ] **Step 4: Chạy, xác nhận fail.** `python -m unittest tests.test_api_config tests.test_scan_uploader -v` → FAIL (`ModuleNotFoundError: demo_ui.api_config`, `ImportError: REPORT_PATH`).
- [ ] **Step 5: Cài đặt** `demo_ui/api_config.py` và sửa `demo_ui/scan_uploader.py` theo Interfaces + bảng ánh xạ; tạo `.env.example`. Cập nhật docstring đầu module `scan_uploader.py` mô tả endpoint mới.
- [ ] **Step 6: Chạy, xác nhận pass.** Lệnh như Step 4 → PASS.
- [ ] **Step 7: Commit** `feat(upload): gửi mã qua API báo cáo tấm có chữ ký X-App-Token`.

---

### Task 3: Nối uploader mới vào các app, bỏ `upload_base_url`

**Files:**
- Modify: `demo_ui/app_settings.py` (bỏ import `DEFAULT_BASE_URL`, trường + validator `upload_base_url`)
- Modify: `demo_ui/main_window.py` (~154-157 tạo uploader; ~286-287 nạp; `on_upload_status` ~796)
- Modify: `demo_ui/dual_window.py` (~208-210; ~316-317; `on_upload_status` ~674)
- Modify: `tests/test_demo_conveyor.py` (`UploadSwitchTests`), `tests/test_dual_app.py` (nếu tạo uploader với `base_url`)

**Interfaces:**
- Consumes: `load_api_config() -> tuple[ApiConfig | None, list[str]]`, `ReportClient(config)`, `ScanUploader(send=..., on_status=...)`, `UploadStatus.last_error` (Task 2).
- Produces: thuộc tính `MainWindow.api_missing: list[str]` / `DualWindow.api_missing: list[str]` (rỗng khi đủ cấu hình hoặc khi test truyền `uploader`).

Hành vi:
- `uploader is None and settings_path` → gọi `load_api_config()`; có config thì `ScanUploader(send=ReportClient(cfg), on_status=self.upload_status.emit)`; không có thì `self.uploader = None`, `self.api_missing = missing`.
- `api_missing` khác rỗng → `cbx_upload.setEnabled(False)`, giữ nguyên trạng thái tích đã lưu (giống ô GPU), tooltip `"Chưa cấu hình API trong .env: thiếu " + ", ".join(missing)`, status bar (dual: `lbl_common`) hiện cùng câu một lần lúc khởi động. `_save_settings` vẫn lưu giá trị `upload_enabled` đang hiển thị.
- `on_upload_status`: khi `last_ok is False` → `"Gửi mã {text} lỗi: {last_error} ({pending} mã chờ)"`.
- `settings_path=None` (test) → không gọi `load_api_config`, `api_missing == []` (giữ nguyên quy ước test không đọc file).

- [ ] **Step 1: Sửa test `UploadSwitchTests`:** `ScanUploader(send=self.sent.append, autostart=False)`; kỳ vọng `self.sent == ["A"]` / `["B"]`. Thêm:
  - `test_missing_env_disables_upload_switch`: patch `window_module.load_api_config` trả `(None, ["API_KEY"])`, patch `window_module.ScanUploader`; tạo `MainWindow(settings_path=path)` → `ScanUploader` không được gọi, `window.uploader is None`, `not window.cbx_upload.isEnabled()`, `"API_KEY" in window.cbx_upload.toolTip()`, `window.on_reads_done([SimpleNamespace(text="A")])` không ném lỗi.
  - `test_upload_error_shows_server_message`: `window.on_upload_status(UploadStatus(1, 0, 1, "A", False, "Không tìm thấy tấm"))` → `"Không tìm thấy tấm" in window.ui.status_bar.text()`.
  - Sửa `test_saved_off_can_be_turned_on_without_restart`: patch thêm `load_api_config` trả `(ApiConfig("https://x.test", "s", "k"), [])`.
- [ ] **Step 2: Thêm test tương ứng cho dual** trong `tests/test_dual_app.py`: `test_missing_env_disables_upload_switch` (cùng kỳ vọng, nhãn là `lbl_common`).
- [ ] **Step 3: Chạy, xác nhận fail.** `python -m unittest tests.test_demo_conveyor tests.test_dual_app -v` → FAIL (`AttributeError: load_api_config`).
- [ ] **Step 4: Cài đặt** theo mục Hành vi.
- [ ] **Step 5: Chạy cả bộ test.** `python -m unittest discover -s tests -t . -p "test_*.py"` → PASS.
- [ ] **Step 6: Thử thật một lần** (cần `.env` thật, mạng tới server): tạo `tools/try_report_api.py <mã>` in `status code`, `warning` hoặc `error` qua `ReportClient(load_api_config()[0])`; chạy với một mã có thật → `200` + `warning`. Ghi kết quả vào mô tả commit, không in secret.
- [ ] **Step 7: Commit** `feat(demo): app demo/Basler/phát lại/hai camera gửi mã qua API báo cáo tấm`.

---

### Task 4: Cập nhật tài liệu

**Files:**
- Modify: `CLAUDE.md` (mục **Gửi QR lên server**: endpoint, `.env`, ánh xạ lỗi, `ReportClient`; xóa đoạn **Gõ mã vào ô đang chọn**; bỏ nhắc "gõ mã" ở mục khay hệ thống; sơ đồ `demo_ui/` thêm `api_config.py`)
- Modify: `README.md` (dòng 239 bỏ "và gõ mã"; dòng 244 bổ sung: cần `.env` có `BASE_URL`, `APP_TOKEN_SECRET`, `API_KEY` — chép từ `.env.example`; thiếu thì ô bị khóa; thông báo `403 … kiểm tra giờ máy` nghĩa là bật đồng bộ giờ)
- Move: `camera-integration.md` → `docs/camera-integration.md` (đang untracked; commit kèm)

- [ ] **Step 1: Sửa tài liệu** theo danh sách trên.
- [ ] **Step 2: Kiểm tra.** `git grep -n -i "gõ mã\|keyboard_output\|upload_base_url\|qr-scan-gp1"` → không còn kết quả ngoài `docs/superpowers/plans/`.
- [ ] **Step 3: Commit** `docs: gửi mã qua API báo cáo tấm, bỏ gõ mã vào ô đang chọn`.
