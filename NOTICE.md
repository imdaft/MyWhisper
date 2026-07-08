# Third-Party Notices

MyWhisper is licensed under GPL-3.0-or-later (see [LICENSE](LICENSE)) because it
links PyQt6, which is GPL-licensed. It bundles or depends on the following
third-party components:

| Component        | License        | Purpose                              |
|-------------------|----------------|---------------------------------------|
| PyQt6             | GPL-3.0 (or commercial) | System tray, overlay, settings UI |
| faster-whisper    | MIT            | Speech-to-text (CTranslate2 backend)  |
| CTranslate2       | MIT            | Whisper model inference engine        |
| sounddevice       | MIT            | Microphone capture (PortAudio)         |
| pynput            | LGPL-3.0       | Global hotkey listener                 |
| pyperclip         | BSD-3-Clause   | Clipboard access                       |
| numpy             | BSD-3-Clause   | Audio buffer processing                |
| onnxruntime       | MIT            | Voice activity detection (VAD)         |

None of these components' license texts are modified by this project; they
retain their own copyright notices in their respective source distributions.
