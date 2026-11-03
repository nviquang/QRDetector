"""Máy trạng thái của nút Bắt đầu/Dừng; các bước mở camera chạy trên thread nền, không chặn GUI.

Việc đóng camera vẫn do MainWindow đảm nhiệm (luồng đóng bất đồng bộ dùng chung với thoát app),
controller chỉ nhận kết quả qua ``on_camera_closed`` / ``on_close_failed``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import logging
import threading

from camera.conveyor import RunSettings

from PyQt5.QtCore import QObject, pyqtSignal

logger = logging.getLogger("solution.ui.run")


class RunState(Enum):
    IDLE = "idle"
    TUNING = "tuning"           # camera mở để chỉnh, chưa decode
    CONNECTING = "connecting"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"


@dataclass(frozen=True)
class StartRequest:
    camera_serial: str
    settings: RunSettings


class StartError(Exception):
    """Lỗi hiển thị thẳng cho người demo — viết bằng tiếng Việt dễ hiểu."""


def pick_camera(cameras: list, serial: str) -> int:
    if not cameras:
        raise StartError("Không tìm thấy camera. Kiểm tra cáp và nguồn của camera.")
    if serial:
        for index, camera in enumerate(cameras):
            if camera.GetSn() == serial:
                return index
        raise StartError("Không thấy camera đã lưu (serial {}). Chọn lại trong Cấu hình.".format(serial))
    if len(cameras) > 1:
        raise StartError("Có {} camera nhưng chưa chọn camera nào. Chọn trong Cấu hình.".format(len(cameras)))
    return 0


class RunController(QObject):
    state_changed = pyqtSignal(object, str)   # (RunState, thông báo cho người dùng)
    camera_chosen = pyqtSignal(str)           # serial của camera vừa tự chọn
    configured = pyqtSignal()                 # camera đã mở và cấu hình xong — cập nhật widget
    cancelled = pyqtSignal()                  # hủy khi đang kết nối — MainWindow đóng camera nếu cần

    _progress = pyqtSignal(str)
    _connect_done = pyqtSignal(str)           # "" = thành công

    def __init__(self, mgr, worker, parent=None):
        super().__init__(parent)
        self._mgr = mgr
        self._worker = worker
        self._state = RunState.IDLE
        self._cancel = False
        self._connecting = False
        self.close_failed = False
        self._progress.connect(self._on_progress)
        self._connect_done.connect(self._on_connect_done)
        worker.ready.connect(self._on_worker_ready)

    @property
    def state(self) -> RunState:
        return self._state

    def _set(self, state: RunState, message: str = ""):
        self._state = state
        self.state_changed.emit(state, message)

    def start(self, request: StartRequest) -> bool:
        if self._state not in (RunState.IDLE, RunState.TUNING, RunState.ERROR):
            return False
        self._cancel = False
        self._connecting = True
        self._set(RunState.CONNECTING, "Đang chuẩn bị…")
        threading.Thread(target=self._connect, args=(request,), daemon=True).start()
        return True

    def cancel(self):
        """Hủy khi đang kết nối: bước đang chạy kết thúc xong mới báo ``cancelled``."""
        self._cancel = True
        self._set(RunState.STOPPING, "Đang dừng…")
        if not self._connecting:
            self.cancelled.emit()

    def begin_stop(self):
        self.close_failed = False
        self._set(RunState.STOPPING, "Đang dừng…")

    def enter_tuning(self):
        if self._state in (RunState.IDLE, RunState.ERROR):
            self._set(RunState.TUNING)

    def on_camera_closed(self):
        self.close_failed = False
        self._set(RunState.IDLE)

    def on_close_failed(self, message: str):
        self.close_failed = True
        self._set(RunState.ERROR, message)

    # ── Thread nền ────────────────────────────────────────────────────────────

    def _connect(self, request: StartRequest):
        try:
            self._run_steps(request)
            self._connect_done.emit("")
        except StartError as exc:
            self._connect_done.emit(str(exc))
        except Exception:
            logger.exception("start_failed")
            self._connect_done.emit("Lỗi không mong đợi khi khởi động. Xem log để biết chi tiết.")

    def _run_steps(self, request: StartRequest):
        mgr = self._mgr
        if mgr.handle is None:
            self._progress.emit("Đang tìm camera…")
            cameras = mgr.list_cameras()
            index = pick_camera(cameras, request.camera_serial)
            if self._cancel:
                return
            self._progress.emit("Đang mở camera…")
            if not mgr.open(index):
                raise StartError("Không mở được camera. Camera có thể đang bị ứng dụng khác sử dụng.")
            self.camera_chosen.emit(cameras[index].GetSn())
        if self._cancel:
            return
        # Không nạp Param: Param lưu gain riêng, nạp ngay sau khi mở làm ảnh tối đi và không đọc được QR.
        self._progress.emit("Đang áp dụng cấu hình camera…")
        mgr.set_trigger_mode(0)
        applied = mgr.apply_run_settings(request.settings)
        if applied is None or not applied["ok"]:
            raise StartError("Không áp dụng được cấu hình camera. Kiểm tra thông số trong Cấu hình.")

    # ── GUI thread ────────────────────────────────────────────────────────────

    def _on_progress(self, message: str):
        if self._state is RunState.CONNECTING:
            self._set(RunState.CONNECTING, message)

    def _on_connect_done(self, error: str):
        self._connecting = False
        if self._cancel:
            self.cancelled.emit()
        elif error:
            self._set(RunState.ERROR, error)
        else:
            self.configured.emit()
            if self._worker.is_ready:
                self._set(RunState.RUNNING)
            else:
                self._set(RunState.CONNECTING, "Đang khởi động nhận diện…")

    def _on_worker_ready(self):
        if self._state is RunState.CONNECTING and not self._connecting:
            self._set(RunState.RUNNING)
