"""Unit tests for src.hotkey_manager.HotkeyManager."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PyQt6.QtWidgets import QApplication

_app: QApplication | None = None


def setUpModule() -> None:
    global _app
    if QApplication.instance() is None:
        _app = QApplication([])


from pynput.keyboard import Key, KeyCode
from src.hotkey_manager import HotkeyManager, _normalize, _resolve_key


# ---------------------------------------------------------------------------
# Tests for the module-level helper functions
# ---------------------------------------------------------------------------


class TestNormalize(unittest.TestCase):
    """_normalize should unify left/right modifier variants."""

    def test_ctrl_l(self) -> None:
        self.assertEqual(_normalize(Key.ctrl_l), Key.ctrl_l)

    def test_ctrl_r_maps_to_ctrl_l(self) -> None:
        self.assertEqual(_normalize(Key.ctrl_r), Key.ctrl_l)

    def test_shift_l(self) -> None:
        self.assertEqual(_normalize(Key.shift_l), Key.shift_l)

    def test_shift_r_maps_to_shift_l(self) -> None:
        self.assertEqual(_normalize(Key.shift_r), Key.shift_l)

    def test_alt_l(self) -> None:
        self.assertEqual(_normalize(Key.alt_l), Key.alt_l)

    def test_alt_r_maps_to_alt_l(self) -> None:
        self.assertEqual(_normalize(Key.alt_r), Key.alt_l)

    def test_space_unchanged(self) -> None:
        self.assertEqual(_normalize(Key.space), Key.space)

    def test_none_returns_none(self) -> None:
        self.assertIsNone(_normalize(None))

    def test_keycode_char_lowercased(self) -> None:
        result = _normalize(KeyCode.from_char("A"))
        self.assertEqual(result, KeyCode.from_char("a"))

    def test_keycode_char_already_lower(self) -> None:
        result = _normalize(KeyCode.from_char("z"))
        self.assertEqual(result, KeyCode.from_char("z"))


class TestResolveKey(unittest.TestCase):
    """_resolve_key should map string names to pynput key objects."""

    def test_ctrl(self) -> None:
        keys = _resolve_key("ctrl")
        self.assertIn(Key.ctrl_l, keys)
        self.assertIn(Key.ctrl_r, keys)

    def test_shift(self) -> None:
        keys = _resolve_key("shift")
        self.assertIn(Key.shift_l, keys)
        self.assertIn(Key.shift_r, keys)

    def test_alt(self) -> None:
        keys = _resolve_key("alt")
        self.assertIn(Key.alt_l, keys)
        self.assertIn(Key.alt_r, keys)

    def test_space(self) -> None:
        keys = _resolve_key("space")
        self.assertEqual(keys, [Key.space])

    def test_tab(self) -> None:
        keys = _resolve_key("tab")
        self.assertEqual(keys, [Key.tab])

    def test_enter(self) -> None:
        keys = _resolve_key("enter")
        self.assertEqual(keys, [Key.enter])

    def test_esc(self) -> None:
        keys = _resolve_key("esc")
        self.assertEqual(keys, [Key.esc])

    def test_single_char(self) -> None:
        keys = _resolve_key("a")
        self.assertEqual(len(keys), 1)
        self.assertEqual(keys[0], KeyCode.from_char("a"))

    def test_case_insensitive(self) -> None:
        keys = _resolve_key("CTRL")
        self.assertIn(Key.ctrl_l, keys)

    def test_unknown_multi_char_treated_as_char(self) -> None:
        keys = _resolve_key("xyz")
        self.assertEqual(len(keys), 1)


# ---------------------------------------------------------------------------
# Tests for HotkeyManager construction and configuration
# ---------------------------------------------------------------------------


class TestHotkeyManagerConstructor(unittest.TestCase):
    """Constructor should accept custom keys and mode."""

    @patch("src.hotkey_manager.Listener")
    def test_default_keys(self, _mock_listener: MagicMock) -> None:
        hm = HotkeyManager()
        self.assertEqual(hm._hotkey_names, ["ctrl", "shift", "space"])

    @patch("src.hotkey_manager.Listener")
    def test_custom_keys(self, _mock_listener: MagicMock) -> None:
        hm = HotkeyManager(keys=["alt", "a"])
        self.assertEqual(hm._hotkey_names, ["alt", "a"])

    @patch("src.hotkey_manager.Listener")
    def test_default_mode_is_hold(self, _mock_listener: MagicMock) -> None:
        hm = HotkeyManager()
        self.assertEqual(hm._mode, "hold")

    @patch("src.hotkey_manager.Listener")
    def test_custom_mode(self, _mock_listener: MagicMock) -> None:
        hm = HotkeyManager(mode="toggle")
        self.assertEqual(hm._mode, "toggle")


class TestSetHotkey(unittest.TestCase):
    """set_hotkey should update internal state and rebuild targets."""

    @patch("src.hotkey_manager.Listener")
    def test_set_hotkey_updates_names(self, _mock_listener: MagicMock) -> None:
        hm = HotkeyManager()
        hm.set_hotkey(["alt", "enter"])
        self.assertEqual(hm._hotkey_names, ["alt", "enter"])

    @patch("src.hotkey_manager.Listener")
    def test_set_hotkey_rebuilds_targets(self, _mock_listener: MagicMock) -> None:
        hm = HotkeyManager()
        hm.set_hotkey(["space"])
        self.assertIn(_normalize(Key.space), hm._hotkey_targets)

    @patch("src.hotkey_manager.Listener")
    def test_set_hotkey_clears_pressed(self, _mock_listener: MagicMock) -> None:
        hm = HotkeyManager()
        hm._pressed.add(Key.ctrl_l)
        hm.set_hotkey(["space"])
        self.assertEqual(len(hm._pressed), 0)

    @patch("src.hotkey_manager.Listener")
    def test_set_hotkey_resets_toggle(self, _mock_listener: MagicMock) -> None:
        hm = HotkeyManager(mode="toggle")
        hm._toggle_active = True
        hm.set_hotkey(["space"])
        self.assertFalse(hm._toggle_active)


class TestSetMode(unittest.TestCase):
    """set_mode should validate and update the mode string."""

    @patch("src.hotkey_manager.Listener")
    def test_set_hold_mode(self, _mock_listener: MagicMock) -> None:
        hm = HotkeyManager(mode="toggle")
        hm.set_mode("hold")
        self.assertEqual(hm._mode, "hold")

    @patch("src.hotkey_manager.Listener")
    def test_set_toggle_mode(self, _mock_listener: MagicMock) -> None:
        hm = HotkeyManager()
        hm.set_mode("toggle")
        self.assertEqual(hm._mode, "toggle")

    @patch("src.hotkey_manager.Listener")
    def test_invalid_mode_ignored(self, _mock_listener: MagicMock) -> None:
        hm = HotkeyManager()
        hm.set_mode("invalid_mode")
        self.assertEqual(hm._mode, "hold")  # unchanged

    @patch("src.hotkey_manager.Listener")
    def test_set_mode_clears_state(self, _mock_listener: MagicMock) -> None:
        hm = HotkeyManager(mode="toggle")
        hm._toggle_active = True
        hm._pressed.add(Key.space)
        hm.set_mode("hold")
        self.assertFalse(hm._toggle_active)
        self.assertEqual(len(hm._pressed), 0)


# ---------------------------------------------------------------------------
# Tests for hold mode behaviour
# ---------------------------------------------------------------------------


class TestHoldMode(unittest.TestCase):
    """In hold mode: pressing all keys -> start, releasing any -> stop."""

    @patch("src.hotkey_manager.Listener")
    def test_press_all_keys_emits_start(self, _mock_listener: MagicMock) -> None:
        hm = HotkeyManager(keys=["ctrl", "shift", "space"], mode="hold")
        start_handler = MagicMock()
        hm.recording_start_requested.connect(start_handler)

        # Simulate pressing each key
        hm._on_press(Key.ctrl_l)
        hm._on_press(Key.shift_l)
        hm._on_press(Key.space)

        start_handler.assert_called_once()

    @patch("src.hotkey_manager.Listener")
    def test_release_after_combo_emits_stop(self, _mock_listener: MagicMock) -> None:
        hm = HotkeyManager(keys=["ctrl", "shift", "space"], mode="hold")
        stop_handler = MagicMock()
        hm.recording_stop_requested.connect(stop_handler)

        hm._on_press(Key.ctrl_l)
        hm._on_press(Key.shift_l)
        hm._on_press(Key.space)

        # Release one key
        hm._on_release(Key.space)

        stop_handler.assert_called_once()

    @patch("src.hotkey_manager.Listener")
    def test_partial_press_does_not_emit(self, _mock_listener: MagicMock) -> None:
        hm = HotkeyManager(keys=["ctrl", "shift", "space"], mode="hold")
        start_handler = MagicMock()
        hm.recording_start_requested.connect(start_handler)

        hm._on_press(Key.ctrl_l)
        hm._on_press(Key.shift_l)
        # space NOT pressed

        start_handler.assert_not_called()

    @patch("src.hotkey_manager.Listener")
    def test_right_modifier_variant_also_works(self, _mock_listener: MagicMock) -> None:
        hm = HotkeyManager(keys=["ctrl", "shift", "space"], mode="hold")
        start_handler = MagicMock()
        hm.recording_start_requested.connect(start_handler)

        hm._on_press(Key.ctrl_r)   # right ctrl
        hm._on_press(Key.shift_r)  # right shift
        hm._on_press(Key.space)

        start_handler.assert_called_once()

    @patch("src.hotkey_manager.Listener")
    def test_irrelevant_key_ignored(self, _mock_listener: MagicMock) -> None:
        hm = HotkeyManager(keys=["space"], mode="hold")
        start_handler = MagicMock()
        hm.recording_start_requested.connect(start_handler)

        hm._on_press(Key.tab)  # not in the hotkey
        start_handler.assert_not_called()

    @patch("src.hotkey_manager.Listener")
    def test_release_irrelevant_key_no_stop(self, _mock_listener: MagicMock) -> None:
        hm = HotkeyManager(keys=["space"], mode="hold")
        stop_handler = MagicMock()
        hm.recording_stop_requested.connect(stop_handler)

        hm._on_press(Key.space)
        hm._on_release(Key.tab)  # not part of hotkey

        stop_handler.assert_not_called()

    @patch("src.hotkey_manager.Listener")
    def test_hold_does_not_re_emit_start_without_release(self, _mock_listener: MagicMock) -> None:
        """Holding all keys down should only emit start once."""
        hm = HotkeyManager(keys=["space"], mode="hold")
        start_handler = MagicMock()
        hm.recording_start_requested.connect(start_handler)

        hm._on_press(Key.space)
        hm._on_press(Key.space)  # repeated press

        self.assertEqual(start_handler.call_count, 1)


# ---------------------------------------------------------------------------
# Tests for toggle mode behaviour
# ---------------------------------------------------------------------------


class TestToggleMode(unittest.TestCase):
    """In toggle mode: first combo -> start, second combo -> stop."""

    @patch("src.hotkey_manager.Listener")
    def test_first_combo_emits_start(self, _mock_listener: MagicMock) -> None:
        hm = HotkeyManager(keys=["space"], mode="toggle")
        start_handler = MagicMock()
        stop_handler = MagicMock()
        hm.recording_start_requested.connect(start_handler)
        hm.recording_stop_requested.connect(stop_handler)

        hm._on_press(Key.space)

        start_handler.assert_called_once()
        stop_handler.assert_not_called()

    @patch("src.hotkey_manager.Listener")
    def test_second_combo_emits_stop(self, _mock_listener: MagicMock) -> None:
        hm = HotkeyManager(keys=["space"], mode="toggle")
        start_handler = MagicMock()
        stop_handler = MagicMock()
        hm.recording_start_requested.connect(start_handler)
        hm.recording_stop_requested.connect(stop_handler)

        # First press -> start
        hm._on_press(Key.space)
        # Must release before pressing again (to reset _combo_was_pressed)
        hm._on_release(Key.space)
        # Second press -> stop
        hm._on_press(Key.space)

        self.assertEqual(start_handler.call_count, 1)
        self.assertEqual(stop_handler.call_count, 1)

    @patch("src.hotkey_manager.Listener")
    def test_third_combo_emits_start_again(self, _mock_listener: MagicMock) -> None:
        hm = HotkeyManager(keys=["space"], mode="toggle")
        start_handler = MagicMock()
        stop_handler = MagicMock()
        hm.recording_start_requested.connect(start_handler)
        hm.recording_stop_requested.connect(stop_handler)

        # 1st press -> start
        hm._on_press(Key.space)
        hm._on_release(Key.space)
        # 2nd press -> stop
        hm._on_press(Key.space)
        hm._on_release(Key.space)
        # 3rd press -> start again
        hm._on_press(Key.space)

        self.assertEqual(start_handler.call_count, 2)
        self.assertEqual(stop_handler.call_count, 1)

    @patch("src.hotkey_manager.Listener")
    def test_toggle_with_multi_key_combo(self, _mock_listener: MagicMock) -> None:
        hm = HotkeyManager(keys=["ctrl", "space"], mode="toggle")
        start_handler = MagicMock()
        hm.recording_start_requested.connect(start_handler)

        hm._on_press(Key.ctrl_l)
        hm._on_press(Key.space)

        start_handler.assert_called_once()


# ---------------------------------------------------------------------------
# Tests for start / stop listener
# ---------------------------------------------------------------------------


class TestListenerStartStop(unittest.TestCase):
    """start() / stop() should manage the pynput Listener."""

    @patch("src.hotkey_manager.Listener")
    def test_start_creates_listener(self, MockListener: MagicMock) -> None:
        hm = HotkeyManager()
        hm.start()

        MockListener.assert_called_once()
        MockListener.return_value.start.assert_called_once()

    @patch("src.hotkey_manager.Listener")
    def test_stop_stops_listener(self, MockListener: MagicMock) -> None:
        hm = HotkeyManager()
        hm.start()
        hm.stop()

        MockListener.return_value.stop.assert_called_once()

    @patch("src.hotkey_manager.Listener")
    def test_stop_without_start_is_safe(self, MockListener: MagicMock) -> None:
        hm = HotkeyManager()
        # Should not raise
        hm.stop()

    @patch("src.hotkey_manager.Listener")
    def test_start_twice_stops_first(self, MockListener: MagicMock) -> None:
        hm = HotkeyManager()
        hm.start()
        hm.start()

        # The first listener should have been stopped
        self.assertEqual(MockListener.return_value.stop.call_count, 1)
        # A second Listener should have been created
        self.assertEqual(MockListener.call_count, 2)


if __name__ == "__main__":
    unittest.main()
