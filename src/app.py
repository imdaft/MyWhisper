from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

import numpy as np
from PyQt6.QtCore import QObject, QThread, pyqtSignal, pyqtSlot

from src.config import Config

if TYPE_CHECKING:
    from src.audio_recorder import AudioRecorder
    from src.hotkey_manager import HotkeyManager
    from src.overlay_widget import OverlayWidget
    from src.text_inserter import TextInserter
    from src.transcriber import Transcriber
    from src.tray_icon import TrayIcon

logger = logging.getLogger(__name__)

# Clips shorter/quieter than these are treated as accidental hotkey taps or
# silence and dropped before Whisper, which can otherwise "hallucinate" phrases
# (e.g. subtitle boilerplate) and paste them into the user's active window.
_SAMPLE_RATE: int = 16000
_MIN_CLIP_SEC: float = 0.25
_MIN_CLIP_RMS: float = 0.004


class TranscriptionWorker(QObject):
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(
        self, transcriber: Transcriber, audio: np.ndarray, language: str, hotwords: str = "",
    ) -> None:
        super().__init__()
        self._transcriber = transcriber
        self._audio = audio
        self._language = language
        self._hotwords = hotwords

    @pyqtSlot()
    def run(self) -> None:
        try:
            lang = self._language if self._language != "auto" else None
            text = self._transcriber.transcribe(
                self._audio, language=lang, hotwords=self._hotwords or None,
            )
            self.finished.emit(text)
        except Exception as exc:
            logger.error("Transcription failed: %s", exc, exc_info=True)
            self.error.emit(str(exc))


class _ModelLoader(QObject):
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, transcriber: Transcriber, model_size: str, device_pref: str) -> None:
        super().__init__()
        self._transcriber = transcriber
        self._model_size = model_size
        self._device_pref = device_pref

    @pyqtSlot()
    def run(self) -> None:
        try:
            self._transcriber.load_model(self._model_size, device_pref=self._device_pref)
            if self._transcriber.is_model_loaded():
                self.finished.emit()
            else:
                self.error.emit("Model failed to load")
        except Exception as exc:
            logger.error("Model loading failed: %s", exc, exc_info=True)
            self.error.emit(str(exc))


class App(QObject):
    def __init__(self) -> None:
        super().__init__()
        self._config = Config()
        self._model_ready: bool = False
        self._worker_thread: QThread | None = None
        self._worker: TranscriptionWorker | None = None
        self._model_loader_thread: QThread | None = None
        self._model_loader: _ModelLoader | None = None

        self._hotkey_manager: HotkeyManager | None = None
        self._audio_recorder: AudioRecorder | None = None
        self._transcriber: Transcriber | None = None
        self._text_inserter: TextInserter | None = None
        self._tray_icon: TrayIcon | None = None
        self._overlay: OverlayWidget | None = None

    def start(self) -> None:
        self._create_components()
        self._connect_signals()
        self._apply_theme(self._config.get("theme", "dark"))
        self._apply_autostart(self._config.get("autostart", False))
        self._hotkey_manager.start()  # type: ignore[union-attr]
        self._tray_icon.show()  # type: ignore[union-attr]
        self._tray_icon.setToolTip("MyWhisper — загрузка модели…")  # type: ignore[union-attr]
        logger.info("App started, loading model in background...")
        self._tray_icon.notify(  # type: ignore[union-attr]
            "MyWhisper", "Запущен. Загружаю модель Whisper…", "info",
        )
        self._load_model_async()

    def _create_components(self) -> None:
        from src.audio_recorder import AudioRecorder
        from src.hotkey_manager import HotkeyManager
        from src.overlay_widget import OverlayWidget
        from src.text_inserter import TextInserter
        from src.transcriber import Transcriber
        from src.tray_icon import TrayIcon

        device = self._config.get("audio_device")
        self._audio_recorder = AudioRecorder(device_id=device)
        self._transcriber = Transcriber()
        self._text_inserter = TextInserter()
        self._tray_icon = TrayIcon()
        self._overlay = OverlayWidget(
            position=self._config.get("overlay_position", "bottom_center"),
            theme=self._config.get("theme", "dark"),
        )

        hotkey = self._config.get("hotkey", ["ctrl", "shift", "space"])
        mode = self._config.get("hotkey_mode", "hold")
        self._hotkey_manager = HotkeyManager(keys=tuple(hotkey), mode=mode)

    def _connect_signals(self) -> None:
        hm = self._hotkey_manager
        assert hm is not None
        hm.recording_start_requested.connect(self._on_recording_start)
        hm.recording_stop_requested.connect(self._on_recording_stop)

        assert self._audio_recorder is not None
        self._audio_recorder.level_changed.connect(self._on_audio_level)

        assert self._tray_icon is not None
        self._tray_icon.settings_requested.connect(self._on_settings_requested)
        self._tray_icon.quit_requested.connect(self._on_quit_requested)

        self._config.config_changed.connect(self._on_config_changed)

    def _load_model_async(self) -> None:
        assert self._transcriber is not None
        if self._model_loader_thread is not None and self._model_loader_thread.isRunning():
            logger.info("Model load already in progress, ignoring new request")
            return
        model_size = self._config.get("model_size", "base")
        device_pref = self._config.get("device", "auto")

        self._model_loader_thread = QThread()
        self._model_loader = _ModelLoader(self._transcriber, model_size, device_pref)
        self._model_loader.moveToThread(self._model_loader_thread)
        self._model_loader_thread.started.connect(self._model_loader.run)
        self._model_loader.finished.connect(self._on_model_loaded)
        self._model_loader.error.connect(self._on_model_load_error)
        self._model_loader.finished.connect(self._model_loader_thread.quit)
        self._model_loader.error.connect(self._model_loader_thread.quit)
        # Clean up only AFTER the thread has fully stopped
        self._model_loader_thread.finished.connect(self._cleanup_model_loader)
        self._model_loader_thread.start()

    @pyqtSlot()
    def _on_model_loaded(self) -> None:
        logger.info("Model loaded successfully")
        was_ready = self._model_ready
        self._model_ready = True
        if self._tray_icon is not None:
            self._tray_icon.set_status("idle")
            if not was_ready:
                self._tray_icon.notify(
                    "MyWhisper", "Модель готова. Нажмите хоткей и говорите.", "info",
                )

    @pyqtSlot(str)
    def _on_model_load_error(self, error_msg: str) -> None:
        logger.error("Failed to load model: %s", error_msg)
        self._model_ready = False
        if self._tray_icon is not None:
            self._tray_icon.setToolTip("MyWhisper — ошибка загрузки модели")
            self._tray_icon.notify(
                "MyWhisper",
                "Не удалось загрузить модель Whisper. При первом запуске нужен "
                "интернет для скачивания; проверьте связь и свободную память.",
                "error",
            )

    @pyqtSlot()
    def _cleanup_model_loader(self) -> None:
        self._model_loader = None
        self._model_loader_thread = None

    @pyqtSlot()
    def _on_recording_start(self) -> None:
        assert self._audio_recorder is not None
        assert self._overlay is not None
        assert self._tray_icon is not None

        if not self._model_ready:
            logger.info("Hotkey pressed but model not ready yet")
            self._tray_icon.notify(
                "MyWhisper", "Модель ещё загружается, подождите…", "info",
            )
            return

        logger.info("Recording started")
        try:
            self._audio_recorder.start_recording()
        except Exception as exc:
            logger.error("Failed to start recording: %s", exc)
            self._tray_icon.notify(
                "MyWhisper",
                "Не удалось начать запись. Проверьте микрофон и его доступ "
                "в настройках конфиденциальности Windows.",
                "error",
            )
            return

        self._overlay.show_recording()
        self._tray_icon.set_status("recording")

    @pyqtSlot()
    def _on_recording_stop(self) -> None:
        assert self._audio_recorder is not None
        assert self._overlay is not None
        assert self._tray_icon is not None
        assert self._transcriber is not None

        # Recording never actually started (model not ready, mic error) — nothing to do.
        if not self._audio_recorder.is_recording:
            return

        logger.info("Recording stopped")
        audio = self._audio_recorder.stop_recording()

        # One clip at a time: don't start a second transcription while one runs.
        # Leave the overlay/tray showing "processing" — the in-flight clip still
        # owns them and its finalize step will clear them.
        if self._worker_thread is not None and self._worker_thread.isRunning():
            logger.warning("Transcription already in progress, dropping new clip")
            self._overlay.show_processing()
            self._tray_icon.set_status("processing")
            self._tray_icon.notify(
                "MyWhisper", "Ещё обрабатываю прошлую фразу, подождите…", "info",
            )
            return

        self._overlay.show_processing()
        self._tray_icon.set_status("processing")

        if audio is None or len(audio) == 0:
            logger.warning("Empty audio captured, skipping transcription")
            self._finalize_transcription("")
            return

        # Drop accidental taps / near-silence before Whisper can hallucinate.
        duration = len(audio) / _SAMPLE_RATE
        rms = float(np.sqrt(np.mean(np.square(audio)))) if audio.size else 0.0
        if duration < _MIN_CLIP_SEC or rms < _MIN_CLIP_RMS:
            logger.info("Clip too short/quiet (%.2fs, rms=%.4f), skipping", duration, rms)
            self._finalize_transcription("")
            return

        self._start_transcription(audio)

    def _start_transcription(self, audio: np.ndarray) -> None:
        language = self._config.get("language", "auto")
        hotwords = self._hotwords_from_config()

        self._worker_thread = QThread()
        self._worker = TranscriptionWorker(
            self._transcriber,  # type: ignore[arg-type]
            audio,
            language,
            hotwords,
        )
        self._worker.moveToThread(self._worker_thread)

        self._worker_thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_transcription_done)
        self._worker.error.connect(self._on_transcription_error)
        self._worker.finished.connect(self._worker_thread.quit)
        self._worker.error.connect(self._worker_thread.quit)
        self._worker_thread.finished.connect(self._cleanup_worker)

        self._worker_thread.start()

    @pyqtSlot(str)
    def _on_transcription_done(self, text: str) -> None:
        logger.info("Transcription done: %d chars", len(text))
        self._finalize_transcription(text)

    @pyqtSlot(str)
    def _on_transcription_error(self, error_msg: str) -> None:
        logger.error("Transcription error: %s", error_msg)
        if self._tray_icon is not None:
            self._tray_icon.notify(
                "MyWhisper", "Не удалось распознать речь. Подробности в журнале.", "error",
            )
        self._finalize_transcription("")

        # If the worker died, the model is gone — reload it so the next hotkey
        # press works instead of failing forever.
        if self._transcriber is not None and not self._transcriber.is_model_loaded():
            logger.info("Model lost after worker failure, reloading in background")
            self._model_ready = False
            if self._tray_icon is not None:
                self._tray_icon.setToolTip("MyWhisper — переподключение к модели…")
            self._load_model_async()

    def _finalize_transcription(self, text: str) -> None:
        assert self._overlay is not None
        assert self._tray_icon is not None
        assert self._text_inserter is not None

        clean = text.strip()
        if clean:
            self._text_inserter.insert_text(clean)
            self._tray_icon.show_last_phrase(clean)

        self._overlay.hide_overlay()
        self._tray_icon.set_status("idle")

    def _cleanup_worker(self) -> None:
        self._worker = None
        self._worker_thread = None

    @pyqtSlot(float)
    def _on_audio_level(self, level: float) -> None:
        if self._overlay is not None:
            self._overlay.update_level(level)

    @pyqtSlot()
    def _on_settings_requested(self) -> None:
        from src.settings_window import SettingsWindow

        dialog = SettingsWindow(self._config)
        if self._transcriber is not None:
            dialog.set_model_status(self._transcriber.is_model_loaded())
        dialog.exec()

    @pyqtSlot()
    def _on_quit_requested(self) -> None:
        logger.info("Quit requested by user")
        self.cleanup()
        from PyQt6.QtWidgets import QApplication
        QApplication.instance().quit()  # type: ignore[union-attr]

    @pyqtSlot(str, object)
    def _on_config_changed(self, key: str, value: object) -> None:
        logger.info("Config changed: %s = %s", key, value)

        if key == "hotkey" and self._hotkey_manager is not None:
            self._hotkey_manager.set_hotkey(tuple(value))  # type: ignore[arg-type]
        elif key == "hotkey_mode" and self._hotkey_manager is not None:
            self._hotkey_manager.set_mode(value)  # type: ignore[arg-type]
        elif key in ("model_size", "device"):
            self._model_ready = False
            if self._tray_icon is not None:
                self._tray_icon.setToolTip("MyWhisper — загрузка модели…")
            self._load_model_async()
        elif key == "audio_device" and self._audio_recorder is not None:
            self._audio_recorder.set_device(value)  # type: ignore[arg-type]
        elif key == "overlay_position" and self._overlay is not None:
            self._overlay.set_position(value)  # type: ignore[arg-type]
        elif key == "theme":
            self._apply_theme(value)  # type: ignore[arg-type]
        elif key == "autostart":
            self._apply_autostart(bool(value))
        elif key == "custom_words":
            logger.info("Custom dictionary updated (%d chars)", len(value or ""))

    def _hotwords_from_config(self) -> str:
        """Turn the user's dictionary (one word/phrase per line or comma) into a
        single hotwords string for faster-whisper."""
        raw = self._config.get("custom_words", "") or ""
        words = [w.strip() for w in re.split(r"[\n,]+", raw) if w.strip()]
        return ", ".join(words)

    def _apply_theme(self, theme: str) -> None:
        from PyQt6.QtWidgets import QApplication
        from src.theme import apply_theme
        apply_theme(QApplication.instance(), theme)
        if self._overlay is not None:
            self._overlay.set_theme(theme)

    def _apply_autostart(self, enabled: bool) -> None:
        try:
            from src import autostart
            autostart.set_enabled(bool(enabled))
        except Exception as exc:
            logger.error("Autostart update failed: %s", exc)

    def cleanup(self) -> None:
        logger.info("Cleaning up...")
        if self._worker_thread is not None and self._worker_thread.isRunning():
            self._worker_thread.quit()
            self._worker_thread.wait(5000)

        if self._hotkey_manager is not None:
            self._hotkey_manager.stop()

        if self._transcriber is not None:
            self._transcriber.shutdown()

        if self._tray_icon is not None:
            self._tray_icon.hide()

        if self._overlay is not None:
            self._overlay.hide_overlay()

        logger.info("Cleanup complete")
