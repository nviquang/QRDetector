"""Gửi thử một mã lên API báo cáo tấm bằng cấu hình .env, in kết quả (không in secret/API key).

    python tools/try_report_api.py <mã tấm>

Lưu ý: mã có thật sẽ được ghi nhận như camera vừa quét (tấm đã xác nhận quay về chờ xác nhận). Để chỉ kiểm tra
chữ ký và API key, gửi mã không tồn tại: kết quả đúng là "404 Không tìm thấy tấm".
"""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from demo_ui.api_config import load_api_config  # noqa: E402
from demo_ui.scan_uploader import PermanentError, ReportClient, TransientError  # noqa: E402


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    config, missing = load_api_config()
    if config is None:
        print("Thiếu trong .env:", ", ".join(missing))
        return 2
    try:
        warning = ReportClient(config)(sys.argv[1])
    except PermanentError as exc:
        print("Bị từ chối:", exc)
        return 1
    except TransientError as exc:
        print("Lỗi tạm thời (thử lại sau):", exc)
        return 1
    print("200 REPORTED", "· " + warning if warning else "")
    return 0


if __name__ == "__main__":
    sys.exit(main())
