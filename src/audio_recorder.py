from __future__ import annotations

import threading
import time
import logging
from typing import Any

import numpy as np
import sounddevice as sd
from PyQt6.QtCore import QObject, pyqtSignal

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16000
CHANNELS = 1
DTYPE = "float32"
BLOCKSIZE = 1024
LEVEL_EMIT_INTERVAL = 1.0 / 30.0


class AudioRecorder(QObject):
    level_changed = pyqtSignal(float)

    def __init__(self, device_id: int | None = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._device_id: int | None = device_id
        self._stream: sd.InputStream | None = None
        self._chunks: list[np.ndarray] = []
        self._lock = threading.Lock()
        self._recording = False
        self._last_level_time: float = 0.0

    def _audio_callback(
        self,
        indata: np.ndarray,
        frames: int,
        time_info: Any,
        status: sd.CallbackFlags,
    ) -> None:
        if status:
            logger.warning("Audio callback status: %s", status)

        chunk = indata[:, 0].copy()

        with self._lock:
            self._chunks.append(chunk)

        now = time.monotonic()
        if now - self._last_level_time >= LEVEL_EMIT_INTERVAL:
            self._last_level_time = now
            rms = float(np.sqrt(np.mean(chunk ** 2)))
            level = min(1.0, rms / 0.3)
            try:
                self.level_changed.emit(level)
            except RuntimeError:
                pass

    def start_recording(self) -> None:
        if self._recording:
            logger.warning("Already recording, ignoring start request")
            return

        with self._lock:
            self._chunks.clear()

        self._last_level_time = 0.0

        try:
            self._stream = sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype=DTYPE,
                blocksize=BLOCKSIZE,
                device=self._device_id,
                callback=self._audio_callback,
            )
            self._stream.start()
            self._recording = True
            logger.info(
                "Recording started (device=%s, sr=%d)",
                self._device_id,
                SAMPLE_RATE,
            )
        except sd.PortAudioError as exc:
            logger.error("Failed to start recording: %s", exc)
            self._recording = False
            raise

    def stop_recording(self) -> np.ndarray:
        if not self._recording:
            logger.warning("Not recording, returning empty array")
            return np.array([], dtype=np.float32)

        try:
            if self._stream is not None:
                self._stream.stop()
                self._stream.close()
                self._stream = None
        except sd.PortAudioError as exc:
            logger.error("Error stopping stream: %s", exc)
        finally:
            self._recording = False

        with self._lock:
            if not self._chunks:
                return np.array([], dtype=np.float32)
            audio = np.concatenate(self._chunks)
            self._chunks.clear()

        logger.info("Recording stopped, captured %.2f seconds", len(audio) / SAMPLE_RATE)
        return audio

    def list_devices(self) -> list[dict]:
        devices: list[dict] = []
        try:
            device_list = sd.query_devices()
        except sd.PortAudioError as exc:
            logger.error("Failed to query audio devices: %s", exc)
            return devices

        # sounddevice returns a single dict (not a list) when only one device
        # exists — normalize so the one microphone still shows up.
        if isinstance(device_list, dict):
            device_list = [device_list]

        for idx, dev in enumerate(device_list):
            if not isinstance(dev, dict):
                continue
            max_input = dev.get("max_input_channels", 0)
            if max_input > 0:
                devices.append({
                    "id": idx,
                    "name": dev.get("name", f"Device {idx}"),
                    "channels": max_input,
                })

        return devices

    def set_device(self, device_id: int | None) -> None:
        if self._recording:
            logger.warning("Cannot change device while recording")
            return
        self._device_id = device_id
        logger.info("Audio device set to %s", device_id)

    @property
    def is_recording(self) -> bool:
        return self._recording
