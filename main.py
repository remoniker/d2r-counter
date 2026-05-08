"""
D2R.exe Game Session Detector — Scapy + psutil + PyQt6 overlay
===============================================================
Passively sniffs packets and detects D2R game join/leave using the
full connection fingerprint from Wireshark captures. Displays a
transparent always-on-top game counter overlay.

Requirements:
    pip install scapy psutil PyQt6
    Npcap installed  →  https://npcap.com/#download

Run as Administrator.
"""

import datetime
import ipaddress
import json
import os
import sys
import threading
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional
import logging
from logging.handlers import RotatingFileHandler

# ── Logging flags ─────────────────────────────────────────────────────────────

ENABLE_PACKET_LOG = True
ENABLE_RUN_LOG    = True

# ── packetLog ─────────────────────────────────────────────────────────────────

packetLog = logging.getLogger("d2r.packets")
if ENABLE_PACKET_LOG:
    packetLog.setLevel(logging.DEBUG)
    _pkt_handler = RotatingFileHandler(
        "packet.log", maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    _pkt_handler.setFormatter(logging.Formatter(
        "%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    ))
    packetLog.addHandler(_pkt_handler)
else:
    packetLog.disabled = True

# ── runLog ────────────────────────────────────────────────────────────────────

runLog = logging.getLogger("d2r.runs")
if ENABLE_RUN_LOG:
    runLog.setLevel(logging.INFO)
    _run_handler = RotatingFileHandler(
        "run.log", maxBytes=2 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    _run_handler.setFormatter(logging.Formatter(
        "%(asctime)s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    ))
    runLog.addHandler(_run_handler)
else:
    runLog.disabled = True

# ── Third-party imports ───────────────────────────────────────────────────────

try:
    from scapy.all import sniff, IP, TCP
except ImportError:
    sys.exit("ERROR: scapy not installed.  Run:  pip install scapy")

try:
    import psutil
except ImportError:
    sys.exit("ERROR: psutil not installed.  Run:  pip install psutil")

try:
    from overlay_manager import OverlayManager, signals
except ImportError:
    sys.exit("ERROR: PyQt6 not installed.  Run:  pip install PyQt6")

# ── Config ────────────────────────────────────────────────────────────────────

PROCESS_NAME      = "D2R.exe"
GAME_SERVER_PORT  = 443
DATA_BURST_WINDOW = 6.0   # seconds before a candidate is expired
STATS_FILE        = "stats.json"

# ── Detection thresholds — positive signals ───────────────────────────────────

EARLY_LARGE_PKT    = 4000    # single inbound packet must exceed this for early_large
EARLY_LARGE_WINDOW = 0.8     # large packet must arrive within this many seconds of SYN-ACK
EARLY_LARGE_MIN    = 15_000  # total inbound bytes required alongside an early large packet
EARLY_LARGE_BURST  = 8_000   # peak_burst required alongside an early large packet
RAPID_BURST_BYTES  = 10_000  # peak inbound bytes within RAPID_BURST_WINDOW triggers join
RAPID_BURST_WINDOW = 0.75    # seconds — sliding window for burst check

# ── Detection thresholds — inbound hard disqualifiers ────────────────────────

GAME_MIN_INBOUND_RATIO = 0.80
GAME_MIN_CONSEC_LARGE  = 2
GAME_MIN_MTU_PACKETS   = 2

# ── Detection thresholds — outbound hard disqualifiers ───────────────────────

GAME_MAX_OUTBOUND_SINGLE = 500
GAME_MAX_OUTBOUND_AVG    = 180
GAME_MIN_OUTBOUND_SAMPLE = 3

# ── High-confidence fast-path override ───────────────────────────────────────

CONSEC_FAST_CERTAIN = 12

# ── Early abandon threshold ───────────────────────────────────────────────────

EARLY_ABANDON_SECONDS = 60

LOCAL_IP: Optional[str] = None

# ── Helpers ───────────────────────────────────────────────────────────────────

def fmt_time() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def is_external(ip: str) -> bool:
    try:
        return not ipaddress.ip_address(ip).is_private
    except ValueError:
        return False

def get_local_ip() -> str:
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()

def get_d2r_pid() -> Optional[int]:
    for proc in psutil.process_iter(["name", "pid"]):
        if proc.info["name"] and proc.info["name"].lower() == PROCESS_NAME.lower():
            return proc.info["pid"]
    return None

def port_belongs_to_d2r(local_port: int, d2r_pid: int) -> bool:
    try:
        for c in psutil.net_connections(kind="tcp"):
            if c.laddr and c.laddr.port == local_port and c.pid == d2r_pid:
                return True
    except psutil.AccessDenied:
        pass
    return False

# ── Log output ────────────────────────────────────────────────────────────────

def log_started() -> None:
    line = "*" * 20 + " APPLICATION STARTED " + "*" * 20
    runLog.info(line)
    packetLog.info(line)

def packetlog_inbound_data(byte_count, conn, pkts, consec_fast, last_gap, server_ip, disq) -> None:
    packetLog.debug(
        f"  pkt={byte_count}b  total={conn.inbound_bytes}b  "
        f"peak_{RAPID_BURST_WINDOW}s={conn.peak_burst(RAPID_BURST_WINDOW)}b  "
        f"pkts={len(pkts)}  "
        f"large={conn.large_packet_count(EARLY_LARGE_PKT)}  "
        f"consec_large={conn.consecutive_large_streak()}  "
        f"consec_fast={consec_fast}  "
        f"ratio={conn.inbound_ratio():.2f}  "
        f"out_pkts={conn.outbound_count()}  "
        f"out_max={conn.max_outbound_packet()}b  "
        f"out_avg={conn.avg_outbound_size():.0f}b  "
        f"age={conn.age():.3f}s  "
        f"last_gap={last_gap}s  "
        f"src={server_ip}"
        + (f"  DISQ=[{disq}]" if disq else "")
    )

def packetlog_game_joined(c_ref) -> None:
    packetLog.info(
        f"JOINED  {c_ref.server_ip}:{c_ref.server_port}  "
        f"total={c_ref.inbound_bytes}b  "
        f"peak_{RAPID_BURST_WINDOW}s={c_ref.peak_burst(RAPID_BURST_WINDOW)}b  "
        f"large={c_ref.large_packet_count(EARLY_LARGE_PKT)}  "
        f"consec_large={c_ref.consecutive_large_streak()}  "
        f"mtu={c_ref.mtu_packet_count()}  "
        f"consec_fast={c_ref.max_consecutive_fast_inbound()}  "
        f"ratio={c_ref.inbound_ratio():.2f}  "
        f"out_total={c_ref.outbound_total()}b  "
        f"out_max={c_ref.max_outbound_packet()}b  "
        f"out_avg={c_ref.avg_outbound_size():.0f}b  "
        f"age={c_ref.age():.3f}s  "
        f"pkt_sizes={[s for _, s in c_ref.packets]}"
    )

def runlog_game_joined(c_ref, game_count) -> None:
    runLog.info(
        f"GAME JOINED  #{game_count}  "
        f"server={c_ref.server_ip}:{c_ref.server_port}  "
    )

# ── Console output ────────────────────────────────────────────────────────────

def cmd_msg_started() -> None:
    print("=" * 60)
    print("  D2R Game Session Detector")
    print(f"  Local IP           : {LOCAL_IP}")
    print(f"  Rapid burst        : >={RAPID_BURST_BYTES:,}b peak in {RAPID_BURST_WINDOW}s window")
    print(f"  Early large pkt    : >{EARLY_LARGE_PKT}b within {EARLY_LARGE_WINDOW}s "
          f"+ total >={EARLY_LARGE_MIN:,}b + peak >={EARLY_LARGE_BURST:,}b")
    print(f"  Consec fast        : >={CONSEC_FAST_CERTAIN} pkts <5ms gap  [override]")
    print(f"  Min inbound ratio  : {GAME_MIN_INBOUND_RATIO:.0%}")
    print(f"  Min consec large   : {GAME_MIN_CONSEC_LARGE}")
    print(f"  Min MTU packets    : {GAME_MIN_MTU_PACKETS}")
    print(f"  Max outbound single: {GAME_MAX_OUTBOUND_SINGLE}b")
    print(f"  Max outbound avg   : {GAME_MAX_OUTBOUND_AVG}b (>={GAME_MIN_OUTBOUND_SAMPLE} pkts)")
    print(f"  Expiry window      : {DATA_BURST_WINDOW}s")
    print("  Ctrl+drag orb to reposition. Ctrl+right-click for options.")
    print("=" * 60)
    stats.print_summary()
    print()

def cmd_msg_joined(c_ref, game_count) -> None:
    print(f"\n[{fmt_time()}] ▶  JOINED game  (#{game_count})")
    print(f"            Server      : {c_ref.server_ip}:{c_ref.server_port}")
    print(f"            Local port  : {c_ref.local_port}")
    print(f"            Total in    : {c_ref.inbound_bytes:,} bytes  "
          f"({c_ref.age():.2f}s after handshake)")
    print(f"            Peak burst  : {c_ref.peak_burst(RAPID_BURST_WINDOW):,} bytes "
          f"/ {RAPID_BURST_WINDOW}s window")
    print(f"            Inbound ratio: {c_ref.inbound_ratio():.0%}")
    print(f"            Total out   : {c_ref.outbound_total():,} bytes  "
          f"({c_ref.outbound_count()} pkts, "
          f"avg {c_ref.avg_outbound_size():.0f}b, "
          f"max {c_ref.max_outbound_packet()}b)")
    print(f"            Consec fast : {c_ref.max_consecutive_fast_inbound()} "
          f"packets <5ms gap")

# ── Stats Manager ─────────────────────────────────────────────────────────────

_STATS_DEFAULT = {
    "alltime": {
        "total_sessions":        0,
        "total_games":           0,
        "total_game_seconds":    0,
        "total_app_seconds":     0,
        "most_games_in_session": 0,
        "longest_game_seconds":  0,
        "first_game_at":         None,
        "last_game_at":          None,
        "unique_servers":        [],
    },
    "last_run": {
        "started_at":   None,
        "ended_at":     None,
        "games":        0,
        "game_seconds": 0,
        "crashed":      False,
    },
    "prefs": {
        "hint_shown": False,
    },
}

def _fmt_duration(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    h, rem = divmod(seconds, 3600)
    m, s   = divmod(rem, 60)
    if h:
        return f"{h}h {m}m {s}s"
    return f"{m}m {s}s"


class StatsManager:
    """
    Lightweight all-time stat tracker backed by a single JSON file.
    All public methods are thread-safe.
    File is written atomically via a temp file on every meaningful event.

    Separation of concerns
    ──────────────────────
    overlay display counter  →  user-adjustable, purely cosmetic
    StatsManager             →  counts real join events; never reads the display counter
    """

    def __init__(self, path: str = STATS_FILE) -> None:
        self._path      = path
        self._lock      = threading.Lock()
        self._data      = self._load()
        self._app_start = time.monotonic()

    # ── Persistence ───────────────────────────────────────────────────────────

    def _load(self) -> dict:
        if os.path.exists(self._path):
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                import copy
                for section, defaults in _STATS_DEFAULT.items():
                    data.setdefault(section, {})
                    for k, v in defaults.items():
                        data[section].setdefault(k, v)
                return data
            except (json.JSONDecodeError, OSError):
                runLog.warning("stats.json unreadable — starting fresh")
        import copy
        return copy.deepcopy(_STATS_DEFAULT)

    def _save(self) -> None:
        tmp = self._path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2)
            os.replace(tmp, self._path)
        except OSError as e:
            runLog.error(f"Failed to save stats: {e}")

    # ── Event hooks ───────────────────────────────────────────────────────────

    def on_session_start(self) -> None:
        with self._lock:
            at = self._data["alltime"]
            lr = self._data["last_run"]

            crashed = lr.get("started_at") and not lr.get("ended_at")
            if crashed:
                runLog.warning(
                    f"Previous session appears to have crashed "
                    f"(started {lr['started_at']}, no clean exit recorded)"
                )
                print(f"[{fmt_time()}] ⚠  Previous session ended without a clean exit "
                      f"(started {lr['started_at']})")

            at["total_sessions"] += 1

            self._data["last_run"] = {
                "started_at":   fmt_time(),
                "ended_at":     None,
                "games":        0,
                "game_seconds": 0,
                "crashed":      False,
            }
            self._save()

    def on_game_joined(self, server_ip: str, server_port: int) -> None:
        now        = fmt_time()
        server_key = f"{server_ip}:{server_port}"
        with self._lock:
            at = self._data["alltime"]
            lr = self._data["last_run"]

            at["total_games"] += 1
            lr["games"]       += 1

            if at["first_game_at"] is None:
                at["first_game_at"] = now
            at["last_game_at"] = now

            if server_key not in at["unique_servers"]:
                at["unique_servers"].append(server_key)

            self._save()

    def on_game_left(self, duration_seconds: int) -> None:
        with self._lock:
            at = self._data["alltime"]
            lr = self._data["last_run"]

            at["total_game_seconds"] += duration_seconds
            lr["game_seconds"]       += duration_seconds

            if duration_seconds > at["longest_game_seconds"]:
                at["longest_game_seconds"] = duration_seconds

            if lr["games"] > at["most_games_in_session"]:
                at["most_games_in_session"] = lr["games"]

            self._save()

    def on_session_end(self) -> None:
        elapsed = int(time.monotonic() - self._app_start)
        with self._lock:
            self._data["alltime"]["total_app_seconds"] += elapsed
            self._data["last_run"]["ended_at"]          = fmt_time()

            lr = self._data["last_run"]
            at = self._data["alltime"]
            if lr["games"] > at["most_games_in_session"]:
                at["most_games_in_session"] = lr["games"]

            self._save()

    # ── Read helpers ──────────────────────────────────────────────────────────

    def avg_game_duration(self) -> float:
        at = self._data["alltime"]
        if at["total_games"] == 0:
            return 0.0
        return at["total_game_seconds"] / at["total_games"]

    def last_run_games(self) -> int:
        return self._data["last_run"]["games"]

    @property
    def hint_shown(self) -> bool:
        return self._data["prefs"].get("hint_shown", False)

    def mark_hint_shown(self) -> None:
        with self._lock:
            self._data["prefs"]["hint_shown"] = True
            self._save()

    # ── Console summary ───────────────────────────────────────────────────────

    def print_summary(self) -> None:
        at  = self._data["alltime"]
        lr  = self._data["last_run"]
        avg = self.avg_game_duration()

        print("  ── All-time stats ──────────────────────────────────────")
        print(f"  Sessions          : {at['total_sessions']}")
        print(f"  Total games       : {at['total_games']}")
        print(f"  Time in-game      : {_fmt_duration(at['total_game_seconds'])}")
        print(f"  Total app runtime : {_fmt_duration(at['total_app_seconds'])}")
        print(f"  Avg game duration : {_fmt_duration(int(avg))}")
        print(f"  Longest game      : {_fmt_duration(at['longest_game_seconds'])}")
        print(f"  Best session      : {at['most_games_in_session']} games")
        print(f"  Unique servers    : {len(at['unique_servers'])}")
        if at["first_game_at"]:
            print(f"  First game ever   : {at['first_game_at']}")
        if at["last_game_at"]:
            print(f"  Last game         : {at['last_game_at']}")
        if lr["started_at"]:
            print(f"  Last run started  : {lr['started_at']}  "
                  f"({lr['games']} games, "
                  f"{_fmt_duration(lr['game_seconds'])} in-game)")
        print("  ────────────────────────────────────────────────────────")


stats = StatsManager()

# ── State machine ─────────────────────────────────────────────────────────────

class State(Enum):
    IDLE     = auto()
    TRACKING = auto()
    IN_GAME  = auto()

# ── Connection record ─────────────────────────────────────────────────────────

@dataclass
class Conn:
    server_ip:   str
    server_port: int
    local_port:  int
    syn_ack_at:  float = field(default_factory=time.monotonic)

    inbound_bytes:  int                    = 0
    _inbound_pkts:  list[tuple[float,int]] = field(default_factory=list)
    _outbound_pkts: list[tuple[float,int]] = field(default_factory=list)

    def key(self) -> tuple:
        return (self.server_ip, self.server_port, self.local_port)

    def age(self) -> float:
        return time.monotonic() - self.syn_ack_at

    # ── Inbound ───────────────────────────────────────────────────────────────

    def add_inbound(self, size: int) -> None:
        self._inbound_pkts.append((time.monotonic(), size))
        self.inbound_bytes += size

    @property
    def packets(self) -> list[tuple[float,int]]:
        return self._inbound_pkts

    def peak_burst(self, window: float) -> int:
        if not self._inbound_pkts:
            return 0
        best = running = 0
        j    = 0
        times = [t for t, _ in self._inbound_pkts]
        sizes = [s for _, s in self._inbound_pkts]
        for i in range(len(self._inbound_pkts)):
            running += sizes[i]
            while times[i] - times[j] > window:
                running -= sizes[j]
                j += 1
            best = max(best, running)
        return best

    def large_packet_count(self, threshold: int) -> int:
        return sum(1 for _, s in self._inbound_pkts if s > threshold)

    def consecutive_large_streak(self, threshold: int = 1000) -> int:
        best = current = 0
        for _, s in self._inbound_pkts:
            if s > threshold:
                current += 1
                best = max(best, current)
            else:
                current = 0
        return best

    def mtu_packet_count(self) -> int:
        return sum(1 for _, s in self._inbound_pkts if s >= 1400)

    def max_consecutive_fast_inbound(self) -> int:
        if len(self._inbound_pkts) < 2:
            return 0
        best = current = 1
        for i in range(1, len(self._inbound_pkts)):
            gap = self._inbound_pkts[i][0] - self._inbound_pkts[i-1][0]
            if gap < 0.005:
                current += 1
                best = max(best, current)
            else:
                current = 1
        return best

    # ── Outbound ──────────────────────────────────────────────────────────────

    def add_outbound(self, size: int) -> None:
        self._outbound_pkts.append((time.monotonic(), size))

    def outbound_total(self) -> int:
        return sum(s for _, s in self._outbound_pkts)

    def outbound_count(self) -> int:
        return len(self._outbound_pkts)

    def max_outbound_packet(self) -> int:
        return max((s for _, s in self._outbound_pkts), default=0)

    def avg_outbound_size(self) -> float:
        count = self.outbound_count()
        return self.outbound_total() / count if count > 0 else 0.0

    # ── Ratio ─────────────────────────────────────────────────────────────────

    def inbound_ratio(self) -> float:
        total = self.inbound_bytes + self.outbound_total()
        return self.inbound_bytes / total if total > 0 else 0.0

    # ── Classifier ────────────────────────────────────────────────────────────

    def disqualified_reason(self) -> Optional[str]:
        # Axis 1: inbound ratio
        ratio = self.inbound_ratio()
        if ratio < GAME_MIN_INBOUND_RATIO:
            return (f"inbound_ratio={ratio:.2f} < {GAME_MIN_INBOUND_RATIO} "
                    f"(client sent {self.outbound_total()}b / "
                    f"{self.inbound_bytes + self.outbound_total()}b total)")

        # Axis 2: inbound shape
        consec_large = self.consecutive_large_streak(threshold=1000)
        if consec_large < GAME_MIN_CONSEC_LARGE:
            consec_fast = self.max_consecutive_fast_inbound()
            if consec_fast < CONSEC_FAST_CERTAIN:
                return (f"consec_large={consec_large} < {GAME_MIN_CONSEC_LARGE} "
                        f"and consec_fast={consec_fast} < {CONSEC_FAST_CERTAIN}")

        mtu_pkts = self.mtu_packet_count()
        if mtu_pkts < GAME_MIN_MTU_PACKETS:
            consec_fast = self.max_consecutive_fast_inbound()
            if consec_fast < CONSEC_FAST_CERTAIN:
                return (f"mtu_pkts={mtu_pkts} < {GAME_MIN_MTU_PACKETS} "
                        f"and consec_fast={consec_fast} < {CONSEC_FAST_CERTAIN}")

        # Axis 3: outbound shape
        max_out = self.max_outbound_packet()
        if max_out > GAME_MAX_OUTBOUND_SINGLE:
            return (f"max_outbound_pkt={max_out}b > {GAME_MAX_OUTBOUND_SINGLE}b "
                    f"(likely credential/token exchange)")

        if self.outbound_count() >= GAME_MIN_OUTBOUND_SAMPLE:
            avg_out = self.avg_outbound_size()
            if avg_out > GAME_MAX_OUTBOUND_AVG:
                return (f"avg_outbound={avg_out:.0f}b > {GAME_MAX_OUTBOUND_AVG}b "
                        f"over {self.outbound_count()} packets "
                        f"(likely auth)")

        return None

    def is_game_like(self) -> bool:
        if self.disqualified_reason() is not None:
            return False

        burst       = self.peak_burst(RAPID_BURST_WINDOW)
        consec_fast = self.max_consecutive_fast_inbound()

        if consec_fast >= CONSEC_FAST_CERTAIN:
            packetLog.debug(
                f"  → consec_fast override ({consec_fast} >= {CONSEC_FAST_CERTAIN})"
            )
            return True

        early_large = (
            self.inbound_bytes >= EARLY_LARGE_MIN and
            burst >= EARLY_LARGE_BURST and
            any(
                size > EARLY_LARGE_PKT and (t - self.syn_ack_at) < EARLY_LARGE_WINDOW
                for t, size in self._inbound_pkts
            )
        )
        rapid_burst = burst >= RAPID_BURST_BYTES

        return early_large or rapid_burst


# ── Session ───────────────────────────────────────────────────────────────────

class Session:
    def __init__(self) -> None:
        self.lock            = threading.Lock()
        self.state           = State.IDLE
        self.conns:          dict[tuple, Conn]           = {}
        self.join_time:      Optional[datetime.datetime] = None
        self.game_server:    Optional[tuple]             = None
        self.d2r_pid:        Optional[int]               = None
        self.game_count:     int                         = 0
        self.bnet_connected: bool                        = False

    # ── PID tracking ──────────────────────────────────────────────────────────

    def refresh_pid(self) -> None:
        pid = get_d2r_pid()
        with self.lock:
            prev_pid = self.d2r_pid

        if pid == prev_pid:
            return

        if pid is None:
            with self.lock:
                self.d2r_pid        = None
                self.bnet_connected = False
            runLog.info(f"D2R CLOSED  (was PID {prev_pid})")
            print(f"[{fmt_time()}] ⚠  {PROCESS_NAME} not found — waiting ...")
        else:
            with self.lock:
                self.d2r_pid = pid
            runLog.info(f"D2R OPEN  pid={pid}")
            print(f"[{fmt_time()}] Found {PROCESS_NAME} (PID {pid})")
            self.check_bnet_already_connected(pid)

    def check_bnet_already_connected(self, pid: int) -> None:
        try:
            established = [
                c for c in psutil.net_connections(kind="tcp")
                if c.pid == pid
                and c.status == "ESTABLISHED"
                and c.raddr
                and c.raddr.port == GAME_SERVER_PORT
                and is_external(c.raddr.ip)
            ]
            if established:
                with self.lock:
                    self.bnet_connected = True
                packetLog.info(
                    f"BNET CONNECTED  (inferred — {len(established)} established "
                    f"connection(s) found at attach time)"
                )
                print(f"[{fmt_time()}] ✔  Already connected to Battle.net "
                      f"({len(established)} active connection(s))")
        except psutil.AccessDenied:
            pass

    # ── Packet events ─────────────────────────────────────────────────────────

    def on_syn_ack(self, server_ip: str, server_port: int, local_port: int) -> None:
        with self.lock:
            if self.state == State.IN_GAME:
                return
            pid = self.d2r_pid
            if pid is None:
                return

        if not port_belongs_to_d2r(local_port, pid):
            return

        key = (server_ip, server_port, local_port)
        with self.lock:
            if self.state == State.IN_GAME:
                return
            if key in self.conns:
                return
            self.conns[key] = Conn(server_ip=server_ip,
                                   server_port=server_port,
                                   local_port=local_port)
            self.state = State.TRACKING

        packetLog.info(
            f"CANDIDATE  {server_ip}:{server_port}  local:{local_port}  "
            f"tracking={len(self.conns)}"
        )
        print(f"[{fmt_time()}] ℹ  D2R candidate: {server_ip}:{server_port} "
              f"← local:{local_port}  (watching ...)")

    def on_inbound_data(self, server_ip: str, server_port: int,
                        local_port: int, byte_count: int) -> None:
        promoted = False
        c_ref    = None
        key      = (server_ip, server_port, local_port)

        with self.lock:
            if self.state != State.TRACKING:
                return
            conn = self.conns.get(key)
            if conn is None:
                return

            conn.add_inbound(byte_count)

            pkts        = conn.packets
            gaps        = [round(pkts[i][0] - pkts[i-1][0], 4) for i in range(1, len(pkts))]
            last_gap    = gaps[-1] if gaps else 0.0
            disq        = conn.disqualified_reason()
            consec_fast = conn.max_consecutive_fast_inbound()

            packetlog_inbound_data(byte_count, conn, pkts, consec_fast, last_gap, server_ip, disq)

            if conn.is_game_like():
                self.state       = State.IN_GAME
                self.join_time   = datetime.datetime.now()
                self.game_server = key
                self.game_count += 1
                c_ref            = conn
                promoted         = True
                self.conns.clear()

        if promoted and c_ref:
            packetlog_game_joined(c_ref)
            runlog_game_joined(c_ref, self.game_count)
            cmd_msg_joined(c_ref, self.game_count)
            stats.on_game_joined(c_ref.server_ip, c_ref.server_port)
            signals.joined.emit()

    def on_outbound_data(self, server_ip: str, server_port: int,
                         local_port: int, byte_count: int) -> None:
        key = (server_ip, server_port, local_port)
        with self.lock:
            conn = self.conns.get(key)
            if conn is None:
                return
            conn.add_outbound(byte_count)

    def on_outbound_fin(self, server_ip: str, server_port: int,
                        local_port: int) -> None:
        left         = False
        duration_sec = 0
        key          = (server_ip, server_port, local_port)

        with self.lock:
            if self.state == State.TRACKING:
                self.conns.pop(key, None)
                if not self.conns:
                    self.state = State.IDLE
                return

            if self.state != State.IN_GAME:
                return
            if key != self.game_server:
                return

            duration = ""
            if self.join_time:
                duration_sec = int(
                    (datetime.datetime.now() - self.join_time).total_seconds()
                )
                duration = f"  (duration: {duration_sec // 60}m {duration_sec % 60}s)"
            server           = f"{server_ip}:{server_port}"
            game_num         = self.game_count
            self.state       = State.IDLE
            self.game_server = None
            self.conns.clear()
            self.join_time   = None
            left             = True

        if left:
            early     = 0 < duration_sec < EARLY_ABANDON_SECONDS
            early_tag = "  [early abandon]" if early else ""
            packetLog.info(f"LEFT  {server}{duration}{early_tag}")
            runLog.info(
                f"GAME LEFT    #{game_num}  server={server}  "
                f"{duration.strip()}{early_tag}"
            )
            print(f"\n[{fmt_time()}] ■  LEFT game{duration}{early_tag}")
            print(f"            Server was : {server}")
            stats.on_game_left(duration_sec)
            signals.left.emit()

    # ── Candidate expiry ──────────────────────────────────────────────────────

    def expire_candidate(self) -> None:
        with self.lock:
            if self.state != State.TRACKING:
                return
            now     = time.monotonic()
            expired = [k for k, c in self.conns.items()
                       if now - c.syn_ack_at > DATA_BURST_WINDOW]

            newly_confirmed_bnet = False

            for k in expired:
                c = self.conns.pop(k)

                if not self.bnet_connected and c.inbound_bytes > 1_000:
                    self.bnet_connected  = True
                    newly_confirmed_bnet = True

                disq       = c.disqualified_reason()
                reason_str = disq if disq else "did not meet burst threshold"

                packetLog.warning(
                    f"EXPIRED  {c.server_ip}:{c.server_port}  "
                    f"total={c.inbound_bytes}b  "
                    f"peak_{RAPID_BURST_WINDOW}s={c.peak_burst(RAPID_BURST_WINDOW)}b  "
                    f"consec_large={c.consecutive_large_streak()}  "
                    f"mtu={c.mtu_packet_count()}  "
                    f"consec_fast={c.max_consecutive_fast_inbound()}  "
                    f"ratio={c.inbound_ratio():.2f}  "
                    f"out_total={c.outbound_total()}b  "
                    f"out_max={c.max_outbound_packet()}b  "
                    f"out_avg={c.avg_outbound_size():.0f}b  "
                    f"age={c.age():.1f}s  "
                    f"reason=[{reason_str}]"
                )
                print(f"[{fmt_time()}] ℹ  Candidate {c.server_ip}:{c.server_port} "
                      f"expired ({c.inbound_bytes:,}b in / "
                      f"{c.outbound_total():,}b out  "
                      f"ratio={c.inbound_ratio():.0%}  "
                      f"reason: {reason_str})")

            if newly_confirmed_bnet:
                runLog.info("BNET CONNECTED")
                print(f"[{fmt_time()}] ✔  Connected to Battle.net")

            if not self.conns:
                self.state = State.IDLE


session = Session()

# ── Packet handler ────────────────────────────────────────────────────────────

def handle_packet(pkt) -> None:
    if not (IP in pkt and TCP in pkt):
        return

    src_ip   = pkt[IP].src
    dst_ip   = pkt[IP].dst
    src_port = pkt[TCP].sport
    dst_port = pkt[TCP].dport
    flags    = pkt[TCP].flags
    length   = len(pkt[IP])

    syn = bool(flags & 0x02)
    fin = bool(flags & 0x01)
    ack = bool(flags & 0x10)
    rst = bool(flags & 0x04)

    tcp_header_len = (pkt[TCP].dataofs or 5) * 4
    ip_header_len  = pkt[IP].ihl * 4
    payload_len    = length - ip_header_len - tcp_header_len

    # Inbound: server → client
    if src_port == GAME_SERVER_PORT and dst_ip == LOCAL_IP and is_external(src_ip):
        if syn and ack and not fin:
            session.on_syn_ack(src_ip, src_port, dst_port)
            return
        if payload_len > 0 and not syn and not fin and not rst:
            session.on_inbound_data(src_ip, src_port, dst_port, payload_len)
            return

    # Outbound: client → server
    if dst_port == GAME_SERVER_PORT and src_ip == LOCAL_IP and is_external(dst_ip):
        if fin and ack and not syn:
            session.on_outbound_fin(dst_ip, dst_port, src_port)
            return
        if payload_len > 0 and not syn and not fin and not rst:
            session.on_outbound_data(dst_ip, dst_port, src_port, payload_len)
            return

# ── Background threads ────────────────────────────────────────────────────────

def expiry_loop() -> None:
    while True:
        time.sleep(0.25)
        session.expire_candidate()

def pid_watch_loop() -> None:
    while True:
        session.refresh_pid()
        time.sleep(5)

def sniffer_loop(bpf: str) -> None:
    sniff(filter=bpf, prn=handle_packet, store=False, iface=None)

def set_bpf(ip: str) -> str:
    return (
        f"tcp port {GAME_SERVER_PORT} "
        f"and (src host {ip} or dst host {ip})"
    )

# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    log_started()

    global LOCAL_IP
    if LOCAL_IP is None:
        LOCAL_IP = get_local_ip()

    stats.on_session_start()

    bpf = set_bpf(LOCAL_IP)
    cmd_msg_started()
    session.refresh_pid()

    threading.Thread(target=expiry_loop,              daemon=True).start()
    threading.Thread(target=pid_watch_loop,           daemon=True).start()
    threading.Thread(target=sniffer_loop, args=(bpf,), daemon=True).start()

    def _on_quit() -> None:
        """
        Capture in-game duration on clean exit so it isn't lost.
        Runs in the Qt thread via aboutToQuit.
        """
        with session.lock:
            active_secs = 0
            if session.state == State.IN_GAME and session.join_time:
                active_secs = int(
                    (datetime.datetime.now() - session.join_time).total_seconds()
                )
        if active_secs:
            stats.on_game_left(active_secs)
        stats.on_session_end()

    manager = OverlayManager(
        on_hint_dismissed  = stats.mark_hint_shown,
        show_hint_on_start = True,
        # show_hint_on_start = not stats.hint_shown,
    )
    manager.app.aboutToQuit.connect(_on_quit)
    manager.run()


if __name__ == "__main__":
    try:
        psutil.net_connections(kind="tcp")
    except psutil.AccessDenied:
        sys.exit("ERROR: Access denied — run as Administrator.")
    main()