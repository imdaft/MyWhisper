"""Unit tests for src.audio_recorder.AudioRecorder."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock, call

import numpy as np

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PyQt6.QtWidgets import QApplication

_app: QApplication | None = None


def setUpModule() -> None:
    global _app
    if QApplication.instance() is None:
        _app = QApplication([])


from src.audio_recorder import AudioRecorder, SAMPLE_RATE, CHANNELS, DTYPE, BLOCKSIZE


class TestAudioRecorderConstructor(unittest.TestCase):
    """Constructor should store the device_id and initialise state."""

    @patch("src.audio_recorder.sd")
    def test_default_device_id_is_none(self, _mock_sd: MagicMock) -> None:
        rec = AudioRecorder()
        self.assertIsNone(rec._device_id)

    @patch("src.audio_recorder.sd")
    def test_custom_device_id(self, _mock_sd: MagicMock) -> None:
        rec = AudioRecorder(device_id=3)
        self.assertEqual(rec._device_id, 3)

    @patch("src.audio_recorder.sd")
    def test_initial_recording_state_is_false(self, _mock_sd: MagicMock) -> None:
        rec = AudioRecorder()
        self.assertFalse(rec.is_recording)


class TestListDevices(unittest.TestCase):
    """list_devices should return a filtered list of input devices."""

    @patch("src.audio_recorder.sd")
    def test_returns_list_of_dicts(self, mock_sd: MagicMock) -> None:
        mock_sd.query_devices.return_value = [
            {"name": "Mic 1", "max_input_channels": 2, "max_output_channels": 0},
            {"name": "Speaker", "max_input_channels": 0, "max_output_channels": 2},
            {"name": "Mic 2", "max_input_channels": 1, "max_output_channels": 0},
        ]
        rec = AudioRecorder()
        devices = rec.list_devices()

        self.assertEqual(len(devices), 2)
        self.assertIsInstance(devices, list)
        for d in devices:
            self.assertIsInstance(d, dict)

    @patch("src.audio_recorder.sd")
    def test_device_dict_keys(self, mock_sd: MagicMock) -> None:
        mock_sd.query_devices.return_value = [
            {"name": "Mic", "max_input_channels": 1, "max_output_channels": 0},
        ]
        rec = AudioRecorder()
        devices = rec.list_devices()

        self.assertEqual(len(devices), 1)
        self.assertIn("id", devices[0])
        self.assertIn("name", devices[0])
        self.assertIn("channels", devices[0])

    @patch("src.audio_recorder.sd")
    def test_filters_out_output_only_devices(self, mock_sd: MagicMock) -> None:
        mock_sd.query_devices.return_value = [
            {"name": "Speaker", "max_input_channels": 0, "max_output_channels": 2},
        ]
        rec = AudioRecorder()
        devices = rec.list_devices()
        self.assertEqual(devices, [])

    @patch("src.audio_recorder.sd")
    def test_handles_single_device_not_list(self, mock_sd: MagicMock) -> None:
        # sounddevice returns a single dict when only one device exists
        mock_sd.query_devices.return_value = {
            "name": "Only Mic",
            "max_input_channels": 1,
            "max_output_channels": 0,
        }
        rec = AudioRecorder()
        devices = rec.list_devices()
        self.assertEqual(len(devices), 1)
        self.assertEqual(devices[0]["name"], "Only Mic")

    @patch("src.audio_recorder.sd")
    def test_handles_port_audio_error(self, mock_sd: MagicMock) -> None:
        import sounddevice as sd
        mock_sd.query_devices.side_effect = sd.PortAudioError("no audio")
        mock_sd.PortAudioError = sd.PortAudioError
        rec = AudioRecorder()
        devices = rec.list_devices()
        self.assertEqual(devices, [])


class TestSetDevice(unittest.TestCase):
    """set_device should update or reject depending on recording state."""

    @patch("src.audio_recorder.sd")
    def test_set_device_updates(self, _mock_sd: MagicMock) -> None:
        rec = AudioRecorder()
        rec.set_device(5)
        self.assertEqual(rec._device_id, 5)

    @patch("src.audio_recorder.sd")
    def test_set_device_to_none(self, _mock_sd: MagicMock) -> None:
        rec = AudioRecorder(device_id=3)
        rec.set_device(None)
        self.assertIsNone(rec._device_id)

    @patch("src.audio_recorder.sd")
    def test_set_device_rejected_while_recording(self, mock_sd: MagicMock) -> None:
        rec = AudioRecorder(device_id=1)
        # Simulate that recording has started
        mock_stream = MagicMock()
        mock_sd.InputStream.return_value = mock_stream
        rec.start_recording()

        rec.set_device(99)
        # Device should NOT have changed
        self.assertEqual(rec._device_id, 1)

        # Clean up
        rec.stop_recording()


class TestRecordingLifecycle(unittest.TestCase):
    """start_recording / stop_recording lifecycle."""

    @patch("src.audio_recorder.sd")
    def test_start_sets_recording_flag(self, mock_sd: MagicMock) -> None:
        mock_stream = MagicMock()
        mock_sd.InputStream.return_value = mock_stream

        rec = AudioRecorder()
        rec.start_recording()

        self.assertTrue(rec.is_recording)
        mock_sd.InputStream.assert_called_once()
        mock_stream.start.assert_called_once()

        rec.stop_recording()

    @patch("src.audio_recorder.sd")
    def test_stop_clears_recording_flag(self, mock_sd: MagicMock) -> None:
        mock_stream = MagicMock()
        mock_sd.InputStream.return_value = mock_stream

        rec = AudioRecorder()
        rec.start_recording()
        result = rec.stop_recording()

        self.assertFalse(rec.is_recording)
        mock_stream.stop.assert_called_once()
        mock_stream.close.assert_called_once()

    @patch("src.audio_recorder.sd")
    def test_stop_when_not_recording_returns_empty(self, _mock_sd: MagicMock) -> None:
        rec = AudioRecorder()
        result = rec.stop_recording()

        self.assertIsInstance(result, np.ndarray)
        self.assertEqual(result.size, 0)
        self.assertEqual(result.dtype, np.float32)

    @patch("src.audio_recorder.sd")
    def test_double_start_is_ignored(self, mock_sd: MagicMock) -> None:
        mock_stream = MagicMock()
        mock_sd.InputStream.return_value = mock_stream

        rec = AudioRecorder()
        rec.start_recording()
        rec.start_recording()  # second call should be ignored

        self.assertEqual(mock_sd.InputStream.call_count, 1)

        rec.stop_recording()


class TestAudioCallback(unittest.TestCase):
    """Simulating audio data through the callback."""

    @patch("src.audio_recorder.sd")
    def test_callback_accumulates_chunks(self, mock_sd: MagicMock) -> None:
        mock_stream = MagicMock()
        mock_sd.InputStream.return_value = mock_stream

        rec = AudioRecorder()
        rec.start_recording()

        # Simulate audio callback with known data
        chunk1 = np.ones((BLOCKSIZE, 1), dtype=np.float32) * 0.5
        chunk2 = np.ones((BLOCKSIZE, 1), dtype=np.float32) * 0.25

        status = MagicMock()
        status.__bool__ = lambda s: False  # no error status

        rec._audio_callback(chunk1, BLOCKSIZE, {}, status)
        rec._audio_callback(chunk2, BLOCKSIZE, {}, status)

        audio = rec.stop_recording()

        self.assertEqual(audio.shape[0], BLOCKSIZE * 2)
        # First half should be 0.5, second half 0.25
        np.testing.assert_allclose(audio[:BLOCKSIZE], 0.5)
        np.testing.assert_allclose(audio[BLOCKSIZE:], 0.25)

    @patch("src.audio_recorder.sd")
    def test_stop_after_no_chunks_returns_empty(self, mock_sd: MagicMock) -> None:
        mock_stream = MagicMock()
        mock_sd.InputStream.return_value = mock_stream

        rec = AudioRecorder()
        rec.start_recording()
        # No audio callback invoked
        audio = rec.stop_recording()

        self.assertEqual(audio.size, 0)


class TestLevelChangedSignal(unittest.TestCase):
    """level_changed signal should be emitted periodically during recording."""

    @patch("src.audio_recorder.sd")
    def test_level_changed_emission(self, mock_sd: MagicMock) -> None:
        mock_stream = MagicMock()
        mock_sd.InputStream.return_value = mock_stream

        rec = AudioRecorder()
        handler = MagicMock()
        rec.level_changed.connect(handler)

        rec.start_recording()

        # The first callback should emit because _last_level_time is 0.0
        chunk = np.ones((BLOCKSIZE, 1), dtype=np.float32) * 0.1
        status = MagicMock()
        status.__bool__ = lambda s: False

        rec._audio_callback(chunk, BLOCKSIZE, {}, status)

        handler.assert_called()
        # level should be a float between 0 and 1
        emitted_level = handler.call_args[0][0]
        self.assertIsInstance(emitted_level, float)
        self.assertGreaterEqual(emitted_level, 0.0)
        self.assertLessEqual(emitted_level, 1.0)

        rec.stop_recording()


if __name__ == "__main__":
    unittest.main()
