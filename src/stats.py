"""
stats_window.py — All-time stats popup for D2R Counter.

Reads directly from stats.json on open so it always shows
current data. Draggable from anywhere, centered on screen.
Close with × button.

Opened from the system tray or Ctrl+right-click menu.
"""

import json
import os
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
PAD_T = 14    # top padding before header

# Row layout
ROW_H       = 22   # height per stat row
SECTION_GAP = 10   # gap between sections
HEADER_H    = 42   # space for title + divider

# Sections and their rows — built dynamically so H is computed from content
_SECTIONS = [
    ("THIS SESSION", [
        "session_games",
        "runs_per_hour",
        "session_game_seconds",
    ]),
    ("ALL TIME", [
        "total_games",
        "avg_game_duration",
        "total_game_seconds",
        "total_sessions",
        "longest_game_seconds",
        "most_games_in_session",
        "unique_servers",
        "first_game_at",
        "last_game_at",
    ]),
]

def _compute_height() -> int:
    h = PAD_T + HEADER_H
    for label, rows in _SECTIONS:
        h += ROW_H          # section header row
        h += len(rows) * ROW_H
        h += SECTION_GAP
    h += 14                 # bottom padding
    return h

H = _compute_height()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fmt_duration(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    h, rem = divmod(int(seconds), 3600)
    m, s   = divmod(rem, 60)
    if h:
        return f"{h}h {m}m {s}s"
    return f"{m}m {s}s"

def _fmt_val(key: str, data: dict, lr: dict) -> str:
    """
    Resolve a stat key to a display string.
    Handles both alltime keys and lr_ prefixed last_run keys.
    """
    at = data.get("alltime", {})

    if key == "total_sessions":
        return str(at.get("total_sessions", 0))

    if key == "total_games":
        return str(at.get("total_games", 0))

    if key == "total_game_seconds":
        return _fmt_duration(at.get("total_game_seconds", 0))

    if key == "total_app_seconds":
        return _fmt_duration(at.get("total_app_seconds", 0))

    if key == "avg_game_duration":
        total  = at.get("total_games", 0)
        secs   = at.get("total_game_seconds", 0)
        return _fmt_duration(secs // total) if total else "—"

    if key == "longest_game_seconds":
        s = at.get("longest_game_seconds", 0)
        return _fmt_duration(s) if s else "—"

    if key == "most_games_in_session":
        v = at.get("most_games_in_session", 0)
        return str(v) if v else "—"

    if key == "unique_servers":
        return str(len(at.get("unique_servers", [])))

    if key == "first_game_at":
        return at.get("first_game_at") or "—"

    if key == "last_game_at":
        return at.get("last_game_at") or "—"

    if key == "session_games":
        return str(lr.get("games", 0))

    if key == "session_game_seconds":
        return _fmt_duration(lr.get("game_seconds", 0))

    if key == "runs_per_hour":
        games   = lr.get("games", 0)
        elapsed = lr.get("elapsed_seconds", 0)
        if elapsed < 60 or games == 0:
            return "—"
        return f"{games / (elapsed / 3600):.1f} / hr"

    return "—"

def _label(key: str) -> str:
    """Human-readable left-hand label for a stat key."""
    return {
        "session_games":         "Games",
        "session_game_seconds":  "Time in-game",
        "runs_per_hour":         "Runs / hour",
        "total_games":           "Total games",
        "total_sessions":        "Sessions",
        "total_game_seconds":    "Total time in-game",
        "avg_game_duration":     "Avg game time",
        "longest_game_seconds":  "Longest game",
        "most_games_in_session": "Best session",
        "unique_servers":        "Unique servers",
        "first_game_at":         "First game",
        "last_game_at":          "Last game",
    }.get(key, key)


def _read_stats(path: str = "stats.json") -> tuple[dict, dict]:
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data, data.get("last_run", {})
    except (json.JSONDecodeError, OSError):
        pass
    return {}, {}


# ── StatsWindow ───────────────────────────────────────────────────────────────

class StatsWindow(QWidget):
    def __init__(self, stats_path: str = "stats.json") -> None:
        super().__init__()
        self._drag_pos: Optional[QPoint] = None
        self._stats_path = stats_path

        self.setWindowFlags(WINDOW_FLAGS)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(W, H)

        self._val_labels: dict[str, QLabel] = {}
        data, lr = _read_stats(stats_path)
        self._build_ui(data, lr)
        self._center_on_screen()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self, data: dict, lr: dict) -> None:

        # ── Close button ──────────────────────────────────────────────────────
        close = QPushButton("×", self)
        close.setStyleSheet(CLOSE_BTN_QSS)
        close.setFixedSize(26, 26)
        close.move(W - 32, 6)
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.clicked.connect(self.close)

        # ── Title ─────────────────────────────────────────────────────────────
        title = QLabel("Statistics", self)
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

        # ── Stat rows ─────────────────────────────────────────────────────────
        f_key = QFont("Segoe UI", 10)
        f_val = QFont("Segoe UI", 10)
        # f_val.setBold(True)
        f_sec = QFont("Segoe UI", 10)
        f_sec.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2.0)

        y = PAD_T + HEADER_H

        for section_label, keys in _SECTIONS:

            # Section header
            sec_lbl = QLabel(section_label, self)
            sec_lbl.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            sec_lbl.setFont(f_sec)
            sec_lbl.setStyleSheet(f"color: {GOLD.name()}; background: transparent;")
            sec_lbl.move(PAD_L, y + 4)
            sec_lbl.adjustSize()
            y += ROW_H

            for key in keys:
                val_str = _fmt_val(key, data, lr)
                lbl_str = _label(key)

                # Key label (left)
                k = QLabel(lbl_str, self)
                k.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
                k.setFont(f_key)
                k.setStyleSheet(f"color: {TEXT.name()}; background: transparent;")
                k.move(PAD_L, y + 3)
                k.adjustSize()

                # Value label (right-aligned)
                v = QLabel(val_str, self)
                v.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
                v.setFont(f_val)
                v.setStyleSheet(f"color: {BLUE.name()}; background: transparent;")
                v.adjustSize()
                v.move(W - PAD_R - v.width(), y + 3)
                self._val_labels[key] = v

                y += ROW_H

            y += SECTION_GAP

    def refresh(self) -> None:
        data, lr = _read_stats(self._stats_path)
        for key, lbl in self._val_labels.items():
            lbl.setText(_fmt_val(key, data, lr))
            lbl.adjustSize()
            lbl.move(W - PAD_R - lbl.width(), lbl.y())

    # ── Paint ─────────────────────────────────────────────────────────────────

    def paintEvent(self, _) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Background
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(BG)
        p.drawRoundedRect(0, 0, W, H, R, R)

        # White border
        border_pen = QPen(GOLD)
        border_pen.setWidthF(1.0)
        p.setPen(border_pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(0, 0, W - 1, H - 1, R, R)

        # Divider under header
        div_pen = QPen(DIVIDER)
        div_pen.setWidthF(0.8)
        p.setPen(div_pen)
        p.drawLine(PAD_L, PAD_T + HEADER_H - 4, W - PAD_R, PAD_T + HEADER_H - 4)

        # Divider between sections
        y = PAD_T + HEADER_H
        for _, keys in _SECTIONS:
            y += ROW_H               # section header
            y += len(keys) * ROW_H
            p.setPen(div_pen)
            p.drawLine(PAD_L, y + SECTION_GAP // 2, W - PAD_R, y + SECTION_GAP // 2)
            y += SECTION_GAP

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

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _center_on_screen(self) -> None:
        screen = QApplication.primaryScreen().geometry()
        self.move(
            (screen.width()  - W) // 2,
            (screen.height() - H) // 2,
        )