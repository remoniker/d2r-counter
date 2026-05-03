"""
hint.py — First-run tutorial popup for D2R Tracker.

Shown automatically on first launch (controlled by stats.json flag).
Accessible any time via the Ctrl+right-click menu.
Drag anywhere to reposition. Close with × or "Got it".
"""

from typing import Callable, Optional

from PyQt6.QtWidgets import QApplication, QWidget, QLabel, QPushButton
from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtGui import QPainter, QColor, QPen, QFont, QMouseEvent, QPolygon

# ── Window geometry ───────────────────────────────────────────────────────────

W       = 240    # wider to prevent text cutoff at higher DPI scaling
ARROW_H = 18     # transparent arrow area: stem + arrowhead
H       = 150    # total window height  (BOX_H = 132)
R       = 8      # corner radius
PAD_L   = 12     # content left edge (no accent bar)
PAD_R   = 12     # content right margin

BOX_H    = H - ARROW_H          # height of the visible rounded rectangle
ARROW_CX = 14                    # x center of arrow = DotWindow.ORB_X, tip points at orb

# ── Window flags (same as overlay) ───────────────────────────────────────────

_FLAGS = (
    Qt.WindowType.FramelessWindowHint   |
    Qt.WindowType.WindowStaysOnTopHint  |
    Qt.WindowType.Tool                  |
    Qt.WindowType.NoDropShadowWindowHint
)

# ── Palette ───────────────────────────────────────────────────────────────────

_BG     = QColor(14,  14,  14, 210)  # matches overlay _BG opacity
_BORDER = QColor(255, 255, 255, 70)  # white border, no glow
_ACCENT = QColor("#387CBC")          # blue — used for header text and GOT IT button
_PURPLE = QColor("#9C10C8")          # purple, matches active orb
_DIM    = QColor(52,  52,  52)       # section label color
_BODY   = QColor(190, 190, 190)      # body text
_MUTED  = QColor(120, 120, 120)      # secondary body text
_ARROW  = QColor(255, 255, 255, 160) # white arrow stroke

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

_GOTIT_QSS = """
QPushButton {
    background-color: rgba(56, 124, 188, 25);
    border: 1px solid rgba(56, 124, 188, 90);
    border-radius: 4px;
    color: #387CBC;
    font-family: "Segoe UI";
    font-size: 8pt;
    padding: 5px 20px;
}
QPushButton:hover   { background-color: rgba(56, 124, 188, 60); color: white; }
QPushButton:pressed { background-color: rgba(56, 124, 188, 100); }
"""

# ── Label factory ─────────────────────────────────────────────────────────────

def _lbl(
    parent:  QWidget,
    text:    str,
    x:       int,
    y:       int,
    *,
    color:   QColor  = _BODY,
    size:    int     = 9,
    bold:    bool    = False,
    spacing: float   = 0.0,
    rich:    bool    = False,
    wrap:    bool    = False,
) -> QLabel:
    """
    Create, style, and place a QLabel as a child of `parent`.
    Returns the label (already placed — caller doesn't need to manage layout).
    """
    label = QLabel(text, parent)
    label.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    font = QFont("Segoe UI", size)
    font.setBold(bold)
    if spacing:
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spacing)
    label.setFont(font)

    hex_color = color.name()
    label.setStyleSheet(f"color: {hex_color}; background: transparent;")

    if rich:
        label.setTextFormat(Qt.TextFormat.RichText)
    if wrap:
        label.setWordWrap(True)
        label.setFixedWidth(W - PAD_L - PAD_R)

    label.move(x, y)
    label.adjustSize()
    return label


# ── HintWindow ────────────────────────────────────────────────────────────────

class HintWindow(QWidget):
    """
    Frameless tutorial popup. Always-on-top, draggable from anywhere.

    Parameters
    ----------
    on_dismiss:
        Called once when the window is closed via × or "Got it".
        Typically stats.mark_hint_shown() so the window won't
        auto-open on next launch.
    """

    def __init__(self, on_dismiss: Callable[[], None], anchor: Optional[QPoint] = None) -> None:
        super().__init__()
        self._on_dismiss        = on_dismiss
        self._drag_pos: Optional[QPoint] = None

        self.setWindowFlags(_FLAGS)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(W, H)

        self._build_ui()

        if anchor is not None:
            self._position_above(anchor)
        else:
            self._center_on_screen()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:

        # ── Close button ──────────────────────────────────────────────────────
        close = QPushButton("×", self)
        close.setStyleSheet(_CLOSE_QSS)
        close.setFixedSize(26, 26)
        close.move(W - 32, 5)
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.clicked.connect(self._dismiss)

        # ── Header ────────────────────────────────────────────────────────────
        _lbl(self, "D2R  TRACKER",
             PAD_L, 10, color=_ACCENT, size=8, spacing=2.5)

        # ── Control instructions (monospaced for alignment) ───────────────────
        for row, (text, y) in enumerate([
            ("CTRL + LEFT CLICK   to MOVE", 44),
            ("CTRL + RIGHT CLICK  for MENU", 61),
        ]):
            lbl = QLabel(text, self)
            lbl.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            lbl.setFont(QFont("Consolas", 9))
            lbl.setStyleSheet("color: rgb(175, 175, 175); background: transparent;")
            lbl.adjustSize()
            lbl.move(PAD_L, y)

        # ── Color dots ────────────────────────────────────────────────────────
        _lbl(self,
             "<span style='color:#387CBC'>●</span>  Idle"
             "&nbsp;&nbsp;&nbsp;&nbsp;"
             "<span style='color:#9C10C8'>●</span>  In game",
             PAD_L, 82, rich=True, color=_MUTED)

        # ── Got it (bottom-right of the box area) ─────────────────────────────
        gotit = QPushButton("GOT IT", self)
        gotit.setStyleSheet(_GOTIT_QSS)
        gotit.setCursor(Qt.CursorShape.PointingHandCursor)
        gotit.adjustSize()
        gotit.move(W - gotit.width() - PAD_R, BOX_H - gotit.height() - 8)
        gotit.clicked.connect(self._dismiss)

    # ── Chrome painting ───────────────────────────────────────────────────────

    def paintEvent(self, _) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Background — only up to BOX_H, leaving arrow area transparent
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_BG)
        p.drawRoundedRect(0, 0, W, BOX_H, R, R)

        # White rounded border — no glow, no shadow, just a clean outline
        border_pen = QPen(_BORDER)
        border_pen.setWidthF(1.0)
        p.setPen(border_pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(0, 0, W - 1, BOX_H - 1, R, R)

        # Divider under header
        div_pen = QPen(QColor(38, 38, 38))
        div_pen.setWidthF(0.8)
        p.setPen(div_pen)
        p.drawLine(PAD_L, 30, W - PAD_R, 30)

        # White stick arrow — line stem + open arrowhead, no fill
        arrow_pen = QPen(_ARROW)
        arrow_pen.setWidthF(1.4)
        arrow_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        arrow_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(arrow_pen)
        p.setBrush(Qt.BrushStyle.NoBrush)

        stem_top = BOX_H + 2
        stem_bot = BOX_H + 10
        head_hw  = 5
        head_tip = H - 2

        # Stem
        p.drawLine(ARROW_CX, stem_top, ARROW_CX, stem_bot)
        # Arrowhead (two lines, open V — no fill)
        p.drawLine(ARROW_CX - head_hw, stem_bot, ARROW_CX, head_tip)
        p.drawLine(ARROW_CX + head_hw, stem_bot, ARROW_CX, head_tip)

        p.end()

    # ── Drag (whole window is draggable — no Ctrl required for a popup) ───────

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

    # ── Dismiss ───────────────────────────────────────────────────────────────

    def _dismiss(self) -> None:
        self._on_dismiss()
        self.close()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _position_above(self, anchor: QPoint) -> None:
        """
        anchor = QPoint(dot.x(), dot.y()) — top-left of the orb window.
        Left edge of hint aligns with left edge of overlay.
        Arrow tip lands 20px above the orb top.
        """
        x = anchor.x()
        y = anchor.y() - H - 8   # 8px gap — arrow tip lands just above the orb
        screen = QApplication.primaryScreen().geometry()
        x = max(0, min(x, screen.width()  - W))
        y = max(0, min(y, screen.height() - H))
        self.move(x, y)

    def reposition(self, anchor: QPoint) -> None:
        """Called by Overlay whenever the orb is dragged."""
        self._position_above(anchor)

    def _center_on_screen(self) -> None:
        screen = QApplication.primaryScreen().geometry()
        self.move(
            (screen.width()  - W) // 2,
            (screen.height() - H) // 2,
        )