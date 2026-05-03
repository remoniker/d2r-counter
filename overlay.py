"""
overlay.py — Default overlay style for D2R Counter.

A pure display class — owns only the orb (DotWindow) and stat panel
(StatPanel). Has no system tray, no menu logic, no hint management.
All of that lives in OverlayManager.

Implements the OverlayBase interface so OverlayManager can swap styles.

Ctrl + left-drag  → reposition (calls on_moved so manager can follow)
Ctrl + right-click → fires on_context_menu callback (manager builds/shows menu)
"""

import sys
import time
from typing import Optional, Callable

try:
    from PyQt6.QtWidgets import QApplication, QWidget
    from PyQt6.QtCore import Qt, QPoint
    from PyQt6.QtGui import (
        QPainter, QColor, QFont, QFontMetrics,
        QMouseEvent, QPen, QCursor
    )
except ImportError:
    raise

from overlay_signals import signals
from overlay_base import OverlayBase

_app = QApplication.instance() or QApplication(sys.argv)
screen = QApplication.primaryScreen().geometry()
OVERLAY_X = int(screen.width() / 2)
OVERLAY_Y = int(screen.height() / 2)

_WINDOW_FLAGS = (
    Qt.WindowType.FramelessWindowHint      |
    Qt.WindowType.WindowStaysOnTopHint     |
    Qt.WindowType.Tool                     |
    Qt.WindowType.NoDropShadowWindowHint
)

# ── Colors ────────────────────────────────────────────────────────────────────

_IDLE_ACCENT  = QColor("#387CBC")
_ACTIVE_ACCENT = QColor("#9C10C8")
_BG           = QColor(14, 14, 14, 210)
_BORDER       = QColor(255, 255, 255, 14)
_TEXT_PRIMARY = QColor(255, 255, 255, 220)
_TEXT_MUTED   = QColor(255, 255, 255, 80)
_TEXT_DIM     = QColor(255, 255, 255, 40)


def _fmt_game_time(centiseconds: int) -> str:
    cs      = centiseconds % 100
    total_s = centiseconds // 100
    h, rem  = divmod(total_s, 3600)
    m, s    = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}:{cs:02d}"
    return f"{m:02d}:{s:02d}:{cs:02d}"


# ── StatPanel ─────────────────────────────────────────────────────────────────

class StatPanel(QWidget):
    W = 160
    H = 74

    def __init__(self, x: int, y: int) -> None:
        super().__init__()
        self.game_count   = 0
        self.in_game      = False
        self._game_start: Optional[float] = None

        self.setWindowFlags(_WINDOW_FLAGS | Qt.WindowType.WindowTransparentForInput)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(self.W, self.H)
        self.move(x, y)
        self.show()

    def tick(self) -> None:
        if self.in_game:
            self.update()

    def on_joined(self) -> None:
        self.in_game     = True
        self.game_count += 1
        self._game_start = time.monotonic()
        self.update()

    def on_left(self) -> None:
        self.in_game     = False
        self._game_start = None
        self.update()

    def _elapsed_cs(self) -> int:
        if self._game_start is None:
            return 0
        return int((time.monotonic() - self._game_start) * 100)

    def paintEvent(self, _) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        accent      = _ACTIVE_ACCENT if self.in_game else _IDLE_ACCENT
        W, H        = self.W, self.H
        BAR, PAD, R = 3, 10, 6

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_BG)
        p.drawRoundedRect(0, 0, W, H, R, R)

        pen = QPen(_BORDER)
        pen.setWidthF(0.8)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(0, 0, W - 1, H - 1, R, R)

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(accent)
        p.drawRoundedRect(0, 0, BAR * 2, H, R, R)
        p.fillRect(BAR, 0, BAR, H, accent)

        X = BAR + PAD

        f_count  = QFont("Segoe UI", 22, QFont.Weight.Bold)
        f_label  = QFont("Segoe UI", 8)
        f_label.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.4)
        f_stat   = QFont("Consolas", 11, QFont.Weight.Bold)
        f_stat_l = QFont("Segoe UI", 7)
        f_stat_l.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.2)

        def shadow_text(px, py, text, font, color):
            p.setFont(font)
            p.setPen(QColor(0, 0, 0, 120))
            p.drawText(px + 1, py + 1, text)
            p.setPen(color)
            p.drawText(px, py, text)

        count_str = str(self.game_count)
        p.setFont(f_count)
        fm_count  = QFontMetrics(f_count)
        count_w   = fm_count.horizontalAdvance(count_str)
        shadow_text(X, 36, count_str, f_count, _TEXT_PRIMARY)

        lbl = "IN GAME" if self.in_game else "GAMES"
        shadow_text(X + count_w + 7, 28, lbl, f_label, accent)

        div_pen = QPen(_TEXT_DIM)
        div_pen.setWidthF(0.6)
        p.setPen(div_pen)
        p.drawLine(X, 44, W - 8, 44)

        if self.in_game:
            shadow_text(X, 63, "GAME", f_stat_l, _TEXT_MUTED)
            timer_str = _fmt_game_time(self._elapsed_cs())
            p.setFont(f_stat)
            tw = QFontMetrics(f_stat).horizontalAdvance(timer_str)
            shadow_text(W - 8 - tw, 63, timer_str, f_stat, accent)

        p.end()


# ── DotWindow ─────────────────────────────────────────────────────────────────

class DotWindow(QWidget):
    """
    Draggable orb.
      Ctrl + left-drag   → reposition; fires on_moved after each move
      Ctrl + right-click → fires on_context_menu at cursor position
    """

    ORB_X = 14
    ORB_Y = 20
    ORB_R = 7

    def __init__(
        self,
        x: int,
        y: int,
        panel: StatPanel,
        on_context_menu: Callable[[QPoint], None],
        on_moved: Optional[Callable] = None,
    ) -> None:
        super().__init__()
        self._panel           = panel
        self._on_context_menu = on_context_menu
        self._on_moved        = on_moved
        self.in_game          = False
        self.locked           = False
        self._drag_pos: Optional[QPoint] = None

        self.setWindowFlags(_WINDOW_FLAGS)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(40, 40)
        self.move(x, y)
        self.show()

    def paintEvent(self, _) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        accent    = _ACTIVE_ACCENT if self.in_game else _IDLE_ACCENT
        cx, cy, r = self.ORB_X, self.ORB_Y, self.ORB_R

        glow = QColor(accent)
        glow.setAlpha(35)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(glow)
        p.drawEllipse(cx - r - 4, cy - r - 4, (r + 4) * 2, (r + 4) * 2)

        ring_pen = QPen(accent)
        ring_pen.setWidthF(1.6)
        p.setPen(ring_pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(cx - r, cy - r, r * 2, r * 2)

        fill = QColor(accent)
        fill.setAlpha(60)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(fill)
        p.drawEllipse(cx - r + 2, cy - r + 2, (r - 2) * 2, (r - 2) * 2)

        p.end()

    def _sync_panel(self) -> None:
        self._panel.move(self.x() + 46, self.y() - 22)

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
            self._sync_panel()
            if self._on_moved:
                self._on_moved()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag_pos = None


# ── Overlay (implements OverlayBase) ──────────────────────────────────────────

class Overlay(OverlayBase):
    """
    Default D2R Counter overlay style.

    Composed of a draggable orb (DotWindow) and a stat panel (StatPanel).
    The manager owns the timer tick — this class does not start its own.
    """

    def __init__(
        self,
        x: int = OVERLAY_X,
        y: int = OVERLAY_Y,
        on_context_menu: Optional[Callable[[QPoint], None]] = None,
        on_moved: Optional[Callable] = None,
    ) -> None:
        self._panel = StatPanel(0, 0)
        self._dot   = DotWindow(
            x, y,
            self._panel,
            on_context_menu or (lambda pos: None),
            on_moved,
        )
        self._panel.move(x + 46, y - 22)
        self._dot.raise_()

    # ── OverlayBase interface ─────────────────────────────────────────────────

    def on_joined(self) -> None:
        self._dot.in_game = True
        self._panel.on_joined()
        self._dot.update()

    def on_left(self) -> None:
        self._dot.in_game = False
        self._panel.on_left()
        self._dot.update()

    def tick(self) -> None:
        self._panel.tick()

    def get_position(self) -> QPoint:
        return QPoint(self._dot.x(), self._dot.y())

    def move_to(self, pos: QPoint) -> None:
        self._dot.move(pos)
        self._panel.move(pos.x() + 46, pos.y() - 22)

    def set_game_count(self, count: int) -> None:
        self._panel.game_count  = count
        self._panel._game_start = None
        self._panel.in_game     = False
        self._dot.in_game       = False
        self._panel.update()
        self._dot.update()

    def get_game_count(self) -> int:
        return self._panel.game_count

    def set_locked(self, locked: bool) -> None:
        self._dot.locked = locked

    def show(self) -> None:
        self._dot.show()
        self._panel.show()

    def hide(self) -> None:
        self._dot.hide()
        self._panel.hide()

    def is_visible(self) -> bool:
        return self._dot.isVisible()

    def destroy(self) -> None:
        self._panel.close()
        self._dot.close()
        self._panel.deleteLater()
        self._dot.deleteLater()