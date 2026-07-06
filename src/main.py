from __future__ import annotations

import ctypes
import logging
import logging.handlers
import os
import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication, QMessageBox


def _get_log_path() -> Path:
    appdata = os.environ.get("APPDATA", "")
    if not appdata:
        appdata = str(Path.home() / "AppData" / "Roaming")
    log_dir = Path(appdata) / "MyWhisper"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / "mywhisper.log"


def _setup_logging() -> None:
    log_path = _get_log_path()
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

    root = logging.getLogger()
    root.setLevel(logging.INFO)

    try:
        # Rotating handler caps disk usage: 5 MB per file, 2 backups.
        fh = logging.handlers.RotatingFileHandler(
            str(log_path),
            maxBytes=5 * 1024 * 1024,
            backupCount=2,
            encoding="utf-8",
        )
        fh.setFormatter(logging.Formatter(fmt))
        root.addHandler(fh)
    except Exception:
        pass

    # In PyInstaller windowed mode, sys.stdout may be None
    if sys.stdout is not None:
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(logging.Formatter(fmt))
        root.addHandler(sh)


def _acquire_single_instance() -> ctypes.c_void_p | None:
    MUTEX_NAME = "Global\\MyWhisper_SingleInstance_Mutex"
    ERROR_ALREADY_EXISTS = 0xB7

    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)

    if handle == 0:
        return None

    if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
        kernel32.CloseHandle(handle)
        return None

    return handle


def _release_mutex(handle: ctypes.c_void_p) -> None:
    if handle:
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        kernel32.ReleaseMutex(handle)
        kernel32.CloseHandle(handle)


def main() -> int:
    _setup_logging()
    logger = logging.getLogger("mywhisper")
    logger.info("MyWhisper starting...")

    mutex_handle = _acquire_single_instance()
    if mutex_handle is None:
        app = QApplication(sys.argv)
        QMessageBox.warning(
            None,
            "MyWhisper",
            "Another instance of MyWhisper is already running.",
        )
        return 1

    exit_code = 1
    try:
        app = QApplication(sys.argv)
        app.setApplicationName("MyWhisper")
        app.setQuitOnLastWindowClosed(False)

        from src.app import App

        controller = App()
        controller.start()

        logger.info("Entering event loop...")
        exit_code = app.exec()
        logger.info("Event loop returned with code %d", exit_code)
    except Exception:
        logger.critical("Unhandled exception", exc_info=True)
    finally:
        try:
            controller.cleanup()  # type: ignore[possibly-undefined]
        except Exception:
            logger.error("Error during cleanup", exc_info=True)
        _release_mutex(mutex_handle)
        logger.info("MyWhisper exited with code %d", exit_code)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
