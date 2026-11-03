"""Nạp torch trước PyQt5 để tránh WinError 1114 (c10.dll) khi chạy cả bộ test.

Chạy từ gốc repo:  python -m unittest discover -s tests -t . -p "test_*.py"
"""

try:
    import torch  # noqa: F401
except (ImportError, OSError):
    pass
