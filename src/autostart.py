"""Windows autostart via the per-user Run registry key.

Writing to HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run makes Windows
launch MyWhisper at logon. This is per-user, so it needs no admin rights.

`winreg` is imported lazily inside each function so this module still imports on
non-Windows machines (e.g. when running the test suite on Linux/CI).
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

_APP_NAME = "MyWhisper"
_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _launch_command() -> str:
    """Command Windows should run at logon, quoted for paths with spaces."""
    if getattr(sys, "frozen", False):
        # PyInstaller build: the packaged .exe relaunches itself.
        return f'"{sys.executable}"'
    # Dev run: use pythonw.exe (no console window) + run.py at the project root.
    root = Path(__file__).resolve().parent.parent
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    python = str(pythonw) if pythonw.exists() else sys.executable
    return f'"{python}" "{root / "run.py"}"'


def is_enabled() -> bool:
    """Return True if MyWhisper is currently registered to start at logon."""
    try:
        import winreg
    except ImportError:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            winreg.QueryValueEx(key, _APP_NAME)
        return True
    except FileNotFoundError:
        return False
    except OSError as exc:
        logger.warning("Could not read autostart state: %s", exc)
        return False


def set_enabled(enabled: bool) -> bool:
    """Enable or disable launch at logon. Returns True on success."""
    try:
        import winreg
    except ImportError:
        logger.info("Autostart is only supported on Windows; skipping")
        return False
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            if enabled:
                winreg.SetValueEx(key, _APP_NAME, 0, winreg.REG_SZ, _launch_command())
                logger.info("Autostart enabled")
            else:
                try:
                    winreg.DeleteValue(key, _APP_NAME)
                    logger.info("Autostart disabled")
                except FileNotFoundError:
                    pass  # already absent
        return True
    except OSError as exc:
        logger.error("Failed to update autostart: %s", exc)
        return False
