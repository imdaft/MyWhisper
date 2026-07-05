# MyWhisper Security Audit Report

**Date:** 2026-02-28
**Scope:** All source files in `src/`
**Auditor:** Automated Security Audit Agent (Claude Opus 4.6)

---

## Executive Summary

A comprehensive security audit was performed on all 10 source files in the MyWhisper project. The application is a local speech-to-text tool that records audio, transcribes it via Whisper, and pastes the result into the active window via the clipboard.

**Overall assessment:** The codebase demonstrates generally good security practices -- audio data stays in memory, config files use atomic writes, and thread synchronization is applied consistently. Several HIGH-severity issues were identified and fixed during this audit. Remaining MEDIUM and LOW issues are documented below for future attention.

### Issues Summary

| Severity | Count | Fixed | Remaining |
|----------|-------|-------|-----------|
| CRITICAL | 0     | 0     | 0         |
| HIGH     | 5     | 5     | 0         |
| MEDIUM   | 6     | 0     | 6         |
| LOW      | 5     | 0     | 5         |

---

## Findings by File

---

### 1. `src/config.py`

#### [HIGH] [FIXED] Arbitrary config keys accepted from file and API

**Location:** `Config.load()` (line ~59), `Config.set()` (line ~87)

**Description:** The `load()` method used `merged.update(parsed)` which would accept any key from a tampered config file, potentially injecting unexpected values into the application. The `set()` method accepted any key without validation.

**Impact:** An attacker who gains write access to the config file could inject arbitrary keys that might be consumed by future code changes, or cause unexpected behavior.

**Fix applied:**
- `load()` now only merges keys that exist in `DEFAULT_CONFIG`, logging a warning for unknown keys.
- `set()` now rejects keys not present in `DEFAULT_CONFIG`.

#### [MEDIUM] No type validation on config values

**Location:** `Config.set()`, `Config.load()`

**Description:** While keys are now restricted to known values, the types of values are not validated. For example, `model_size` should always be a string, `hotkey` should always be a list of strings, etc. A corrupted or tampered config file could set `hotkey` to an integer, causing downstream crashes.

**Recommendation:** Add a schema validation step in `load()` and `set()` that checks each value against expected types from `DEFAULT_CONFIG`.

#### [LOW] Config file readable by other users on shared systems

**Location:** `Config._save_locked()`

**Description:** The config file at `%APPDATA%/MyWhisper/config.json` is created with default OS permissions. On shared Windows systems, other administrators could read it. This config does not currently store secrets, so impact is low.

**Recommendation:** If secrets are ever added to the config (e.g., API keys), use Windows DACLs to restrict file permissions to the current user.

---

### 2. `src/main.py`

#### [HIGH] [FIXED] Unbounded log file growth

**Location:** `_setup_logging()` (line ~21)

**Description:** The original code used a plain `FileHandler` with no size limit. A long-running instance could grow the log file indefinitely, filling disk space.

**Fix applied:** Replaced `FileHandler` with `RotatingFileHandler` with a 5 MB max size and 2 backup files.

#### [MEDIUM] Log file may contain sensitive context

**Location:** `_setup_logging()`

**Description:** The log file at `%APPDATA%/MyWhisper/mywhisper.log` could accumulate context about user activity (recording times, transcription lengths, config changes). While no transcription text is logged, the metadata could reveal user behavior patterns.

**Recommendation:** Consider adding a log level configuration option, or redacting timing information in production builds.

#### [LOW] Single-instance mutex name is predictable

**Location:** `_acquire_single_instance()` (line ~34)

**Description:** The mutex name `Global\MyWhisper_SingleInstance_Mutex` is hardcoded and predictable. A malicious process could create this mutex first to prevent MyWhisper from starting (denial of service).

**Recommendation:** This is a standard pattern for single-instance applications and the risk is low. No action required unless targeted DoS is a concern.

---

### 3. `src/app.py`

#### [MEDIUM] Transcription text logged by length, not content (GOOD)

**Location:** `_on_transcription_done()` (line ~162)

**Description:** The log message `"Transcription done: %d chars"` correctly avoids logging the actual transcription text. This is a positive finding.

#### [MEDIUM] Worker thread cleanup may leave dangling references

**Location:** `_cleanup_worker()` (line ~181), `cleanup()` (line ~219)

**Description:** If `_worker_thread.wait(5000)` times out (after 5 seconds), the thread continues running but `_worker` and `_worker_thread` references may still be set. During `_on_quit_requested`, this could result in the application exiting while the worker thread is still running, potentially leaving audio data in an indeterminate state.

**Recommendation:** After the 5-second wait timeout, forcibly terminate the thread or block until completion.

#### [LOW] assert statements used for control flow

**Location:** Multiple `assert` statements in `_connect_signals()`, `_on_recording_start()`, etc.

**Description:** `assert` statements are removed when Python is run with `-O` (optimize), which would cause `AttributeError` on `None` instead of clean `AssertionError`. These are used as null-checks for component initialization.

**Recommendation:** Replace `assert` with explicit `if x is None: raise RuntimeError(...)` checks.

---

### 4. `src/audio_recorder.py`

#### [MEDIUM] `_recording` flag is not protected by the lock

**Location:** `start_recording()` (line ~58), `stop_recording()` (line ~89)

**Description:** The `_recording` boolean is read and written outside the `_lock` in several places (e.g., `start_recording` checks `self._recording` at line 59 without holding the lock, then sets it at line 78). While audio recording start/stop is typically driven from the main thread, a rapid sequence of start/stop calls from signal handlers could cause a race condition.

**Recommendation:** Protect all reads and writes to `_recording` with the existing `_lock`.

#### [LOW] Audio data held in memory until explicitly cleared

**Location:** `_audio_callback()`, `stop_recording()`

**Description (POSITIVE):** Audio data is stored only in memory (in `_chunks` list) and is cleared when `stop_recording()` is called. Audio data is never written to disk. This is a good privacy practice.

---

### 5. `src/transcriber.py`

#### [HIGH] [FIXED] Language parameter not validated

**Location:** `transcribe()` (line ~116)

**Description:** The `language` parameter was passed directly to `faster_whisper` without validation. While `faster_whisper` has its own validation, defense-in-depth requires input validation at the boundary.

**Fix applied:** Added validation that the language code must be alphabetic and at most 10 characters. Invalid values fall back to auto-detect.

#### [LOW] Model size already validated (POSITIVE)

**Location:** `load_model()` (line ~69-75)

**Description (POSITIVE):** The `model_size` parameter is validated against a whitelist of `AVAILABLE_MODELS` before being passed to `WhisperModel()`. This prevents arbitrary string injection into the model loading path.

---

### 6. `src/hotkey_manager.py`

#### [MEDIUM] Global keyboard listener captures all keystrokes

**Location:** `start()` (line ~134), `_on_press()` (line ~97)

**Description:** The `pynput.keyboard.Listener` with `suppress=False` receives all keyboard events system-wide. While the handler only processes keys matching the hotkey targets and discards all others, the listener itself has access to every keystroke. This is inherent to the global hotkey functionality.

**Recommendation:** This is an architectural necessity. Ensure that:
1. The `_on_press` / `_on_release` callbacks never log the actual key values for non-hotkey keys (currently correct -- they return early).
2. The listener is stopped during cleanup (currently correct).

#### [LOW] No maximum hotkey length validation

**Location:** `set_hotkey()` (line ~76)

**Description:** There is no upper limit on the number of keys in a hotkey combination. An extremely large hotkey list from a corrupted config could cause performance issues.

**Recommendation:** Add a maximum hotkey length check (e.g., max 5 keys).

---

### 7. `src/text_inserter.py`

#### [HIGH] [FIXED] Clipboard contents could leak to log files

**Location:** `insert_text()` (line ~23, 31), `_restore_clipboard()` (line ~45)

**Description:** All three `except` blocks used `exc_info=True` which logs the full stack trace. Since these operations involve clipboard contents (which may include passwords, secrets, etc.), the stack trace could include clipboard data in the log file.

**Fix applied:** Removed `exc_info=True` from all clipboard-related exception handlers to prevent sensitive clipboard contents from being written to the log file.

#### [HIGH] [FIXED] Clipboard restore race condition -- paste not yet consumed

**Location:** `insert_text()` (line ~29-30)

**Description:** The original code waited only 50ms after sending `Ctrl+V` before restoring the clipboard. This was insufficient time for many applications to consume the paste event, resulting in the original clipboard content being pasted instead of the transcription.

**Fix applied:** Increased the post-paste delay from 50ms to 150ms (`_PASTE_SETTLE_DELAY`), and renamed the constants for clarity. The pre-copy delay remains at 50ms.

#### [MEDIUM] Clipboard mechanism is inherently racy

**Location:** `insert_text()`

**Description:** The clipboard-based text insertion mechanism is inherently subject to race conditions with other applications that may read or write the clipboard between the copy and paste operations. There is no lock mechanism available across processes.

**Recommendation:** Consider using Windows-specific APIs (e.g., `SendInput` with `WM_CHAR` messages, or UI Automation `IValueProvider.SetValue`) for direct text insertion without clipboard involvement. This would eliminate the race condition entirely.

---

### 8. `src/overlay_widget.py`

No security issues identified. This is a pure UI widget.

**Positive findings:**
- Window flags include `WindowTransparentForInput` preventing the overlay from stealing focus or input.
- No file I/O or external data processing.
- The `set_position()` method validates position names against a whitelist.

---

### 9. `src/tray_icon.py`

No security issues identified. This is a pure UI component.

**Positive findings:**
- Status values are validated against `_STATE_COLORS` before use.
- The "About" dialog uses hardcoded HTML, not user-supplied content.

---

### 10. `src/settings_window.py`

#### [MEDIUM] Microphone test recording data is discarded (GOOD)

**Location:** `_stop_mic_test()` (line ~475)

**Description (POSITIVE):** The microphone test calls `stop_recording()` which returns the audio data, but the return value is discarded. Audio data from the test is never stored or processed.

#### [LOW] No input sanitization on audio device index

**Location:** `_populate_microphones()` (line ~372)

**Description:** Device indices from `sounddevice.query_devices()` are stored as combo box data and later passed to `AudioRecorder.set_device()`. While these indices come from the OS audio subsystem and not from user input directly, a corrupted device list could provide unexpected values.

**Recommendation:** Validate that the device ID is a non-negative integer before passing it to `set_device()`.

---

## Positive Security Practices Observed

1. **Audio data stays in memory.** Audio chunks are stored in a Python list and never written to disk. They are cleared immediately after transcription.

2. **Atomic config writes.** Config is written to a `.tmp` file first, then atomically renamed, preventing corruption from crashes during write.

3. **Thread-safe config access.** All config reads and writes are protected by a `threading.Lock`.

4. **Model size whitelisted.** The transcriber validates model names against a known list before passing to `WhisperModel`.

5. **No network communication.** The entire transcription pipeline is local (faster-whisper runs on-device). No audio data is sent to external services.

6. **Daemon listener thread.** The hotkey listener is a daemon thread, ensuring it does not prevent application exit.

7. **Transcription text not logged.** Only the character count is logged, not the actual transcription content.

8. **Overlay does not capture input.** The overlay widget uses `WindowTransparentForInput` to avoid interfering with user interaction.

---

## Dependency Risk Assessment

| Dependency       | Risk Level | Notes |
|-----------------|------------|-------|
| `faster-whisper` | LOW | Well-maintained, runs locally, no network access |
| `PyQt6`          | LOW | Mature framework, no known critical vulnerabilities |
| `sounddevice`    | LOW | Thin wrapper around PortAudio, OS-level audio access |
| `pynput`         | MEDIUM | Global keyboard listener requires elevated access on some platforms; inherent keylogging capability |
| `pyautogui`      | MEDIUM | Simulates keyboard/mouse input; could be abused if application is compromised |
| `pyperclip`      | MEDIUM | Reads/writes system clipboard; clipboard contents may be sensitive |
| `numpy`          | LOW | Numerical computation, no I/O |

---

## Recommendations Summary

### Immediate (addressed in this audit)

1. ~~Restrict config keys to known defaults~~ -- **FIXED**
2. ~~Prevent clipboard contents from leaking to logs~~ -- **FIXED**
3. ~~Increase paste settle delay to prevent clipboard restore race~~ -- **FIXED**
4. ~~Add language code validation in transcriber~~ -- **FIXED**
5. ~~Add log rotation to prevent unbounded disk usage~~ -- **FIXED**

### Short-term

6. Add type validation for config values (MEDIUM)
7. Protect `_recording` flag with lock in `AudioRecorder` (MEDIUM)
8. Consider Windows-native text insertion to avoid clipboard (MEDIUM)

### Long-term

9. Investigate UI Automation APIs for clipboard-free text insertion
10. Add config file integrity checks (e.g., checksum)
11. Consider memory-wiping for audio data buffers after use (for high-security environments)
12. Add maximum hotkey length validation

---

*End of Security Audit Report*
