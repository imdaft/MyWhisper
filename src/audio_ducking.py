"""Duck (temporarily lower) the volume of every OTHER app's audio session while
recording, so background music/video doesn't compete with the microphone.
Restores each session's exact original volume/mute state afterward.

Windows-only, via the Core Audio per-application session API (pycaw). All
failures are caught and logged at debug level — if pycaw or the audio
subsystem is unavailable, ducking is simply skipped and recording proceeds
normally.
"""
from __future__ import annotations

import logging
import os
import sys

logger = logging.getLogger(__name__)

_OUR_PID = os.getpid()

# Named ducking levels exposed in settings, mapped to a target volume fraction
# (0.0 = fully muted, 1.0 = untouched). "off" disables ducking entirely.
DUCK_LEVELS: dict[str, float | None] = {
    "off": None,
    "quiet": 0.15,
    "mute": 0.0,
}


class AudioDucker:
    """Call duck() when recording starts and restore() when it stops."""

    def __init__(self) -> None:
        # session pid -> (original_volume, original_mute)
        self._saved: dict[int, tuple[float, int]] = {}
        self._ducked = False

    def duck(self, level: float) -> None:
        if self._ducked or sys.platform != "win32":
            return
        sessions = self._get_sessions()
        if sessions is None:
            return

        saved: dict[int, tuple[float, int]] = {}
        for session, volume_ctl in sessions:
            pid = session.ProcessId
            if pid == _OUR_PID:
                continue
            try:
                saved[pid] = (volume_ctl.GetMasterVolume(), volume_ctl.GetMute())
                volume_ctl.SetMasterVolume(level, None)
            except Exception as exc:
                logger.debug("Could not duck audio session pid=%s: %s", pid, exc)

        self._saved = saved
        self._ducked = True
        if saved:
            logger.info("Ducked %d other audio session(s) to %.0f%%", len(saved), level * 100)

    def restore(self) -> None:
        if not self._ducked:
            return
        saved, self._saved = self._saved, {}
        self._ducked = False
        if not saved:
            return

        sessions = self._get_sessions()
        if sessions is None:
            return
        by_pid = {session.ProcessId: volume_ctl for session, volume_ctl in sessions}

        for pid, (orig_volume, orig_mute) in saved.items():
            volume_ctl = by_pid.get(pid)
            if volume_ctl is None:
                continue  # app closed while ducked — nothing left to restore
            try:
                volume_ctl.SetMasterVolume(orig_volume, None)
                volume_ctl.SetMute(orig_mute, None)
            except Exception as exc:
                logger.debug("Could not restore audio session pid=%s: %s", pid, exc)
        logger.debug("Restored %d audio session(s)", len(saved))

    @staticmethod
    def _get_sessions():
        try:
            from pycaw.pycaw import AudioUtilities, ISimpleAudioVolume
            sessions = AudioUtilities.GetAllSessions()
            return [(s, s._ctl.QueryInterface(ISimpleAudioVolume)) for s in sessions]
        except Exception as exc:
            logger.debug("Audio ducking unavailable: %s", exc)
            return None
