"""Ghép hai bộ giải: tái tạo trên lưới (B) trước, giải ô rồi đọc bằng zxing/WeChat (C) sau."""
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def _load(relative: str, cls: str):
    path = os.path.join(HERE, relative)
    sys.path.insert(0, os.path.dirname(path))
    name = "qr_solver_" + os.path.basename(relative)[:-3]
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return getattr(module, cls)()


class ComboBC:
    def __init__(self):
        self.parts = [_load("grid_sr/grid_sr.py", "GridSR"), _load("preproc_sweep/preproc_sweep.py", "PreprocSweep")]

    def read_pass(self, obs, ctx):
        for part in self.parts:
            text = part.read_pass(obs, ctx)
            if text:
                return text
        return None
