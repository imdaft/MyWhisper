# MyWhisper

[![License: GPL-3.0](https://img.shields.io/badge/license-GPL--3.0-blue.svg)](LICENSE)
[![Release](https://img.shields.io/github/v/release/imdaft/MyWhisper?include_prereleases)](https://github.com/imdaft/MyWhisper/releases/latest)
[![Platform](https://img.shields.io/badge/platform-Windows%2010%2F11-0078D6)](https://github.com/imdaft/MyWhisper/releases/latest)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](requirements.txt)

Локальный голосовой ввод для Windows на базе OpenAI Whisper. Бесплатная
оффлайн-альтернатива Wispr Flow: нажал и держишь горячую клавишу, говоришь,
отпускаешь — распознанный текст вставляется в активное поле. 100% локально,
без облака и подписок.

> Local push-to-talk voice typing for Windows, powered by faster-whisper.
> Hold a hotkey, speak, release — the transcription is pasted into the focused
> field. Fully offline, no cloud, no subscription.

## Скачать

Самый простой способ — готовая сборка, ничего устанавливать не нужно:

**[⬇ Скачать MyWhisper (Windows x64, .zip)](https://github.com/imdaft/MyWhisper/releases/latest)**

Распакуй архив в любую папку и запусти `MyWhisper.exe` — рядом должна остаться
папка `_internal`, переносить их нужно вместе.

## Возможности

- Глобальная горячая клавиша (по умолчанию `Ctrl+Shift+Space`), режимы «удержание» и «переключение»
- Оффлайн-распознавание через `faster-whisper` (CTranslate2), CPU или NVIDIA GPU
- Модели на выбор: `tiny` … `large-v3`, а также быстрая `large-v3-turbo`
- Свой словарь имён и терминов (повышает точность)
- Компактный оверлей с индикатором записи и уровнем громкости
- Иконка и меню в системном трее, тема Light/Dark
- Автозапуск с Windows
- Аудио не сохраняется на диск, телеметрии нет

## Требования

- Windows 10/11 (x64)
- Для готовой сборки — ничего дополнительно, работает из коробки на CPU
- Для запуска из исходников — Python 3.10+
- NVIDIA GPU — опционально, для ускорения распознавания (см. [Ускорение](#ускорение-gpu))

## Установка и запуск (из исходников)

```bash
pip install -r requirements.txt
python run.py
```

При первом запуске выбранная модель Whisper скачивается автоматически
(в фоне; статус виден по уведомлениям в трее).

## Использование

1. Запусти приложение — в трее появится иконка микрофона.
2. Дождись уведомления **«Модель готова»** (при первом запуске модель качается,
   это может занять минуту-две).
3. Нажми и удерживай горячую клавишу, говори, отпусти.
4. Текст вставится в активное поле.

Настройки (горячая клавиша, модель, язык, микрофон, словарь, тема,
автозапуск) — правый клик по иконке в трее → **Settings**:

| Вкладка     | Что настраивается                                    |
|-------------|-------------------------------------------------------|
| General     | Горячая клавиша, режим (удержание/переключение), язык, автозапуск |
| Audio & Model | Микрофон, модель Whisper, ускорение (CPU/GPU)       |
| Словарь     | Имена и термины, которые Whisper часто путает          |
| Appearance  | Тема (Light/Dark), позиция оверлея на экране            |

## Ускорение (GPU)

- **Запуск из исходника** (`python run.py`) использует NVIDIA GPU, если он есть
  и в окружении установлен PyTorch/cuDNN — распознавание заметно быстрее.
- **Готовая сборка (`.exe`) работает на CPU.** Библиотеки cuDNN для GPU весят
  ~1 ГБ и в сборку не включены, чтобы она оставалась компактной и запускалась
  на любой машине. Для CPU рекомендуются модели `base`/`small` — они быстрые
  и без видеокарты; тяжёлые модели (`large-v3`, `large-v3-turbo`) на CPU
  распознают медленно.

## Сборка .exe из исходников

Собирать нужно обычным Python с python.org (3.10–3.11), **не** версией из
Microsoft Store: упакованный ctranslate2 из Store-Python падает при запуске.

```bash
py -3.11 -m pip install pyinstaller
py -3.11 -m PyInstaller build.spec --noconfirm --clean
```

Готовое приложение появится в `dist/MyWhisper/` (~350 МБ).

## Приватность

- Всё распознавание идёт локально на твоём компьютере.
- Аудио хранится только в оперативной памяти и удаляется сразу после распознавания.
- Нет сети, нет телеметрии.

## Тесты

```bash
pip install pytest
python -m pytest tests/ -q
```

## Структура проекта

```
src/
  app.py              — координатор приложения (сигналы между компонентами)
  main.py             — точка входа, логирование, single-instance
  config.py           — настройки (%APPDATA%/MyWhisper/config.json)
  audio_recorder.py   — захват звука с микрофона (sounddevice)
  hotkey_manager.py   — глобальная горячая клавиша (pynput)
  transcriber.py      — управление процессом распознавания
  whisper_worker.py   — отдельный процесс с faster-whisper
  text_inserter.py    — вставка текста через буфер обмена / SendInput
  overlay_widget.py   — оверлей записи (индикатор, VU-метр)
  tray_icon.py        — иконка и меню в трее
  settings_window.py  — окно настроек
  autostart.py        — автозапуск с Windows (реестр)
  theme.py            — тема Light/Dark для всего приложения
docs/                 — спецификация и архитектура (подробнее)
tests/                — юнит-тесты (pytest)
```

Подробное описание архитектуры — в [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md),
исходная спецификация — в [docs/SPEC.md](docs/SPEC.md).

## Участие в разработке

Issues и pull request'ы приветствуются. Перед PR убедись, что тесты проходят
(`python -m pytest tests/ -q`) и код собирается без ошибок
(`python -m py_compile src/*.py`).

## Лицензия

GPL-3.0-or-later. См. [LICENSE](LICENSE) и [NOTICE.md](NOTICE.md) (лицензии
сторонних зависимостей).
