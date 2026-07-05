from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
from PyQt6.QtCore import QObject, pyqtSignal

logger = logging.getLogger(__name__)

AVAILABLE_MODELS: list[dict[str, Any]] = [
    {"name": "tiny", "size_mb": 75, "description": "Fastest, lowest quality. Good for testing."},
    {"name": "base", "size_mb": 150, "description": "Good balance of speed and quality. Recommended default."},
    {"name": "small", "size_mb": 500, "description": "Good quality, moderate speed."},
    {"name": "medium", "size_mb": 1500, "description": "High quality, slower transcription."},
    {"name": "large-v3", "size_mb": 3000, "description": "Best quality, requires significant resources."},
]

_VALID_MODEL_NAMES: set[str] = {m["name"] for m in AVAILABLE_MODELS}

_WORKER_SCRIPT: str = str(Path(__file__).resolve().parent / "whisper_worker.py")


def _get_worker_cmd() -> list[str]:
    """Return the command to launch the whisper worker subprocess."""
    if getattr(sys, "frozen", False):
        # PyInstaller frozen exe — use same exe with --worker flag
        return [sys.executable, "--worker"]
    return [sys.executable, _WORKER_SCRIPT]


def _detect_device() -> str:
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda"
    except ImportError:
        pass
    return "cpu"


def _resolve_compute_type(compute_type: str, device: str) -> str:
    if compute_type != "auto":
        return compute_type
    return "float16" if device == "cuda" else "int8"


class Transcriber(QObject):
    model_loaded = pyqtSignal()
    transcription_done = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._model_size: str | None = None
        self._proc: subprocess.Popen | None = None

    def _ensure_worker(self) -> None:
        if self._proc is not None and self._proc.poll() is None:
            return

        creationflags = 0
        if sys.platform == "win32":
            creationflags = subprocess.CREATE_NO_WINDOW

        self._proc = subprocess.Popen(
            _get_worker_cmd(),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            creationflags=creationflags,
        )
        logger.info("Whisper worker process started (pid=%d)", self._proc.pid)

    def _send(self, msg: dict) -> dict:
        assert self._proc is not None
        assert self._proc.stdin is not None
        assert self._proc.stdout is not None

        line = json.dumps(msg, ensure_ascii=False) + "\n"
        self._proc.stdin.write(line)
        self._proc.stdin.flush()

        resp_line = self._proc.stdout.readline()
        if not resp_line:
            stderr_out = ""
            if self._proc.stderr:
                stderr_out = self._proc.stderr.read()
            self._proc = None
            raise RuntimeError(f"Worker process died. stderr: {stderr_out[:1000]}")

        return json.loads(resp_line)

    def load_model(self, model_size: str, compute_type: str = "auto") -> None:
        if model_size not in _VALID_MODEL_NAMES:
            msg = f"Unknown model size '{model_size}'. Available: {sorted(_VALID_MODEL_NAMES)}"
            logger.error(msg)
            self.error.emit(msg)
            return

        device = _detect_device()
        resolved_compute = _resolve_compute_type(compute_type, device)
        logger.info("Loading model '%s' on %s with compute_type=%s", model_size, device, resolved_compute)

        self._ensure_worker()

        try:
            resp = self._send({
                "cmd": "load",
                "model": model_size,
                "device": device,
                "compute": resolved_compute,
            })
        except Exception as exc:
            msg = f"Worker process error during model load: {exc}"
            logger.error(msg)
            self.error.emit(msg)
            return

        if resp.get("status") == "ok":
            self._model_size = model_size
            logger.info("Model '%s' loaded successfully", model_size)
            self.model_loaded.emit()
        else:
            self._model_size = None
            err = resp.get("msg", "Unknown error")
            msg = f"Failed to load model '{model_size}': {err}"
            logger.error(msg)
            self.error.emit(msg)

    def transcribe(self, audio: np.ndarray, language: str | None = None) -> str:
        if self._proc is None or self._proc.poll() is not None:
            msg = "No model loaded. Call load_model() first."
            logger.error(msg)
            self.error.emit(msg)
            return ""

        if audio.size == 0:
            logger.warning("Empty audio provided, returning empty string")
            return ""

        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".npy", prefix="mywhisper_")
        os.close(tmp_fd)
        np.save(tmp_path, audio.astype(np.float32))

        try:
            resp = self._send({
                "cmd": "transcribe",
                "audio_path": tmp_path,
                "language": language or "auto",
            })
        except Exception as exc:
            msg = f"Worker process error during transcription: {exc}"
            logger.error(msg)
            self.error.emit(msg)
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            return ""

        if resp.get("status") == "ok":
            text = resp.get("text", "")
            logger.info(
                "Transcription complete: language=%s, probability=%.2f, length=%d chars",
                resp.get("lang", "?"), resp.get("prob", 0.0), len(text),
            )
            self.transcription_done.emit(text)
            return text
        else:
            err = resp.get("msg", "Unknown error")
            msg = f"Transcription failed: {err}"
            logger.error(msg)
            self.error.emit(msg)
            return ""

    def is_model_loaded(self) -> bool:
        return self._model_size is not None and self._proc is not None and self._proc.poll() is None

    @staticmethod
    def get_available_models() -> list[dict[str, Any]]:
        return [m.copy() for m in AVAILABLE_MODELS]

    @property
    def current_model_size(self) -> str | None:
        return self._model_size

    def shutdown(self) -> None:
        if self._proc is not None and self._proc.poll() is None:
            try:
                assert self._proc.stdin is not None
                self._proc.stdin.write(json.dumps({"cmd": "quit"}) + "\n")
                self._proc.stdin.flush()
            except OSError:
                pass
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        self._proc = None
        self._model_size = None
