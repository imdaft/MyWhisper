from __future__ import annotations

import logging
from typing import Set

from pynput.keyboard import Key, KeyCode, Listener
from PyQt6.QtCore import QObject, pyqtSignal

logger = logging.getLogger(__name__)

_KEY_MAP: dict[str, list[Key | KeyCode]] = {
    "ctrl": [Key.ctrl_l, Key.ctrl_r],
    "shift": [Key.shift_l, Key.shift_r],
    "alt": [Key.alt_l, Key.alt_r],
    "win": [Key.cmd_l, Key.cmd_r],
    "meta": [Key.cmd_l, Key.cmd_r],
    "cmd": [Key.cmd_l, Key.cmd_r],
    "space": [Key.space],
    "tab": [Key.tab],
    "enter": [Key.enter],
    "esc": [Key.esc],
    "backspace": [Key.backspace],
    "delete": [Key.delete],
    "capslock": [Key.caps_lock],
    "f1": [Key.f1], "f2": [Key.f2], "f3": [Key.f3], "f4": [Key.f4],
    "f5": [Key.f5], "f6": [Key.f6], "f7": [Key.f7], "f8": [Key.f8],
    "f9": [Key.f9], "f10": [Key.f10], "f11": [Key.f11], "f12": [Key.f12],
}


def _resolve_key(name: str) -> list[Key | KeyCode]:
    lower = name.lower().strip()
    if lower in _KEY_MAP:
        return _KEY_MAP[lower]
    if len(lower) == 1:
        return [KeyCode.from_char(lower)]
    logger.warning("Unknown key name '%s', treating as single char", name)
    return [KeyCode.from_char(lower)]


def _normalize(key: Key | KeyCode | None) -> Key | KeyCode | None:
    if key is None:
        return None
    if isinstance(key, Key):
        if key in (Key.ctrl_l, Key.ctrl_r):
            return Key.ctrl_l
        if key in (Key.shift_l, Key.shift_r):
            return Key.shift_l
        if key in (Key.alt_l, Key.alt_r):
            return Key.alt_l
        if key in (Key.cmd_l, Key.cmd_r, Key.cmd):
            return Key.cmd_l
    if isinstance(key, KeyCode) and key.char is not None:
        return KeyCode.from_char(key.char.lower())
    return key


class HotkeyManager(QObject):
    recording_start_requested = pyqtSignal()
    recording_stop_requested = pyqtSignal()

    def __init__(
        self,
        keys: tuple[str, ...] | list[str] = ("ctrl", "shift", "space"),
        mode: str = "hold",
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._hotkey_names: list[str] = list(keys)
        self._hotkey_targets: Set[Key | KeyCode] = set()
        self._mode: str = mode
        self._pressed: Set[Key | KeyCode] = set()
        self._listener: Listener | None = None
        self._toggle_active: bool = False
        self._combo_was_pressed: bool = False
        self._rebuild_targets()

    def _rebuild_targets(self) -> None:
        targets: Set[Key | KeyCode] = set()
        for name in self._hotkey_names:
            candidates = _resolve_key(name)
            if candidates:
                targets.add(_normalize(candidates[0]))
        self._hotkey_targets = targets
        logger.debug("Hotkey targets rebuilt: %s", self._hotkey_targets)

    def set_hotkey(self, keys: list[str] | tuple[str, ...]) -> None:
        self._hotkey_names = list(keys)
        self._rebuild_targets()
        self._pressed.clear()
        self._toggle_active = False
        self._combo_was_pressed = False
        logger.info("Hotkey updated to %s", keys)

    def set_mode(self, mode: str) -> None:
        if mode not in ("hold", "toggle"):
            logger.error("Invalid hotkey mode '%s', ignoring", mode)
            return
        self._mode = mode
        self._toggle_active = False
        self._combo_was_pressed = False
        self._pressed.clear()
        logger.info("Hotkey mode set to '%s'", mode)

    def _all_pressed(self) -> bool:
        return self._hotkey_targets.issubset(self._pressed)

    def _on_press(self, key: Key | KeyCode | None) -> None:
        normalized = _normalize(key)
        if normalized is None or normalized not in self._hotkey_targets:
            return
        self._pressed.add(normalized)
        if not self._all_pressed():
            return

        if self._mode == "hold":
            if not self._combo_was_pressed:
                self._combo_was_pressed = True
                logger.debug("Hold-mode combo pressed, requesting start")
                self.recording_start_requested.emit()
        elif self._mode == "toggle":
            if not self._combo_was_pressed:
                self._combo_was_pressed = True
                self._toggle_active = not self._toggle_active
                if self._toggle_active:
                    logger.debug("Toggle-mode combo pressed, requesting start")
                    self.recording_start_requested.emit()
                else:
                    logger.debug("Toggle-mode combo pressed, requesting stop")
                    self.recording_stop_requested.emit()

    def _on_release(self, key: Key | KeyCode | None) -> None:
        normalized = _normalize(key)
        if normalized is None or normalized not in self._hotkey_targets:
            return

        was_all_pressed = self._combo_was_pressed
        self._pressed.discard(normalized)
        self._combo_was_pressed = False

        if self._mode == "hold" and was_all_pressed:
            logger.debug("Hold-mode key released, requesting stop")
            self.recording_stop_requested.emit()

    def start(self) -> None:
        if self._listener is not None:
            logger.warning("Listener already running, stopping first")
            self.stop()
        self._pressed.clear()
        self._toggle_active = False
        self._combo_was_pressed = False
        self._listener = Listener(
            on_press=self._on_press,
            on_release=self._on_release,
            suppress=False,
        )
        self._listener.daemon = True
        self._listener.start()
        logger.info("Global hotkey listener started")

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None
            self._pressed.clear()
            self._toggle_active = False
            self._combo_was_pressed = False
            logger.info("Global hotkey listener stopped")
