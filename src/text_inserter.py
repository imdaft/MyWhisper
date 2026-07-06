from __future__ import annotations

import ctypes
import ctypes.wintypes
import logging
import time

import pyperclip
from pynput.keyboard import Controller as KbController, Key

logger = logging.getLogger(__name__)

# Delay after copying to clipboard to ensure it is available for paste
_CLIPBOARD_COPY_DELAY = 0.05
# Delay after paste keystroke to ensure the target application has consumed
# the clipboard contents before we restore the original clipboard value
_PASTE_SETTLE_DELAY = 0.25
# Delay after releasing modifier keys before pasting
_KEY_RELEASE_DELAY = 0.15

# ALL modifiers that must be released before simulating Ctrl+V
# (including Ctrl itself — user's hotkey may include Ctrl)
_MODIFIERS_TO_RELEASE = [
    Key.ctrl, Key.ctrl_l, Key.ctrl_r,
    Key.shift, Key.shift_l, Key.shift_r,
    Key.alt, Key.alt_l, Key.alt_r,
    Key.cmd, Key.cmd_l, Key.cmd_r,
]

# --- Win32 SendInput structures (correct for x64) ---
_INPUT_KEYBOARD = 1
_KEYEVENTF_KEYUP = 0x0002
_KEYEVENTF_UNICODE = 0x0004
_VK_CONTROL = 0x11
_VK_V = 0x56

# Clipboard formats that pyperclip.copy() would silently destroy.
_CF_BITMAP = 2
_CF_DIB = 8
_CF_DIBV5 = 17
_CF_HDROP = 15  # file list

ULONG_PTR = ctypes.POINTER(ctypes.c_ulong)


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", ctypes.c_ulong),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ULONG_PTR),
    ]


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.c_ushort),
        ("wScan", ctypes.c_ushort),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ULONG_PTR),
    ]


class _HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", ctypes.c_ulong),
        ("wParamL", ctypes.c_ushort),
        ("wParamH", ctypes.c_ushort),
    ]


class _INPUT_UNION(ctypes.Union):
    _fields_ = [
        ("mi", _MOUSEINPUT),
        ("ki", _KEYBDINPUT),
        ("hi", _HARDWAREINPUT),
    ]


class _INPUT(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_ulong),
        ("u", _INPUT_UNION),
    ]


def _send_ctrl_v() -> None:
    """Simulate Ctrl+V via Win32 SendInput — the most reliable method on Windows."""
    inputs = (_INPUT * 4)()

    for i, (vk, flags) in enumerate([
        (_VK_CONTROL, 0),                    # Ctrl down
        (_VK_V, 0),                          # V down
        (_VK_V, _KEYEVENTF_KEYUP),           # V up
        (_VK_CONTROL, _KEYEVENTF_KEYUP),     # Ctrl up
    ]):
        inputs[i].type = _INPUT_KEYBOARD
        inputs[i].u.ki.wVk = vk
        inputs[i].u.ki.wScan = 0
        inputs[i].u.ki.dwFlags = flags
        inputs[i].u.ki.time = 0

    sent = ctypes.windll.user32.SendInput(4, ctypes.byref(inputs), ctypes.sizeof(_INPUT))
    logger.debug("SendInput sent %d of 4 events (sizeof INPUT=%d)", sent, ctypes.sizeof(_INPUT))


def _type_text_unicode(text: str) -> None:
    """Type text character-by-character via SendInput with Unicode scan codes.

    Used when the clipboard holds non-text data we must not overwrite. Handles
    characters outside the BMP (e.g. emoji) via UTF-16 surrogate pairs.
    """
    for ch in text:
        raw = ch.encode("utf-16-le")
        units = [raw[i] | (raw[i + 1] << 8) for i in range(0, len(raw), 2)]
        n = len(units) * 2
        inputs = (_INPUT * n)()
        idx = 0
        for unit in units:
            for flags in (_KEYEVENTF_UNICODE, _KEYEVENTF_UNICODE | _KEYEVENTF_KEYUP):
                inputs[idx].type = _INPUT_KEYBOARD
                inputs[idx].u.ki.wVk = 0
                inputs[idx].u.ki.wScan = unit
                inputs[idx].u.ki.dwFlags = flags
                inputs[idx].u.ki.time = 0
                idx += 1
        ctypes.windll.user32.SendInput(n, ctypes.byref(inputs), ctypes.sizeof(_INPUT))


def _clipboard_has_nontext() -> bool:
    """True if the clipboard holds an image or file list that pyperclip.copy()
    would silently destroy. Uses Win32 directly (no clipboard open needed)."""
    try:
        user32 = ctypes.windll.user32
        for fmt in (_CF_BITMAP, _CF_DIB, _CF_DIBV5, _CF_HDROP):
            if user32.IsClipboardFormatAvailable(fmt):
                return True
        return False
    except Exception:
        return False


class TextInserter:
    def __init__(self) -> None:
        self._kb = KbController()

    def _release_modifiers(self) -> None:
        for key in _MODIFIERS_TO_RELEASE:
            try:
                self._kb.release(key)
            except Exception:
                pass
        time.sleep(_KEY_RELEASE_DELAY)

    def insert_text(self, text: str) -> bool:
        if not text:
            logger.debug("Empty text provided, skipping insertion")
            return False

        # Release ALL held modifier keys (including Ctrl from user hotkey)
        self._release_modifiers()

        # If the clipboard holds an image or files, typing the text directly
        # avoids destroying that content (and is the SPEC's paste fallback).
        if _clipboard_has_nontext():
            try:
                _type_text_unicode(text)
                logger.info("Text typed directly (%d chars, clipboard preserved)", len(text))
                return True
            except Exception:
                logger.error("Failed to insert text via typing")
                return False

        saved_clipboard: str | None = None
        try:
            saved_clipboard = pyperclip.paste()
        except Exception:
            logger.warning("Failed to save clipboard contents")

        try:
            pyperclip.copy(text)
            time.sleep(_CLIPBOARD_COPY_DELAY)
            # Use Win32 SendInput directly — pyautogui conflicts with pynput hooks
            _send_ctrl_v()
            time.sleep(_PASTE_SETTLE_DELAY)
        except Exception:
            logger.error("Failed to insert text via clipboard paste", exc_info=True)
            self._restore_clipboard(saved_clipboard)
            return False

        self._restore_clipboard(saved_clipboard)
        logger.info("Text inserted successfully (%d chars)", len(text))
        return True

    @staticmethod
    def _restore_clipboard(content: str | None) -> None:
        # Skip restore for None (save failed) and for "" — pyperclip returns an
        # empty string for a non-text clipboard (image/files) it cannot read, so
        # copying "" back would needlessly clobber it. Leave our text instead.
        if not content:
            return
        try:
            pyperclip.copy(content)
        except Exception:
            # Do NOT log exc_info here -- clipboard content may be sensitive
            logger.warning("Failed to restore clipboard contents")
