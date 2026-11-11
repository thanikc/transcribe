"""Local speech-to-text adapter: faster-whisper."""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Callable

from transcribe.domain import Segment

log = logging.getLogger(__name__)


class WhisperSpeechToText:
    def __init__(self, model: str) -> None:
        self._name = model
        self._model = None
        self._device = ""
        self._lock = threading.Lock()

    def _load(self):
        with self._lock:
            if self._model is None:
                import ctranslate2
                from faster_whisper import WhisperModel

                cuda = ctranslate2.get_cuda_device_count() > 0
                device, compute_type = ("cuda", "float16") if cuda else ("cpu", "int8")
                self._model = WhisperModel(self._name, device=device, compute_type=compute_type)
                self._device = f"{device} ({compute_type})"
            return self._model

    def transcribe(
        self, wav: Path, language: str | None, on_progress: Callable[[float], None]
    ) -> tuple[list[Segment], str]:
        started = time.monotonic()
        # Lazy generator: the decoding happens while iterating, so progress follows it.
        segments, info = self._load().transcribe(str(wav), language=language, vad_filter=True)
        result = []
        for s in segments:
            result.append(Segment(s.start, s.end, s.text.strip()))
            if info.duration:
                on_progress(s.end / info.duration)
        on_progress(1.0)
        minutes, seconds = divmod(round(info.duration or 0), 60)
        log.info(
            "transcribed %s (%dm%02ds of audio) in %.1fs on %s",
            wav.name, minutes, seconds, time.monotonic() - started, self._device,
        )
        return result, info.language
