"""Cửa sổ Cấu hình: kết nối camera và băng chuyền; không chặn màn hình chính."""

from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QDialog, QLabel, QTabWidget, QVBoxLayout, QWidget

TAB_CONNECTION, TAB_CONVEYOR = range(2)
TAB_TITLES = ("Kết nối camera", "Băng chuyền")


def _page(*widgets) -> QWidget:
    page = QWidget()
    page.setObjectName("settingsPage")
    layout = QVBoxLayout(page)
    for widget in widgets:
        layout.addWidget(widget)
    layout.addStretch(1)
    return page


class SettingsWindow(QDialog):
    def __init__(self, parent, camera_group: QWidget, conveyor_group: QWidget, message: QLabel):
        super().__init__(parent)
        self.setWindowTitle("Cấu hình")
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setModal(False)
        self.resize(640, 400)

        # Form cũ đặt widget theo tọa độ: giữ nguyên kích thước
        camera_group.setFixedSize(camera_group.size())
        message.setWordWrap(True)

        self.tabs = QTabWidget(self)
        self.tabs.addTab(_page(camera_group), TAB_TITLES[TAB_CONNECTION])
        self.tabs.addTab(_page(conveyor_group, message), TAB_TITLES[TAB_CONVEYOR])

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(self.tabs)

    def open_tab(self, index: int | None = None):
        if index is not None:
            self.tabs.setCurrentIndex(index)
        self.show()
        self.raise_()
        self.activateWindow()
