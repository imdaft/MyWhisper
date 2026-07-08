"""Unit tests for src.audio_ducking.AudioDucker (pycaw mocked — no real audio)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.audio_ducking import AudioDucker, DUCK_LEVELS


def _fake_session(pid: int, volume: float = 1.0, mute: int = 0):
    session = MagicMock()
    session.ProcessId = pid
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


if __name__ == "__main__":
    unittest.main()
