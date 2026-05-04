"""
about_window.py — Help / About window for D2R Counter.

Describes all features and controls. Gold border, gold section headers,
blue body text. Frameless, always-on-top, draggable, centered on open.
Opened from the right-click menu or system tray.
"""

from typing import Optional

from PyQt6.QtWidgets import QApplication, QWidget, QPushButton, QLabel
from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtGui import QPainter, QColor, QPen, QFont, QMouseEvent

# ── Geometry ──────────────────────────────────────────────────────────────────

W     = 310
R     = 8
PAD_L = 16
PAD_R = 16

ROW_H       = 18   # standard text row height
SECTION_GAP = 12   # space above each section header
HEADER_H    = 44   # title block height before first section

# Content definition — (type, text)
# type: "section" | "body" | "key" | "gap"
_CONTENT = [
    ("section", "THE OVERLAY"),
    ("body",    "A transparent always-on-top game counter."),
    ("body",    "Detects D2R game joins automatically via"),
    ("body",    "packet analysis — no manual input needed."),
    ("key",     "●  Blue orb     Idle / waiting"),
    ("key",     "●  Purple orb   In game"),
    ("gap",     ""),
    ("section", "CONTROLS"),
    ("key",     "Ctrl + drag          Move the overlay"),
    ("key",     "Ctrl + right-click   Open options menu"),
    ("gap",     ""),
    ("section", "GAME COUNTER"),
    ("body",    "Counts confirmed game joins this session."),
    ("body",    "Reset Session zeroes the display counter"),
    ("body",    "without affecting all-time stats."),
    ("body",    "Set Count lets you start from any number."),
    ("gap",     ""),
    ("section", "TIMER"),
    ("body",    "Appears in-game only. Tracks time in the"),
    ("body",    "current game at centisecond precision."),
    ("body",    "Format:  MM:SS:cs  /  H:MM:SS:cs"),
    ("gap",     ""),
    ("section", "STATS"),
    ("body",    "All-time stats are saved to stats.json and"),
    ("body",    "persist across sessions. Tracked values:"),
    ("key",     "→  Total sessions, games, time in-game"),
    ("key",     "→  Longest game, avg game, best session"),
    ("key",     "→  Unique servers seen, first/last game"),
    ("gap",     ""),
    ("section", "DETECTION"),
    ("body",    "Sniffs TCP packets on port 443. Requires"),
    ("body",    "Npcap installed and run as Administrator."),
    ("body",    "D2R.exe must be running to track games."),
]

def _compute_height() -> int:
    h = HEADER_H + 8
    for kind, _ in _CONTENT:
        if kind == "section":
            h += SECTION_GAP + ROW_H
        elif kind == "gap":
            h += 4
        else:
            h += ROW_H
    h += 20   # bottom padding + close button room
    return h

H = _compute_height()

# ── Window flags ──────────────────────────────────────────────────────────────

_FLAGS = (
    Qt.WindowType.FramelessWindowHint   |
    Qt.WindowType.WindowStaysOnTopHint  |
    Qt.WindowType.Tool                  |
    Qt.WindowType.NoDropShadowWindowHint
)

# ── Palette ───────────────────────────────────────────────────────────────────

_BG      = QColor(14,  14,  14,  220)
_BORDER  = QColor(180, 140,  20, 160)   # gold border
_GOLD    = QColor(200, 160,  20)         # section headers, title accent
_GOLD_DIM= QColor(140, 110,  15)         # divider line
_BLUE    = QColor("#387CBC")             # body text
_KEY_C   = QColor("#2d6fa0")             # key/detail rows — slightly dimmer blue
_MUTED   = QColor( 80,  80,  80)         # subtitle
_WHITE   = QColor(210, 210, 210)         # close button idle

# ── Stylesheets ───────────────────────────────────────────────────────────────

_CLOSE_QSS = """
QPushButton {
    background: transparent;
    border: none;
    color: rgb(70, 70, 70);
    font-family: "Segoe UI";
    font-size: 15pt;
    padding: 0px 2px 2px 2px;
}
QPushButton:hover   { color: rgb(200, 160, 20); }
QPushButton:pressed { color: rgb(255, 255, 255); }
"""


# ── AboutWindow ───────────────────────────────────────────────────────────────

class AboutWindow(QWidget):
    """
    Frameless Help / About popup. Gold border, gold section headers,
    blue body text. Draggable from anywhere, centered on open.
    """

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

        # ── Close button ──────────────────────────────────────────────────────
        close = QPushButton("×", self)
        close.setStyleSheet(_CLOSE_QSS)
        close.setFixedSize(26, 26)
        close.move(W - 32, 6)
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.clicked.connect(self.close)

        # ── Title ─────────────────────────────────────────────────────────────
        f_title = QFont("Segoe UI", 9)
        f_title.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2.5)
        f_title.setBold(True)
        self._lbl(
            "D2R  COUNTER", PAD_L, 12,
            font=f_title, color=_GOLD
        )

        f_sub = QFont("Segoe UI", 7)
        f_sub.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2.0)
        self._lbl(
            "HELP  &  FEATURES", PAD_L, 28,
            font=f_sub, color=_MUTED
        )

        # ── Dynamic content rows ──────────────────────────────────────────────
        f_sec  = QFont("Segoe UI", 7)
        f_sec.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2.2)

        f_body = QFont("Segoe UI", 8)

        f_key  = QFont("Consolas", 8)

        y = HEADER_H + 8

        for kind, text in _CONTENT:
            if kind == "gap":
                y += 4
                continue

            if kind == "section":
                y += SECTION_GAP
                self._lbl(text, PAD_L, y, font=f_sec, color=_GOLD)
                y += ROW_H
                continue

            color = _BLUE  if kind == "body" else _KEY_C
            font  = f_body if kind == "body" else f_key

            # Inline color dots for the orb legend
            if "●" in text and "Blue" in text:
                self._rich_lbl(
                    text.replace("●", "<span style='color:#387CBC'>●</span>", 1),
                    PAD_L, y
                )
            elif "●" in text and "Purple" in text:
                self._rich_lbl(
                    text.replace("●", "<span style='color:#9C10C8'>●</span>", 1),
                    PAD_L, y
                )
            else:
                self._lbl(text, PAD_L, y, font=font, color=color)

            y += ROW_H

    def _lbl(
        self,
        text:  str,
        x:     int,
        y:     int,
        *,
        font:  QFont,
        color: QColor,
    ) -> QLabel:
        lbl = QLabel(text, self)
        lbl.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        lbl.setFont(font)
        lbl.setStyleSheet(f"color: {color.name()}; background: transparent;")
        lbl.setFixedWidth(W - PAD_L - PAD_R)
        lbl.move(x, y)
        lbl.adjustSize()
        return lbl

    def _rich_lbl(self, html: str, x: int, y: int) -> QLabel:
        lbl = QLabel(html, self)
        lbl.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        lbl.setTextFormat(Qt.TextFormat.RichText)
        f = QFont("Segoe UI", 8)
        lbl.setFont(f)
        lbl.setStyleSheet(f"color: {_KEY_C.name()}; background: transparent;")
        lbl.setFixedWidth(W - PAD_L - PAD_R)
        lbl.move(x, y)
        lbl.adjustSize()
        return lbl

    # ── Paint ─────────────────────────────────────────────────────────────────

    def paintEvent(self, _) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Background
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_BG)
        p.drawRoundedRect(0, 0, W, H, R, R)

        # Gold border
        border_pen = QPen(_BORDER)
        border_pen.setWidthF(1.0)
        p.setPen(border_pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(0, 0, W - 1, H - 1, R, R)

        # Gold divider under header
        div_pen = QPen(_GOLD_DIM)
        div_pen.setWidthF(0.8)
        p.setPen(div_pen)
        p.drawLine(PAD_L, HEADER_H, W - PAD_R, HEADER_H)

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