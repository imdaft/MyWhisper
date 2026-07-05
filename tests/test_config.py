"""Unit tests for src.config.Config."""
from __future__ import annotations

import json
import sys
import threading
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ---------------------------------------------------------------------------
# PyQt6 QApplication must exist before any QObject subclass is instantiated.
# We create it once for the whole module.
# ---------------------------------------------------------------------------
from PyQt6.QtWidgets import QApplication

_app: QApplication | None = None


def setUpModule() -> None:
    global _app
    if QApplication.instance() is None:
        _app = QApplication([])


from src.config import Config, DEFAULT_CONFIG


class TestConfigDefaults(unittest.TestCase):
    """Verify the default configuration dictionary values."""

    def test_default_hotkey(self) -> None:
        self.assertEqual(DEFAULT_CONFIG["hotkey"], ["ctrl", "shift", "space"])

    def test_default_hotkey_mode(self) -> None:
        self.assertEqual(DEFAULT_CONFIG["hotkey_mode"], "hold")

    def test_default_model_size(self) -> None:
        self.assertEqual(DEFAULT_CONFIG["model_size"], "base")

    def test_default_language(self) -> None:
        self.assertEqual(DEFAULT_CONFIG["language"], "auto")

    def test_default_audio_device(self) -> None:
        self.assertIsNone(DEFAULT_CONFIG["audio_device"])

    def test_default_overlay_position(self) -> None:
        self.assertEqual(DEFAULT_CONFIG["overlay_position"], "bottom_center")

    def test_default_theme(self) -> None:
        self.assertEqual(DEFAULT_CONFIG["theme"], "dark")

    def test_default_autostart(self) -> None:
        self.assertFalse(DEFAULT_CONFIG["autostart"])

    def test_default_compute_type(self) -> None:
        self.assertEqual(DEFAULT_CONFIG["compute_type"], "auto")


class TestConfigLoadCreatesFile(unittest.TestCase):
    """Config.load() should create the config file if it does not exist."""

    def test_load_creates_config_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_file = Path(tmp) / "config.json"
            self.assertFalse(config_file.exists())

            with patch("src.config._get_config_path", return_value=config_file):
                cfg = Config()

            self.assertTrue(config_file.exists())
            data = json.loads(config_file.read_text(encoding="utf-8"))
            self.assertEqual(data, DEFAULT_CONFIG)


class TestConfigSaveLoadRoundtrip(unittest.TestCase):
    """save() followed by a fresh load() should preserve data."""

    def test_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_file = Path(tmp) / "config.json"

            with patch("src.config._get_config_path", return_value=config_file):
                cfg1 = Config()
                cfg1.set("theme", "light")
                cfg1.set("language", "en")
                cfg1.save()

                # Create a brand-new Config to re-load from disk
                cfg2 = Config()

            self.assertEqual(cfg2.get("theme"), "light")
            self.assertEqual(cfg2.get("language"), "en")
            # Defaults that were not changed should still be present
            self.assertEqual(cfg2.get("model_size"), "base")


class TestConfigGet(unittest.TestCase):
    """Config.get() should return default for missing keys."""

    def test_get_existing_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_file = Path(tmp) / "config.json"
            with patch("src.config._get_config_path", return_value=config_file):
                cfg = Config()
            self.assertEqual(cfg.get("theme"), "dark")

    def test_get_missing_key_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_file = Path(tmp) / "config.json"
            with patch("src.config._get_config_path", return_value=config_file):
                cfg = Config()
            self.assertIsNone(cfg.get("nonexistent_key"))

    def test_get_missing_key_returns_custom_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_file = Path(tmp) / "config.json"
            with patch("src.config._get_config_path", return_value=config_file):
                cfg = Config()
            self.assertEqual(cfg.get("nonexistent_key", "fallback"), "fallback")


class TestConfigSet(unittest.TestCase):
    """Config.set() should update, save, and emit signals correctly."""

    def _make_config(self, tmp: str) -> Config:
        config_file = Path(tmp) / "config.json"
        with patch("src.config._get_config_path", return_value=config_file):
            cfg = Config()
        # After construction, keep the patched path for subsequent saves.
        cfg._config_path = config_file
        return cfg

    def test_set_updates_value(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self._make_config(tmp)
            cfg.set("theme", "light")
            self.assertEqual(cfg.get("theme"), "light")

    def test_set_persists_to_disk(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self._make_config(tmp)
            cfg.set("theme", "light")
            data = json.loads(cfg._config_path.read_text(encoding="utf-8"))
            self.assertEqual(data["theme"], "light")

    def test_set_emits_signal_on_change(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self._make_config(tmp)
            handler = MagicMock()
            cfg.config_changed.connect(handler)

            cfg.set("theme", "light")

            handler.assert_called_once_with("theme", "light")

    def test_set_does_not_emit_signal_when_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self._make_config(tmp)
            handler = MagicMock()
            cfg.config_changed.connect(handler)

            # Set to the same value that is already the default
            cfg.set("theme", "dark")

            handler.assert_not_called()


class TestConfigCorruptFile(unittest.TestCase):
    """A corrupt JSON file should cause a reset to defaults."""

    def test_corrupt_json_resets_to_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_file = Path(tmp) / "config.json"
            config_file.write_text("NOT VALID JSON {{{", encoding="utf-8")

            with patch("src.config._get_config_path", return_value=config_file):
                cfg = Config()

            self.assertEqual(cfg.get("theme"), "dark")
            self.assertEqual(cfg.get("model_size"), "base")
            # The file should have been re-written with valid defaults
            data = json.loads(config_file.read_text(encoding="utf-8"))
            self.assertEqual(data, DEFAULT_CONFIG)

    def test_non_dict_json_resets_to_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_file = Path(tmp) / "config.json"
            config_file.write_text('"just a string"', encoding="utf-8")

            with patch("src.config._get_config_path", return_value=config_file):
                cfg = Config()

            self.assertEqual(cfg.data, DEFAULT_CONFIG)


class TestConfigThreadSafety(unittest.TestCase):
    """Concurrent set() calls from multiple threads must not corrupt data."""

    def test_concurrent_sets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_file = Path(tmp) / "config.json"
            with patch("src.config._get_config_path", return_value=config_file):
                cfg = Config()
            cfg._config_path = config_file

            errors: list[Exception] = []
            iterations = 50

            def setter(key: str, values: list) -> None:
                try:
                    for v in values:
                        cfg.set(key, v)
                except Exception as exc:
                    errors.append(exc)

            threads = [
                threading.Thread(
                    target=setter,
                    args=("theme", [f"theme_{i}" for i in range(iterations)]),
                ),
                threading.Thread(
                    target=setter,
                    args=("language", [f"lang_{i}" for i in range(iterations)]),
                ),
                threading.Thread(
                    target=setter,
                    args=("model_size", [f"model_{i}" for i in range(iterations)]),
                ),
            ]

            for t in threads:
                t.start()
            for t in threads:
                t.join()

            self.assertEqual(errors, [])
            # After all threads finish, the config should still be readable
            data = cfg.data
            self.assertIn("theme", data)
            self.assertIn("language", data)
            self.assertIn("model_size", data)

            # The file on disk should be valid JSON
            disk_data = json.loads(config_file.read_text(encoding="utf-8"))
            self.assertIsInstance(disk_data, dict)


if __name__ == "__main__":
    unittest.main()
