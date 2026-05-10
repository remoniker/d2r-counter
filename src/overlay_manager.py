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
        on_hint_dismissed  = config.mark_hint_shown,
        show_hint_on_start = not config.hint_shown,
    )
    manager.app.aboutToQuit.connect(stats.on_session_end)
    manager.run()
"""

import os
import sys
from typing import Optional, Callable

from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QDialog, QSpinBox, QPushButton, QLabel
from PyQt6.QtCore import Qt, QTimer, QPoint, QObject, pyqtSignal
from PyQt6.QtGui import QIcon, QAction, QFont, QCursor, QPainter, QPen, QMouseEvent

from theme import GOLD, BG, DIVIDER, MENU_QSS, SPINBOX_QSS, DIALOG_BTN_QSS, DIALOG_FLAGS, POPUP_FLAGS


class _GameSignals(QObject):
    joined = pyqtSignal()
    left   = pyqtSignal()

signals = _GameSignals()

_app = QApplication.instance() or QApplication(sys.argv)





def _resource(name: str) -> str:
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, name)
    # Running from source: assets/ is at project root, one level above src/
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(root, "assets", name)


def _get_styles() -> dict[str, type]:
    from overlay import Overlay
    return {"Default": Overlay}

DEFAULT_STYLE = "Default"

# ── Set-count dialog ──────────────────────────────────────────────────────────

_DW, _DH, _DR = 240, 112, 8


class _SetCountDialog(QDialog):
    def __init__(self, current: int) -> None:
        super().__init__(None)
        self._drag_pos: Optional[QPoint] = None

        self.setWindowFlags(DIALOG_FLAGS)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(_DW, _DH)

        self._build_ui(current)
        screen = QApplication.primaryScreen().geometry()
        self.move(
            (screen.width()  - _DW) // 2,
            (screen.height() - _DH) // 2,
        )

    def _build_ui(self, current: int) -> None:
        title = QLabel("SET COUNTER", self)
        title.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        f = QFont("Segoe UI", 8)
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2.0)
        title.setFont(f)
        title.setStyleSheet(f"color: {GOLD.name()}; background: transparent;")
        title.move(14, 12)
        title.adjustSize()

        self._spin = QSpinBox(self)
        self._spin.setRange(0, 99999)
        self._spin.setValue(current)
        self._spin.setFixedSize(212, 28)
        self._spin.move(14, 36)
        self._spin.setStyleSheet(SPINBOX_QSS)

        ok = QPushButton("OK", self)
        ok.setFixedSize(100, 26)
        ok.move(14, 74)
        ok.setCursor(Qt.CursorShape.PointingHandCursor)
        ok.setStyleSheet(DIALOG_BTN_QSS)
        ok.clicked.connect(self.accept)

        cancel = QPushButton("Cancel", self)
        cancel.setFixedSize(100, 26)
        cancel.move(126, 74)
        cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel.setStyleSheet(DIALOG_BTN_QSS)
        cancel.clicked.connect(self.reject)

    def get_value(self) -> Optional[int]:
        if self.exec() == QDialog.DialogCode.Accepted:
            return self._spin.value()
        return None

    def paintEvent(self, _) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(BG)
        p.drawRoundedRect(0, 0, _DW, _DH, _DR, _DR)

        pen = QPen(GOLD)
        pen.setWidthF(1.0)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(0, 0, _DW - 1, _DH - 1, _DR, _DR)

        div = QPen(DIVIDER)
        div.setWidthF(0.8)
        p.setPen(div)
        p.drawLine(14, 30, _DW - 14, 30)

        p.end()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = (
                event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            )

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_pos and event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, _: QMouseEvent) -> None:
        self._drag_pos = None


# ── OverlayManager ────────────────────────────────────────────────────────────

class OverlayManager:
    """
    Central controller. Owns tray, menu, timer, and hint/stats windows.
    Holds exactly one active overlay style at a time and can swap it.
    """

    def __init__(
        self,
        on_hint_dismissed:     Optional[Callable]       = None,
        show_hint_on_start:    bool                     = False,
        initial_count:         int                      = 0,
        continue_from_last:    bool                     = False,
        on_counter_saved:      Optional[Callable[[int], None]]       = None,
        on_continue_toggled:   Optional[Callable[[bool], None]]      = None,
        initial_pos:           Optional[tuple[int, int]]             = None,
    ) -> None:
        self.app = _app

        self._on_hint_dismissed_cb  = on_hint_dismissed
        self._on_counter_saved_cb   = on_counter_saved
        self._on_continue_toggled_cb = on_continue_toggled
        self._continue_from_last    = continue_from_last

        self._hint_window  = None
        self._stats_window = None
        self._about_window = None

        self._visible      = True
        self._active_style = DEFAULT_STYLE
        self._styles       = _get_styles()

        # ── Start with the default overlay ────────────────────────────────────
        saved_pos = None
        if initial_pos is not None:
            p = QPoint(initial_pos[0], initial_pos[1])
            if _app.primaryScreen().geometry().contains(p):
                saved_pos = p
        self._overlay = self._instantiate(DEFAULT_STYLE, pos=saved_pos)
        if initial_count:
            self._overlay.set_game_count(initial_count)
        self._overlay.hide()
        QTimer.singleShot(0, self._overlay.show)

        # ── 50 ms tick — forwarded to whatever overlay is active ──────────────
        self._timer = QTimer()
        self._timer.setInterval(50)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

        # ── System tray ───────────────────────────────────────────────────────
        self._tray = QSystemTrayIcon()
        self._tray.setIcon(QIcon(_resource("off.ico")))
        self._tray.setToolTip("D2R Counter  |  Ctrl+right-click overlay for options")
        self._tray.setContextMenu(self._build_tray_menu())
        self._tray.show()

        # ── Game signal routing ───────────────────────────────────────────────
        signals.joined.connect(self._on_joined,          Qt.ConnectionType.QueuedConnection)
        signals.left.connect(self._on_left,              Qt.ConnectionType.QueuedConnection)
        signals.joined.connect(self._refresh_stats_window, Qt.ConnectionType.QueuedConnection)
        signals.left.connect(self._refresh_stats_window,   Qt.ConnectionType.QueuedConnection)

        # ── Hint on first launch ──────────────────────────────────────────────
        if show_hint_on_start:
            QTimer.singleShot(0, self.show_hint)

    # ── Public interface ──────────────────────────────────────────────────────

    def run(self) -> None:
        _app.setStyle("Fusion")
        _app.setQuitOnLastWindowClosed(False)
        _app.exec()

    def show_hint(self) -> None:
        self._show_hint()

    def get_overlay_position(self) -> tuple[int, int]:
        p = self._overlay.get_position()
        return (p.x(), p.y())

    def _instantiate(self, name: str, pos: Optional[QPoint] = None):
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
        if self._on_counter_saved_cb:
            self._on_counter_saved_cb(self._overlay.get_game_count())

    # ── Context menu (on-screen, Ctrl+right-click) ────────────────────────────

    def _show_context_menu(self, pos: QPoint) -> None:
        self._build_context_menu().exec(pos)

    def _build_context_menu(self) -> QMenu:
        """
        Rebuilt on every open so labels always reflect current state.
        """
        menu = QMenu()
        menu.setWindowFlags(POPUP_FLAGS)
        menu.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        menu.setStyleSheet(MENU_QSS)

        # Header — non-interactive title
        header = QAction("D2R  COUNTER", menu)
        header.setEnabled(False)
        f_hdr = QFont("Segoe UI", 7)
        f_hdr.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2.8)
        header.setFont(f_hdr)
        menu.addAction(header)
        menu.addSeparator()

        # Windows
        menu.addAction("Hint",       self._show_hint)
        menu.addAction("About",      self._show_about)
        menu.addAction("Statistics", self._show_stats)
        menu.addSeparator()

        # Overlay controls
        vis_lbl = "Hide overlay" if self._visible else "Show overlay"
        menu.addAction(vis_lbl,      self._toggle_visibility)
        menu.addAction("Set count…", self._set_count)
        menu.addSeparator()

        # Persistence toggle
        cont_act = QAction("Remember count", menu)
        cont_act.setCheckable(True)
        cont_act.setChecked(self._continue_from_last)
        cont_act.triggered.connect(self._toggle_continue_from_last)
        menu.addAction(cont_act)
        menu.addSeparator()

        quit_act = QAction("Quit", menu)
        quit_act.triggered.connect(_app.quit)
        menu.addAction(quit_act)

        return menu

    # ── Tray menu ─────────────────────────────────────────────────────────────

    def _build_tray_menu(self) -> QMenu:
        menu = QMenu()

        menu.addAction("Hint",          self._show_hint)
        menu.addAction("About",         self._show_about)
        menu.addAction("Statistics",    self._show_stats)
        menu.addSeparator()

        vis_lbl = "Hide overlay" if self._visible else "Show overlay"
        menu.addAction(vis_lbl,         self._toggle_visibility)
        menu.addAction("Set count…",    self._set_count)
        menu.addSeparator()

        cont_act = QAction("Remember count", menu)
        cont_act.setCheckable(True)
        cont_act.setChecked(self._continue_from_last)
        cont_act.triggered.connect(self._toggle_continue_from_last)
        menu.addAction(cont_act)
        menu.addSeparator()

        menu.addAction("Quit", _app.quit)
        return menu

    # ── Actions ───────────────────────────────────────────────────────────────

    def _show_about(self) -> None:
        from about import AboutWindow
        if self._about_window and self._about_window.isVisible():
            self._about_window.raise_()
            self._about_window.activateWindow()
            return
        self._about_window = AboutWindow()
        self._about_window.show()

    def _toggle_visibility(self) -> None:
        if self._visible:
            self._overlay.hide()
        else:
            self._overlay.show()
        self._visible = not self._visible
        self._tray.setContextMenu(self._build_tray_menu())

    def _set_count(self) -> None:
        n = _SetCountDialog(self._overlay.get_game_count()).get_value()
        if n is not None:
            self._overlay.set_game_count(n)
            if self._on_counter_saved_cb:
                self._on_counter_saved_cb(n)

    def _toggle_continue_from_last(self) -> None:
        self._continue_from_last = not self._continue_from_last
        if self._on_continue_toggled_cb:
            self._on_continue_toggled_cb(self._continue_from_last)
        self._tray.setContextMenu(self._build_tray_menu())

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
        from stats import StatsWindow
        if self._stats_window and self._stats_window.isVisible():
            self._stats_window.raise_()
            self._stats_window.activateWindow()
            return
        self._stats_window = StatsWindow()
        self._stats_window.show()

    def _refresh_stats_window(self) -> None:
        if self._stats_window and self._stats_window.isVisible():
            self._stats_window.refresh()

