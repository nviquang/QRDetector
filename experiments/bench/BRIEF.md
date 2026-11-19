# Brief chung cho agent thử nghiệm thuật toán đọc QR

> **Cấu hình cũ (trước 18/11/2026).** Tài liệu này lập theo thông số đã thay thế (tem 25/36 mm, camera cao 1 m, 0,673 mm/px, băng 100 mm/s, nội dung 12#12 hoặc version 1, một camera, máy CPU). Ràng buộc hiện hành: mục "Bài toán và ràng buộc" trong `README.md`. Kỹ thuật và tài liệu tham khảo vẫn dùng được, nhưng số px/ô và mọi đề xuất đổi tem, nội dung, version/mức sửa lỗi, camera, ống kính, line-scan, đầu đọc thương mại hay vị trí dán tem không còn áp dụng.

Bài toán: đọc QR nhỏ trên băng chuyền, chỉ CPU. Mục tiêu giai đoạn này là **tăng khả năng đọc đúng**, không phải tốc độ.

Dữ liệu thật: Basler 8 MP, ống 4 mm, cao 1 m, tem 36 mm, QR in lẫn version 1–3 và mức L/M/Q/H (version 1 khoảng 2,57 px/ô, version 2 khoảng 2,16, version 3 khoảng 1,86), nội dung 12 số `#` 12 số hoặc 12 số, băng khoảng 100 mm/s, exposure khoảng 3 ms, 25 fps. Ảnh khá tối (nền trắng tem chỉ 50–80/255). Ba đoạn: `gan` (băng dưới camera), `xa` (lệch ra mép), `cheo` (băng chéo).

Đọc thêm khi cần: `reports/Phương pháp đọc QR nhỏ mờ.md`, `reports/Độ khả thi thuật toán đọc QR.md`, `reports/Plan nghiên cứu thuật toán đọc QR.md`. Các đường dẫn ở đây tính từ checkout chính `C:\Users\nviquang\Documents\AISTDR\QRDetector`, gọi là MAIN.

## Bộ chấm điểm (đã dựng sẵn, chỉ dùng, không sửa)

- `MAIN\experiments\bench\api.py`: phương pháp là class có `read_pass(obs: list[Obs], ctx: Ctx) -> str | None`.
  `Obs` gồm crop xám quanh tem, bbox, quad, polygon, conf, origin, frame, t. `Ctx` gồm vận tốc (px/frame), fps, exposure, độ dài vệt mờ ước tính. Không giữ trạng thái giữa hai lượt. Không biết đáp án và không biết điều kiện thử nào đang chạy.
- `MAIN\experiments\bench\readers\baseline.py`: mốc, là `PassDecoder` của sản phẩm, xem cách dựng `Detection`/`Track` và gọi code trong `qr/`.
- Chạy (dùng Python của MAIN, cwd tùy ý; `--method` có thể trỏ vào file trong worktree của bạn):

```
C:\Users\nviquang\Documents\AISTDR\QRDetector\.venv\Scripts\python.exe C:\Users\nviquang\Documents\AISTDR\QRDetector\experiments\bench\run.py --method <file.py>:<Class> --jobs 3 --seeds 2 --out kq.json
```

  Tùy chọn: `--conds goc,mo`, `--ks 3`, `--clips xa`, `--seeds 1` để chạy nhanh khi đang thử. Kết quả cuối phải chạy đủ mặc định (5 điều kiện, k = 1,3,5, 2 seed).

  Điều kiện thử: `goc` ảnh thật; `nho80`, `nho65` thu nhỏ ảnh (2,05 và 1,65 px/ô); `mo` thêm vệt mờ 4 px theo hướng chạy (khoảng 1,6 ô); `nhieu` tối đi và thêm nhiễu. `k` = số frame của lượt được dùng (CPU chỉ xử lý được vài frame mỗi lượt).

**Mốc trên tập phát triển (40 lượt, 1200 lần chấm): ĐIỂM TỔNG 79,25%, báo sai 0.**

| cond | k=1 | k=3 | k=5 |
|---|---:|---:|---:|
| goc | 97,5 | 100,0 | 97,5 |
| nho80 | 93,8 | 96,2 | 97,5 |
| nho65 | 87,5 | 87,5 | 92,5 |
| mo | 33,8 | 36,2 | 57,5 |
| nhieu | 62,5 | 62,5 | 86,2 |

Theo đoạn: cheo 78,5; gan 96,0; xa 62,1. Lượt khó thật: `xa_04` (cascade chỉ đọc được 3/25 frame).

## Quy tắc

1. Làm trong worktree được cấp, chỉ tạo/sửa trong `experiments/methods/<tên hướng>/`. Không sửa `experiments/bench/`, `qr/`, `camera/`, `ui/`, không sửa gì trong MAIN ngoài bước sao chép cuối (quy tắc 8). Dùng lại code `qr/` bằng import.
2. **Chỉ dùng tập phát triển** `MAIN\experiments\out\bench\tracks_dev`. Không tìm kiếm tập khác. Không chép đáp án vào code.
3. **Báo sai là lỗi nặng nhất.** Điều kiện qua: 0 lần báo sai trên tập phát triển. Khi không chắc thì trả None. Với QR mức L, sửa lỗi hết ngân sách rất dễ cho ra chuỗi sai hợp lệ: phải có lớp kiểm tra (độ khớp ô chức năng, đồng thuận nhiều frame, độ dư RS...).
4. Chỉ CPU, không GPU, chỉ dùng `--jobs 3` trở xuống vì nhiều agent chạy cùng lúc trên một máy. Mục tiêu: p95 dưới 20 s mỗi lần `read_pass` để chấm được; không tối ưu tốc độ thêm.
5. Thư viện thêm: `pip install --target <worktree>\.deps <gói>` và thêm vào `sys.path` trong file phương pháp. Không cài vào `.venv`. Không thêm `basicsr`/`realesrgan`. Không dùng dịch vụ mạng hay khóa bản quyền.
6. Không commit, không push, không tạo PR.
7. Đừng thử tham số vô tận: tập dev chỉ có 40 lượt nên dễ học thuộc. Ghi lại số cấu hình đã thử. Ưu tiên cải tiến có lý do vật lý.
8. Khi xong:
   - Sao chép thư mục phương pháp sang `MAIN\experiments\out\methods\<tên hướng>\` (thư mục này không commit), gồm cả `.deps` nếu dùng. Kiểm tra file đó chạy được từ chỗ mới, vì điều phối sẽ chấm từ đó.
   - Viết `REPORT.md` trong thư mục đó, tiếng Việt: ý tưởng, lệnh chạy, bảng kết quả đầy đủ so với mốc, số báo sai, lượt đọc thêm và lượt bị mất so với mốc, số cấu hình đã thử, thời gian tham khảo, giới hạn.
   - Lưu `results_dev.json` (từ `--out`) cạnh đó.
   - Tin nhắn cuối cho điều phối: lớp `file.py:Class`, ĐIỂM TỔNG, bảng 5×3, số báo sai, kết luận ngắn. Trung thực: nếu không thắng mốc thì nói rõ.
