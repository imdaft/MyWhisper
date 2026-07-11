"""Unit tests for src.tray_icon.TrayIcon last-phrase recovery feature."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PyQt6.QtWidgets import QApplication

_app: QApplication | None = None


def setUpModule() -> None:
    global _app
    if QApplication.instance() is None:
        _app = QApplication([])


from src.tray_icon import TrayIcon


class TestFormatLastPhraseLabel(unittest.TestCase):

    def test_empty_shows_placeholder(self) -> None:
        self.assertEqual(TrayIcon._format_last_phrase_label(""), "Копировать: (нет)")

    def test_short_text_shown_in_full(self) -> None:
        label = TrayIcon._format_last_phrase_label("Привет, мир")
        self.assertEqual(label, "Копировать: Привет, мир")

    def test_long_text_is_truncated(self) -> None:
        text = "a" * 100
        label = TrayIcon._format_last_phrase_label(text)
        self.assertTrue(label.startswith("Копировать: " + "a" * 57 + "..."))
        self.assertLess(len(label), len(text))


class TestPersistence(unittest.TestCase):

    def test_persist_and_reload_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "MyWhisper" / "last_phrase.txt"
            with patch("src.tray_icon._get_last_phrase_path", return_value=path):
                TrayIcon._persist_last_phrase("Тестовая фраза")
                loaded = TrayIcon._load_persisted_last_phrase()
            self.assertEqual(loaded, "Тестовая фраза")

    def test_load_missing_file_returns_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "MyWhisper" / "last_phrase.txt"
            with patch("src.tray_icon._get_last_phrase_path", return_value=path):
                loaded = TrayIcon._load_persisted_last_phrase()
            self.assertEqual(loaded, "")

    def test_persist_failure_does_not_raise(self) -> None:
        # A filesystem error while writing should be swallowed, not crash
        # the caller (e.g. disk full, permission denied).
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "MyWhisper" / "last_phrase.txt"
            with patch("src.tray_icon._get_last_phrase_path", return_value=path), \
                 patch.object(Path, "mkdir", side_effect=OSError("disk full")):
                TrayIcon._persist_last_phrase("text")  # must not raise


class TestTrayIconStartup(unittest.TestCase):

    def test_constructor_restores_persisted_phrase(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "MyWhisper" / "last_phrase.txt"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("Восстановленная фраза", encoding="utf-8")
            with patch("src.tray_icon._get_last_phrase_path", return_value=path):
                icon = TrayIcon()
            self.assertEqual(icon._last_text, "Восстановленная фраза")
            self.assertTrue(icon._last_phrase_action.isEnabled())
            self.assertIn("Восстановленная фраза", icon._last_phrase_action.text())

    def test_constructor_with_no_persisted_phrase_disables_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "MyWhisper" / "last_phrase.txt"
            with patch("src.tray_icon._get_last_phrase_path", return_value=path):
                icon = TrayIcon()
            self.assertEqual(icon._last_text, "")
            self.assertFalse(icon._last_phrase_action.isEnabled())


class TestShowLastPhrase(unittest.TestCase):

    def test_show_last_phrase_updates_state_and_persists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "MyWhisper" / "last_phrase.txt"
            with patch("src.tray_icon._get_last_phrase_path", return_value=path):
                icon = TrayIcon()
                icon.show_last_phrase("Новая фраза")
                self.assertEqual(icon._last_text, "Новая фраза")
                self.assertTrue(icon._last_phrase_action.isEnabled())
                self.assertIn("Новая фраза", icon._last_phrase_action.text())
                self.assertEqual(path.read_text(encoding="utf-8"), "Новая фраза")


class TestCopyLastPhrase(unittest.TestCase):

    @patch("src.tray_icon.pyperclip")
    def test_copy_copies_full_text_and_notifies(self, mock_pyperclip: MagicMock) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "MyWhisper" / "last_phrase.txt"
            with patch("src.tray_icon._get_last_phrase_path", return_value=path):
                icon = TrayIcon()
                long_text = "Длинная фраза, которая не помещается в 60 символов меню целиком"
                icon.show_last_phrase(long_text)
                icon._on_copy_last_phrase()
        mock_pyperclip.copy.assert_called_once_with(long_text)

    @patch("src.tray_icon.pyperclip")
    def test_copy_noop_when_nothing_recorded_yet(self, mock_pyperclip: MagicMock) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "MyWhisper" / "last_phrase.txt"
            with patch("src.tray_icon._get_last_phrase_path", return_value=path):
                icon = TrayIcon()
                icon._on_copy_last_phrase()
        mock_pyperclip.copy.assert_not_called()

    @patch("src.tray_icon.pyperclip")
    def test_copy_failure_does_not_raise(self, mock_pyperclip: MagicMock) -> None:
        mock_pyperclip.copy.side_effect = Exception("clipboard busy")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "MyWhisper" / "last_phrase.txt"
            with patch("src.tray_icon._get_last_phrase_path", return_value=path):
                icon = TrayIcon()
                icon.show_last_phrase("text")
                icon._on_copy_last_phrase()  # must not raise


if __name__ == "__main__":
    unittest.main()
