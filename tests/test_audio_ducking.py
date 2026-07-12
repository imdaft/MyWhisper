"""Unit tests for src.audio_ducking.AudioDucker (pycaw mocked — no real audio)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.audio_ducking import AudioDucker, DUCK_LEVELS


def _fake_session(pid: int, volume: float = 1.0, mute: int = 0, name: str | None = "app.exe"):
    session = MagicMock()
    session.ProcessId = pid
    if name is None:
        session.Process = None
    else:
        session.Process.name.return_value = name
    ctl = MagicMock()
    ctl.GetMasterVolume.return_value = volume
    ctl.GetMute.return_value = mute
    session._ctl.QueryInterface.return_value = ctl
    return session, ctl


class TestDuckLevels(unittest.TestCase):

    def test_off_is_none(self) -> None:
        self.assertIsNone(DUCK_LEVELS["off"])

    def test_quiet_and_mute_are_fractions(self) -> None:
        self.assertEqual(DUCK_LEVELS["mute"], 0.0)
        self.assertGreater(DUCK_LEVELS["quiet"], 0.0)
        self.assertLess(DUCK_LEVELS["quiet"], 1.0)


class TestAudioDucker(unittest.TestCase):

    def _patch_sessions(self, sessions: list) -> None:
        patcher = patch.object(AudioDucker, "_get_sessions", return_value=sessions)
        self.addCleanup(patcher.stop)
        patcher.start()

    def test_duck_lowers_other_sessions_not_our_own(self) -> None:
        own_session, own_ctl = _fake_session(pid=99999)  # our pid, must be skipped
        other_session, other_ctl = _fake_session(pid=123, volume=0.8)
        with patch("src.audio_ducking._OUR_PID", 99999):
            self._patch_sessions([(own_session, own_ctl), (other_session, other_ctl)])
            d = AudioDucker()
            d.duck(0.1)
        other_ctl.SetMasterVolume.assert_called_once_with(0.1, None)
        own_ctl.SetMasterVolume.assert_not_called()

    def test_duck_is_idempotent(self) -> None:
        session, ctl = _fake_session(pid=123, volume=0.8)
        self._patch_sessions([(session, ctl)])
        d = AudioDucker()
        d.duck(0.1)
        d.duck(0.1)  # second call while already ducked should no-op
        self.assertEqual(ctl.SetMasterVolume.call_count, 1)

    def test_restore_sets_back_original_volume_and_mute(self) -> None:
        session, ctl = _fake_session(pid=123, volume=0.73, mute=1)
        self._patch_sessions([(session, ctl)])
        d = AudioDucker()
        d.duck(0.1)
        d.restore()
        ctl.SetMasterVolume.assert_called_with(0.73, None)
        ctl.SetMute.assert_called_once_with(1, None)

    def test_restore_without_duck_is_noop(self) -> None:
        d = AudioDucker()
        d.restore()  # must not raise even though nothing was ducked

    def test_restore_skips_session_that_disappeared(self) -> None:
        session, ctl = _fake_session(pid=123, volume=0.5)
        self._patch_sessions([(session, ctl)])
        d = AudioDucker()
        d.duck(0.1)
        self._patch_sessions([])  # app closed while ducked
        d.restore()  # must not raise

    def test_get_sessions_none_makes_duck_and_restore_noop(self) -> None:
        with patch.object(AudioDucker, "_get_sessions", return_value=None):
            d = AudioDucker()
            d.duck(0.1)  # pycaw unavailable -> silently does nothing
            self.assertFalse(d._ducked)
            d.restore()


class TestChromeStylePidChurn(unittest.TestCase):
    """Some apps (notably Chrome) recreate their audio session under a new
    pid between duck() and restore() — the old session simply vanishes from
    GetAllSessions(). These tests cover the executable-name fallback that
    catches that case instead of leaving the app perpetually ducked."""

    def _patch_sessions(self, sessions: list) -> None:
        patcher = patch.object(AudioDucker, "_get_sessions", return_value=sessions)
        self.addCleanup(patcher.stop)
        patcher.start()

    def test_restore_falls_back_to_name_when_pid_changed(self) -> None:
        old_session, old_ctl = _fake_session(pid=1000, volume=0.9, mute=0, name="chrome.exe")
        self._patch_sessions([(old_session, old_ctl)])
        d = AudioDucker()
        d.duck(0.1)
        old_ctl.SetMasterVolume.assert_called_once_with(0.1, None)

        # Old pid 1000 is gone (Chrome recreated its audio session); a new
        # session with a different pid but the SAME executable name appears.
        new_session, new_ctl = _fake_session(pid=2000, volume=1.0, mute=0, name="chrome.exe")
        self._patch_sessions([(new_session, new_ctl)])
        d.restore()

        new_ctl.SetMasterVolume.assert_called_once_with(0.9, None)
        new_ctl.SetMute.assert_called_once_with(0, None)
        self.assertEqual(d._pending, {}, "should not remain pending once name-matched")

    def test_unmatched_entry_is_queued_pending_and_retried_on_next_duck(self) -> None:
        session, ctl = _fake_session(pid=1000, volume=0.9, mute=0, name="chrome.exe")
        self._patch_sessions([(session, ctl)])
        d = AudioDucker()
        d.duck(0.1)

        # Chrome fully closed while ducked — nothing to restore to at all.
        self._patch_sessions([])
        d.restore()
        self.assertIn(1000, d._pending)

        # Later, Chrome is reopened (new pid, same name) and the user
        # records again — the pending restore should be applied first,
        # before the fresh duck() snapshot is taken.
        new_session, new_ctl = _fake_session(pid=3000, volume=1.0, mute=0, name="chrome.exe")
        self._patch_sessions([(new_session, new_ctl)])
        d.duck(0.2)

        new_ctl.SetMasterVolume.assert_any_call(0.9, None)  # pending restore
        new_ctl.SetMasterVolume.assert_any_call(0.2, None)  # then the fresh duck
        self.assertEqual(d._pending, {})

    def test_name_fallback_does_not_touch_our_own_process(self) -> None:
        with patch("src.audio_ducking._OUR_PID", 99999):
            old_session, old_ctl = _fake_session(pid=1000, volume=0.9, name="chrome.exe")
            self._patch_sessions([(old_session, old_ctl)])
            d = AudioDucker()
            d.duck(0.1)

            # Old session gone; only OUR OWN process remains under the same
            # name (contrived, but must never be restored into).
            own_session, own_ctl = _fake_session(pid=99999, volume=1.0, name="chrome.exe")
            self._patch_sessions([(own_session, own_ctl)])
            d.restore()

        own_ctl.SetMasterVolume.assert_not_called()
        self.assertIn(1000, d._pending)

    def test_no_name_available_cannot_fallback_but_does_not_raise(self) -> None:
        session, ctl = _fake_session(pid=1000, volume=0.9, name=None)
        self._patch_sessions([(session, ctl)])
        d = AudioDucker()
        d.duck(0.1)

        self._patch_sessions([])
        d.restore()  # must not raise
        self.assertIn(1000, d._pending)


if __name__ == "__main__":
    unittest.main()
