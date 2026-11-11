"""Local speech-to-text adapter: faster-whisper."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable

from transcribe.domain import Segment


class WhisperSpeechToText:
    def __init__(self, model: str) -> None:
        self._name = model
        self._model = None
        self._lock = threading.Lock()

    def _load(self):
        with self._lock:
            if self._model is None:
                import ctranslate2
                from faster_whisper import WhisperModel

                cuda = ctranslate2.get_cuda_device_count() > 0
                self._model = WhisperModel(
                    self._name,
                    device="cuda" if cuda else "cpu",
                    compute_type="float16" if cuda else "int8",
                )
            return self._model

    def transcribe(
        self, wav: Path, language: str | None, on_progress: Callable[[float], None]
    ) -> tuple[list[Segment], str]:
        # Lazy generator: the decoding happens while iterating, so progress follows it.
        segments, info = self._load().transcribe(str(wav), language=language, vad_filter=True)
        result = []
        for s in segments:
            result.append(Segment(s.start, s.end, s.text.strip()))
            if info.duration:
                on_progress(s.end / info.duration)
        on_progress(1.0)
        return result, info.language
