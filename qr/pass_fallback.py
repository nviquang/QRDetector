"""Đọc nền cho lượt mà PassDecoder không đọc được: chạy một bộ giải ở tiến trình riêng, không chặn luồng decode.

Bộ giải (``qr/solvers``) nhận k crop của MỘT lượt và trả nội dung đã chốt hoặc None; mất tới vài chục giây mỗi lượt.
``PassReader`` giữ lượt lại tới khi có kết quả, nên lượt đó được báo muộn nhưng chỉ báo một lần. Chỉ hoạt động sau
``enable()`` (``main_basler.py``); tắt bằng biến môi trường ``QR_FALLBACK=off``.
"""

from __future__ import annotations

import atexit
import importlib.util
import inspect
import logging
import multiprocessing as mp
import os
import queue
import sys
import time
from dataclasses import dataclass

import numpy as np

from .solvers import SOLVER

logger = logging.getLogger("solution.qr")

K_FRAMES = 5           # số crop đưa cho bộ giải, trải đều trên lượt
MAX_BACKLOG = 8        # số lượt chờ tối đa; đầy thì lượt mới coi như không đọc được
FLUSH_WAIT_S = 5.0     # Dừng/Reset chờ kết quả tối đa chừng này
MIN_CROPS = 2
MAX_CROPS = 64
STAGE_SOLVING = "giải"  # giai đoạn chung khi bộ giải không báo tiến độ (ComboBC báo "B" rồi "C")
_EDGE_PX = 3
_SOLVERS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "solvers")
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@dataclass
class PassObs:
    gray: np.ndarray            # crop xám quanh tem
    bbox: np.ndarray            # [x1, y1, x2, y2] theo tọa độ crop
    quad: np.ndarray            # (4, 2) padded quad của qrdet, tọa độ crop
    polygon: np.ndarray | None  # (N, 2) đường bao mask, tọa độ crop
    conf: float
    origin: np.ndarray          # gốc crop trong frame
    frame: int
    t: float


@dataclass
class PassCtx:
    velocity: tuple[float, float]  # px / seq
    fps: float                     # seq / giây
    exposure_ms: float
    blur_px: float


def make_obs(image_bgr: np.ndarray, det, frame_idx: int, t: float) -> PassObs | None:
    """Cắt crop quanh detection; None nếu chạm mép ảnh (QR có thể bị cắt)."""
    h, w = image_bgr.shape[:2]
    x1, y1, x2, y2 = (float(v) for v in det.bbox_xyxy)
    if x1 < _EDGE_PX or y1 < _EDGE_PX or x2 > w - _EDGE_PX or y2 > h - _EDGE_PX:
        return None
    m = max(45.0, 0.8 * max(x2 - x1, y2 - y1))
    cx1, cy1, cx2, cy2 = int(max(0, x1 - m)), int(max(0, y1 - m)), int(min(w, x2 + m)), int(min(h, y2 + m))
    origin = np.array([cx1, cy1], np.float32)
    crop = image_bgr[cy1:cy2, cx1:cx2, 0].copy()
    polygon = None if det.polygon_xy is None else np.asarray(det.polygon_xy, np.float32) - origin
    return PassObs(crop, np.asarray(det.bbox_xyxy, np.float32) - np.r_[origin, origin],
                   np.asarray(det.quad_xy, np.float32) - origin, polygon, float(det.confidence), origin, frame_idx, t)


def _load_solver(spec: str):
    relative, cls = spec.rsplit(":", 1)
    path = relative if os.path.isabs(relative) else os.path.join(_SOLVERS_DIR, relative)
    sys.path.insert(0, os.path.dirname(path))
    module_spec = importlib.util.spec_from_file_location("qr_active_solver", path)
    module = importlib.util.module_from_spec(module_spec)
    sys.modules[module_spec.name] = module
    module_spec.loader.exec_module(module)
    return getattr(module, cls)()


def _accepts_progress(solver) -> bool:
    try:
        return "progress" in inspect.signature(solver.read_pass).parameters
    except (TypeError, ValueError):
        return False


def _worker(spec: str, jobs, results):
    import cv2
    os.environ["QR_MAIN"] = _ROOT      # bộ giải dùng qr/ của chính thư mục này
    cv2.setNumThreads(1)
    try:
        solver = _load_solver(spec)
    except Exception as e:
        results.put(("fatal", repr(e)))
        return
    results.put(("ready", None))
    reports_progress = _accepts_progress(solver)
    parent = mp.parent_process()
    while True:
        try:
            job = jobs.get(timeout=1.0)
        except queue.Empty:
            if parent is not None and not parent.is_alive():   # app bị tắt đột ngột: không để sót tiến trình
                return
            continue
        if job is None:
            return
        key, obs, ctx = job
        t0 = time.perf_counter()
        try:
            if reports_progress:
                text = solver.read_pass(obs, ctx, progress=lambda stage, k=key: results.put(("progress", (k, stage))))
            else:
                results.put(("progress", (key, STAGE_SOLVING)))
                text = solver.read_pass(obs, ctx)
            error = None
        except Exception as e:         # lỗi ở một lượt không được làm chết tiến trình đọc nền
            text, error = None, repr(e)
        results.put((key, (text, (time.perf_counter() - t0) * 1000.0, error)))


class PassFallback:
    def __init__(self, spec: str = SOLVER):
        self.spec = spec
        context = mp.get_context("spawn")
        self._jobs = context.Queue()
        self._results = context.Queue()
        self._jobs.cancel_join_thread()
        self._results.cancel_join_thread()
        self._pending: set[int] = set()
        self._stage: dict[int, tuple[str, float]] = {}   # khóa → (giai đoạn, monotonic lúc bắt đầu)
        self.revision = 0                                # tăng mỗi khi giai đoạn của một việc đổi
        self._next_key = 0
        self._failed = False
        self._process = context.Process(target=_worker, args=(spec, self._jobs, self._results), daemon=True,
                                        name="qr-pass-fallback")
        self._process.start()
        logger.info("pass_fallback started solver=%s pid=%s", spec, self._process.pid)

    @property
    def pending(self) -> int:
        return len(self._pending)

    def stage(self, key: int) -> tuple[str, float] | None:
        """(giai đoạn, monotonic lúc vào giai đoạn) của việc đang giải; None nếu còn chờ trong hàng đợi."""
        return self._stage.get(key)

    def _forget(self, key: int):
        self._pending.discard(key)
        if self._stage.pop(key, None) is not None:
            self.revision += 1

    def submit(self, obs: list[PassObs], ctx: PassCtx) -> int | None:
        """Trả khóa của việc, hoặc None nếu hàng đợi đầy / tiến trình đã lỗi."""
        if self._failed or len(self._pending) >= MAX_BACKLOG:
            return None
        key, self._next_key = self._next_key, self._next_key + 1
        self._pending.add(key)
        self._jobs.put((key, obs, ctx))
        return key

    def poll(self) -> list[tuple[int, str | None, float, str | None]]:
        """Các việc vừa xong: (khóa, nội dung, ms, lỗi). Không chặn."""
        done = []
        while True:
            try:
                key, value = self._results.get_nowait()
            except queue.Empty:
                break
            if key == "ready":
                logger.info("pass_fallback ready solver=%s", self.spec)
            elif key == "fatal":
                logger.error("pass_fallback không nạp được bộ giải %s: %s", self.spec, value)
                self._failed = True
            elif key == "progress":
                job, stage = value
                if job in self._pending:
                    self._stage[job] = (stage, time.monotonic())
                    self.revision += 1
            elif key in self._pending:
                self._forget(key)
                done.append((key, *value))
        if self._pending and (self._failed or not self._process.is_alive()):
            done += [(key, None, 0.0, "tiến trình đọc nền đã dừng") for key in self._pending]
            self._pending.clear()
            self._clear_stages()
            self._failed = True
        return done

    def _clear_stages(self):
        if self._stage:
            self._stage.clear()
            self.revision += 1

    def wait(self, timeout: float) -> list[tuple[int, str | None, float, str | None]]:
        """Chờ hết việc tối đa ``timeout`` giây, trả các việc xong trong lúc chờ."""
        deadline = time.monotonic() + timeout
        done = self.poll()
        while self._pending and time.monotonic() < deadline:
            time.sleep(0.02)
            done += self.poll()
        return done

    def discard(self):
        """Bỏ việc đang chờ: kết quả về muộn sẽ bị bỏ qua."""
        self._pending.clear()
        self._clear_stages()
        try:
            while True:
                self._jobs.get_nowait()
        except queue.Empty:
            pass

    def close(self):
        if self._process.is_alive():
            self.discard()
            self._jobs.put(None)
            self._process.join(1.0)
            if self._process.is_alive():
                self._process.terminate()


_active: PassFallback | None = None


def enable(spec: str = SOLVER) -> PassFallback | None:
    """Bật đọc nền cho các PassReader tạo sau lời gọi này. Gọi trong ``if __name__ == "__main__"``."""
    global _active
    if os.environ.get("QR_FALLBACK", "").lower() == "off":
        logger.info("pass_fallback off (QR_FALLBACK=off)")
        return None
    if _active is None:
        _active = PassFallback(spec)
        atexit.register(_active.close)
    return _active


def active() -> PassFallback | None:
    return _active
