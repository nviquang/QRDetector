"""ReplayEndWatcher: hết dữ liệu phát lại thì Dừng như bấm nút — window/controller giả, không cần camera.

Chạy (từ gốc repo):  python -m unittest tests.test_replay_end
"""
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import torch  # noqa: F401,E402  (torch trước PyQt5)
from PyQt5.QtCore import QObject, pyqtSignal  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

from demo_ui.replay_end import ReplayEndWatcher  # noqa: E402
from demo_ui.run_controller import RunState  # noqa: E402


class FakeController(QObject):
    state_changed = pyqtSignal(object, str)

    def __init__(self):
        super().__init__()
        self.state = RunState.IDLE

    def set(self, state):
        self.state = state
        self.state_changed.emit(state, "")


class ReplayEndWatcherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.controller = FakeController()
        self.window = mock.Mock(controller=self.controller)
        self.mgr = mock.Mock(finished=False, current_id="rec_a", playing=True)
        self.watcher = ReplayEndWatcher(self.window, self.mgr, interval_ms=1000)

    def test_stops_once_when_running_and_finished(self):
        self.controller.state = RunState.RUNNING
        self.watcher.check()
        self.window.on_stop.assert_not_called()
        self.mgr.finished = True
        self.watcher.check()
        self.watcher.check()
        self.window.on_stop.assert_called_once()

    def test_starts_playback_when_running(self):
        self.mgr.playing = False
        self.controller.set(RunState.CONNECTING)
        self.mgr.start_playback.assert_not_called()
        self.controller.set(RunState.RUNNING)
        self.mgr.start_playback.assert_called()
        self.mgr.start_playback.reset_mock()
        self.watcher.check()                      # tín hiệu lỡ mất: check() cũng bắt đầu phát
        self.mgr.start_playback.assert_called_once()
        self.mgr.finished = True
        self.watcher.check()                      # chưa phát thì không coi là hết dữ liệu
        self.window.on_stop.assert_not_called()

    def test_ignores_finished_when_not_running(self):
        self.mgr.finished = True
        for state in (RunState.IDLE, RunState.CONNECTING, RunState.STOPPING, RunState.TUNING):
            self.controller.state = state
            self.watcher.check()
        self.window.on_stop.assert_not_called()

    def test_shows_end_message_after_stop_completes(self):
        self.controller.state = RunState.RUNNING
        self.mgr.finished = True
        self.watcher.check()
        self.controller.set(RunState.STOPPING)
        self.window.workspace.video.show_message.assert_not_called()
        self.controller.set(RunState.IDLE)
        text = self.window.workspace.video.show_message.call_args[0][0]
        self.assertIn("Hết dữ liệu", text)
        self.assertIn("rec_a", text)

    def test_user_stop_does_not_show_end_message(self):
        self.controller.set(RunState.RUNNING)
        self.controller.set(RunState.STOPPING)
        self.controller.set(RunState.IDLE)
        self.window.workspace.video.show_message.assert_not_called()

    def test_can_stop_again_on_next_run(self):
        self.controller.state = RunState.RUNNING
        self.mgr.finished = True
        self.watcher.check()
        self.controller.set(RunState.IDLE)
        self.mgr.finished = False
        self.controller.set(RunState.RUNNING)
        self.mgr.finished = True
        self.watcher.check()
        self.assertEqual(self.window.on_stop.call_count, 2)


if __name__ == "__main__":
    unittest.main()
