# MyWhisper — Product Specification

## Vision
Бесплатная open-source альтернатива Wispr Flow для Windows.
Системное приложение для голосового ввода текста в **любое** текстовое поле через OpenAI Whisper.
100% оффлайн, без подписок, без отправки данных на серверы.

## Core User Flow
1. Пользователь нажимает и **удерживает** глобальный хоткей (по умолчанию `Ctrl+Shift+Space`)
2. Появляется компактный оверлей с индикатором записи и уровнем громкости
3. Пользователь говорит
4. При **отпускании** хоткея — аудио передаётся в Whisper
5. Транскрибированный текст **вставляется** в активное текстовое поле (через clipboard + Ctrl+V)
6. Оверлей скрывается

## Key Features (MVP)

### F1: Push-to-Talk Global Hotkey
- Глобальная комбинация клавиш, работает из любого приложения
- Настраиваемый хоткей через Settings
- Режимы: Hold-to-record (по умолчанию), Toggle (нажал — начал, нажал — остановил)

### F2: Whisper Transcription (Offline)
- Используем `faster-whisper` (CTranslate2) для максимальной скорости
- Модели: tiny, base, small, medium, large-v3 (выбор в настройках)
- По умолчанию: `base` — баланс скорости и качества
- Автоопределение языка или ручной выбор

### F3: System Tray Application
- Иконка в трее Windows
- Контекстное меню: Settings, About, Quit
- Статус: Idle / Recording / Processing
- Минимальное потребление ресурсов в idle

### F4: Recording Overlay
- Компактное полупрозрачное окно поверх всех окон
- Показывает: статус записи, уровень громкости (VU meter), таймер
- Появляется при начале записи, исчезает после вставки текста
- Позиция: настраиваемая (по умолчанию — центр снизу)

### F5: Smart Text Insertion
- Сохраняет текущий clipboard, вставляет текст, восстанавливает clipboard
- Fallback: если Ctrl+V не работает — посимвольный ввод через SendInput

### F6: Settings UI
- Выбор модели Whisper (с индикатором размера/скорости)
- Выбор языка (или авто)
- Настройка хоткея
- Выбор аудиоустройства (микрофон)
- Автозапуск с Windows
- Позиция оверлея
- Тема: Light / Dark

### F7: Audio Device Selection
- Список доступных микрофонов
- Тест микрофона (уровень громкости в реальном времени)
- Автовыбор системного микрофона по умолчанию

### F8: Model Management
- Автозагрузка выбранной модели при первом запуске
- Индикатор загрузки модели
- Кэширование моделей локально

## Non-Functional Requirements

### Performance
- Транскрипция < 2 сек для 10 сек аудио (модель base, GPU)
- CPU fallback если нет CUDA
- Потребление RAM в idle < 100 MB
- Горячая загрузка модели (держим в памяти)

### Compatibility
- Windows 10/11 (x64)
- Python 3.10+
- GPU: NVIDIA с CUDA (опционально, для ускорения)

### Privacy
- Все данные обрабатываются локально
- Никакой телеметрии
- Аудио не сохраняется на диск (только в RAM)

## Tech Stack
- **Language**: Python 3.11+
- **Transcription**: faster-whisper (CTranslate2 backend)
- **GUI**: PyQt6 (system tray + overlay + settings)
- **Audio**: sounddevice (PortAudio backend)
- **Hotkeys**: pynput (global keyboard hooks)
- **Text insertion**: pyperclip + pyautogui
- **Packaging**: PyInstaller (single .exe)
- **Config**: JSON file in %APPDATA%/MyWhisper/

## File Structure
```
MyWhisper/
├── src/
│   ├── main.py              # Entry point
│   ├── app.py               # Application controller
│   ├── config.py            # Configuration management
│   ├── hotkey_manager.py    # Global hotkey handling
│   ├── audio_recorder.py    # Audio capture
│   ├── transcriber.py       # Whisper integration
│   ├── text_inserter.py     # Clipboard + paste logic
│   ├── overlay_widget.py    # Recording overlay UI
│   ├── tray_icon.py         # System tray icon
│   ├── settings_window.py   # Settings dialog
│   └── resources/
│       ├── icons/
│       │   ├── mic_idle.png
│       │   ├── mic_recording.png
│       │   └── mic_processing.png
│       └── styles/
│           └── dark.qss
├── tests/
│   ├── test_config.py
│   ├── test_audio_recorder.py
│   ├── test_transcriber.py
│   └── test_text_inserter.py
├── docs/
│   ├── SPEC.md
│   └── ARCHITECTURE.md
├── requirements.txt
├── setup.py
├── build.spec            # PyInstaller spec
└── README.md
```
