# MyWhisper — System Architecture

## High-Level Architecture

```
┌─────────────────────────────────────────────────────┐
│                    main.py                          │
│              (Entry Point / Bootstrap)              │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│                   App Controller                     │
│                    (app.py)                          │
│                                                     │
│  Orchestrates all components, manages lifecycle     │
│  Runs PyQt6 event loop                              │
└──┬──────┬──────┬──────┬──────┬──────┬───────────────┘
   │      │      │      │      │      │
   ▼      ▼      ▼      ▼      ▼      ▼
┌────┐ ┌────┐ ┌────┐ ┌────┐ ┌────┐ ┌────┐
│Tray│ │Hot │ │Aud │ │Tran│ │Text│ │Over│
│Icon│ │Key │ │Rec │ │scr │ │Ins │ │lay │
└────┘ └────┘ └────┘ └────┘ └────┘ └────┘
```

## Component Diagram

### 1. Config Manager (`config.py`)
```
Responsibilities:
  - Load/save JSON config from %APPDATA%/MyWhisper/config.json
  - Provide defaults for all settings
  - Emit change signals (PyQt Signal) when config updates
  - Validate config values

Interface:
  Config.load() -> dict
  Config.save(data: dict) -> None
  Config.get(key: str, default=None) -> Any
  Config.set(key: str, value: Any) -> None
  Config.config_changed: Signal  # PyQt signal
```

### 2. Hotkey Manager (`hotkey_manager.py`)
```
Responsibilities:
  - Register global keyboard hook via pynput
  - Detect key press and release for push-to-talk
  - Support toggle mode
  - Run in separate thread (pynput requirement)
  - Emit signals: recording_started, recording_stopped

Threading: Dedicated thread (pynput listener thread)

Interface:
  HotkeyManager.start() -> None
  HotkeyManager.stop() -> None
  HotkeyManager.set_hotkey(keys: tuple) -> None
  HotkeyManager.set_mode(mode: 'hold' | 'toggle') -> None
  Signals: recording_start_requested, recording_stop_requested
```

### 3. Audio Recorder (`audio_recorder.py`)
```
Responsibilities:
  - Capture audio from selected microphone via sounddevice
  - Stream audio into in-memory buffer (numpy array)
  - Provide real-time audio level (RMS) for VU meter
  - Support start/stop recording
  - Return audio as numpy array (16kHz mono float32 — Whisper format)

Threading: Uses sounddevice callback (runs in audio thread)

Interface:
  AudioRecorder.start_recording() -> None
  AudioRecorder.stop_recording() -> np.ndarray  # returns audio data
  AudioRecorder.get_level() -> float  # 0.0 - 1.0
  AudioRecorder.list_devices() -> list[dict]
  AudioRecorder.set_device(device_id: int) -> None
  Signals: level_changed(float)
```

### 4. Transcriber (`transcriber.py`)
```
Responsibilities:
  - Load faster-whisper model (lazy, on first use)
  - Transcribe audio (numpy array) -> text
  - Support model selection (tiny/base/small/medium/large)
  - Auto-detect or use specified language
  - Keep model in memory for fast subsequent calls
  - Download model if not cached

Threading: Worker thread (via QThread) to avoid blocking UI

Interface:
  Transcriber.load_model(model_size: str) -> None
  Transcriber.transcribe(audio: np.ndarray, language: str = None) -> str
  Transcriber.is_model_loaded() -> bool
  Transcriber.get_available_models() -> list[dict]
  Signals: model_loading(int), transcription_done(str), error(str)
```

### 5. Text Inserter (`text_inserter.py`)
```
Responsibilities:
  - Save current clipboard content
  - Copy transcribed text to clipboard
  - Simulate Ctrl+V to paste
  - Restore original clipboard content
  - Fallback: character-by-character input via SendInput

Threading: Main thread (needs UI access for clipboard)

Interface:
  TextInserter.insert_text(text: str) -> bool
```

### 6. System Tray (`tray_icon.py`)
```
Responsibilities:
  - Display icon in Windows system tray
  - Show status (idle/recording/processing) via icon change
  - Context menu: Settings, About, Quit
  - Tooltip with current status

Interface:
  TrayIcon(parent: QApplication)
  TrayIcon.set_status(status: str) -> None
  Signals: settings_requested, quit_requested
```

### 7. Overlay Widget (`overlay_widget.py`)
```
Responsibilities:
  - Frameless, always-on-top, semi-transparent window
  - Show/hide on recording start/stop
  - Display: recording indicator (pulsing dot), VU meter, timer
  - Rounded corners, modern minimal design
  - Click-through (doesn't steal focus!)

Window flags: Tool | FramelessWindowHint | WindowStaysOnTopHint |
              WindowTransparentForInput

Interface:
  OverlayWidget.show_recording() -> None
  OverlayWidget.hide_overlay() -> None
  OverlayWidget.update_level(level: float) -> None
  OverlayWidget.show_processing() -> None
```

### 8. Settings Window (`settings_window.py`)
```
Responsibilities:
  - Modal dialog for all settings
  - Tabs: General, Audio, Model, Appearance
  - Hotkey recorder widget
  - Microphone test with live VU meter
  - Model download with progress bar
  - Apply / Cancel / OK buttons

Interface:
  SettingsWindow(config: Config, parent=None)
  SettingsWindow.exec() -> None
```

## Data Flow — Recording Session

```
User holds hotkey
       │
       ▼
HotkeyManager ──signal──► App Controller
                              │
                    ┌─────────┼─────────┐
                    ▼         ▼         ▼
              AudioRecorder  Overlay   TrayIcon
              .start()       .show()   .set_status("recording")
                    │
                    │ (audio level callbacks)
                    ▼
              Overlay.update_level()

User releases hotkey
       │
       ▼
HotkeyManager ──signal──► App Controller
                              │
                    ┌─────────┼─────────┐
                    ▼         ▼         ▼
              AudioRecorder  Overlay   TrayIcon
              .stop()        .show_    .set_status("processing")
              → audio data   processing()
                    │
                    ▼
              Transcriber.transcribe(audio)
              (in worker thread)
                    │
                    ▼
              TextInserter.insert_text(text)
                    │
                    ▼
              Overlay.hide() + TrayIcon.set_status("idle")
```

## Threading Model

```
┌─────────────────────┐
│   Main Thread        │  PyQt event loop, UI rendering
│   (QApplication)     │  Overlay, TrayIcon, Settings
└──────────┬──────────┘
           │
┌──────────┴──────────┐
│   Hotkey Thread      │  pynput listener (daemon thread)
│   (pynput)           │  Sends signals to main thread via Qt
└─────────────────────┘
           │
┌──────────┴──────────┐
│   Audio Thread       │  sounddevice callback thread
│   (sounddevice)      │  Writes to shared buffer
└─────────────────────┘
           │
┌──────────┴──────────┐
│   Transcription      │  QThread for Whisper inference
│   Worker Thread      │  Blocks during transcription
└─────────────────────┘
```

## Config File Format

```json
{
  "hotkey": ["ctrl", "shift", "space"],
  "hotkey_mode": "hold",
  "model_size": "base",
  "language": "auto",
  "audio_device": null,
  "overlay_position": "bottom_center",
  "theme": "dark",
  "autostart": false,
  "compute_type": "auto"
}
```
