"""
about.py — About window for D2R Counter.

Opened from the right-click menu or system tray.
"""

from typing import Optional

from PyQt6.QtWidgets import QApplication, QWidget, QPushButton, QLabel
from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtGui import QPainter, QColor, QPen, QFont, QMouseEvent

# ── Geometry ──────────────────────────────────────────────────────────────────

W     = 300
R     = 8
PAD_L = 16
PAD_R = 16
PAD_T = 14

ROW_H       = 22
SECTION_GAP = 10
HEADER_H    = 42

# ── Content ───────────────────────────────────────────────────────────────────
# Each entry: (text, kind)   kind: "section" | "body" | "gap"
# Edit this list to customise what the About window shows.

_ROWS = [
    ("OVERVIEW",  "section"),
    ("D2R Counter is a minimal overlay for", "body"),
    ("Diablo II: Resurrected. It detects",   "body"),
    ("game joins automatically and tracks",  "body"),
    ("your sessions without manual input.",  "body"),
    ("", "gap"),
    ("HOW IT WORKS", "section"),
    ("Monitors TCP traffic on port 443 to",  "body"),
    ("detect join and leave events.",        "body"),
    ("Requires Npcap + run as Administrator.","body"),
    ("", "gap"),
    ("CONTROLS", "section"),
    ("Ctrl + drag          Move the overlay", "body"),
    ("Ctrl + right-click   Options menu",     "body"),
]


def _compute_height() -> int:
    h = PAD_T + HEADER_H
    for _, kind in _ROWS:
        if kind == "section":
            h += ROW_H + 4
        elif kind == "gap":
            h += 8
        else:
            h += ROW_H
    h += 14
    return h


H = _compute_height()

# ── Window flags ──────────────────────────────────────────────────────────────

_FLAGS = (
    Qt.WindowType.FramelessWindowHint   |
    Qt.WindowType.WindowStaysOnTopHint  |
    Qt.WindowType.Tool                  |
    Qt.WindowType.NoDropShadowWindowHint
)

# ── Palette (matches stats.py exactly) ───────────────────────────────────────

_GOLD_ACCENT = QColor("#CCB980")
_BG      = QColor(14,  14,  14,  255)
_BORDER  = QColor(255, 255, 255,  70)
_ACCENT  = QColor("#387CBC")
_SECTION = QColor("#CCB980")
_BODY    = QColor("#CCB980")
_DIVIDER = QColor(32,  32,  32)

# ── Stylesheets ───────────────────────────────────────────────────────────────

_CLOSE_QSS = """
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


# ── AboutWindow ───────────────────────────────────────────────────────────────

class AboutWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._drag_pos: Optional[QPoint] = None

        self.setWindowFlags(_FLAGS)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(W, H)

        self._build_ui()
        self._center_on_screen()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        close = QPushButton("×", self)
        close.setStyleSheet(_CLOSE_QSS)
        close.setFixedSize(26, 26)
        close.move(W - 32, 6)
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.clicked.connect(self.close)

        title = QLabel("D2R - GAME COUNTER", self)
        title.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        f_title = QFont("Segoe UI", 12)
        f_title.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2.5)
        title.setFont(f_title)
        title.setStyleSheet(f"color: {_ACCENT.name()}; background: transparent;")
        title.move(PAD_L, PAD_T)
        title.adjustSize()

        sub = QLabel("ABOUT", self)
        sub.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        f_sub = QFont("Segoe UI", 10)
        f_sub.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2.0)
        sub.setFont(f_sub)
        sub.setStyleSheet(f"color: {_SECTION.name()}; background: transparent;")
        sub.move(PAD_L, PAD_T + 16)
        sub.adjustSize()

        f_sec  = QFont("Segoe UI", 10)
        f_sec.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2.0)
        f_body = QFont("Segoe UI", 10)

        y = PAD_T + HEADER_H

        for text, kind in _ROWS:
            if kind == "gap":
                y += 8
                continue

            if kind == "section":
                lbl = QLabel(text, self)
                lbl.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
                lbl.setFont(f_sec)
                lbl.setStyleSheet(f"color: {_SECTION.name()}; background: transparent;")
                lbl.move(PAD_L, y + 4)
                lbl.adjustSize()
                y += ROW_H + 4
                continue

            lbl = QLabel(text, self)
            lbl.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            lbl.setFont(f_body)
            lbl.setStyleSheet(f"color: {_BODY.name()}; background: transparent;")
            lbl.move(PAD_L, y + 3)
            lbl.adjustSize()
            y += ROW_H

    # ── Paint ─────────────────────────────────────────────────────────────────

    def paintEvent(self, _) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_BG)
        p.drawRoundedRect(0, 0, W, H, R, R)

        border_pen = QPen(_GOLD_ACCENT)
        border_pen.setWidthF(1.0)
        p.setPen(border_pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(0, 0, W - 1, H - 1, R, R)

        div_pen = QPen(_DIVIDER)
        div_pen.setWidthF(0.8)
        p.setPen(div_pen)
        p.drawLine(PAD_L, PAD_T + HEADER_H - 4, W - PAD_R, PAD_T + HEADER_H - 4)

        p.end()

    # ── Drag ─────────────────────────────────────────────────────────────────

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = (
                event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            )

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_pos and event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag_pos = None

    # ── Position ─────────────────────────────────────────────────────────────

    def _center_on_screen(self) -> None:
        screen = QApplication.primaryScreen().geometry()
        self.move(
            (screen.width()  - W) // 2,
            (screen.height() - H) // 2,
        )
