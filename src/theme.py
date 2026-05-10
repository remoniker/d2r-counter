"""
theme.py — Shared visual constants for D2R Counter popup windows.

Used by stats.py, about.py, and overlay_manager.py.
Do NOT import in hint.py or overlay.py — those are complete and self-contained.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

# ── Palette ───────────────────────────────────────────────────────────────────

GOLD    = QColor("#CCB980")
BLUE    = QColor("#387CBC")
PURPLE  = QColor("#8E47DE")
BG      = QColor(14, 14, 14, 255)
BORDER  = QColor(255, 255, 255, 70)
DIVIDER = QColor(32, 32, 32)
TEXT    = QColor(158, 158, 158)   # body / secondary labels

# ── Window flags ──────────────────────────────────────────────────────────────

WINDOW_FLAGS = (
    Qt.WindowType.FramelessWindowHint   |
    Qt.WindowType.WindowStaysOnTopHint  |
    Qt.WindowType.Tool                  |
    Qt.WindowType.NoDropShadowWindowHint
)

POPUP_FLAGS = (
    Qt.WindowType.FramelessWindowHint   |
    Qt.WindowType.Popup                 |
    Qt.WindowType.NoDropShadowWindowHint
)

DIALOG_FLAGS = (
    Qt.WindowType.FramelessWindowHint   |
    Qt.WindowType.WindowStaysOnTopHint  |
    Qt.WindowType.NoDropShadowWindowHint
)

# ── Stylesheets ───────────────────────────────────────────────────────────────

CLOSE_BTN_QSS = """
QPushButton {
    background: transparent;
    border: none;
    color: rgb(55, 55, 55);
    font-family: "Segoe UI";
    font-size: 15pt;
    padding: 0px 2px 2px 2px;
}
QPushButton:hover   { color: rgb(180, 180, 180); }
QPushButton:pressed { color: rgb(255, 255, 255); }
"""

SPINBOX_QSS = """
QSpinBox {
    background: rgb(22, 22, 22);
    border: 1px solid rgb(55, 55, 55);
    border-radius: 4px;
    color: rgb(210, 210, 210);
    padding: 2px 6px;
    font-family: "Segoe UI";
    font-size: 10pt;
}
QSpinBox::up-button, QSpinBox::down-button { width: 0; }
"""

DIALOG_BTN_QSS = """
QPushButton {
    background: transparent;
    border: 1px solid rgb(55, 55, 55);
    border-radius: 4px;
    color: rgb(160, 160, 160);
    font-family: "Segoe UI";
    font-size: 9pt;
}
QPushButton:hover   { border-color: #CCB980; color: #CCB980; }
QPushButton:pressed { background: rgba(204, 185, 128, 20); }
"""

MENU_QSS = """
QMenu {
    background-color: rgb(14, 14, 14);
    border: 1px solid rgba(204, 185, 128, 120);
    border-radius: 8px;
    padding: 5px 0px;
    font-family: "Segoe UI";
    font-size: 9pt;
    color: rgb(210, 210, 210);
}
QMenu::item {
    padding: 6px 24px 6px 14px;
    margin: 1px 5px;
    border-radius: 4px;
    border-left: 3px solid transparent;
}
QMenu::item:selected {
    background-color: rgba(56, 124, 188, 35);
    border-left: 3px solid #387CBC;
    color: rgb(255, 255, 255);
}
QMenu::item:pressed  { background-color: rgba(56, 124, 188, 60); }
QMenu::item:disabled {
    color: rgb(58, 58, 58);
    border-left: 3px solid transparent;
    background: transparent;
}
QMenu::separator {
    height: 1px;
    background-color: rgb(38, 38, 38);
    margin: 4px 10px;
}
"""
