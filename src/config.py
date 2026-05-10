"""
config.py — User preferences and logging flags for D2R Counter.

Stored in config.json alongside stats.json.
Pure stdlib — safe to import before PyQt6 is available.
"""

import copy
import json
import os

_CONFIG_FILE = "config.json"

_DEFAULTS: dict = {
    "hint_shown":         False,
    "last_seen_counter":  0,
    "continue_from_last": False,
    "overlay_x":          None,
    "overlay_y":          None,
    "enable_packet_log":  True,
    "enable_run_log":     True,
}


class ConfigManager:
    def __init__(self, path: str = _CONFIG_FILE) -> None:
        self._path = path
        self._data = self._load()

    # ── Persistence ───────────────────────────────────────────────────────────

    def _load(self) -> dict:
        if os.path.exists(self._path):
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for k, v in _DEFAULTS.items():
                    data.setdefault(k, v)
                return data
            except (json.JSONDecodeError, OSError):
                pass

        # First run: migrate prefs from stats.json if present
        data = copy.deepcopy(_DEFAULTS)
        try:
            with open("stats.json", "r", encoding="utf-8") as f:
                stats_data = json.load(f)
            for k in _DEFAULTS:
                if k in stats_data.get("prefs", {}):
                    data[k] = stats_data["prefs"][k]
        except (json.JSONDecodeError, OSError, KeyError):
            pass
        return data

    def _save(self) -> None:
        tmp = self._path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2)
            os.replace(tmp, self._path)
        except OSError:
            pass

    # ── Prefs ─────────────────────────────────────────────────────────────────

    @property
    def hint_shown(self) -> bool:
        return self._data.get("hint_shown", False)

    def mark_hint_shown(self) -> None:
        self._data["hint_shown"] = True
        self._save()

    @property
    def last_seen_counter(self) -> int:
        return self._data.get("last_seen_counter", 0)

    def set_last_seen_counter(self, n: int) -> None:
        self._data["last_seen_counter"] = n
        self._save()

    @property
    def continue_from_last(self) -> bool:
        return self._data.get("continue_from_last", False)

    def set_continue_from_last(self, val: bool) -> None:
        self._data["continue_from_last"] = val
        self._save()

    @property
    def overlay_position(self) -> tuple[int, int] | None:
        x = self._data.get("overlay_x")
        y = self._data.get("overlay_y")
        return (x, y) if x is not None and y is not None else None

    def set_overlay_position(self, x: int, y: int) -> None:
        self._data["overlay_x"] = x
        self._data["overlay_y"] = y
        self._save()

    # ── Logging flags ─────────────────────────────────────────────────────────

    @property
    def enable_packet_log(self) -> bool:
        return self._data.get("enable_packet_log", True)

    @property
    def enable_run_log(self) -> bool:
        return self._data.get("enable_run_log", True)


config = ConfigManager()
