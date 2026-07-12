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

# pid -> (original_volume, original_mute, executable_name)
_Entries = dict[int, tuple[float, int, "str | None"]]


class AudioDucker:
    """Call duck() when recording starts and restore() when it stops."""

    def __init__(self) -> None:
        self._saved: _Entries = {}
        # Entries we couldn't restore last time (session gone, no name match
        # either) — retried opportunistically on the next duck(). Some apps,
        # notably Chrome, recreate their audio session under a new PID
        # between duck() and restore(), so the original session simply
        # vanishes from GetAllSessions() and a plain pid-based restore
        # would leave that app quietly ducked forever.
        self._pending: _Entries = {}
        self._ducked = False

    def duck(self, level: float) -> None:
        if self._ducked or sys.platform != "win32":
            return
        sessions = self._get_sessions()
        if sessions is None:
            return

        if self._pending:
            self._pending = self._try_restore(self._pending, sessions)

        saved: _Entries = {}
        for session, volume_ctl in sessions:
            pid = session.ProcessId
            if pid == _OUR_PID:
                continue
            try:
                name = self._process_name(session)
                saved[pid] = (volume_ctl.GetMasterVolume(), volume_ctl.GetMute(), name)
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
            # Couldn't even enumerate right now — keep everything pending
            # so the next duck()/restore() cycle gets another shot at it.
            self._pending.update(saved)
            return

        unrestored = self._try_restore(saved, sessions)
        if unrestored:
            logger.info(
                "%d session(s) not restored yet (audio session likely "
                "recreated with a new pid) — will retry next recording",
                len(unrestored),
            )
            self._pending.update(unrestored)
        logger.debug("Restored %d/%d audio session(s)", len(saved) - len(unrestored), len(saved))

    def _try_restore(self, entries: _Entries, sessions: list) -> _Entries:
        """Restore volume/mute for `entries` against the live `sessions`.
        Returns the subset that could NOT be restored."""
        by_pid = {session.ProcessId: volume_ctl for session, volume_ctl in sessions}
        restored: set[int] = set()

        # Pass 1: exact pid match — the common, fast path.
        for pid, (orig_volume, orig_mute, _name) in entries.items():
            volume_ctl = by_pid.get(pid)
            if volume_ctl is None:
                continue
            try:
                volume_ctl.SetMasterVolume(orig_volume, None)
                volume_ctl.SetMute(orig_mute, None)
                restored.add(pid)
            except Exception as exc:
                logger.debug("Could not restore audio session pid=%s: %s", pid, exc)

        # Pass 2: fall back to matching by executable name for whatever pid
        # wasn't found — catches apps that recreate their audio session
        # (a new renderer/audio-service pid) while we were still recording.
        missing = {pid: v for pid, v in entries.items() if pid not in restored}
        if missing:
            claimed: set[int] = set()
            for pid, (orig_volume, orig_mute, name) in missing.items():
                if not name:
                    continue
                for session, volume_ctl in sessions:
                    spid = session.ProcessId
                    if spid == _OUR_PID or spid in restored or spid in claimed:
                        continue
                    if self._process_name(session) != name:
                        continue
                    try:
                        volume_ctl.SetMasterVolume(orig_volume, None)
                        volume_ctl.SetMute(orig_mute, None)
                        restored.add(pid)
                        claimed.add(spid)
                        logger.info("Restored '%s' via name fallback (pid changed)", name)
                    except Exception as exc:
                        logger.debug("Could not restore '%s' via name fallback: %s", name, exc)
                    break

        return {pid: v for pid, v in entries.items() if pid not in restored}

    @staticmethod
    def _process_name(session) -> str | None:
        try:
            proc = session.Process
            return proc.name() if proc else None
        except Exception:
            return None

    @staticmethod
    def _get_sessions():
        try:
            from pycaw.pycaw import AudioUtilities, ISimpleAudioVolume
            sessions = AudioUtilities.GetAllSessions()
            return [(s, s._ctl.QueryInterface(ISimpleAudioVolume)) for s in sessions]
        except Exception as exc:
            logger.debug("Audio ducking unavailable: %s", exc)
            return None
