"""
overlay_circle.py — Circle ring overlay style for D2R Counter.

A single frameless window — no separate orb or panel.
The ring is drawn in blue (idle) or purple (in-game).
The in-game timer appears below the ring only while in a game.

Drag behaviour:
  Ctrl + left-drag      → reposition the whole window
  Ctrl + right-click    → fires on_context_menu (manager shows menu)
"""

import sys
import time
from typing import Optional, Callable

from PyQt6.QtWidgets import QApplication, QWidget
from PyQt6.QtCore import Qt, QPoint, QRectF
from PyQt6.QtGui import (
    QPainter, QColor, QFont, QFontMetrics,
    QMouseEvent, QPen, QCursor
)

from overlay_base import OverlayBase

_app = QApplication.instance() or QApplication(sys.argv)

_WINDOW_FLAGS = (
    Qt.WindowType.FramelessWindowHint      |
    Qt.WindowType.WindowStaysOnTopHint     |
    Qt.WindowType.Tool                     |
    Qt.WindowType.NoDropShadowWindowHint
)

# ── Palette ───────────────────────────────────────────────────────────────────

_BLUE        = QColor("#387CBC")        # idle ring
_PURPLE      = QColor("#9C10C8")        # active ring + timer
_WHITE       = QColor(255, 255, 255, 200)
_LABEL       = QColor(255, 255, 255, 60)
_BG_FILL     = QColor(14, 14, 14, 180)  # subtle dark fill inside ring

# ── Geometry ──────────────────────────────────────────────────────────────────

W          = 92     # window width
H_IDLE     = 96     # height when idle  (ring + count + label)
H_INGAME   = 118    # height when in game (adds timer row)
CX         = W // 2
CY         = 46     # ring center y
RING_R     = 34     # outer radius of the ring
RING_W     = 4.5    # stroke width of the ring


def _fmt_timer(centiseconds: int) -> str:
    cs      = centiseconds % 100
    total_s = centiseconds // 100
    h, rem  = divmod(total_s, 3600)
    m, s    = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}:{cs:02d}"
    return f"{m:02d}:{s:02d}:{cs:02d}"


# ── CircleWidget ──────────────────────────────────────────────────────────────

class CircleWidget(QWidget):
    """
    Single widget — the entire visible overlay.
    Handles its own painting, dragging, and context menu callback.
    """

    def __init__(
        self,
        x: int,
        y: int,
        on_context_menu: Callable[[QPoint], None],
        on_moved: Optional[Callable] = None,
    ) -> None:
        super().__init__()
        self._on_context_menu = on_context_menu
        self._on_moved        = on_moved
        self._drag_pos: Optional[QPoint] = None

        self.game_count  = 0
        self.in_game     = False
        self.locked      = False
        self._game_start: Optional[float] = None

        self.setWindowFlags(_WINDOW_FLAGS)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(W, H_IDLE)
        self.move(x, y)
        self.show()

    # ── State updates (called by OverlayCircle) ───────────────────────────────

    def on_joined(self) -> None:
        self.in_game     = True
        self.game_count += 1
        self._game_start = time.monotonic()
        self.setFixedSize(W, H_INGAME)
        self.update()

    def on_left(self) -> None:
        self.in_game     = False
        self._game_start = None
        self.setFixedSize(W, H_IDLE)
        self.update()

    def tick(self) -> None:
        if self.in_game:
            self.update()

    def _elapsed_cs(self) -> int:
        if self._game_start is None:
            return 0
        return int((time.monotonic() - self._game_start) * 100)

    # ── Paint ─────────────────────────────────────────────────────────────────

    def paintEvent(self, _) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        accent = _PURPLE if self.in_game else _BLUE

        # ── Dark fill inside ring ─────────────────────────────────────────────
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_BG_FILL)
        p.drawEllipse(
            QRectF(CX - RING_R, CY - RING_R, RING_R * 2, RING_R * 2)
        )

        # ── Ring ──────────────────────────────────────────────────────────────
        ring_pen = QPen(accent)
        ring_pen.setWidthF(RING_W)
        ring_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(ring_pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        inset = RING_W / 2
        p.drawEllipse(
            QRectF(
                CX - RING_R + inset,
                CY - RING_R + inset,
                (RING_R - inset) * 2,
                (RING_R - inset) * 2,
            )
        )

        # ── Count ─────────────────────────────────────────────────────────────
        f_count = QFont("Segoe UI", 20, QFont.Weight.Bold)
        p.setFont(f_count)
        p.setPen(_WHITE)
        count_str = str(self.game_count)
        fm        = QFontMetrics(f_count)
        p.drawText(
            CX - fm.horizontalAdvance(count_str) // 2,
            CY - 4 + fm.ascent() // 2 - 4,
            count_str,
        )

        # ── "GAMES" label ─────────────────────────────────────────────────────
        f_label = QFont("Segoe UI", 5)
        f_label.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.5)
        p.setFont(f_label)
        p.setPen(_LABEL)
        lbl_str = "GAMES"
        fm_l    = QFontMetrics(f_label)
        p.drawText(
            CX - fm_l.horizontalAdvance(lbl_str) // 2,
            CY + 16,
            lbl_str,
        )

        # ── Timer (only in-game) ──────────────────────────────────────────────
        if self.in_game:
            f_timer = QFont("Consolas", 9, QFont.Weight.Bold)
            p.setFont(f_timer)
            p.setPen(_PURPLE)
            timer_str = _fmt_timer(self._elapsed_cs())
            fm_t      = QFontMetrics(f_timer)
            p.drawText(
                CX - fm_t.horizontalAdvance(timer_str) // 2,
                CY + RING_R + 26,
                timer_str,
            )

        p.end()

    # ── Drag and context menu ─────────────────────────────────────────────────

    def mousePressEvent(self, event: QMouseEvent) -> None:
        ctrl = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
        if event.button() == Qt.MouseButton.RightButton and ctrl:
            self._on_context_menu(QCursor.pos())
            return
        if event.button() == Qt.MouseButton.LeftButton and ctrl and not self.locked:
            self._drag_pos = (
                event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            )

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_pos and event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            if self._on_moved:
                self._on_moved()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag_pos = None


# ── OverlayCircle (implements OverlayBase) ────────────────────────────────────

class OverlayCircle(OverlayBase):
    """
    Circle ring overlay style.
    One widget, no orb/panel split.
    """

    def __init__(
        self,
        x: int,
        y: int,
        on_context_menu: Optional[Callable[[QPoint], None]] = None,
        on_moved: Optional[Callable] = None,
    ) -> None:
        screen = _app.primaryScreen().geometry()
        if x == 0 and y == 0:
            x = screen.width()  // 2
            y = screen.height() // 2

        self._widget = CircleWidget(
            x, y,
            on_context_menu or (lambda pos: None),
            on_moved,
        )

    # ── OverlayBase interface ─────────────────────────────────────────────────

    def on_joined(self) -> None:
        self._widget.on_joined()

    def on_left(self) -> None:
        self._widget.on_left()

    def tick(self) -> None:
        self._widget.tick()

    def get_position(self) -> QPoint:
        return QPoint(self._widget.x(), self._widget.y())

    def move_to(self, pos: QPoint) -> None:
        self._widget.move(pos)

    def set_game_count(self, count: int) -> None:
        self._widget.game_count  = count
        self._widget.in_game     = False
        self._widget._game_start = None
        self._widget.setFixedSize(W, H_IDLE)
        self._widget.update()

    def get_game_count(self) -> int:
        return self._widget.game_count

    def set_locked(self, locked: bool) -> None:
        self._widget.locked = locked

    def show(self) -> None:
        self._widget.show()

    def hide(self) -> None:
        self._widget.hide()

    def is_visible(self) -> bool:
        return self._widget.isVisible()

    def destroy(self) -> None:
        self._widget.close()
        self._widget.deleteLater()