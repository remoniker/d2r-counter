import sys
import time
from typing import Optional, Callable

from hint import HintWindow

try:
    from PyQt6.QtWidgets import (
        QApplication, QWidget, QSystemTrayIcon, QMenu
    )
    from PyQt6.QtCore import Qt, QObject, pyqtSignal, QPoint, QTimer
    from PyQt6.QtGui import (
        QPainter, QColor, QFont, QFontMetrics,
        QMouseEvent, QIcon, QPen, QCursor, QAction
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

# ── Context menu stylesheet ───────────────────────────────────────────────────
#
# Matches the overlay's dark glass aesthetic:
#   • Near-black solid background (rgba is unreliable in QSS menus on Windows)
#   • Blue accent left-border strip on hover — matches idle orb color
#   • Disabled header item acts as a non-interactive section title
#   • Separators are single-pixel dim lines with horizontal margin
#   • Items have vertical breathing room and rounded corners
#
_MENU_QSS = """
QMenu {
    background-color: rgb(14, 14, 14);
    border: 1px solid rgb(48, 48, 48);
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

QMenu::item:pressed {
    background-color: rgba(56, 124, 188, 60);
}

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

_MENU_HEADER = "D2R  TRACKER"


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

        accent     = _ACTIVE_ACCENT if self.in_game else _IDLE_ACCENT
        W, H       = self.W, self.H
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
      Ctrl + left-drag   → reposition
      Ctrl + right-click → open styled on-screen context menu at cursor
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


# ── Overlay ───────────────────────────────────────────────────────────────────

class Overlay:
    """Owns the orb, stat panel, tick timer, and system tray."""

    def __init__(
        self,
        x: int = OVERLAY_X,
        y: int = OVERLAY_Y,
        on_hint_dismissed: Optional[Callable] = None,
        show_hint_on_start: bool = False
    ) -> None:
       
        self.app    = _app  # exposed so detector can connect aboutToQuit
        self._locked = False
        self._hint_dismissed_cb = on_hint_dismissed
        self._hint_window: Optional[HintWindow] = None

        self._panel = StatPanel(0, 0)
        self._dot   = DotWindow(x, y, self._panel, self._show_context_menu, self._sync_hint_window)
        self._panel.move(x + 46, y - 22)
        self._dot.raise_()

        self._timer = QTimer()
        self._timer.setInterval(50)
        self._timer.timeout.connect(self._panel.tick)
        self._timer.start()

        # ── Tray (secondary access, same actions) ─────────────────────────────
        self._tray = QSystemTrayIcon()
        self._tray.setIcon(QIcon("off.ico"))
        self._tray.setToolTip("D2R Session Tracker  |  Ctrl+right-click orb for options")
        self._tray.setContextMenu(self._build_tray_menu())
        self._tray.show()

        signals.joined.connect(self._on_joined, Qt.ConnectionType.QueuedConnection)
        signals.left.connect(self._on_left,     Qt.ConnectionType.QueuedConnection)

        if show_hint_on_start:
            QTimer.singleShot(0, self._show_hint)

    def run(self) -> None:
        _app.setStyle("Fusion")
        _app.exec()

    # ── On-screen context menu ────────────────────────────────────────────────

    def _show_context_menu(self, pos: QPoint) -> None:
        self._build_context_menu().exec(pos)

    def _build_context_menu(self) -> QMenu:
        """
        Styled on-screen menu. Rebuilt on every call so labels always
        reflect current state (visible/hidden, locked/unlocked).
        """
        menu = QMenu()
        menu.setStyleSheet(_MENU_QSS)
        menu.setWindowFlags(
            menu.windowFlags() | Qt.WindowType.NoDropShadowWindowHint
        )

        # ── Non-interactive header ────────────────────────────────────────────
        header = QAction(_MENU_HEADER, menu)
        header.setEnabled(False)
        f_hdr = QFont("Segoe UI", 7)
        f_hdr.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2.8)
        header.setFont(f_hdr)
        menu.addAction(header)
        menu.addSeparator()

        # ── Windows ───────────────────────────────────────────────────────────
        menu.addAction("Stats",  self._show_stats)
        menu.addAction("Help",   self._show_hint)
        menu.addSeparator()

        # ── Overlay controls ──────────────────────────────────────────────────
        vis_lbl = "Hide overlay" if self._dot.isVisible() else "Show overlay"
        menu.addAction(vis_lbl, self._toggle_visibility)

        lock_lbl = "Unlock position" if self._locked else "Lock position"
        menu.addAction(lock_lbl, self._toggle_lock)

        menu.addAction("Reset session", self._reset_session)
        menu.addSeparator()

        # ── Quit ─────────────────────────────────────────────────────────────
        quit_act = QAction("Quit", menu)
        f_quit = QFont("Segoe UI", 9)
        quit_act.setFont(f_quit)
        quit_act.triggered.connect(_app.quit)
        menu.addAction(quit_act)

        return menu

    # ── Tray menu (minimal mirror) ────────────────────────────────────────────

    def _build_tray_menu(self) -> QMenu:
        menu = QMenu()
        menu.addAction("Stats",         self._show_stats)
        menu.addAction("Help",          self._show_hint)
        menu.addSeparator()
        menu.addAction("Show / Hide",   self._toggle_visibility)
        menu.addAction("Lock position", self._toggle_lock)
        menu.addAction("Reset session", self._reset_session)
        menu.addSeparator()
        menu.addAction("Quit",          _app.quit)
        return menu

    # ── Signal handlers ───────────────────────────────────────────────────────

    def _on_joined(self) -> None:
        self._dot.in_game = True
        self._panel.on_joined()
        self._dot.update()

    def _on_left(self) -> None:
        self._dot.in_game = False
        self._panel.on_left()
        self._dot.update()

    # ── Actions ───────────────────────────────────────────────────────────────

    def _toggle_visibility(self) -> None:
        vis = self._dot.isVisible()
        self._dot.setVisible(not vis)
        self._panel.setVisible(not vis)

    def _toggle_lock(self) -> None:
        self._locked     = not self._locked
        self._dot.locked = self._locked

    def _reset_session(self) -> None:
        """Resets display counter only — all-time stats are never touched."""
        self._panel.game_count  = 0
        self._panel._game_start = None
        self._panel.in_game     = False
        self._dot.in_game       = False
        self._panel.update()
        self._dot.update()

    def _show_stats(self) -> None:
        """Placeholder — wired up when stats_window.py is implemented."""
        pass

    def show_hint(self) -> None:
        """Public — called from main() on first launch."""
        QTimer.singleShot(0, self._show_hint)
        self._show_hint()

    def _show_hint(self) -> None:
        """Open the hint window above the orb. If already open, bring it to front."""
        if self._hint_window and self._hint_window.isVisible():
            self._hint_window.raise_()
            self._hint_window.activateWindow()
            return
        # Anchor = top-left of dot window so hint left edge aligns with overlay left edge
        anchor = QPoint(self._dot.x(), self._dot.y())
        self._hint_window = HintWindow(on_dismiss=self._on_hint_dismissed, anchor=anchor)
        self._hint_window.show()

    def _sync_hint_window(self) -> None:
        """Called on every orb drag tick — keeps hint pinned above the overlay."""
        if self._hint_window and self._hint_window.isVisible():
            self._hint_window.reposition(QPoint(self._dot.x(), self._dot.y()))

    def _on_hint_dismissed(self) -> None:
        if self._hint_dismissed_cb:
            self._hint_dismissed_cb()