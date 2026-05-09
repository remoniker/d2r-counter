# D2R Counter

A lightweight, passive game-session tracker for Diablo II: Resurrected. D2R Counter monitors local TCP traffic to automatically detect when you join and leave a game — no manual input, no interaction with the game process.

![Overlay](docs/overlay.png)
*The overlay dot and stat panel during an active session.*

---

## Table of Contents

1. [What It Is](#1-what-it-is)
2. [Why It's Safe for Battle.net](#2-why-its-safe-for-battlenet)
3. [Requirements](#3-requirements)
4. [Installation](#4-installation)
5. [Running](#5-running)
6. [How Detection Works](#6-how-detection-works)
   - [The BPF Filter](#the-bpf-filter)
   - [Connection Candidates and the State Machine](#connection-candidates-and-the-state-machine)
   - [The Classifier](#the-classifier)
   - [Threshold Reference](#threshold-reference)
   - [Log-Driven Threshold Tuning](#log-driven-threshold-tuning)
7. [UI Windows](#7-ui-windows)
8. [Configuration and Usage](#8-configuration-and-usage)
9. [Data Files](#9-data-files)
10. [Troubleshooting](#10-troubleshooting)
11. [Building from Source](#11-building-from-source)
12. [Function Reference](#12-function-reference)

---

## 1. What It Is

D2R Counter runs alongside Diablo II: Resurrected and automatically increments a game counter each time you join a game — no button presses required. It tracks game duration, runs per hour, session statistics, and maintains an all-time record of your runs.

The overlay is a small, always-on-top transparent window that stays out of your way. The counter and live timer update in real time. All data is stored locally in JSON files.

D2R can be launched before or after D2R Counter — the application polls for `D2R.exe` and picks it up automatically.

---

## 2. Why It's Safe for Battle.net

**D2R Counter is entirely passive and read-only. It never sends, modifies, or injects any data.**

- **No packet injection.** Scapy's sniffer opens the network interface in read-only mode via Npcap. It receives copies of packets from the driver; it never writes to the network or modifies any traffic.

- **No process interaction.** D2R Counter does not attach to `D2R.exe`, does not read or write its memory, does not hook any Windows APIs, and does not inject code. `psutil` is used purely to read the operating system's process list and TCP connection table — the same information visible in Task Manager and `netstat`.

- **No game file interaction.** D2R Counter does not read, write, or modify any Diablo II game files, save files, or registry entries.

- **No external communication.** D2R Counter makes zero outbound network connections of its own. There is no telemetry, no update checker, and no analytics. Everything stays on your local machine.

- **Port ownership verification.** Before tracking any connection, the code confirms via `psutil.net_connections()` that the specific local TCP port belongs to `D2R.exe`'s PID. This prevents other applications that also use port 443 (browsers, update services, etc.) from triggering false positives.

- **Payload content is never read.** Only packet metadata is used: direction, size, and timing. The BPF filter limits capture to TCP port 443 traffic to and from your local IP; the payload bytes are not inspected, logged, or stored.

Battle.net's anti-cheat (Warden) targets code injection, memory modification, API hooking, and unauthorized interaction with the game process. D2R Counter does none of these things. It is, functionally, a passive traffic analyser watching its own network card.

---

## 3. Requirements

- **Windows 10 / 11** — the sniffer depends on Npcap, which is Windows-only
- **[Npcap](https://npcap.com/#download)** — the packet capture driver; install with *WinPcap API-compatible mode* enabled
- **Administrator privileges** — required to open a raw packet capture interface
- **Diablo II: Resurrected** — the app waits for `D2R.exe`; it does not need to be running at launch

If running from source:

- Python 3.11+
- `pip install scapy psutil PyQt6`

---

## 4. Installation

### Standalone (Recommended)

1. Download and extract the `D2RCounter` folder.
2. Install [Npcap](https://npcap.com/#download) if you have not already.
3. Right-click `D2RCounter.exe` → **Run as administrator**.

`stats.json`, `config.json`, and the `logs/` folder will be created automatically in the same directory as the `.exe`.

### From Source

```
git clone <repo-url>
cd D2RCounter
pip install scapy psutil PyQt6
```

Run as Administrator:

```
python main.py
```

---

## 5. Running

D2R Counter **must be launched as Administrator**. Without elevation, Npcap cannot open the raw capture interface and the program exits immediately with an access-denied error.

On launch, a console window opens showing:

- Your detected local IP address
- All active detection threshold values
- All-time stats from previous sessions

The system tray icon appears and the overlay positions on screen. When you join a game, the console prints a detailed join event, the overlay counter increments, and the in-game timer starts. When you leave, the timer freezes showing the final game duration and the counter remains.

D2R does not need to be running when D2R Counter starts. The PID watcher checks every 5 seconds and logs when it finds or loses `D2R.exe`.

---

## 6. How Detection Works

### The BPF Filter

Npcap captures packets at the driver level before the OS TCP stack processes them. To avoid inspecting every packet on the machine, D2R Counter provides a **Berkeley Packet Filter (BPF)** expression when starting the sniffer:

```
tcp port 443 and (src host <LOCAL_IP> or dst host <LOCAL_IP>)
```

BPF is a kernel-level bytecode filter that runs inside the capture driver. Only packets matching this expression are handed to Python — everything else is discarded at the driver with no Python overhead. This means:

- Only TCP is considered. UDP, ICMP, and other protocols are dropped at the driver.
- Only port 443 traffic is captured. D2R game servers exclusively use port 443.
- Only packets involving the local machine's IP are captured. Traffic between other hosts on the same network is ignored.

On a busy network the raw capture rate might be thousands of packets per second; after the BPF filter, D2R Counter typically processes only a handful.

---

### Connection Candidates and the State Machine

Detection is modelled as a three-state machine:

```
         SYN-ACK from external:443, local port verified to belong to D2R.exe
  IDLE ──────────────────────────────────────────────────────────────────► TRACKING
   ▲                                                                            │
   │   All candidates expire — no burst within DATA_BURST_WINDOW (6s)          │  is_game_like() → True
   │◄───────────────────────────────────────────────────────────────────────────┤
   │                                                                            ▼
   └──────────────────────────────────────────────────────────────────────── IN_GAME
                            Outbound FIN+ACK on the tracked connection
```

**IDLE** — No active tracking. All inbound data packets are ignored.

**TRACKING** — One or more *connection candidates* exist. Each candidate is a `Conn` object keyed by `(server_ip, server_port, local_port)`. Every inbound data packet is measured and tested against the classifier. A candidate that reaches no burst threshold within 6 seconds of its SYN-ACK is discarded and the state returns to IDLE if no other candidates remain.

**IN_GAME** — A candidate has passed the classifier. The overlay and stats are updated. Only the outbound `FIN+ACK` on the confirmed game server connection moves state back to IDLE.

**Why verify local port ownership?**
Port 443 is used by many applications. When a SYN-ACK arrives, the code calls `psutil.net_connections()` to check whether the destination local port is listed as belonging to `D2R.exe`'s PID. This filters out browser, update service, and other application traffic before any tracking begins.

---

### The Classifier

Each time a candidate receives an inbound data packet, `is_game_like()` is called. Checks run in priority order.

#### Step 1 — Disqualifiers (hard gates)

Any single disqualifier immediately rules the connection out. They are grouped into inbound-shape checks and outbound-shape checks.

**Inbound shape:**

- **Inbound ratio** — At least 80% of total bytes must be inbound. Joining a game downloads world state; auth and TLS handshakes are more symmetric, producing a lower inbound ratio.

- **Consecutive large packets** — At least 2 consecutive inbound packets must exceed 1000 bytes. Real game data arrives in a sustained stream of large packets. Credential exchanges tend to be smaller and more scattered.

- **MTU-sized packets** — At least 2 inbound packets must be at or above 1400 bytes (near Ethernet MTU). Full-MTU packets indicate a bulk transfer, which is characteristic of game world data loading.

**Outbound shape:**

- **Max outbound packet** — No single outbound packet may exceed 500 bytes. In-game client-to-server messages (actions, keepalives) are tiny. A large outbound packet early in a connection indicates a credential or token exchange.

- **Average outbound size** — Once at least 3 outbound packets have been observed, their average must be below 180 bytes. Login and authentication flows send larger outbound packets than in-game client packets.

#### Step 2 — Positive Signals

If all disqualifiers pass, any one of three positive signals confirms the join:

**`consec_fast` override (highest confidence)**
If 12 or more consecutive inbound packets arrive with inter-packet gaps of less than 5ms, the connection is immediately confirmed. This high-speed burst pattern is extremely specific to the initial game world download. No non-game connection has produced this pattern in collected data.

**`early_large`**
A single inbound packet exceeding 4000 bytes arrives within 0.8 seconds of the SYN-ACK, AND total inbound bytes are at or above 15,000, AND the peak 0.75-second burst is at or above 8,000 bytes. This captures the pattern where the game server pushes an initial large world-state packet almost immediately after the handshake completes.

**`rapid_burst`**
The peak inbound throughput in any 0.75-second sliding window exceeds 10,000 bytes. This is the primary detection path for the majority of game joins: game world data downloads quickly.

The `peak_burst()` sliding window is computed with a two-pointer algorithm. As one pointer advances through the packet list, a second pointer trails behind and is advanced forward whenever the window duration is exceeded. This keeps the running byte sum accurate in O(n) time without recomputing from scratch for each packet.

---

### Threshold Reference

| Constant | Value | Role |
|---|---|---|
| `EARLY_LARGE_PKT` | 4,000 b | Single-packet size threshold for the early-large path |
| `EARLY_LARGE_WINDOW` | 0.8 s | Max time after SYN-ACK for the qualifying large packet to arrive |
| `EARLY_LARGE_MIN` | 15,000 b | Min total inbound bytes required alongside an early large packet |
| `EARLY_LARGE_BURST` | 8,000 b | Min peak-burst value required alongside an early large packet |
| `RAPID_BURST_BYTES` | 10,000 b | Peak inbound bytes in any sliding window to trigger a join |
| `RAPID_BURST_WINDOW` | 0.75 s | Duration of the sliding window for burst measurement |
| `GAME_MIN_INBOUND_RATIO` | 0.80 | Minimum fraction of total bytes that must be inbound |
| `GAME_MIN_CONSEC_LARGE` | 2 | Minimum consecutive large (> 1000 b) packet streak |
| `GAME_MIN_MTU_PACKETS` | 2 | Minimum packets at near-MTU size (≥ 1400 b) |
| `GAME_MAX_OUTBOUND_SINGLE` | 500 b | Maximum size of any single outbound packet |
| `GAME_MAX_OUTBOUND_AVG` | 180 b | Maximum average outbound packet size (after ≥ 3 outbound packets) |
| `GAME_MIN_OUTBOUND_SAMPLE` | 3 | Minimum outbound packets before the average check fires |
| `CONSEC_FAST_CERTAIN` | 12 | Consecutive inbound packets < 5ms apart triggers an immediate override |
| `DATA_BURST_WINDOW` | 6.0 s | Seconds before an unconfirmed candidate is discarded |
| `EARLY_ABANDON_SECONDS` | 60 s | Games shorter than this are tagged as early abandons in the logs |

All constants are defined at the top of `main.py` and can be adjusted without touching any other code.

---

### Log-Driven Threshold Tuning

The threshold values were derived empirically from real D2R traffic, not estimated.

`packet.log` records every inbound data packet for every candidate connection with all classifier metrics at that moment: packet size, cumulative inbound bytes, peak burst, consecutive large streak, consecutive fast count, inbound ratio, outbound packet count/sizes, and connection age. When a connection is disqualified the reason is written. When it is promoted to IN_GAME a full summary of all metrics is logged.

The tuning process was iterative:

1. Run D2R Counter with `enable_packet_log: true`.
2. Play normally — join games, exit games, switch characters, log in to Battle.net, open menus, visit the shop.
3. Review `packet.log` for two things:
   - **Promoted connections (JOINED)**: verify the correct connection was confirmed and note the metric values at the moment of promotion.
   - **Expired candidates (EXPIRED)**: read the `reason=[...]` field to see which disqualifier fired, and confirm it fired for the right reason.
4. Identify the metric ranges that separate true positives (game joins) from false positives (Battle.net auth, lobby, CDN, menus).
5. Tighten or relax specific thresholds accordingly. Repeat.

Over multiple sessions the thresholds were converged to values that detect every game join reliably with no false positives across all observed traffic patterns — game joins at different server locations, early abandons, character switching, in-game trading, and Battle.net login flows.

The `DISQ=[...]` field in `packet.log` is particularly useful for this process. It shows exactly which condition disqualified a given candidate, making threshold adjustments surgical rather than speculative.

---

## 7. UI Windows

### Main Overlay — Dot and StatPanel

The overlay is two frameless, transparent, always-on-top windows that move together:

**DotWindow** — The interactive orb. It is the draggable handle and the primary visual status indicator. The orb is blue when idle and purple when a game is active. `Ctrl + left-drag` moves both windows. `Ctrl + right-click` opens the options menu. The window is sized at 300×100px even though the visible orb is much smaller; the extra area is fully transparent and passes input through.

**StatPanel** — The stat card to the right of the dot. Displays the current game count, an `IN GAME` / `GAMES` label, a divider, and either a live centisecond timer while in a game or the duration of the most recent completed game. The panel is set `WindowTransparentForInput` — clicks pass through it so it never interferes with the game.

Both windows use `WA_TranslucentBackground` and are drawn entirely in `paintEvent` via `QPainter` with no OS window chrome.

![Overlay In-Game](docs/overlay_ingame.png)
*The dot turns purple and the timer counts up while in a game.*

### Statistics Window

Opened from the options menu or tray. Shows two sections:

- **This Session** — games this run, runs per hour, time in-game this session
- **All Time** — total games, average game time, total time in-game, total sessions, longest game, best session (most games), unique servers seen, first and last game timestamps

Data is read fresh from `stats.json` each time the window is opened. While open, the displayed values update live whenever a join or leave event fires — without rebuilding the window. Right-hand value labels are repositioned after each update so they remain right-aligned regardless of text length.

### About Window

Opened from the options menu or tray. Shows a brief description of the program, a controls reference, and the available options. Content is defined in the `_ROWS` list at the top of `about.py` — each entry is a `(text, kind)` tuple where `kind` is `"section"`, `"body"`, or `"gap"`. Editing that list is sufficient to update the displayed text; window height is recomputed automatically from the row list at module load time.

### Set Counter Dialog

Opened via **Set count…** in either menu. A small frameless dialog matching the application style. Contains a spin box accepting values from 0 to 99,999. Draggable. Confirms with OK or dismisses with Cancel.

This only changes the *display counter* on the overlay. `StatsManager` is unaffected — its game count is always derived from real detected join events and is not adjustable from the UI.

### Hint Window

Shown automatically on first launch; available from the menu thereafter. A short control reference anchored below the overlay dot, using a typewriter animation. Dismisses on `Ctrl + click` anywhere or via the dismiss button. The hint repositions itself to track the dot when the overlay is dragged, so it never gets separated from the orb it is describing.

After being dismissed for the first time, the hint is not shown automatically on subsequent launches. This is recorded in `config.json` (`hint_shown: true`).

---

## 8. Configuration and Usage

### Moving the Overlay

Hold `Ctrl` and left-drag the dot. The stat panel follows. Position is saved to `config.json` on exit and restored on the next launch.

### Opening the Menu

Hold `Ctrl` and right-click the dot. The identical menu is also available from the system tray icon (right-click the tray).

### Menu Options

| Option | Description |
|---|---|
| **Hint** | Re-shows the hint window |
| **About** | Opens the About window |
| **Statistics** | Opens the Statistics window |
| **Hide overlay / Show overlay** | Toggles dot and panel visibility |
| **Set count…** | Opens the Set Counter dialog to manually adjust the display counter |
| **Remember count** | Checkbox. When checked, the display counter is saved on each game leave and restored on the next launch |
| **Quit** | Cleanly shuts down, saving all stats and the current overlay position |

### Remember Count

When **Remember count** is enabled, the display counter is written to `config.json` each time you leave a game. On the next launch, the counter resumes from that value instead of starting at zero.

Useful for marathon sessions across multiple application restarts, or if you want the counter to reflect total runs across a day rather than just the current session.

---

## 9. Data Files

### stats.json

Stores all game statistics. Located next to the executable (or `main.py` when running from source).

Written atomically on every meaningful event using a `.tmp` file followed by `os.replace()`. This ensures the file is never left in a partially-written state if the application crashes mid-write.

```json
{
  "alltime": {
    "total_sessions": 12,
    "total_games": 847,
    "total_game_seconds": 304200,
    "total_app_seconds": 86400,
    "most_games_in_session": 143,
    "longest_game_seconds": 1802,
    "first_game_at": "2024-11-01 19:32:14",
    "last_game_at":  "2025-04-30 22:11:09",
    "unique_servers": ["12.34.56.78:443", "98.76.54.32:443"]
  },
  "last_run": {
    "started_at": "2025-04-30 20:00:00",
    "ended_at":   "2025-04-30 22:11:09",
    "games": 87,
    "game_seconds": 18200,
    "elapsed_seconds": 7869,
    "crashed": false
  }
}
```

The file can be edited manually. The loader merges any missing keys against defaults on next launch, so partial or hand-edited files are safe.

If a previous session has a `started_at` but no `ended_at` when the app starts, it is detected as an unclean exit (crash or force-kill), logged as a warning, and printed to the console. Stats from that session are preserved.

### config.json

Stores user preferences. Created on first write — typically when you first change a setting or quit cleanly. If `config.json` does not exist but `stats.json` contains a legacy `prefs` section, those values are migrated automatically.

```json
{
  "hint_shown": true,
  "last_seen_counter": 87,
  "continue_from_last": false,
  "overlay_x": 960,
  "overlay_y": 540,
  "enable_packet_log": true,
  "enable_run_log": true
}
```

| Key | Default | Description |
|---|---|---|
| `hint_shown` | `false` | Whether the first-launch hint has been shown and dismissed |
| `last_seen_counter` | `0` | Display counter saved at last game leave; used by Remember count |
| `continue_from_last` | `false` | Whether the Remember count option is enabled |
| `overlay_x` / `overlay_y` | `null` | Last saved overlay position; falls back to screen centre if null or off-screen |
| `enable_packet_log` | `true` | Whether `logs/packet.log` is written |
| `enable_run_log` | `true` | Whether `logs/run.log` is written |

To disable a log, set the corresponding flag to `false` and restart. The logger is disabled entirely — no file is opened or written.

### Log Files

Both log files live in the `logs/` subfolder alongside the executable and rotate automatically.

**`logs/run.log`** — High-level session log. Human-readable and appropriate as a permanent record.

- Application starts and stops
- Game joins with server IP and game number
- Game leaves with duration and early-abandon tags
- D2R process found / lost
- Battle.net connection detected
- Crash/unclean exit warnings

Rotates at 2 MB, keeps 5 backup files.

```
2025-04-30 20:00:00  *** APPLICATION STARTED ***
2025-04-30 20:01:43  GAME JOINED  #1  server=12.34.56.78:443
2025-04-30 20:03:28  GAME LEFT    #1  server=12.34.56.78:443  (duration: 1m 45s)
```

**`logs/packet.log`** — Detailed per-packet debug log. Records every inbound data packet for every candidate connection with all classifier metrics. Also records CANDIDATE (connection seen), JOINED (promoted), EXPIRED (timed out), and DISQ (disqualification reason).

Used for threshold tuning — see [Log-Driven Threshold Tuning](#log-driven-threshold-tuning).

Can grow quickly during active play. Rotates at 5 MB, keeps 3 backup files.

```
2025-04-30 20:01:41  INFO      CANDIDATE  12.34.56.78:443  local:54321  tracking=1
2025-04-30 20:01:41  DEBUG       pkt=4218b  total=4218b  peak_0.75s=4218b  consec_large=1  ratio=1.00 ...
2025-04-30 20:01:42  DEBUG       pkt=8934b  total=13152b  peak_0.75s=13152b  consec_large=2 ...
2025-04-30 20:01:42  INFO      JOINED  12.34.56.78:443  total=18540b  ratio=0.98  ...
```

---

## 10. Troubleshooting

**"Access denied — run as Administrator."**
The sniffer requires elevation. Right-click the exe or the terminal → Run as administrator.

---

**Npcap error on startup / sniffer fails**
Install [Npcap](https://npcap.com/#download). During installation, enable *WinPcap API-compatible mode*. If Npcap is already installed, try reinstalling it. Scapy on Windows requires Npcap specifically; the built-in Windows packet capture API is not supported.

---

**Overlay appears but games are not being detected**
1. Check the console for `Found D2R.exe (PID XXXX)`. If absent, D2R is not running or is not found by name.
2. Check the console for `✔ Connected to Battle.net`. If absent after logging in, the BPF filter may not be matching your active interface — confirm that `LOCAL_IP` shown in the console matches your active network adapter's IP (not a VPN, virtual, or inactive adapter).
3. Open `logs/packet.log` and look for `CANDIDATE` entries around the time you joined. If candidates appear and then `EXPIRED`, read the `reason=[...]` field to see which disqualifier fired. If no candidates appear at all, the port ownership check is likely failing — which would indicate the local port on that connection is not attributed to `D2R.exe` by the OS.

---

**A game join was not counted (false negative)**
Look in `logs/packet.log` for an `EXPIRED` entry near the time of the missed join. The `reason=` field identifies the failing check. If the disqualifier seems wrong (e.g. the outbound max was 520b on a legitimate game join), adjust the relevant threshold in `main.py` and note the metric values — see [Log-Driven Threshold Tuning](#log-driven-threshold-tuning).

---

**The counter incremented when I did not join a game (false positive)**
Find the `JOINED` entry in `packet.log`. It includes the server IP, total bytes, burst, ratio, and all outbound metrics. If a non-game connection was promoted, the most diagnostic values are `inbound_ratio`, `out_max`, and `out_avg`. Tighten the relevant threshold and test again.

---

**The system tray icon is missing (packaged .exe)**
PyInstaller bundles `off.ico` but it is extracted to a temporary path at runtime, not the working directory. To fix this, update `overlay_manager.py` before building to resolve the icon path from `sys._MEIPASS`:

```python
import sys, os

def _resource(name: str) -> str:
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)
```

Then change `QIcon("off.ico")` to `QIcon(_resource("off.ico"))`.

---

**"Previous session ended without a clean exit"**
Printed on startup when `stats.json` has a `started_at` but no `ended_at` for the last run. This means the previous session was force-killed or crashed. All recorded stats from that session are preserved; only the session end time and final elapsed time are missing. This message is informational — no action required.

---

**Stats window shows `—` for all values**
`stats.json` does not exist yet (no completed games recorded) or was deleted. Play a game and exit normally; the file will be created and populated on first join/leave.

---

## 11. Building from Source

### Overview

D2R Counter is packaged with [PyInstaller](https://pyinstaller.org). The recommended mode is `--onedir`: a folder containing the `.exe` with all dependencies unpacked alongside it. This starts instantly. The alternative `--onefile` packs everything into a single binary that extracts to a temp directory on every launch, adding several seconds to startup time.

`stats.json`, `config.json`, and `logs/` are runtime-generated files. They are created in the working directory when the exe runs — normally the folder the exe lives in. Do not bundle them with PyInstaller.

### Before Building — Tray Icon Path

When running via PyInstaller, bundled data files are extracted to `sys._MEIPASS`, not the working directory. The `off.ico` path in `overlay_manager.py` needs updating before building or the tray icon will silently fail to load.

In `overlay_manager.py`, add this helper and update the icon line:

```python
import sys, os

def _resource(name: str) -> str:
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)

# In OverlayManager.__init__, change:
self._tray.setIcon(QIcon("off.ico"))
# to:
self._tray.setIcon(QIcon(_resource("off.ico")))
```

### build.bat

Place this file in the project root alongside `main.py` and run it from an Administrator command prompt.

```batch
@echo off
setlocal
echo =============================================
echo  D2R Counter - Build Script
echo =============================================

echo.
echo [1/3] Installing Python dependencies...
pip install --upgrade pyinstaller scapy psutil PyQt6
if errorlevel 1 ( echo ERROR: pip install failed. & pause & exit /b 1 )

echo.
echo [2/3] Building with PyInstaller...
pyinstaller ^
    --onedir ^
    --console ^
    --icon=off.ico ^
    --add-data "off.ico;." ^
    --name D2RCounter ^
    main.py
if errorlevel 1 ( echo ERROR: PyInstaller build failed. & pause & exit /b 1 )

echo.
echo [3/3] Done.
echo Output: dist\D2RCounter\D2RCounter.exe
echo.
echo IMPORTANT: Npcap must be installed separately on the target machine.
echo            https://npcap.com/#download
echo.
pause
```

### Scapy Import Issues

Scapy uses dynamic imports that PyInstaller may not detect automatically. If the packaged exe crashes on startup with an `ImportError`, add hidden imports to the PyInstaller command:

```
--hidden-import scapy.layers.all
--hidden-import scapy.layers.inet
--hidden-import scapy.arch.windows
```

### Distribution Checklist

Before distributing the `dist\D2RCounter\` folder:

- [ ] `D2RCounter.exe` is present
- [ ] `off.ico` is present in the same folder (added by `--add-data`)
- [ ] The tray icon path fix has been applied (see above)
- [ ] Npcap is installed on the target machine
- [ ] The exe is launched as Administrator

---

## 12. Function Reference

### `main.py` — Module-Level Functions

| Function | Description |
|---|---|
| `fmt_time()` | Returns current datetime as `YYYY-MM-DD HH:MM:SS` |
| `is_external(ip)` | Returns `True` if the IP is not an RFC-1918 private address; filters out LAN and loopback traffic |
| `get_local_ip()` | Detects the machine's primary outbound IP by opening a UDP socket toward `8.8.8.8` — no data is sent, the socket is immediately closed |
| `get_d2r_pid()` | Iterates the running process list via psutil; returns the PID of `D2R.exe` or `None` |
| `port_belongs_to_d2r(local_port, d2r_pid)` | Queries `psutil.net_connections()` to confirm a local TCP port is owned by D2R's PID |
| `log_started()` | Writes a `*** APPLICATION STARTED ***` banner to both log files |
| `packetlog_inbound_data(...)` | Writes a `DEBUG` line to `packet.log` with every per-packet classifier metric for the current candidate |
| `packetlog_game_joined(c_ref)` | Writes a full `INFO` join summary (all metrics, all packet sizes) to `packet.log` |
| `runlog_game_joined(c_ref, game_count)` | Writes a brief `INFO` join line to `run.log` |
| `cmd_msg_started()` | Prints the startup banner with active threshold values and all-time stats to the console |
| `cmd_msg_joined(c_ref, game_count)` | Prints a detailed join event (server IP, bytes received, peak burst, inbound ratio, outbound stats) to the console |
| `_fmt_duration(seconds)` | Formats an integer number of seconds into `Xh Xm Xs`, `Xm Xs`, or `Xs` |
| `handle_packet(pkt)` | Scapy per-packet callback; decodes TCP flags and calculates payload length, then routes to the appropriate `Session` method |
| `expiry_loop()` | Daemon thread body; calls `session.expire_candidate()` every 250ms |
| `pid_watch_loop()` | Daemon thread body; calls `session.refresh_pid()` every 5 seconds |
| `sniffer_loop(bpf)` | Daemon thread body; blocks in `scapy.sniff()` with the BPF filter and `handle_packet` as the per-packet callback |
| `set_bpf(ip)` | Builds the BPF expression string: `tcp port 443 and (src host <ip> or dst host <ip>)` |
| `main()` | Entry point: detects local IP, starts the three background daemon threads, creates `OverlayManager`, wires `aboutToQuit` to `_on_quit` |

---

### `main.py` — `StatsManager`

Backed by `stats.json`. All public methods are thread-safe via a `threading.Lock`. All writes are atomic via a temp file and `os.replace()`.

| Method | Description |
|---|---|
| `__init__(path)` | Loads `stats.json`, records `time.monotonic()` as the session start reference |
| `_load()` | Reads and merges `stats.json` against defaults; returns a fresh default dict if the file is absent or corrupt |
| `_save()` | Updates `elapsed_seconds` from the monotonic clock, serialises to `.tmp`, then atomically replaces the target file |
| `on_session_start()` | Increments `total_sessions`, resets `last_run`, detects and logs unclean exits from previous runs |
| `on_game_joined(server_ip, server_port)` | Increments total and session game counts, records first/last game timestamps, appends unique server entries |
| `on_game_left(duration_seconds)` | Accumulates in-game time totals, updates longest-game and best-session records |
| `on_session_end()` | Records `ended_at`, accumulates `total_app_seconds`, finalises the best-session record |
| `avg_game_duration()` | Returns `total_game_seconds / total_games`, or `0.0` if no games recorded |
| `print_summary()` | Formats and prints all-time and last-run stats to the console at startup |

---

### `main.py` — `Conn`

A `dataclass` representing one tracked TCP connection candidate. Keyed in `Session.conns` by `(server_ip, server_port, local_port)`. Accumulates per-packet data and computes all classifier metrics on demand.

| Method | Description |
|---|---|
| `key()` | Returns the 3-tuple used as the dict key |
| `age()` | Seconds elapsed since the SYN-ACK was recorded |
| `add_inbound(size)` | Appends `(monotonic_time, size)` to the inbound list and increments `inbound_bytes` |
| `add_outbound(size)` | Appends `(monotonic_time, size)` to the outbound list |
| `packets` | Property; returns the raw inbound packet list |
| `peak_burst(window)` | Two-pointer sliding window; returns the maximum inbound bytes in any `window`-second span |
| `large_packet_count(threshold)` | Count of inbound packets strictly exceeding `threshold` bytes |
| `consecutive_large_streak(threshold)` | Length of the longest unbroken run of inbound packets above `threshold` |
| `mtu_packet_count()` | Count of inbound packets at or above 1400 bytes |
| `max_consecutive_fast_inbound()` | Length of the longest run where inter-arrival gap is < 5ms |
| `outbound_total()` | Sum of all outbound payload bytes |
| `outbound_count()` | Number of outbound packets recorded |
| `max_outbound_packet()` | Largest single outbound packet in bytes |
| `avg_outbound_size()` | Mean outbound packet size, or `0.0` if no outbound packets |
| `inbound_ratio()` | `inbound_bytes / (inbound + outbound_total)` |
| `disqualified_reason()` | Runs all hard-gate checks in order; returns a descriptive string on first failure, `None` if all pass |
| `is_game_like()` | Runs `disqualified_reason()` first, then tests positive signals; returns `True` if the connection should be promoted to IN_GAME |

---

### `main.py` — `Session`

Manages the `IDLE → TRACKING → IN_GAME` state machine. Holds the active `Conn` candidate dict and the confirmed game server reference. Thread-safe via `self.lock`.

| Method | Description |
|---|---|
| `refresh_pid()` | Checks the process list for `D2R.exe`; logs and handles process open and close events |
| `check_bnet_already_connected(pid)` | On D2R attach, checks for existing `ESTABLISHED` connections on port 443 belonging to D2R's PID |
| `on_syn_ack(server_ip, server_port, local_port)` | Verifies port ownership; creates a new `Conn` candidate and transitions to TRACKING if not already IN_GAME |
| `on_inbound_data(server_ip, server_port, local_port, byte_count)` | Feeds bytes to the matching candidate; promotes to IN_GAME and emits `signals.joined` if `is_game_like()` returns `True` |
| `on_outbound_data(server_ip, server_port, local_port, byte_count)` | Records outbound bytes to the matching candidate for ratio calculations |
| `on_outbound_fin(server_ip, server_port, local_port)` | Handles game leave: calculates duration, transitions to IDLE, updates stats, emits `signals.left` |
| `expire_candidate()` | Discards candidates older than `DATA_BURST_WINDOW`; uses non-game expired candidates to infer Battle.net connectivity |

---

### `overlay_manager.py` and `overlay.py`

`OverlayManager` is the central Qt controller. It owns the system tray icon, both menus (on-overlay and tray), a 50ms tick timer forwarded to the active overlay, and the lifetimes of all popup windows (`HintWindow`, `StatsWindow`, `AboutWindow`, `_SetCountDialog`).

Game events flow in via `signals.joined` and `signals.left` — two `pyqtSignal` signals on a `QObject` (`_GameSignals`). Both are connected with `Qt.ConnectionType.QueuedConnection`, which marshals the signal from the sniffer's background thread onto the Qt main thread before the slot executes. This is what makes it safe to call Qt widget methods from a `threading.Thread` without locks.

`Overlay` is a plain class (not a `QWidget`) that composes `DotWindow` and `StatPanel`. It exposes a clean interface — `on_joined()`, `on_left()`, `tick()`, `move_to()`, `set_game_count()`, `get_game_count()`, `show()`, `hide()` — that `OverlayManager` calls without knowing the internal window structure. This separation means the overlay style could be replaced with a different implementation without changing any manager code.

The on-overlay context menu is rebuilt from scratch on every open so its labels always reflect current state (hide vs show, checked state of Remember count). It is a `QMenu` with `FramelessWindowHint | Popup | NoDropShadowWindowHint` and `WA_TranslucentBackground`, producing clean rounded corners on Windows. The tray menu uses the OS default style — Qt's native tray menus interact unreliably with stylesheet transparency on Windows.

---

### UI Windows — Common Patterns

All popup windows (`StatsWindow`, `AboutWindow`, `_SetCountDialog`) share the same construction and rendering patterns:

**Window flags:** `FramelessWindowHint | WindowStaysOnTopHint | Tool | NoDropShadowWindowHint` combined with `WA_TranslucentBackground` removes all OS window chrome and produces a floating transparent panel. The `Tool` flag prevents the window from appearing in the taskbar.

**Painting:** Background, border, and dividers are drawn entirely in `paintEvent` via `QPainter` with antialiasing. The background is a filled rounded rectangle in the near-black `BG` colour. The border is a 1px gold rounded rectangle drawn offset by 1px to sit inside the widget bounds. A dim `DIVIDER`-coloured line separates the title header from the content area. There are no stylesheets on the windows themselves — only on child widgets (buttons, spin boxes).

**Dragging:** All windows are draggable from any point on their surface. `mousePressEvent` stores `event.globalPosition().toPoint() - self.frameGeometry().topLeft()` as the drag anchor. `mouseMoveEvent` calls `self.move(event.globalPosition().toPoint() - self._drag_pos)`. `mouseReleaseEvent` clears the anchor. This three-method pattern is identical across all draggable windows.

**Label layout:** Labels are placed with absolute coordinates using `move()`. Each label sets `WA_TranslucentBackground` (so the QPainter-drawn background shows through) and calls `adjustSize()` after text is set. Right-aligned labels compute their x position as `W - PAD_R - label.width()`. There are no Qt layout managers. Window height is computed from the content data at module load time, before any widget is created.

**Theme:** All colours, window flag constants, and QSS strings are defined in `theme.py` and imported. `overlay.py` and `hint.py` are self-contained with their own local palettes and are not modified by theme changes.

---

## License

MIT License

Copyright (c) 2025

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
