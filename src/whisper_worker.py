"""Standalone Whisper worker process.

Communicates with the parent via stdin/stdout using JSON lines.
Runs faster-whisper in a process completely separate from PyQt6.

Protocol:
  -> {"cmd": "load", "model": "base", "device": "cpu", "compute": "int8"}
  <- {"status": "ok"} | {"status": "error", "msg": "..."}

  -> {"cmd": "transcribe", "audio_path": "/tmp/audio.npy", "language": "auto"}
  <- {"status": "ok", "text": "...", "lang": "en", "prob": 0.95}
  <- {"status": "error", "msg": "..."}

  -> {"cmd": "quit"}
  (process exits)
"""
from __future__ import annotations

import json
import os
import sys


def main() -> None:
    # Force UTF-8 on the pipe in both directions. Without this the worker uses
    # the Windows locale (e.g. cp1251), which corrupts Cyrillic transcriptions
    # and breaks the JSON protocol the parent reads as UTF-8.
    for stream in (sys.stdin, sys.stdout):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

    model = None

    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue

        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            _respond({"status": "error", "msg": "Invalid JSON"})
            continue

        cmd = msg.get("cmd")

        if cmd == "quit":
            break

        elif cmd == "load":
            try:
                import numpy as np  # noqa: F401
                from faster_whisper import WhisperModel

                model_size = msg["model"]
                device = msg.get("device", "cpu")
                compute_type = msg.get("compute", "int8")
                model = WhisperModel(model_size, device=device, compute_type=compute_type)
                _respond({"status": "ok"})
            except Exception as exc:
                model = None
                _respond({"status": "error", "msg": str(exc)})

        elif cmd == "transcribe":
            if model is None:
                _respond({"status": "error", "msg": "No model loaded"})
                continue
            audio_path = msg.get("audio_path")
            try:
                import numpy as np

                audio = np.load(audio_path).astype(np.float32)

                language = msg.get("language")
                lang = language if language and language != "auto" else None
                if lang is not None and (len(lang) > 10 or not lang.isalpha()):
                    lang = None

                # User dictionary: bias recognition toward these words/phrases.
                hotwords = (msg.get("hotwords") or "").strip()[:2000] or None

                # Try with VAD filter; fall back if onnxruntime is missing
                try:
                    segments, info = model.transcribe(
                        audio, language=lang, beam_size=5, vad_filter=True,
                        hotwords=hotwords,
                    )
                except Exception:
                    segments, info = model.transcribe(
                        audio, language=lang, beam_size=5, vad_filter=False,
                        hotwords=hotwords,
                    )
                text = "".join(seg.text for seg in segments).strip()
                _respond({
                    "status": "ok",
                    "text": text,
                    "lang": info.language,
                    "prob": round(info.language_probability, 4),
                })
            except Exception as exc:
                _respond({"status": "error", "msg": str(exc)})
            finally:
                # Always remove the temp audio file, even if np.load failed,
                # so raw audio never lingers on disk.
                if audio_path and os.path.exists(audio_path):
                    try:
                        os.unlink(audio_path)
                    except OSError:
                        pass

        else:
            _respond({"status": "error", "msg": f"Unknown command: {cmd}"})


def _respond(data: dict) -> None:
    sys.stdout.write(json.dumps(data, ensure_ascii=False) + "\n")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
