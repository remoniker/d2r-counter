"""
npcap.py — Npcap presence check and silent installer for D2R Counter.

Called once at startup via npcap.ensure(). Exits the process if Npcap
is missing and the user declines installation, or if installation fails.
"""

import os
import subprocess
import sys
import tempfile
import urllib.request

_INSTALLER_URL = "https://npcap.com/dist/npcap-1.80.exe"


def _installed() -> bool:
    try:
        r = subprocess.run(["sc", "query", "npcap"], capture_output=True, text=True)
        return "RUNNING" in r.stdout or "STOPPED" in r.stdout
    except OSError:
        return False


def ensure() -> None:
    """Ensure Npcap is installed. Prompts to download and install if not. Blocks until done."""
    if _installed():
        return

    from PyQt6.QtWidgets import QApplication, QMessageBox
    QApplication.instance() or QApplication(sys.argv)

    reply = QMessageBox.question(
        None,
        "Npcap Required",
        "D2R Counter requires Npcap for packet capture — it is not currently installed.\n\n"
        "Download and install Npcap now? (~1 MB, may take a moment)",
    )
    if reply != QMessageBox.StandardButton.Yes:
        sys.exit(0)

    tmp = os.path.join(tempfile.gettempdir(), "npcap-installer.exe")
    try:
        urllib.request.urlretrieve(_INSTALLER_URL, tmp)
        subprocess.run([tmp, "/winpcap_mode=yes"], check=True)
    except Exception as e:
        QMessageBox.critical(
            None,
            "Installation Failed",
            f"Could not install Npcap automatically:\n{e}\n\n"
            "Please install manually from https://npcap.com",
        )
        sys.exit(1)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
