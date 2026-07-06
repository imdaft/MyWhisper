from __future__ import annotations

import logging
from typing import Any

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from src.config import Config

logger = logging.getLogger(__name__)

_LANGUAGES: list[tuple[str, str]] = [
    ("auto", "Auto-detect"),
    ("en", "English"),
    ("ru", "Russian"),
    ("es", "Spanish"),
    ("fr", "French"),
    ("de", "German"),
    ("zh", "Chinese"),
    ("ja", "Japanese"),
    ("ko", "Korean"),
    ("pt", "Portuguese"),
    ("it", "Italian"),
    ("uk", "Ukrainian"),
]

_MODELS: list[tuple[str, str]] = [
    ("tiny", "tiny (~75MB)"),
    ("base", "base (~150MB)"),
    ("small", "small (~500MB)"),
    ("medium", "medium (~1.5GB)"),
    ("large-v3", "large-v3 (~3GB)"),
]

_COMPUTE_OPTIONS: list[tuple[str, str]] = [
    ("auto", "Auto"),
    ("cpu", "CPU"),
    ("cuda", "GPU (CUDA)"),
]

_OVERLAY_POSITIONS: list[tuple[str, str]] = [
    ("bottom_center", "Bottom Center"),
    ("top_center", "Top Center"),
    ("top_right", "Top Right"),
    ("bottom_right", "Bottom Right"),
]

_THEMES: list[tuple[str, str]] = [
    ("dark", "Dark"),
    ("light", "Light"),
]

_MODES: list[tuple[str, str]] = [
    ("hold", "Hold to record"),
    ("toggle", "Toggle"),
]

_QT_KEY_NAMES: dict[int, str] = {
    Qt.Key.Key_Control: "Ctrl",
    Qt.Key.Key_Shift: "Shift",
    Qt.Key.Key_Alt: "Alt",
    Qt.Key.Key_Meta: "Win",
    Qt.Key.Key_Space: "Space",
    Qt.Key.Key_Tab: "Tab",
    Qt.Key.Key_Return: "Enter",
    Qt.Key.Key_Enter: "Enter",
    Qt.Key.Key_Escape: "Esc",
    Qt.Key.Key_Backspace: "Backspace",
    Qt.Key.Key_Delete: "Delete",
    Qt.Key.Key_Insert: "Insert",
    Qt.Key.Key_Home: "Home",
    Qt.Key.Key_End: "End",
    Qt.Key.Key_PageUp: "PageUp",
    Qt.Key.Key_PageDown: "PageDown",
    Qt.Key.Key_Up: "Up",
    Qt.Key.Key_Down: "Down",
    Qt.Key.Key_Left: "Left",
    Qt.Key.Key_Right: "Right",
    Qt.Key.Key_CapsLock: "CapsLock",
    Qt.Key.Key_F1: "F1",
    Qt.Key.Key_F2: "F2",
    Qt.Key.Key_F3: "F3",
    Qt.Key.Key_F4: "F4",
    Qt.Key.Key_F5: "F5",
    Qt.Key.Key_F6: "F6",
    Qt.Key.Key_F7: "F7",
    Qt.Key.Key_F8: "F8",
    Qt.Key.Key_F9: "F9",
    Qt.Key.Key_F10: "F10",
    Qt.Key.Key_F11: "F11",
    Qt.Key.Key_F12: "F12",
}

_MODIFIER_KEYS: set[int] = {
    Qt.Key.Key_Control,
    Qt.Key.Key_Shift,
    Qt.Key.Key_Alt,
    Qt.Key.Key_Meta,
}


def _qt_key_to_name(key: int) -> str | None:
    if key in _QT_KEY_NAMES:
        return _QT_KEY_NAMES[key]
    if Qt.Key.Key_A <= key <= Qt.Key.Key_Z:
        return chr(key)
    if Qt.Key.Key_0 <= key <= Qt.Key.Key_9:
        return chr(key)
    return None


def _format_hotkey(keys: list[str]) -> str:
    return "+".join(k.capitalize() for k in keys)


def _hotkey_names_to_config(names: list[str]) -> list[str]:
    mapping: dict[str, str] = {
        "Ctrl": "ctrl",
        "Shift": "shift",
        "Alt": "alt",
        "Win": "win",
        "Space": "space",
        "Tab": "tab",
        "Enter": "enter",
        "Esc": "esc",
    }
    result: list[str] = []
    for name in names:
        lower = mapping.get(name, name.lower())
        result.append(lower)
    return result


class HotkeyRecorder(QLineEdit):
    hotkey_changed = pyqtSignal(list)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setReadOnly(True)
        self.setPlaceholderText("Click to record hotkey")
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)

        self._recording: bool = False
        self._pressed_keys: list[str] = []
        self._current_keys: set[int] = set()
        self._display_names: list[str] = []

    def set_hotkey(self, keys: list[str]) -> None:
        self._display_names = [k.capitalize() for k in keys]
        self.setText(_format_hotkey(keys))

    def get_hotkey_config(self) -> list[str]:
        return _hotkey_names_to_config(self._display_names)

    def mousePressEvent(self, event: Any) -> None:
        super().mousePressEvent(event)
        self._start_recording()

    def focusInEvent(self, event: Any) -> None:
        super().focusInEvent(event)
        self._start_recording()

    def focusOutEvent(self, event: Any) -> None:
        super().focusOutEvent(event)
        if self._recording:
            self._stop_recording()

    def _start_recording(self) -> None:
        if self._recording:
            return
        self._recording = True
        self._current_keys.clear()
        self._pressed_keys.clear()
        self.setText("Press keys...")
        self.setStyleSheet("QLineEdit { border: 2px solid #3daee9; }")

    def _stop_recording(self) -> None:
        self._recording = False
        self.setStyleSheet("")
        if self._pressed_keys:
            self._display_names = list(self._pressed_keys)
            self.setText("+".join(self._pressed_keys))
            self.hotkey_changed.emit(self.get_hotkey_config())
        elif self._display_names:
            self.setText("+".join(self._display_names))
        else:
            self.clear()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if not self._recording:
            return

        key = event.key()
        if key == Qt.Key.Key_unknown:
            return

        name = _qt_key_to_name(key)
        if name is None:
            return

        if key not in self._current_keys:
            self._current_keys.add(key)
            self._pressed_keys.append(name)
            self.setText("+".join(self._pressed_keys))

    def keyReleaseEvent(self, event: QKeyEvent) -> None:
        if not self._recording:
            return

        key = event.key()
        if key in self._current_keys:
            self._current_keys.discard(key)

        if not self._current_keys and self._pressed_keys:
            self._stop_recording()
            self.clearFocus()


class SettingsWindow(QDialog):
    settings_applied = pyqtSignal()

    def __init__(self, config: Config, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._config = config

        self.setWindowTitle("MyWhisper Settings")
        self.setFixedWidth(500)
        self.setMinimumHeight(100)

        self._mic_test_timer: QTimer | None = None
        self._audio_recorder: Any = None

        self._build_ui()
        self._populate_from_config()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self._tabs = QTabWidget()
        layout.addWidget(self._tabs)

        self._build_general_tab()
        self._build_audio_model_tab()
        self._build_appearance_tab()

        self._button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.Apply,
        )
        self._button_box.accepted.connect(self._on_ok)
        self._button_box.rejected.connect(self._on_cancel)

        apply_btn = self._button_box.button(QDialogButtonBox.StandardButton.Apply)
        if apply_btn is not None:
            apply_btn.clicked.connect(self._on_apply)

        layout.addWidget(self._button_box)

    def _build_general_tab(self) -> None:
        tab = QWidget()
        form = QFormLayout(tab)
        form.setContentsMargins(12, 16, 12, 12)
        form.setSpacing(10)

        hotkey_row = QHBoxLayout()
        self._hotkey_recorder = HotkeyRecorder()
        self._hotkey_recorder.setMinimumWidth(200)
        hotkey_row.addWidget(self._hotkey_recorder, 1)

        hotkey_widget = QWidget()
        hotkey_widget.setLayout(hotkey_row)
        form.addRow("Hotkey:", hotkey_widget)

        self._mode_combo = QComboBox()
        for value, label in _MODES:
            self._mode_combo.addItem(label, value)
        form.addRow("Mode:", self._mode_combo)

        self._language_combo = QComboBox()
        for value, label in _LANGUAGES:
            self._language_combo.addItem(label, value)
        form.addRow("Language:", self._language_combo)

        self._autostart_check = QCheckBox("Start with Windows")
        form.addRow("Autostart:", self._autostart_check)

        self._tabs.addTab(tab, "General")

    def _build_audio_model_tab(self) -> None:
        tab = QWidget()
        form = QFormLayout(tab)
        form.setContentsMargins(12, 16, 12, 12)
        form.setSpacing(10)

        self._mic_combo = QComboBox()
        self._populate_microphones()
        form.addRow("Microphone:", self._mic_combo)

        mic_test_layout = QVBoxLayout()
        mic_test_btn_row = QHBoxLayout()
        self._mic_test_btn = QPushButton("Test Microphone")
        self._mic_test_btn.clicked.connect(self._on_test_microphone)
        mic_test_btn_row.addWidget(self._mic_test_btn)
        mic_test_btn_row.addStretch()
        mic_test_layout.addLayout(mic_test_btn_row)

        self._mic_vu_meter = QProgressBar()
        self._mic_vu_meter.setRange(0, 100)
        self._mic_vu_meter.setValue(0)
        self._mic_vu_meter.setTextVisible(False)
        self._mic_vu_meter.setFixedHeight(16)
        self._mic_vu_meter.setVisible(False)
        mic_test_layout.addWidget(self._mic_vu_meter)

        mic_test_widget = QWidget()
        mic_test_widget.setLayout(mic_test_layout)
        form.addRow("", mic_test_widget)

        self._model_combo = QComboBox()
        for value, label in _MODELS:
            self._model_combo.addItem(label, value)
        form.addRow("Model:", self._model_combo)

        self._compute_combo = QComboBox()
        for value, label in _COMPUTE_OPTIONS:
            self._compute_combo.addItem(label, value)
        form.addRow("Compute:", self._compute_combo)

        self._model_status_label = QLabel("Model not downloaded")
        self._model_status_label.setStyleSheet("color: #888;")
        form.addRow("Model Status:", self._model_status_label)

        self._tabs.addTab(tab, "Audio && Model")

    def _build_appearance_tab(self) -> None:
        tab = QWidget()
        form = QFormLayout(tab)
        form.setContentsMargins(12, 16, 12, 12)
        form.setSpacing(10)

        self._theme_combo = QComboBox()
        for value, label in _THEMES:
            self._theme_combo.addItem(label, value)
        form.addRow("Theme:", self._theme_combo)

        self._overlay_combo = QComboBox()
        for value, label in _OVERLAY_POSITIONS:
            self._overlay_combo.addItem(label, value)
        form.addRow("Overlay Position:", self._overlay_combo)

        self._tabs.addTab(tab, "Appearance")

    def _populate_microphones(self) -> None:
        self._mic_combo.clear()
        self._mic_combo.addItem("Default", None)

        try:
            import sounddevice as sd

            device_list = sd.query_devices()
            # sounddevice returns a single dict (not a list) when only one
            # device exists — normalize so the one microphone still shows up.
            if isinstance(device_list, dict):
                device_list = [device_list]

            for idx, dev in enumerate(device_list):
                if not isinstance(dev, dict):
                    continue
                if dev.get("max_input_channels", 0) > 0:
                    name = dev.get("name", f"Device {idx}")
                    self._mic_combo.addItem(name, idx)
        except Exception as exc:
            logger.warning("Could not enumerate audio devices: %s", exc)

    def _populate_from_config(self) -> None:
        hotkey_keys: list[str] = self._config.get("hotkey", ["ctrl", "shift", "space"])
        self._hotkey_recorder.set_hotkey(hotkey_keys)

        mode: str = self._config.get("hotkey_mode", "hold")
        self._set_combo_by_data(self._mode_combo, mode)

        language: str = self._config.get("language", "auto")
        self._set_combo_by_data(self._language_combo, language)

        autostart: bool = self._config.get("autostart", False)
        self._autostart_check.setChecked(autostart)

        device_id: int | None = self._config.get("audio_device", None)
        if device_id is not None:
            self._set_combo_by_data(self._mic_combo, device_id)
        else:
            self._mic_combo.setCurrentIndex(0)

        model_size: str = self._config.get("model_size", "base")
        self._set_combo_by_data(self._model_combo, model_size)

        compute_type: str = self._config.get("compute_type", "auto")
        self._set_combo_by_data(self._compute_combo, compute_type)

        theme: str = self._config.get("theme", "dark")
        self._set_combo_by_data(self._theme_combo, theme)

        overlay: str = self._config.get("overlay_position", "bottom_center")
        self._set_combo_by_data(self._overlay_combo, overlay)

    def _apply_settings(self) -> None:
        self._config.set("hotkey", self._hotkey_recorder.get_hotkey_config())
        self._config.set("hotkey_mode", self._mode_combo.currentData())
        self._config.set("language", self._language_combo.currentData())
        self._config.set("autostart", self._autostart_check.isChecked())
        self._config.set("audio_device", self._mic_combo.currentData())
        self._config.set("model_size", self._model_combo.currentData())
        self._config.set("compute_type", self._compute_combo.currentData())
        self._config.set("theme", self._theme_combo.currentData())
        self._config.set("overlay_position", self._overlay_combo.currentData())
        self.settings_applied.emit()

    def _on_ok(self) -> None:
        self._apply_settings()
        self.accept()

    def _on_cancel(self) -> None:
        self._stop_mic_test()
        self.reject()

    def _on_apply(self) -> None:
        self._apply_settings()

    def _on_test_microphone(self) -> None:
        if self._mic_vu_meter.isVisible():
            self._stop_mic_test()
            return

        self._mic_vu_meter.setVisible(True)
        self._mic_vu_meter.setValue(0)
        self._mic_test_btn.setText("Stop Test")

        try:
            from src.audio_recorder import AudioRecorder

            self._audio_recorder = AudioRecorder(self)
            device_id = self._mic_combo.currentData()
            if device_id is not None:
                self._audio_recorder.set_device(device_id)
            self._audio_recorder.level_changed.connect(self._on_mic_level)
            self._audio_recorder.start_recording()

            self._mic_test_timer = QTimer(self)
            self._mic_test_timer.setSingleShot(True)
            self._mic_test_timer.timeout.connect(self._stop_mic_test)
            self._mic_test_timer.start(10_000)
        except Exception as exc:
            logger.warning("Microphone test failed: %s", exc)
            self._mic_vu_meter.setVisible(False)
            self._mic_test_btn.setText("Test Microphone")

    def _on_mic_level(self, level: float) -> None:
        self._mic_vu_meter.setValue(int(level * 100))

    def _stop_mic_test(self) -> None:
        if self._mic_test_timer is not None:
            self._mic_test_timer.stop()
            self._mic_test_timer = None

        if self._audio_recorder is not None:
            try:
                self._audio_recorder.stop_recording()
            except Exception as exc:
                logger.warning("Error stopping mic test: %s", exc)
            self._audio_recorder = None

        self._mic_vu_meter.setValue(0)
        self._mic_vu_meter.setVisible(False)
        self._mic_test_btn.setText("Test Microphone")

    def set_model_status(self, loaded: bool) -> None:
        if loaded:
            self._model_status_label.setText("Model loaded")
            self._model_status_label.setStyleSheet("color: #27ae60;")
        else:
            self._model_status_label.setText("Model not downloaded")
            self._model_status_label.setStyleSheet("color: #888;")

    def closeEvent(self, event: Any) -> None:
        self._stop_mic_test()
        super().closeEvent(event)

    @staticmethod
    def _set_combo_by_data(combo: QComboBox, value: Any) -> None:
        for i in range(combo.count()):
            if combo.itemData(i) == value:
                combo.setCurrentIndex(i)
                return
