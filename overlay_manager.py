"""
overlay_manager.py — Central controller for D2R Counter overlays.

Owns:
  • QSystemTrayIcon
  • Right-click context menu (including style switcher submenu)
  • Game signal routing  (signals.joined / signals.left)
  • 50ms tick timer forwarded to the active overlay
  • Hint and stats window lifetimes

Each overlay style is a separate class implementing OverlayBase.
The manager swaps styles at runtime, preserving position and game state.

Usage in main():
    manager = OverlayManager(
        on_hint_dismissed  = stats.mark_hint_shown,
        show_hint_on_start = not stats.hint_shown,
    )
    manager.app.aboutToQuit.connect(stats.on_session_end)
    manager.run()
"""

import sys
from typing import Optional, Callable

from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PyQt6.QtCore import Qt, QTimer, QPoint
from PyQt6.QtGui import QIcon, QAction, QFont, QCursor

from overlay_signals import signals
from overlay_base import OverlayBase

_app = QApplication.instance() or QApplication(sys.argv)

# ── Context menu stylesheet ───────────────────────────────────────────────────

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




# ── Style registry ────────────────────────────────────────────────────────────
#
# Add a new overlay style in two steps:
#   1. Import the class above this block
#   2. Add an entry:  "Display Name": ClassName
#
# Imports are deferred to avoid a circular import at module level —
# overlay.py imports OverlayBase from this file, so this file must
# not import overlay.py at the top level. The registry is populated
# lazily in _get_styles() the first time it is needed.

def _get_styles() -> dict[str, type]:
    from overlay import Overlay as StyleDefault
    # from overlay_pill  import OverlayPill  as StylePill
    # from overlay_ghost import OverlayGhost as StyleGhost
    from overlay_circle import OverlayCircle as StyleCircle
    return {
        "Default": StyleDefault,
        "Circle":  StyleCircle,
        # "Pill":  StylePill,
        # "Ghost": StyleGhost,
    }

DEFAULT_STYLE = "Default"


# ── OverlayManager ────────────────────────────────────────────────────────────

class OverlayManager:
    """
    Central controller. Owns tray, menu, timer, and hint/stats windows.
    Holds exactly one active overlay style at a time and can swap it.
    """

    def __init__(
        self,
        on_hint_dismissed:  Optional[Callable] = None,
        show_hint_on_start: bool = False,
    ) -> None:
        self.app = _app

        self._on_hint_dismissed_cb = on_hint_dismissed
        self._hint_window  = None
        # self._stats_window = None  # wire up when stats_window.py is built

        self._locked       = False
        self._visible      = True
        self._active_style = DEFAULT_STYLE
        self._styles       = _get_styles()

        # ── Start with the default overlay ────────────────────────────────────
        self._overlay: OverlayBase = self._instantiate(DEFAULT_STYLE)

        # ── 50 ms tick — forwarded to whatever overlay is active ──────────────
        self._timer = QTimer()
        self._timer.setInterval(50)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

        # ── System tray ───────────────────────────────────────────────────────
        self._tray = QSystemTrayIcon()
        self._tray.setIcon(QIcon("off.ico"))
        self._tray.setToolTip("D2R Counter  |  Ctrl+right-click overlay for options")
        self._tray.setContextMenu(self._build_tray_menu())
        self._tray.show()

        # ── Game signal routing ───────────────────────────────────────────────
        signals.joined.connect(self._on_joined, Qt.ConnectionType.QueuedConnection)
        signals.left.connect(self._on_left,     Qt.ConnectionType.QueuedConnection)

        # ── Hint on first launch ──────────────────────────────────────────────
        if show_hint_on_start:
            QTimer.singleShot(0, self.show_hint)

    # ── Public interface ──────────────────────────────────────────────────────

    def run(self) -> None:
        _app.setStyle("Fusion")
        _app.exec()

    def show_hint(self) -> None:
        self._show_hint()

    # ── Style switching ───────────────────────────────────────────────────────

    def switch_style(self, name: str) -> None:
        """
        Swap the active overlay to `name`.
        Preserves position, game count, lock state, and visibility.
        """
        if name == self._active_style or name not in self._styles:
            return

        pos         = self._overlay.get_position()
        count       = self._overlay.get_game_count()
        was_visible = self._overlay.is_visible()

        self._overlay.destroy()

        self._active_style = name
        self._overlay = self._instantiate(name, pos=pos)
        self._overlay.set_game_count(count)
        self._overlay.set_locked(self._locked)

        if not was_visible:
            self._overlay.hide()

        # Rebuild tray menu so the style checkmark updates
        self._tray.setContextMenu(self._build_tray_menu())

    def _instantiate(self, name: str, pos: Optional[QPoint] = None) -> OverlayBase:
        """
        Create a fresh overlay of style `name` at `pos`.
        Passes the manager's callbacks so the overlay can trigger the
        context menu and notify the manager when it is dragged.
        """
        if pos is None:
            screen = _app.primaryScreen().geometry()
            pos = QPoint(screen.width() // 2, screen.height() // 2)

        cls = self._styles[name]
        return cls(
            x=pos.x(),
            y=pos.y(),
            on_context_menu=self._show_context_menu,
            on_moved=self._sync_hint_window,
        )

    # ── Timer ─────────────────────────────────────────────────────────────────

    def _tick(self) -> None:
        self._overlay.tick()

    # ── Signal routing ────────────────────────────────────────────────────────

    def _on_joined(self) -> None:
        self._overlay.on_joined()

    def _on_left(self) -> None:
        self._overlay.on_left()

    # ── Context menu (on-screen, Ctrl+right-click) ────────────────────────────

    def _show_context_menu(self, pos: QPoint) -> None:
        self._build_context_menu().exec(pos)

    def _build_context_menu(self) -> QMenu:
        """
        Rebuilt on every open so labels always reflect current state.
        """
        menu = QMenu()
        menu.setStyleSheet(_MENU_QSS)
        menu.setWindowFlags(
            menu.windowFlags() | Qt.WindowType.NoDropShadowWindowHint
        )

        # Header — non-interactive title
        header = QAction("D2R  COUNTER", menu)
        header.setEnabled(False)
        f_hdr = QFont("Segoe UI", 7)
        f_hdr.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2.8)
        header.setFont(f_hdr)
        menu.addAction(header)
        menu.addSeparator()

        # Windows
        menu.addAction("Stats", self._show_stats)
        menu.addAction("Help",  self._show_hint)
        menu.addSeparator()

        # Style switcher submenu (only shown when more than one style exists)
        style_menu = QMenu("Style", menu)
        style_menu.setStyleSheet(_MENU_QSS)
        for name in self._styles:
            act = QAction(name, style_menu)
            act.setCheckable(True)
            act.setChecked(name == self._active_style)
            act.triggered.connect(lambda checked, n=name: self.switch_style(n))
            style_menu.addAction(act)
        menu.addMenu(style_menu)
        menu.addSeparator()

        # Overlay controls
        vis_lbl  = "Hide overlay"     if self._visible else "Show overlay"
        lock_lbl = "Unlock position"  if self._locked  else "Lock position"
        menu.addAction(vis_lbl,          self._toggle_visibility)
        menu.addAction(lock_lbl,         self._toggle_lock)
        menu.addAction("Reset session",  self._reset_session)
        menu.addSeparator()

        quit_act = QAction("Quit", menu)
        quit_act.triggered.connect(_app.quit)
        menu.addAction(quit_act)

        return menu

    # ── Tray menu ─────────────────────────────────────────────────────────────

    def _build_tray_menu(self) -> QMenu:
        menu = QMenu()
        menu.addAction("Stats",         self._show_stats)
        menu.addAction("Help",          self._show_hint)
        menu.addSeparator()
        menu.addAction("Show / Hide",   self._toggle_visibility)
        menu.addAction("Lock position", self._toggle_lock)
        menu.addAction("Reset session", self._reset_session)
        menu.addSeparator()
        for name in self._styles:
            menu.addAction(
                f"Style: {name}",
                lambda n=name: self.switch_style(n)
            )
        menu.addSeparator()
        menu.addAction("Quit", _app.quit)
        return menu

    # ── Actions ───────────────────────────────────────────────────────────────

    def _toggle_visibility(self) -> None:
        if self._visible:
            self._overlay.hide()
        else:
            self._overlay.show()
        self._visible = not self._visible

    def _toggle_lock(self) -> None:
        self._locked = not self._locked
        self._overlay.set_locked(self._locked)

    def _reset_session(self) -> None:
        """Resets the display counter only — all-time stats are never touched."""
        self._overlay.set_game_count(0)

    # ── Hint window ───────────────────────────────────────────────────────────

    def _show_hint(self) -> None:
        from hint import HintWindow
        if self._hint_window and self._hint_window.isVisible():
            self._hint_window.raise_()
            self._hint_window.activateWindow()
            return
        self._hint_window = HintWindow(
            on_dismiss=self._on_hint_dismissed,
            anchor=self._overlay.get_position(),
        )
        self._hint_window.show()

    def _sync_hint_window(self) -> None:
        """Called on every orb drag tick — keeps hint pinned above the overlay."""
        if self._hint_window and self._hint_window.isVisible():
            self._hint_window.reposition(self._overlay.get_position())

    def _on_hint_dismissed(self) -> None:
        if self._on_hint_dismissed_cb:
            self._on_hint_dismissed_cb()

    # ── Stats window ──────────────────────────────────────────────────────────

    def _show_stats(self) -> None:
        pass  # wire up when stats_window.py is built