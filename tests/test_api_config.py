"""Đọc cấu hình API (BASE_URL, APP_TOKEN_SECRET, API_KEY) từ .env và biến môi trường.

Chạy (từ gốc repo):  python -m unittest tests.test_api_config
"""
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from demo_ui.api_config import ApiConfig, load_api_config  # noqa: E402


class LoadApiConfigTests(unittest.TestCase):
    def env_file(self, text: str) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / ".env"
        path.write_text(text, encoding="utf-8")
        return path

    def test_reads_keys_quotes_comments_bom(self):
        path = self.env_file('\ufeff# c\nBASE_URL="https://x.test/"\nexport API_KEY=k\nAPP_TOKEN_SECRET=\'s\'\n')
        self.assertEqual(load_api_config(path, environ={}), (ApiConfig("https://x.test/", "s", "k"), []))

    def test_environment_overrides_file(self):
        path = self.env_file("BASE_URL=https://x.test\nAPP_TOKEN_SECRET=s\nAPI_KEY=file\n")
        config, missing = load_api_config(path, environ={"API_KEY": "env"})
        self.assertEqual(config.api_key, "env")
        self.assertEqual(missing, [])

    def test_missing_file_reports_all_keys(self):
        path = Path(tempfile.gettempdir()) / "khong-co-file-nay.env"
        self.assertEqual(load_api_config(path, environ={}),
                         (None, ["BASE_URL", "APP_TOKEN_SECRET", "API_KEY"]))

    def test_empty_value_and_bad_url_count_as_missing(self):
        path = self.env_file("BASE_URL=ftp://x\nAPP_TOKEN_SECRET=s\nAPI_KEY=\n")
        config, missing = load_api_config(path, environ={})
        self.assertIsNone(config)
        self.assertEqual(missing, ["BASE_URL", "API_KEY"])

    def test_repr_hides_secrets(self):
        text = repr(ApiConfig("https://x.test", "s3cret", "k3y", basic_user="u", basic_password="pa55"))
        self.assertNotIn("s3cret", text)
        self.assertNotIn("k3y", text)
        self.assertNotIn("pa55", text)

    def test_optional_basic_auth_keys(self):
        path = self.env_file("BASE_URL=https://x.test\nAPP_TOKEN_SECRET=s\nAPI_KEY=k\n"
                             "BASIC_AUTH_USER=u\nBASIC_AUTH_PASSWORD=p\n")
        config, missing = load_api_config(path, environ={})
        self.assertEqual((config.basic_user, config.basic_password, missing), ("u", "p", []))

    def test_basic_auth_keys_not_required(self):
        path = self.env_file("BASE_URL=https://x.test\nAPP_TOKEN_SECRET=s\nAPI_KEY=k\n")
        config, missing = load_api_config(path, environ={})
        self.assertEqual((config.basic_user, config.basic_password, missing), ("", "", []))


if __name__ == "__main__":
    unittest.main()
