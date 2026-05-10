# D2R Counter

A lightweight, passive game-session tracker for Diablo II: Resurrected. Monitors local TCP traffic to automatically detect game joins and leaves — no manual input, no interaction with the game process.

---

## About

D2R Counter runs alongside D2R and increments a counter each time you join a game. It tracks game duration, runs per hour, and session and all-time statistics. All data is stored locally in JSON files. D2R can be launched before or after D2R Counter — it polls for `D2R.exe` automatically.

![Overlay](docs/overlay.png)

The overlay is two small always-on-top transparent windows — a coloured dot (blue when idle, purple in-game) and a stat panel showing the current count and a live timer. The panel is click-through; only the dot is interactive.

### Controls

| Action | Result |
|---|---|
| `Ctrl` + left-drag the dot | Move the overlay |
| `Ctrl` + right-click the dot | Open the options menu |
| Right-click the tray icon | Same options menu |

Position is saved on quit and restored on the next launch.

### Options

| Option | Description |
|---|---|
| **Hint** | Re-show the first-launch control reference |
| **About** | Open the About window |
| **Statistics** | Session and all-time stats |
| **Hide / Show overlay** | Toggle dot and panel visibility |
| **Set count…** | Manually set the display counter (0–99,999) |
| **Remember count** | Persist the counter across restarts — written on each game leave, restored on next launch |
| **Quit** | Save all data and exit cleanly |

### Logging

Two log files are written to `logs/` alongside the executable:

- **`run.log`** — one line per join/leave with server IP, game number, and duration. A permanent human-readable record of your sessions.
- **`packet.log`** — per-packet classifier detail for every tracked connection candidate. Used for threshold tuning (see [Log-Driven Threshold Tuning](#log-driven-threshold-tuning)). Can be disabled if not needed.

Both logs can be independently disabled by setting `enable_run_log` or `enable_packet_log` to `false` in `config.json` and restarting.

---

## Why It's Safe for Battle.net

**D2R Counter is entirely passive and read-only. It never sends, modifies, or injects any data.**

- **No packet injection.** Scapy's sniffer opens the network interface in read-only mode via Npcap. It receives copies of packets from the driver; it never writes to the network or modifies any traffic.

- **No process interaction.** D2R Counter does not attach to `D2R.exe`, does not read or write its memory, does not hook any Windows APIs, and does not inject code. `psutil` is used purely to read the operating system's process list and TCP connection table — the same information visible in Task Manager and `netstat`.

- **No game file interaction.** D2R Counter does not read, write, or modify any Diablo II game files, save files, or registry entries.

- **No external communication.** D2R Counter makes zero outbound network connections of its own. There is no telemetry, no update checker, and no analytics. Everything stays on your local machine.

- **Port ownership verification.** Before tracking any connection, the code confirms via `psutil.net_connections()` that the specific local TCP port belongs to `D2R.exe`'s PID. This prevents other applications that also use port 443 (browsers, update services, etc.) from triggering false positives.

- **Payload content is never read.** Only packet metadata is used: direction, size, and timing. The BPF filter limits capture to TCP port 443 traffic to and from your local IP; the payload bytes are not inspected, logged, or stored.

Battle.net's anti-cheat (Warden) targets code injection, memory modification, API hooking, and unauthorized interaction with the game process. D2R Counter does none of these things. It is, functionally, a passive traffic analyser watching its own network card.

---

## Requirements

- **Windows 10 / 11** — the sniffer depends on Npcap, which is Windows-only
- **[Npcap](https://npcap.com/#download)** — the packet capture driver; install with *WinPcap API-compatible mode* enabled
- **Administrator privileges** — required to open a raw packet capture interface
- **Diablo II: Resurrected** — the app waits for `D2R.exe`; it does not need to be running at launch

If running from source:

- Python 3.11+
- `pip install scapy psutil PyQt6`

---

## Installation

### Standalone (Recommended)

**[Download the latest release →](https://github.com/USERNAME/D2RCounter/releases/latest)**

Extract the `D2RCounter` folder anywhere. Right-click `D2RCounter.exe` → **Run as administrator**.

`stats.json`, `config.json`, and the `logs/` folder are created automatically on first run.

### Npcap

Npcap ships with Wireshark and several developer tools, so it may already be on your machine. To check, open a command prompt and run:

```
sc query npcap
```

If you see `STATE: 4 RUNNING`, you're set. Otherwise, [download and install Npcap](https://npcap.com/#download) — enable **WinPcap API-compatible mode** during setup.

### From Source

```
git clone <repo-url>
cd D2RCounter
pip install scapy psutil PyQt6
```

Then run as Administrator:

```
python main.py
```

---

## How Detection Works

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

## Data Files

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

Stores user preferences. Created on first write — typically when you first change a setting or quit cleanly.

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

### Log Files

Both log files live in the `logs/` subfolder and rotate automatically.

**`logs/run.log`** — High-level session log. Records application starts/stops, game joins with server IP and game number, game leaves with duration, D2R process found/lost, and crash warnings. Rotates at 2 MB, keeps 5 backup files.

```
2025-04-30 20:00:00  *** APPLICATION STARTED ***
2025-04-30 20:01:43  GAME JOINED  #1  server=12.34.56.78:443
2025-04-30 20:03:28  GAME LEFT    #1  server=12.34.56.78:443  (duration: 1m 45s)
```

**`logs/packet.log`** — Per-packet classifier detail for every candidate connection. Records CANDIDATE (seen), JOINED (promoted), EXPIRED (timed out), and DISQ (disqualification reason) events. Used for threshold tuning. Rotates at 5 MB, keeps 3 backup files.

```
2025-04-30 20:01:41  INFO      CANDIDATE  12.34.56.78:443  local:54321  tracking=1
2025-04-30 20:01:41  DEBUG       pkt=4218b  total=4218b  peak_0.75s=4218b  consec_large=1  ratio=1.00 ...
2025-04-30 20:01:42  DEBUG       pkt=8934b  total=13152b  peak_0.75s=13152b  consec_large=2 ...
2025-04-30 20:01:42  INFO      JOINED  12.34.56.78:443  total=18540b  ratio=0.98  ...
```

---

## Building from Source

### Overview

D2R Counter is packaged with [PyInstaller](https://pyinstaller.org). The recommended mode is `--onedir`: a folder containing the `.exe` with all dependencies unpacked alongside it. This starts instantly. The alternative `--onefile` packs everything into a single binary that extracts to a temp directory on every launch, adding several seconds to startup time.

`stats.json`, `config.json`, and `logs/` are runtime-generated files. They are created in the working directory when the exe runs. Do not bundle them with PyInstaller.

### build.bat

Place `build.bat` in the project root alongside `main.py` and run it from an Administrator command prompt.

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
- [ ] Npcap is installed on the target machine
- [ ] The exe is launched as Administrator

---

## License

MIT License

Copyright (c) 2025

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
