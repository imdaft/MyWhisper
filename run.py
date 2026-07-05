"""MyWhisper entry point. Run from project root: python run.py

When called with --worker, runs the whisper subprocess (used by PyInstaller build).
"""
from __future__ import annotations

import multiprocessing
import sys
from pathlib import Path

# Ensure project root is on sys.path so `from src.xxx` imports work
ROOT = str(Path(__file__).resolve().parent)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


if __name__ == "__main__":
    multiprocessing.freeze_support()

    if "--worker" in sys.argv:
        # Whisper worker subprocess — no PyQt6 imports here
        from src.whisper_worker import main as worker_main
        worker_main()
    else:
        from src.main import main
        sys.exit(main())
