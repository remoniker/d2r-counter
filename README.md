# D2R Counter

Passive game-session tracker for Diablo II: Resurrected. Reads local TCP traffic to detect game joins and leaves — no manual input, no game interaction required. Safe for battle.net!

![Overlay](docs/overlay.png)

---

## Requirements

- Windows 10 / 11
- [Npcap](https://npcap.com/#download) with *WinPcap API-compatible mode* enabled
- Administrator privileges
- D2R.exe — does not need to be running at launch

From source: Python 3.11+, `pip install scapy psutil PyQt6`

---

## Installation

**[Download latest release →](https://github.com/USERNAME/D2RCounter/releases/latest)**

Extract anywhere. Right-click `D2RCounter.exe` → **Run as administrator**.

**Npcap** ships with Wireshark and may already be installed. To check:

```
sc query npcap
```

`STATE: 4  RUNNING` means you're good. Otherwise [download Npcap](https://npcap.com/#download) and enable WinPcap compatibility during setup.

**From source:**

```
git clone <repo-url>
cd D2RCounter
pip install scapy psutil PyQt6
python main.py        # must be run as Administrator
```

`stats.json`, `config.json`, and `logs/` are created on first run.

---

## Usage

The overlay is a dot (blue = idle, purple = in-game) and a click-through stat panel. Drag and menu access are on the dot only.

| Action | Result |
|---|---|
| `Ctrl` + left-drag dot | Move overlay |
| `Ctrl` + right-click dot | Open menu |
| Right-click tray icon | Same menu |

| Option | Description |
|---|---|
| **Statistics** | Session and all-time stats |
| **Hide / Show overlay** | Toggle visibility |
| **Set count…** | Manually set counter (0–99,999) |
| **Remember count** | Persist counter across restarts |
| **Quit** | Save all data and exit |

Overlay position is saved on quit and restored on next launch.

---

## Safe for Battle.net

Read-only packet capture only — no process injection, no memory access, no game file interaction, no outbound connections. See [TECHNICAL.md](TECHNICAL.md) for the full breakdown.

---

## License

MIT — see [TECHNICAL.md](TECHNICAL.md#license).
