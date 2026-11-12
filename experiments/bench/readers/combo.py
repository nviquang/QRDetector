"""Ghép các phương pháp đã xong: chạy lần lượt, phương pháp đầu tiên chốt được thì trả ngay.

--kwargs '{"parts": ["<file.py>:<Class>", ...]}'. Mỗi phương pháp đều đã chạy PassDecoder trước các bước riêng.
"""
import importlib.util
import os
import sys
import zlib


def _load(spec):
    path, cls = spec.rsplit(":", 1)
    path = os.path.abspath(path)
    sys.path.insert(0, os.path.dirname(path))
    name = "combo_part_" + str(zlib.crc32(path.encode()))
    if name not in sys.modules:
        m = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(m)
        sys.modules[name] = mod
        m.loader.exec_module(mod)
    return getattr(sys.modules[name], cls)()


class Combo:
    def __init__(self, parts):
        self.parts = [_load(p) for p in parts]

    def read_pass(self, obs, ctx):
        for part in self.parts:
            text = part.read_pass(obs, ctx)
            if text:
                return text
        return None
