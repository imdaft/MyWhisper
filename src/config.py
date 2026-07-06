from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QObject, pyqtSignal

logger = logging.getLogger(__name__)

DEFAULT_CONFIG: dict[str, Any] = {
    "hotkey": ["ctrl", "shift", "space"],
    "hotkey_mode": "hold",
    "model_size": "base",
    "language": "auto",
    "audio_device": None,
    "overlay_position": "bottom_center",
    "theme": "dark",
    "autostart": False,
    "compute_type": "auto",
    # User dictionary: names / terms fed to Whisper as hotwords to improve
    # recognition. Free text, one word or phrase per line.
    "custom_words": "",
}


def _get_config_dir() -> Path:
    appdata = os.environ.get("APPDATA", "")
    if not appdata:
        appdata = str(Path.home() / "AppData" / "Roaming")
    return Path(appdata) / "MyWhisper"


def _get_config_path() -> Path:
    return _get_config_dir() / "config.json"


class Config(QObject):
    config_changed = pyqtSignal(str, object)  # key, new_value

    def __init__(self) -> None:
        super().__init__()
        self._lock = threading.Lock()
        self._data: dict[str, Any] = dict(DEFAULT_CONFIG)
        self._config_path = _get_config_path()
        self.load()

    def load(self) -> None:
        with self._lock:
            if not self._config_path.exists():
                self._data = dict(DEFAULT_CONFIG)
                self._save_locked()
                return
            try:
                raw = self._config_path.read_text(encoding="utf-8")
                parsed = json.loads(raw)
                if not isinstance(parsed, dict):
                    raise ValueError("Config root must be a JSON object")
                merged = dict(DEFAULT_CONFIG)
                # Only accept keys that exist in DEFAULT_CONFIG to prevent
                # injection of arbitrary config keys from a tampered file
                for k, v in parsed.items():
                    if k in DEFAULT_CONFIG:
                        merged[k] = v
                    else:
                        logger.warning("Ignoring unknown config key '%s'", k)
                self._data = merged
            except (json.JSONDecodeError, ValueError, OSError) as exc:
                logger.warning("Corrupt config file, resetting to defaults: %s", exc)
                self._data = dict(DEFAULT_CONFIG)
                self._save_locked()

    def save(self) -> None:
        with self._lock:
            self._save_locked()

    def _save_locked(self) -> None:
        try:
            self._config_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = self._config_path.with_suffix(".tmp")
            tmp_path.write_text(
                json.dumps(self._data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            tmp_path.replace(self._config_path)
        except OSError as exc:
            logger.error("Failed to save config: %s", exc)

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        if key not in DEFAULT_CONFIG:
            logger.warning("Attempted to set unknown config key '%s', ignoring", key)
            return
        with self._lock:
            old = self._data.get(key)
            self._data[key] = value
            self._save_locked()
        if old != value:
            self.config_changed.emit(key, value)

    @property
    def data(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._data)
