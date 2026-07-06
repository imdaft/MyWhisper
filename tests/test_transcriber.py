"""Unit tests for src.transcriber.Transcriber (subprocess-based)."""
from __future__ import annotations

import json
import sys
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch, MagicMock, PropertyMock

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PyQt6.QtWidgets import QApplication

_app: QApplication | None = None


def setUpModule() -> None:
    global _app
    if QApplication.instance() is None:
        _app = QApplication([])


from src.transcriber import Transcriber, AVAILABLE_MODELS, _detect_device, _resolve_compute_type


class _FakePopen:
    """Simulates subprocess.Popen for the whisper worker."""

    def __init__(self, responses: list[dict] | None = None) -> None:
        self.pid = 99999
        self._responses = list(responses or [])
        self._resp_idx = 0
        self._sent: list[dict] = []
        self.stdin = StringIO()
        self.stderr = StringIO()

        self._stdout_buf = StringIO()
        self.stdout = self._stdout_buf

    def poll(self) -> int | None:
        return None  # process alive

    def wait(self, timeout: float = 5) -> None:
        pass

    def kill(self) -> None:
        pass

    def _prepare_stdout(self) -> None:
        """Load next response into stdout buffer."""
        if self._resp_idx < len(self._responses):
            resp = self._responses[self._resp_idx]
            self._resp_idx += 1
            self._stdout_buf = StringIO(json.dumps(resp) + "\n")
            self.stdout = self._stdout_buf


def _make_transcriber_with_fake(responses: list[dict]) -> tuple[Transcriber, _FakePopen]:
    t = Transcriber()
    fake = _FakePopen(responses)

    original_send = t._send

    def mock_send(msg: dict, timeout: float | None = None) -> dict:
        fake._sent.append(msg)
        fake._prepare_stdout()
        t._proc = fake  # type: ignore
        if timeout is None:
            return original_send(msg)
        return original_send(msg, timeout=timeout)

    t._send = mock_send  # type: ignore
    t._proc = fake  # type: ignore
    return t, fake


class TestGetAvailableModels(unittest.TestCase):

    def test_returns_list(self) -> None:
        models = Transcriber.get_available_models()
        self.assertIsInstance(models, list)
        self.assertTrue(len(models) > 0)

    def test_model_dict_keys(self) -> None:
        for m in Transcriber.get_available_models():
            self.assertIn("name", m)
            self.assertIn("size_mb", m)
            self.assertIn("description", m)

    def test_expected_model_names(self) -> None:
        names = [m["name"] for m in Transcriber.get_available_models()]
        for expected in ["tiny", "base", "small", "medium", "large-v3"]:
            self.assertIn(expected, names)

    def test_returns_copies(self) -> None:
        models = Transcriber.get_available_models()
        models[0]["name"] = "TAMPERED"
        fresh = Transcriber.get_available_models()
        self.assertNotEqual(fresh[0]["name"], "TAMPERED")


class TestIsModelLoaded(unittest.TestCase):

    def test_initially_not_loaded(self) -> None:
        t = Transcriber()
        self.assertFalse(t.is_model_loaded())

    def test_loaded_after_successful_load(self) -> None:
        t, fake = _make_transcriber_with_fake([{"status": "ok"}])
        with patch("src.transcriber._detect_device", return_value="cpu"):
            t.load_model("base")
        self.assertTrue(t.is_model_loaded())

    def test_not_loaded_after_failed_load(self) -> None:
        t, fake = _make_transcriber_with_fake([{"status": "error", "msg": "Download failed"}])
        with patch("src.transcriber._detect_device", return_value="cpu"):
            t.load_model("base")
        self.assertFalse(t.is_model_loaded())


class TestLoadModel(unittest.TestCase):

    def test_invalid_model_name_emits_error(self) -> None:
        t = Transcriber()
        handler = MagicMock()
        t.error.connect(handler)
        t.load_model("nonexistent_model_xyz")
        handler.assert_called_once()
        self.assertIn("nonexistent_model_xyz", handler.call_args[0][0])

    def test_invalid_model_name_does_not_set_model(self) -> None:
        t = Transcriber()
        t.load_model("nonexistent_model_xyz")
        self.assertFalse(t.is_model_loaded())

    def test_valid_model_emits_model_loaded(self) -> None:
        t, fake = _make_transcriber_with_fake([{"status": "ok"}])
        handler = MagicMock()
        t.model_loaded.connect(handler)
        with patch("src.transcriber._detect_device", return_value="cpu"):
            t.load_model("tiny")
        handler.assert_called_once()

    def test_load_model_sends_correct_cmd(self) -> None:
        t, fake = _make_transcriber_with_fake([{"status": "ok"}])
        with patch("src.transcriber._detect_device", return_value="cpu"):
            t.load_model("small", compute_type="int8")
        self.assertEqual(len(fake._sent), 1)
        sent = fake._sent[0]
        self.assertEqual(sent["cmd"], "load")
        self.assertEqual(sent["model"], "small")
        self.assertEqual(sent["device"], "cpu")
        self.assertEqual(sent["compute"], "int8")

    def test_load_model_auto_compute_cpu(self) -> None:
        t, fake = _make_transcriber_with_fake([{"status": "ok"}])
        with patch("src.transcriber._detect_device", return_value="cpu"):
            t.load_model("base", compute_type="auto")
        self.assertEqual(fake._sent[0]["compute"], "int8")

    def test_load_model_auto_compute_cuda(self) -> None:
        t, fake = _make_transcriber_with_fake([{"status": "ok"}])
        with patch("src.transcriber._detect_device", return_value="cuda"):
            t.load_model("base", compute_type="auto")
        self.assertEqual(fake._sent[0]["compute"], "float16")

    def test_load_model_error_emits_error(self) -> None:
        t, fake = _make_transcriber_with_fake([{"status": "error", "msg": "Model load failure"}])
        error_handler = MagicMock()
        t.error.connect(error_handler)
        with patch("src.transcriber._detect_device", return_value="cpu"):
            t.load_model("base")
        error_handler.assert_called_once()
        self.assertIn("Model load failure", error_handler.call_args[0][0])

    def test_current_model_size_after_load(self) -> None:
        t, fake = _make_transcriber_with_fake([{"status": "ok"}])
        with patch("src.transcriber._detect_device", return_value="cpu"):
            t.load_model("medium")
        self.assertEqual(t.current_model_size, "medium")

    def test_current_model_size_none_initially(self) -> None:
        t = Transcriber()
        self.assertIsNone(t.current_model_size)


class TestTranscribe(unittest.TestCase):

    def test_transcribe_without_model_returns_empty(self) -> None:
        t = Transcriber()
        error_handler = MagicMock()
        t.error.connect(error_handler)
        result = t.transcribe(np.zeros(16000, dtype=np.float32))
        self.assertEqual(result, "")
        error_handler.assert_called_once()

    def test_transcribe_with_empty_audio_returns_empty(self) -> None:
        t, fake = _make_transcriber_with_fake([{"status": "ok"}])
        with patch("src.transcriber._detect_device", return_value="cpu"):
            t.load_model("base")
        result = t.transcribe(np.array([], dtype=np.float32))
        self.assertEqual(result, "")

    def test_transcribe_returns_text(self) -> None:
        t, fake = _make_transcriber_with_fake([
            {"status": "ok"},  # load response
            {"status": "ok", "text": "Hello world", "lang": "en", "prob": 0.95},  # transcribe response
        ])
        with patch("src.transcriber._detect_device", return_value="cpu"):
            t.load_model("base")
        audio = np.random.randn(16000).astype(np.float32)
        result = t.transcribe(audio, language="en")
        self.assertEqual(result, "Hello world")

    def test_transcribe_emits_transcription_done(self) -> None:
        t, fake = _make_transcriber_with_fake([
            {"status": "ok"},
            {"status": "ok", "text": "Test text", "lang": "en", "prob": 0.99},
        ])
        with patch("src.transcriber._detect_device", return_value="cpu"):
            t.load_model("base")
        handler = MagicMock()
        t.transcription_done.connect(handler)
        audio = np.random.randn(16000).astype(np.float32)
        t.transcribe(audio)
        handler.assert_called_once_with("Test text")

    def test_transcribe_error_emits_error(self) -> None:
        t, fake = _make_transcriber_with_fake([
            {"status": "ok"},
            {"status": "error", "msg": "CUDA OOM"},
        ])
        with patch("src.transcriber._detect_device", return_value="cpu"):
            t.load_model("base")
        error_handler = MagicMock()
        t.error.connect(error_handler)
        audio = np.random.randn(16000).astype(np.float32)
        result = t.transcribe(audio)
        self.assertEqual(result, "")
        error_handler.assert_called_once()
        self.assertIn("CUDA OOM", error_handler.call_args[0][0])


class TestHelperFunctions(unittest.TestCase):

    def test_detect_device_cpu_no_torch(self) -> None:
        with patch.dict("sys.modules", {"torch": None}):
            result = _detect_device()
        self.assertEqual(result, "cpu")

    def test_resolve_compute_type_auto_cpu(self) -> None:
        self.assertEqual(_resolve_compute_type("auto", "cpu"), "int8")

    def test_resolve_compute_type_auto_cuda(self) -> None:
        self.assertEqual(_resolve_compute_type("auto", "cuda"), "float16")

    def test_resolve_compute_type_explicit(self) -> None:
        self.assertEqual(_resolve_compute_type("float32", "cpu"), "float32")


if __name__ == "__main__":
    unittest.main()
