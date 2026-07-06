from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import tempfile
import threading
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
    {"name": "large-v3-turbo", "size_mb": 1600, "description": "Near large-v3 quality, much faster. Best with a GPU."},
]

_VALID_MODEL_NAMES: set[str] = {m["name"] for m in AVAILABLE_MODELS}

_WORKER_SCRIPT: str = str(Path(__file__).resolve().parent / "whisper_worker.py")

# Worker response timeouts (seconds). The first model load may download several
# GB from HuggingFace, so it gets a generous window; transcribing a short clip
# is fast, so a hang there almost certainly means the worker is stuck.
_LOAD_TIMEOUT: float = 1800.0
_TRANSCRIBE_TIMEOUT: float = 180.0


def _get_worker_cmd() -> list[str]:
    """Return the command to launch the whisper worker subprocess."""
    if getattr(sys, "frozen", False):
        # PyInstaller frozen exe — use same exe with --worker flag
        return [sys.executable, "--worker"]
    return [sys.executable, _WORKER_SCRIPT]


def _cuda_available() -> bool:
    # CTranslate2 (the faster-whisper backend) reports usable NVIDIA GPUs
    # without pulling in torch (a ~2 GB dependency faster-whisper doesn't need).
    try:
        import ctranslate2
        return ctranslate2.get_cuda_device_count() > 0
    except Exception:
        return False


def _detect_device() -> str:
    return "cuda" if _cuda_available() else "cpu"


def _resolve_device(pref: str) -> str:
    """Turn a user device preference (auto/cpu/cuda) into a real device, falling
    back to CPU if a GPU was requested but none is available."""
    # Frozen builds don't bundle the ~1 GB of cuDNN libraries ctranslate2 needs
    # for GPU inference (they'd otherwise crash mid-transcription). Force CPU
    # there; run from source (python run.py) for GPU acceleration.
    if getattr(sys, "frozen", False):
        return "cpu"
    if pref == "cpu":
        return "cpu"
    if pref in ("cuda", "gpu"):
        return "cuda" if _cuda_available() else "cpu"
    return _detect_device()  # "auto" or anything unexpected


def _compute_for_device(device: str) -> str:
    # ctranslate2 compute types: float16 is the right default on GPU, int8 on CPU.
    return "float16" if device == "cuda" else "int8"


class Transcriber(QObject):
    model_loaded = pyqtSignal()
    transcription_done = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._model_size: str | None = None
        self._proc: subprocess.Popen | None = None
        # Serializes access to the worker pipe so a model reload and a
        # transcription (each on its own QThread) can never interleave their
        # JSON messages on the shared stdin/stdout.
        self._lock = threading.Lock()

    def _ensure_worker(self) -> None:
        with self._lock:
            if self._proc is not None and self._proc.poll() is None:
                return

            # A previous worker may have died; make sure its handle is gone
            # before spawning a replacement so we never orphan a process.
            if self._proc is not None:
                try:
                    self._proc.kill()
                except Exception:
                    pass

            creationflags = 0
            if sys.platform == "win32":
                creationflags = subprocess.CREATE_NO_WINDOW

            # Force the worker's Python stdio to UTF-8 regardless of the Windows
            # locale so Cyrillic (and any non-ASCII) transcriptions round-trip.
            # errors="replace" keeps one stray byte from killing the protocol.
            env = dict(os.environ)
            env["PYTHONIOENCODING"] = "utf-8"
            env["PYTHONUTF8"] = "1"

            self._proc = subprocess.Popen(
                _get_worker_cmd(),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=creationflags,
                env=env,
            )
            logger.info("Whisper worker process started (pid=%d)", self._proc.pid)

    def _send(self, msg: dict, timeout: float = _TRANSCRIBE_TIMEOUT) -> dict:
        with self._lock:
            assert self._proc is not None
            assert self._proc.stdin is not None
            assert self._proc.stdout is not None
            proc = self._proc

            line = json.dumps(msg, ensure_ascii=False) + "\n"
            proc.stdin.write(line)
            proc.stdin.flush()

            # Read the reply on a helper thread so a hung/native worker can't
            # block us forever — readline() has no timeout of its own.
            holder: dict[str, Any] = {}

            def _read() -> None:
                try:
                    holder["line"] = proc.stdout.readline()
                except Exception as exc:  # pragma: no cover - defensive
                    holder["exc"] = exc

            reader = threading.Thread(target=_read, daemon=True)
            reader.start()
            reader.join(timeout)

            if reader.is_alive():
                logger.error("Worker did not respond within %.0fs, killing it", timeout)
                try:
                    proc.kill()
                except Exception:
                    pass
                if self._proc is proc:
                    self._proc = None
                    self._model_size = None
                raise RuntimeError(f"Worker timed out after {timeout:.0f}s")

            if "exc" in holder:
                if self._proc is proc:
                    self._proc = None
                raise RuntimeError(f"Worker read error: {holder['exc']}")

            resp_line = holder.get("line")
            if not resp_line:
                stderr_out = ""
                try:
                    if proc.stderr is not None:
                        stderr_out = proc.stderr.read()
                except Exception:
                    pass
                if self._proc is proc:
                    self._proc = None
                    self._model_size = None
                raise RuntimeError(f"Worker process died. stderr: {stderr_out[:1000]}")

            return json.loads(resp_line)

    def load_model(self, model_size: str, device_pref: str = "auto") -> None:
        if model_size not in _VALID_MODEL_NAMES:
            msg = f"Unknown model size '{model_size}'. Available: {sorted(_VALID_MODEL_NAMES)}"
            logger.error(msg)
            self.error.emit(msg)
            return

        device = _resolve_device(device_pref)
        compute = _compute_for_device(device)
        logger.info(
            "Loading model '%s' on %s (compute=%s, pref=%s)",
            model_size, device, compute, device_pref,
        )

        self._ensure_worker()

        try:
            resp = self._send(
                {
                    "cmd": "load",
                    "model": model_size,
                    "device": device,
                    "compute": compute,
                },
                timeout=_LOAD_TIMEOUT,
            )
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

    def transcribe(
        self, audio: np.ndarray, language: str | None = None, hotwords: str | None = None,
    ) -> str:
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
            try:
                resp = self._send(
                    {
                        "cmd": "transcribe",
                        "audio_path": tmp_path,
                        "language": language or "auto",
                        "hotwords": hotwords or "",
                    },
                    timeout=_TRANSCRIBE_TIMEOUT,
                )
            except Exception as exc:
                # Worker died or hung: surface it so the caller (and the user)
                # find out instead of silently receiving an empty result.
                msg = f"Worker process error during transcription: {exc}"
                logger.error(msg)
                self.error.emit(msg)
                raise

            if resp.get("status") == "ok":
                text = resp.get("text", "")
                logger.info(
                    "Transcription complete: language=%s, probability=%.2f, length=%d chars",
                    resp.get("lang", "?"), resp.get("prob", 0.0), len(text),
                )
                self.transcription_done.emit(text)
                return text

            err = resp.get("msg", "Unknown error")
            msg = f"Transcription failed: {err}"
            logger.error(msg)
            self.error.emit(msg)
            return ""
        finally:
            # We own the temp file's lifetime. The worker also unlinks it after
            # loading, so it may already be gone — guard with exists().
            if os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    def is_model_loaded(self) -> bool:
        return self._model_size is not None and self._proc is not None and self._proc.poll() is None

    @staticmethod
    def get_available_models() -> list[dict[str, Any]]:
        return [m.copy() for m in AVAILABLE_MODELS]

    @property
    def current_model_size(self) -> str | None:
        return self._model_size

    def shutdown(self) -> None:
        with self._lock:
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
