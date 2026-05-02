import sys
import time
from typing import Optional

try:
    from PyQt6.QtWidgets import QApplication, QWidget, QSystemTrayIcon, QMenu
    from PyQt6.QtCore import Qt, QObject, pyqtSignal, QPoint, QTimer
    from PyQt6.QtGui import (
        QPainter, QColor, QFont, QFontMetrics,
        QMouseEvent, QIcon, QPen
    )
except ImportError:
    raise

_app = QApplication.instance() or QApplication(sys.argv)
screen = QApplication.primaryScreen().geometry()
OVERLAY_X = int(screen.width() / 2)
OVERLAY_Y = int(screen.height() / 2)


class GameSignals(QObject):
    joined = pyqtSignal()
    left   = pyqtSignal()


signals = GameSignals()

_WINDOW_FLAGS = (
    Qt.WindowType.FramelessWindowHint      |
    Qt.WindowType.WindowStaysOnTopHint     |
    Qt.WindowType.Tool                     |
    Qt.WindowType.NoDropShadowWindowHint
)

# ── Colors ────────────────────────────────────────────────────────────────────

_IDLE_ACCENT   = QColor("#387CBC")
_ACTIVE_ACCENT = QColor("#9C10C8")

_BG            = QColor(14, 14, 14, 210)
_BORDER        = QColor(255, 255, 255, 14)
_TEXT_PRIMARY  = QColor(255, 255, 255, 220)
_TEXT_MUTED    = QColor(255, 255, 255, 80)
_TEXT_DIM      = QColor(255, 255, 255, 40)


def _fmt_game_time(centiseconds: int) -> str:
    """
    Format centiseconds as H:MM:SS:cs.
    Hours are omitted until needed (most games won't exceed 59:59).
      e.g.  00:04:23   →  no run yet / idle placeholder
            03:47:cs   →  active short game
            1:02:14:09 →  long game with hours
    """
    cs        = centiseconds % 100
    total_s   = centiseconds // 100
    h, rem    = divmod(total_s, 3600)
    m, s      = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}:{cs:02d}"
    return f"{m:02d}:{s:02d}:{cs:02d}"


# ── StatPanel ─────────────────────────────────────────────────────────────────

class StatPanel(QWidget):
    """
    Transparent-input panel showing:
      ├ accent bar   (left edge, idle=blue / active=purple)
      ├ top row:     count + "GAMES" label
      ├ divider
      └ timer row:   live H:MM:SS:cs — visible only when in-game,
                     hidden (empty space) when idle
    """

    W = 160   # slightly wider to fit H:MM:SS:cs comfortably
    H = 74

    def __init__(self, x: int, y: int) -> None:
        super().__init__()
        self.game_count    = 0
        self.in_game       = False
        self._game_start:  Optional[float] = None   # monotonic timestamp

        self.setWindowFlags(_WINDOW_FLAGS | Qt.WindowType.WindowTransparentForInput)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(self.W, self.H)
        self.move(x, y)
        self.show()

    # ── Public interface ──────────────────────────────────────────────────────

    def tick(self) -> None:
        """Called every 50 ms. Only schedules a repaint when in-game."""
        if self.in_game:
            self.update()

    def on_joined(self) -> None:
        self.in_game      = True
        self.game_count  += 1
        self._game_start  = time.monotonic()
        self.update()

    def on_left(self) -> None:
        self.in_game     = False
        self._game_start = None
        self.update()

    # ── Computed centiseconds from wall clock ─────────────────────────────────

    def _elapsed_cs(self) -> int:
        if self._game_start is None:
            return 0
        return int((time.monotonic() - self._game_start) * 100)

    # ── Paint ─────────────────────────────────────────────────────────────────

    def paintEvent(self, _) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        accent = _ACTIVE_ACCENT if self.in_game else _IDLE_ACCENT
        W, H   = self.W, self.H
        BAR    = 3
        PAD    = 10
        R      = 6

        # background
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_BG)
        p.drawRoundedRect(0, 0, W, H, R, R)

        # border
        pen = QPen(_BORDER)
        pen.setWidthF(0.8)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(0, 0, W - 1, H - 1, R, R)

        # accent bar
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(accent)
        p.drawRoundedRect(0, 0, BAR * 2, H, R, R)
        p.fillRect(BAR, 0, BAR, H, accent)

        X = BAR + PAD

        # ── fonts ─────────────────────────────────────────────────────────────
        f_count  = QFont("Segoe UI", 22, QFont.Weight.Bold)
        f_label  = QFont("Segoe UI", 8)
        f_label.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.4)
        f_stat   = QFont("Consolas", 11, QFont.Weight.Bold)   # monospaced for timer
        f_stat_l = QFont("Segoe UI", 7)
        f_stat_l.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.2)

        def shadow_text(px, py, text, font, color):
            p.setFont(font)
            p.setPen(QColor(0, 0, 0, 120))
            p.drawText(px + 1, py + 1, text)
            p.setPen(color)
            p.drawText(px, py, text)

        # ── count ─────────────────────────────────────────────────────────────
        count_str = str(self.game_count)
        p.setFont(f_count)
        fm_count  = QFontMetrics(f_count)
        count_w   = fm_count.horizontalAdvance(count_str)
        shadow_text(X, 36, count_str, f_count, _TEXT_PRIMARY)

        # ── label beside count ────────────────────────────────────────────────
        lbl = "IN GAME" if self.in_game else "GAMES"
        shadow_text(X + count_w + 7, 28, lbl, f_label, accent)

        # ── divider ───────────────────────────────────────────────────────────
        div_pen = QPen(_TEXT_DIM)
        div_pen.setWidthF(0.6)
        p.setPen(div_pen)
        p.drawLine(X, 44, W - 8, 44)

        # ── in-game timer (hidden when idle) ──────────────────────────────────
        if self.in_game:
            TIMER_Y = 63

            shadow_text(X, TIMER_Y, "GAME", f_stat_l, _TEXT_MUTED)

            timer_str = _fmt_game_time(self._elapsed_cs())
            p.setFont(f_stat)
            fm_t = QFontMetrics(f_stat)
            tw   = fm_t.horizontalAdvance(timer_str)
            shadow_text(W - 8 - tw, TIMER_Y, timer_str, f_stat, accent)

        p.end()


# ── DotWindow ─────────────────────────────────────────────────────────────────

class DotWindow(QWidget):
    """
    Draggable orb — Ctrl+drag to reposition.
    Outer glow ring + filled circle, color tracks game state.
    """

    ORB_X = 14
    ORB_Y = 20
    ORB_R = 7

    def __init__(self, x: int, y: int, panel: StatPanel) -> None:
        super().__init__()
        self._panel    = panel
        self.in_game   = False
        self.locked    = False
        self._drag_pos: Optional[QPoint] = None

        self.setWindowFlags(_WINDOW_FLAGS)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(40, 40)
        self.move(x, y)
        self.show()

    def paintEvent(self, _) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        accent = _ACTIVE_ACCENT if self.in_game else _IDLE_ACCENT
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
        if event.button() == Qt.MouseButton.LeftButton:
            ctrl = event.modifiers() & Qt.KeyboardModifier.ControlModifier
            if not self.locked and ctrl:
                self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_pos and event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            self._sync_panel()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag_pos = None


# ── Overlay ───────────────────────────────────────────────────────────────────

class Overlay:
    """Owns the orb, stat panel, tick timer, and system tray."""

    def __init__(self, x: int = OVERLAY_X, y: int = OVERLAY_Y) -> None:
        self.app    = _app   # exposed so detector can connect aboutToQuit

        self._panel = StatPanel(0, 0)
        self._dot   = DotWindow(x, y, self._panel)
        self._panel.move(x + 46, y - 22)
        self._dot.raise_()

        # 50 ms tick — smooth centisecond display, negligible CPU
        self._timer = QTimer()
        self._timer.setInterval(50)
        self._timer.timeout.connect(self._panel.tick)
        self._timer.start()

        # ── Tray ──────────────────────────────────────────────────────────────
        self._tray = QSystemTrayIcon()
        self._tray.setIcon(QIcon("off.ico"))
        self._tray.setToolTip("D2R Session Tracker  |  Ctrl+drag orb to move")

        menu = QMenu()
        menu.addAction("Show / Hide",    self._toggle_visibility)
        menu.addSeparator()
        self._lock_action = menu.addAction("Lock position", self._toggle_lock)
        menu.addSeparator()
        menu.addAction("Reset session",  self._reset_session)
        menu.addSeparator()
        menu.addAction("Quit", _app.quit)

        self._tray.setContextMenu(menu)
        self._tray.show()

        signals.joined.connect(self._on_joined, Qt.ConnectionType.QueuedConnection)
        signals.left.connect(self._on_left,     Qt.ConnectionType.QueuedConnection)

    def run(self) -> None:
        _app.setStyle("Fusion")
        _app.exec()

    # ── Signal handlers ───────────────────────────────────────────────────────

    def _on_joined(self) -> None:
        self._dot.in_game = True
        self._panel.on_joined()
        self._dot.update()

    def _on_left(self) -> None:
        self._dot.in_game = False
        self._panel.on_left()
        self._dot.update()

    # ── Tray actions ──────────────────────────────────────────────────────────

    def _toggle_visibility(self) -> None:
        vis = self._dot.isVisible()
        self._dot.setVisible(not vis)
        self._panel.setVisible(not vis)

    def _toggle_lock(self) -> None:
        self._dot.locked = not self._dot.locked
        self._lock_action.setText(
            "Unlock position" if self._dot.locked else "Lock position"
        )

    def _reset_session(self) -> None:
        """Resets the display counter only — all-time stats are unaffected."""
        self._panel.game_count   = 0
        self._panel._game_start  = None
        self._panel.in_game      = False
        self._dot.in_game        = False
        self._panel.update()
        self._dot.update()