"""
hint.py — Typewriter hint for D2R Counter.

A fully transparent frameless window — no background, no border,
no chrome. Just two lines of blue monospaced text that type themselves
in 2-3 characters at a time, then sit until the user does their first
Ctrl+click anywhere on screen, at which point the window closes.

Also auto-dismisses after AUTO_DISMISS_SECS as a fallback.

Positioning: placed below the anchor point (orb top-left) passed in
from OverlayManager, so it sits just beneath the overlay.
"""

from typing import Callable, Optional

from PyQt6.QtWidgets import QApplication, QWidget, QLabel
from PyQt6.QtCore import Qt, QPoint, QTimer, QObject, QEvent
from PyQt6.QtGui import QFont, QColor, QMouseEvent, QPainter, QPen

# ── Config ────────────────────────────────────────────────────────────────────

LINE_1 = "ctrl+drag to move"
LINE_2 = "ctrl+right for menu"

CHARS_PER_TICK  = 2       # characters revealed per timer tick
TICK_MS         = 55      # ms between ticks — full line in ~500ms
LINE_PAUSE_MS   = 300     # pause between line 1 finishing and line 2 starting
AUTO_DISMISS_SECS = 14    # fallback auto-dismiss

# ── Geometry ──────────────────────────────────────────────────────────────────

ORB_DX   = 10       # offset from anchor.x() to window left edge (≈ orb center)
LINE_X   = 195      # x of vertical line within window
TEXT_X   = 200      # x of text within window  (anchor.x()+ORB_DX+TEXT_X ≈ anchor.x()+170)
W        = TEXT_X + 220   # total width — right section holds the text
H        = 60   # tall enough for line to reach near orb center below

LINE_1_Y = 8
LINE_2_Y = 30

ORB_H    = 40    # DotWindow height — used to compute gap above orb
GAP_Y    = 50    # px above anchor.y() for window top

# ── Colors ────────────────────────────────────────────────────────────────────

_BLUE_1 = "#4a9fd4"              # first line  — brighter
_BLUE_2 = "#2d6fa0"              # second line — dimmer
_LINE_C = QColor(45, 111, 160, 255)   # vertical line — same blue, semi-transparent

# ── Window flags ──────────────────────────────────────────────────────────────

_FLAGS = (
    Qt.WindowType.FramelessWindowHint   |
    Qt.WindowType.WindowStaysOnTopHint  |
    Qt.WindowType.Tool                  |
    Qt.WindowType.NoDropShadowWindowHint
)


# ── Global Ctrl+click watcher ─────────────────────────────────────────────────

class _CtrlClickFilter(QObject):
    """
    Application-level event filter. Watches for any mouse press
    where Ctrl is held, then fires the dismiss callback once and
    removes itself.
    """

    def __init__(self, on_ctrl_click: Callable) -> None:
        super().__init__()
        self._cb = on_ctrl_click
        QApplication.instance().installEventFilter(self)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.MouseButtonPress:
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                QApplication.instance().removeEventFilter(self)
                self._cb()
        return False   # never consume — pass event through normally


# ── HintWindow ────────────────────────────────────────────────────────────────

class HintWindow(QWidget):
    """
    Transparent typewriter hint window.

    Parameters
    ----------
    on_dismiss:
        Called once when the window closes for any reason.
        Typically stats.mark_hint_shown().
    anchor:
        QPoint(dot.x(), dot.y()) — top-left of the orb window.
        The hint is placed GAP_BELOW px below the orb's bottom edge.
    """

    def __init__(
        self,
        on_dismiss: Callable[[], None],
        anchor: Optional[QPoint] = None,
    ) -> None:
        super().__init__()
        self._on_dismiss  = on_dismiss
        self._dismissed   = False
        self._filter: Optional[_CtrlClickFilter] = None

        self.setWindowFlags(_FLAGS)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setFixedSize(W, H)

        # ── Labels ────────────────────────────────────────────────────────────
        f = QFont("Consolas", 10)

        self._lbl1 = QLabel("", self)
        self._lbl1.setFont(f)
        self._lbl1.setStyleSheet(
            f"color: {_BLUE_1}; background: transparent;"
        )
        self._lbl1.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._lbl1.move(TEXT_X, LINE_1_Y)
        self._lbl1.setFixedWidth(W - TEXT_X)

        self._lbl2 = QLabel("", self)
        self._lbl2.setFont(f)
        self._lbl2.setStyleSheet(
            f"color: {_BLUE_2}; background: transparent;"
        )
        self._lbl2.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._lbl2.move(TEXT_X, LINE_2_Y)
        self._lbl2.setFixedWidth(W - TEXT_X)

        # ── Typewriter state ──────────────────────────────────────────────────
        self._pos     = 0        # chars revealed so far in current line
        self._phase   = 1        # 1 = typing line 1, 2 = typing line 2

        self._ticker = QTimer(self)
        self._ticker.setInterval(TICK_MS)
        self._ticker.timeout.connect(self._tick)

        # ── Auto-dismiss ──────────────────────────────────────────────────────
        self._auto = QTimer(self)
        self._auto.setSingleShot(True)
        self._auto.setInterval(AUTO_DISMISS_SECS * 1000)
        self._auto.timeout.connect(self._dismiss)

        # ── Ctrl+click watcher ────────────────────────────────────────────────
        self._filter = _CtrlClickFilter(self._dismiss)

        # ── Position ──────────────────────────────────────────────────────────
        if anchor is not None:
            self._place(anchor)
        else:
            self._center_on_screen()

    # ── Show override — start typing when visible ─────────────────────────────

    def show(self) -> None:
        super().show()
        self._ticker.start()
        self._auto.start()

    # ── Typewriter tick ───────────────────────────────────────────────────────

    def _tick(self) -> None:
        if self._phase == 1:
            self._pos = min(self._pos + CHARS_PER_TICK, len(LINE_1))
            self._lbl1.setText(LINE_1[:self._pos])
            if self._pos >= len(LINE_1):
                self._ticker.stop()
                # Pause then start line 2
                QTimer.singleShot(LINE_PAUSE_MS, self._start_line2)

        elif self._phase == 2:
            self._pos = min(self._pos + CHARS_PER_TICK, len(LINE_2))
            self._lbl2.setText(LINE_2[:self._pos])
            if self._pos >= len(LINE_2):
                self._ticker.stop()
                # Done — just sit and wait for Ctrl+click or auto-dismiss

    def _start_line2(self) -> None:
        if self._dismissed:
            return
        self._phase = 2
        self._pos   = 0
        self._ticker.start()

    # ── Dismiss ───────────────────────────────────────────────────────────────

    def _dismiss(self) -> None:
        if self._dismissed:
            return
        self._dismissed = True
        self._ticker.stop()
        self._auto.stop()
        # Filter removes itself on first Ctrl+click, but clean up if
        # we're dismissing via auto-timer before a Ctrl+click occurs
        if self._filter is not None:
            try:
                QApplication.instance().removeEventFilter(self._filter)
            except RuntimeError:
                pass
            self._filter = None
        self._on_dismiss()
        self.close()

    # ── paintEvent — intentionally empty to keep window transparent ───────────

    def paintEvent(self, _) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Vertical line rising from orb — drawn at LINE_X, full window height
        pen = QPen(_LINE_C)
        pen.setWidthF(1.0)
        p.setPen(pen)
        p.drawLine(LINE_X, 0, LINE_X, H)

        p.end()

    # ── Positioning ───────────────────────────────────────────────────────────

    def _place(self, anchor: QPoint) -> None:
        """
        Window left edge pinned to orb x center (anchor.x() + ORB_DX).
        Window top placed GAP_Y px above orb top so the line runs from
        text level down to just above the orb.
        """
        x = anchor.x() + ORB_DX
        y = anchor.y() - GAP_Y
        screen = QApplication.primaryScreen().geometry()
        x = max(0, min(x, screen.width()  - W))
        y = max(0, min(y, screen.height() - H))
        self.move(x, y)

    def reposition(self, anchor: QPoint) -> None:
        """Called by manager when the orb is dragged."""
        if not self._dismissed:
            self._place(anchor)

    def _center_on_screen(self) -> None:
        screen = QApplication.primaryScreen().geometry()
        self.move(
            (screen.width()  - W) // 2,
            (screen.height() - H) // 2,
        )