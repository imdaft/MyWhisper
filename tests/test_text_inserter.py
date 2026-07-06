"""Unit tests for src.text_inserter.TextInserter."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock, call

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.text_inserter import TextInserter

# The clipboard path is what these tests exercise; force the "clipboard holds
# only text" branch so results don't depend on the machine's real clipboard.
_nontext_patcher = None


def setUpModule() -> None:
    global _nontext_patcher
    _nontext_patcher = patch("src.text_inserter._clipboard_has_nontext", return_value=False)
    _nontext_patcher.start()


def tearDownModule() -> None:
    if _nontext_patcher is not None:
        _nontext_patcher.stop()


class TestInsertTextEmpty(unittest.TestCase):
    """insert_text with empty or falsy string should return False immediately."""

    def test_empty_string_returns_false(self) -> None:
        ti = TextInserter()
        result = ti.insert_text("")
        self.assertFalse(result)

    def test_none_coerced_to_falsy_returns_false(self) -> None:
        ti = TextInserter()
        # Type annotation says str, but we test defensive behaviour
        result = ti.insert_text(None)  # type: ignore[arg-type]
        self.assertFalse(result)


class TestInsertTextHappyPath(unittest.TestCase):
    """Successful insertion should copy, paste, and restore clipboard."""

    @patch("src.text_inserter.time")
    @patch("src.text_inserter._send_ctrl_v")
    @patch("src.text_inserter.pyperclip")
    def test_calls_copy_sendctrlv_and_restore(
        self,
        mock_pyperclip: MagicMock,
        mock_send_ctrl_v: MagicMock,
        mock_time: MagicMock,
    ) -> None:
        mock_pyperclip.paste.return_value = "original clipboard"

        ti = TextInserter()
        result = ti.insert_text("Hello World")

        self.assertTrue(result)

        # pyperclip.paste() was called first to save clipboard
        mock_pyperclip.paste.assert_called_once()

        # pyperclip.copy() was called at least twice:
        #   1) to set the text to paste
        #   2) to restore the original clipboard
        copy_calls = mock_pyperclip.copy.call_args_list
        self.assertGreaterEqual(len(copy_calls), 2)
        self.assertEqual(copy_calls[0], call("Hello World"))
        self.assertEqual(copy_calls[-1], call("original clipboard"))

        # _send_ctrl_v was called for Ctrl+V
        mock_send_ctrl_v.assert_called_once()

    @patch("src.text_inserter.time")
    @patch("src.text_inserter._send_ctrl_v")
    @patch("src.text_inserter.pyperclip")
    def test_sleep_called_for_clipboard_delay(
        self,
        mock_pyperclip: MagicMock,
        mock_send_ctrl_v: MagicMock,
        mock_time: MagicMock,
    ) -> None:
        mock_pyperclip.paste.return_value = ""

        ti = TextInserter()
        ti.insert_text("text")

        # time.sleep should be called at least twice (before and after hotkey)
        self.assertGreaterEqual(mock_time.sleep.call_count, 2)


class TestInsertTextClipboardSaveFailure(unittest.TestCase):
    """If saving the clipboard fails, insertion should still proceed."""

    @patch("src.text_inserter.time")
    @patch("src.text_inserter._send_ctrl_v")
    @patch("src.text_inserter.pyperclip")
    def test_clipboard_save_failure_still_inserts(
        self,
        mock_pyperclip: MagicMock,
        mock_send_ctrl_v: MagicMock,
        mock_time: MagicMock,
    ) -> None:
        # pyperclip.paste raises when trying to read clipboard
        mock_pyperclip.paste.side_effect = Exception("Clipboard read error")

        ti = TextInserter()
        result = ti.insert_text("Hello")

        self.assertTrue(result)
        # copy was still called with the text
        mock_pyperclip.copy.assert_any_call("Hello")
        # _send_ctrl_v was still called
        mock_send_ctrl_v.assert_called_once()

    @patch("src.text_inserter.time")
    @patch("src.text_inserter._send_ctrl_v")
    @patch("src.text_inserter.pyperclip")
    def test_clipboard_save_failure_does_not_restore(
        self,
        mock_pyperclip: MagicMock,
        mock_send_ctrl_v: MagicMock,
        mock_time: MagicMock,
    ) -> None:
        mock_pyperclip.paste.side_effect = Exception("Clipboard read error")

        ti = TextInserter()
        ti.insert_text("Hello")

        # copy should be called once (for the text) but NOT a second time
        # to restore, because saved_clipboard is None when paste() fails
        copy_calls = mock_pyperclip.copy.call_args_list
        self.assertEqual(len(copy_calls), 1)
        self.assertEqual(copy_calls[0], call("Hello"))


class TestInsertTextPasteFailure(unittest.TestCase):
    """If the paste operation fails, insert_text should return False."""

    @patch("src.text_inserter.time")
    @patch("src.text_inserter._send_ctrl_v")
    @patch("src.text_inserter.pyperclip")
    def test_paste_failure_returns_false(
        self,
        mock_pyperclip: MagicMock,
        mock_send_ctrl_v: MagicMock,
        mock_time: MagicMock,
    ) -> None:
        mock_pyperclip.paste.return_value = "saved"
        mock_send_ctrl_v.side_effect = Exception("SendInput error")

        ti = TextInserter()
        result = ti.insert_text("Hello")

        self.assertFalse(result)

    @patch("src.text_inserter.time")
    @patch("src.text_inserter._send_ctrl_v")
    @patch("src.text_inserter.pyperclip")
    def test_paste_failure_restores_clipboard(
        self,
        mock_pyperclip: MagicMock,
        mock_send_ctrl_v: MagicMock,
        mock_time: MagicMock,
    ) -> None:
        mock_pyperclip.paste.return_value = "saved"
        mock_send_ctrl_v.side_effect = Exception("SendInput error")

        ti = TextInserter()
        ti.insert_text("Hello")

        # The last copy call should be the restoration of "saved"
        copy_calls = mock_pyperclip.copy.call_args_list
        self.assertEqual(copy_calls[-1], call("saved"))

    @patch("src.text_inserter.time")
    @patch("src.text_inserter._send_ctrl_v")
    @patch("src.text_inserter.pyperclip")
    def test_copy_failure_returns_false(
        self,
        mock_pyperclip: MagicMock,
        mock_send_ctrl_v: MagicMock,
        mock_time: MagicMock,
    ) -> None:
        mock_pyperclip.paste.return_value = "saved"
        mock_pyperclip.copy.side_effect = Exception("copy error")

        ti = TextInserter()
        result = ti.insert_text("Hello")

        self.assertFalse(result)


class TestRestoreClipboard(unittest.TestCase):
    """_restore_clipboard static method edge cases."""

    @patch("src.text_inserter.pyperclip")
    def test_restore_none_does_nothing(self, mock_pyperclip: MagicMock) -> None:
        TextInserter._restore_clipboard(None)
        mock_pyperclip.copy.assert_not_called()

    @patch("src.text_inserter.pyperclip")
    def test_restore_string_copies_it(self, mock_pyperclip: MagicMock) -> None:
        TextInserter._restore_clipboard("my data")
        mock_pyperclip.copy.assert_called_once_with("my data")

    @patch("src.text_inserter.pyperclip")
    def test_restore_failure_does_not_raise(self, mock_pyperclip: MagicMock) -> None:
        mock_pyperclip.copy.side_effect = Exception("restore error")
        # Should not raise
        TextInserter._restore_clipboard("data")


if __name__ == "__main__":
    unittest.main()
