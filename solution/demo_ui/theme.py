"""Bảng màu và QSS của ứng dụng — đổi theme chỉ cần sửa ở đây."""

from __future__ import annotations

from PyQt5.QtGui import QColor, QFont, QPalette

BG = "#0f1419"
SURFACE = "#171d25"
SURFACE_HIGH = "#1f2731"
FIELD = "#3a4656"        # nền ô nhập/radio/checkbox của form cũ — phải nổi trên SURFACE
BORDER = "#2c3642"
TEXT = "#e6edf3"
MUTED = "#8b98a5"
GREEN = "#22c55e"
BLUE = "#3b82f6"
AMBER = "#f59e0b"
RED = "#ef4444"

STATE_COLORS = {"idle": MUTED, "tuning": AMBER, "connecting": BLUE, "running": GREEN,
                "stopping": MUTED, "error": RED}

QSS = f"""
QWidget {{ color: {TEXT}; font-family: "Segoe UI"; font-size: 12px; }}
QMainWindow, QDialog, #workspace {{ background: {BG}; }}
QToolTip {{ color: {TEXT}; background: {SURFACE_HIGH}; border: 1px solid {BORDER}; }}

/* ── Màn hình làm việc ─────────────────────────────────── */
#headerBar, #footerBar {{ background: {SURFACE}; border: none; }}
#headerBar {{ border-bottom: 1px solid {BORDER}; }}
#footerBar {{ border-top: 1px solid {BORDER}; }}
#appTitle {{ font-size: 18px; font-weight: 600; }}
#stateText {{ font-size: 14px; font-weight: 600; }}
#elapsedText {{ font-size: 14px; color: {MUTED}; font-family: Consolas; }}
#videoPanel {{ background: #000000; border-radius: 8px; }}
#label_image {{ background: #000000; border: none; }}
#videoOverlay {{ background: rgba(15, 20, 25, 215); }}
#overlayMessage {{ font-size: 20px; }}
#overlayMessage[error="true"] {{ color: {RED}; }}
#card, #latestCard {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 8px; }}
#latestCard[flash="true"] {{ border: 2px solid {GREEN}; }}
#cardTitle {{ font-size: 11px; font-weight: 600; color: {MUTED}; }}
#latestCode {{ font-family: Consolas; font-weight: 700; color: {GREEN}; }}
#latestMeta {{ font-size: 13px; color: {MUTED}; }}
#kpiValue {{ font-size: 28px; font-weight: 700; }}
#footerItem {{ font-size: 13px; color: {MUTED}; }}
#footerItem[level="ok"] {{ color: {GREEN}; }}
#footerItem[level="warn"] {{ color: {AMBER}; }}
#footerItem[level="bad"] {{ color: {RED}; }}

#primaryButton {{ font-size: 15px; font-weight: 700; color: #ffffff; background: {GREEN};
                  border: none; border-radius: 6px; padding: 10px 28px; min-width: 130px; }}
#primaryButton:hover {{ background: #16a34a; }}
#primaryButton[running="true"] {{ background: {RED}; }}
#primaryButton[running="true"]:hover {{ background: #dc2626; }}
#primaryButton:disabled {{ background: {SURFACE_HIGH}; color: {MUTED}; }}
#headerButton, #overlayButton {{ font-size: 13px; background: {SURFACE_HIGH};
                                 border: 1px solid {BORDER}; border-radius: 6px; padding: 6px 14px; }}
#headerButton:hover, #overlayButton:hover {{ border-color: {MUTED}; }}
#headerButton:disabled {{ color: {MUTED}; }}
#headerButton::menu-indicator {{ image: none; }}

#passTable {{ background: transparent; border: none; font-size: 13px; }}
#passTable::item {{ padding: 3px 6px; border-bottom: 1px solid {SURFACE_HIGH}; }}
#passTable::item:selected {{ background: {SURFACE_HIGH}; }}

QMenu {{ background: {SURFACE_HIGH}; border: 1px solid {BORDER}; padding: 4px; }}
QMenu::item {{ padding: 6px 24px; font-size: 13px; }}
QMenu::item:selected {{ background: {BLUE}; color: #ffffff; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 4px 6px; }}

/* ── Cửa sổ Cấu hình ── */
QTabWidget::pane {{ border: 1px solid {BORDER}; background: {SURFACE}; }}
QTabBar::tab {{ background: {SURFACE_HIGH}; color: {MUTED}; padding: 8px 16px;
                border: 1px solid {BORDER}; border-bottom: none; }}
QTabBar::tab:selected {{ background: {SURFACE}; color: {TEXT}; }}
#settingsPage {{ background: {SURFACE}; border: none; }}
QGroupBox {{ border: 1px solid {BORDER}; border-radius: 4px; margin-top: 8px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 8px; padding: 0 4px; color: {MUTED}; }}
"""


def apply(app):
    """Fusion + palette tối cho các control của form cũ; QSS cho phần còn lại."""
    app.setStyle("Fusion")
    palette = QPalette()
    for role, value in ((QPalette.Window, SURFACE), (QPalette.WindowText, TEXT),
                        (QPalette.Base, FIELD), (QPalette.AlternateBase, SURFACE),
                        (QPalette.Text, TEXT), (QPalette.Button, SURFACE_HIGH),
                        (QPalette.ButtonText, TEXT), (QPalette.Highlight, BLUE),
                        (QPalette.HighlightedText, "#ffffff"), (QPalette.ToolTipBase, SURFACE_HIGH),
                        (QPalette.ToolTipText, TEXT)):
        palette.setColor(role, QColor(value))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        palette.setColor(QPalette.Disabled, role, QColor("#5b6773"))
    app.setPalette(palette)
    app.setFont(QFont("Segoe UI", 9))
    app.setStyleSheet(QSS)
