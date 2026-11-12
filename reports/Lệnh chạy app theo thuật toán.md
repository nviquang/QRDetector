# Lệnh chạy app Basler theo từng thuật toán

Mỗi worktree là một bản `main_basler.py` dùng một thuật toán đọc nền cho lượt mà pipeline hiện tại không đọc được. Tên thuật toán hiện trên thanh tiêu đề cửa sổ.

Lệnh dùng trong PowerShell. Mỗi lần chỉ chạy **một** app, và đóng pylon Viewer cùng mọi app Basler khác trước khi chạy, vì camera chỉ mở được bởi một chương trình.

## Lệnh chạy

| Thuật toán | Ghi chú |
|---|---|
| Mốc | Pipeline cũ, không đọc nền. Từ commit `f5e6123`, `main_basler.py` ở thư mục gốc đã chạy B rồi C; muốn chạy mốc phải đặt `$env:QR_FALLBACK="off"` trước |
| A `soft_reader` | Bộ đọc mềm |
| B `grid_sr` | Tái tạo trên lưới |
| C `preproc_sweep` | Giải ô rồi đọc bằng zxing/WeChat |
| D `engines` | Thêm engine mã nguồn mở; cần Java |
| **B rồi C** | Bản ghép, điểm kiểm tra cao nhất (98,6%); nên thử đầu tiên |

**Mốc**

```bash
cd C:\Users\nviquang\Documents\AISTDR\QRDetector; $env:QR_FALLBACK="off"; .venv\Scripts\python.exe main_basler.py
```

**A `soft_reader`**

```bash
cd C:\Users\nviquang\Documents\AISTDR\QRDetector\.claude\worktrees\agent-a07a16b0b3c5f42bb; ..\..\..\.venv\Scripts\python.exe main_basler.py
```

**B `grid_sr`**

```bash
cd C:\Users\nviquang\Documents\AISTDR\QRDetector\.claude\worktrees\agent-a41f91eb3f8121858; ..\..\..\.venv\Scripts\python.exe main_basler.py
```

**C `preproc_sweep`**

```bash
cd C:\Users\nviquang\Documents\AISTDR\QRDetector\.claude\worktrees\agent-ad7cec03199a2e199; ..\..\..\.venv\Scripts\python.exe main_basler.py
```

**D `engines`**

```bash
cd C:\Users\nviquang\Documents\AISTDR\QRDetector\.claude\worktrees\agent-a2ef276e6ae02d137; ..\..\..\.venv\Scripts\python.exe main_basler.py
```

**B rồi C (bản ghép)**

```bash
cd C:\Users\nviquang\Documents\AISTDR\QRDetector\.claude\worktrees\combo-b-c; ..\..\..\.venv\Scripts\python.exe main_basler.py
```

## Tắt đọc nền để đối chiếu

Chạy trong cùng cửa sổ PowerShell, trước lệnh chạy app:

```bash
$env:QR_FALLBACK="off"
```

Bật lại:

```bash
Remove-Item Env:QR_FALLBACK
```

## Xem lượt do thuật toán mới đọc

Chạy trong thư mục worktree tương ứng, sau khi đã thử app:

```bash
Get-ChildItem logs | Sort-Object LastWriteTime | Select-Object -Last 1 | Select-String "pass_fallback"
```

- `pass_fallback_done ... text=<mã>`: thuật toán mới đọc được lượt đó.
- `pass_fallback_done ... text=None`: không đọc được.
- `pass_fallback_abandoned`: bấm Dừng khi lượt đó chưa giải xong.
- `pass_fallback_skipped`: hàng đợi đầy hoặc bộ giải lỗi.

## Cách so sánh

1. Thả cùng một bộ tem, cùng thứ tự cho mỗi lần chạy, rồi ghi tỉ lệ đọc trên màn hình.
2. Bấm **Dừng** rồi chờ vài giây trước khi đóng app. Lúc dừng, app chỉ chờ kết quả nền tối đa 5 giây.

## Lưu ý

- Lượt do thuật toán mới đọc được sẽ báo mã trễ khoảng 0,2–25 giây.
- Hàng đợi tối đa 8 lượt chờ; lượt thứ 9 trở đi tính là không đọc được.
- Mỗi worktree có bản sao riêng của `config/basler_settings.json`. Sửa cấu hình ở một app không làm các app khác đổi theo.
- Chỉ `main_basler.py` được bật đọc nền. `main_demo.py` và `main_dual.py` trong các worktree vẫn chạy như cũ.
- Mã trong các worktree chưa commit. Không dọn các thư mục `.claude/worktrees/agent-*` nếu còn cần chạy.
