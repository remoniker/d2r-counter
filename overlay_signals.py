"""
overlay_signals.py — Shared Qt signals for game join/leave events.

Kept in its own file so overlay styles, the manager, and the detector
can all import from here without creating circular dependencies.
"""

from PyQt6.QtCore import QObject, pyqtSignal


class GameSignals(QObject):
    joined = pyqtSignal()
    left   = pyqtSignal()


signals = GameSignals()