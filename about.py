"""
about.py — About window for D2R Counter.

Opened from the right-click menu or system tray.
"""

from typing import Optional

from PyQt6.QtWidgets import QApplication, QWidget, QPushButton, QLabel
from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtGui import QPainter, QPen, QFont, QMouseEvent

from theme import GOLD, BLUE, BG, DIVIDER, TEXT, CLOSE_BTN_QSS, WINDOW_FLAGS

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
    ("A safe for battle.net game counter for D2R.",    "body"),
    ("This program passively reads local traffic to ", "body"),
    ("determine games played and duration.",   "body"),
    ("", "gap"),
    ("CONTROLS", "section"),
    ("Ctrl + drag the dot — move the overlay",  "body"),
    ("Ctrl + right-click the dot — open menu",  "body"),
    ("", "gap"),
    ("OPTIONS", "section"),
    ("Remember count — persist on exit",       "body"),
    ("Set count — manually set the counter",   "body"),
    ("Hide overlay — toggle visibility",       "body"),
    ("Statistics — session and all-time data", "body"),
    ("Menu options also available from systray icon",  "body"),
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



# ── AboutWindow ───────────────────────────────────────────────────────────────

class AboutWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._drag_pos: Optional[QPoint] = None

        self.setWindowFlags(WINDOW_FLAGS)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(W, H)

        self._build_ui()
        self._center_on_screen()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        close = QPushButton("×", self)
        close.setStyleSheet(CLOSE_BTN_QSS)
        close.setFixedSize(26, 26)
        close.move(W - 32, 6)
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.clicked.connect(self.close)

        title = QLabel("About", self)
        title.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        f_title = QFont("Segoe UI", 12)
        f_title.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.0)
        title.setFont(f_title)
        title.setStyleSheet(f"color: {GOLD.name()}; background: transparent;")
        title.move(PAD_L, PAD_T)
        title.adjustSize()

        sub = QLabel("D2R Counter", self)
        sub.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        f_sub = QFont("Segoe UI", 8)
        f_sub.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.0)
        sub.setFont(f_sub)
        sub.setStyleSheet(f"color: {BLUE.name()}; background: transparent;")
        sub.move(PAD_L, PAD_T + 18)
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
                lbl.setStyleSheet(f"color: {GOLD.name()}; background: transparent;")
                lbl.move(PAD_L, y + 4)
                lbl.adjustSize()
                y += ROW_H + 4
                continue

            lbl = QLabel(text, self)
            lbl.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            lbl.setFont(f_body)
            lbl.setStyleSheet(f"color: {TEXT.name()}; background: transparent;")
            lbl.move(PAD_L, y + 3)
            lbl.adjustSize()
            y += ROW_H

    # ── Paint ─────────────────────────────────────────────────────────────────

    def paintEvent(self, _) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(BG)
        p.drawRoundedRect(0, 0, W, H, R, R)

        border_pen = QPen(GOLD)
        border_pen.setWidthF(1.0)
        p.setPen(border_pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(0, 0, W - 1, H - 1, R, R)

        div_pen = QPen(DIVIDER)
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
