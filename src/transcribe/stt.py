"""Local speech-to-text adapter: faster-whisper."""

from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path
from typing import Callable

from transcribe.domain import Segment

log = logging.getLogger(__name__)

# The models the Windows installer offers, with their download size.
MODEL_SIZES = {"large-v3": "about 3 GB", "large-v3-turbo": "about 1.6 GB"}

# The files faster_whisper.download_model fetches.
_WHISPER_FILES = ["config.json", "preprocessor_config.json", "model.bin", "tokenizer.json", "vocabulary.*"]


class WhisperSpeechToText:
    def __init__(self, model: str) -> None:
        self._name = model
        self._model = None
        self._device = ""
        self._lock = threading.Lock()

    def download(self) -> None:
        """Fetch the model into the Hugging Face cache, where WhisperModel(name) finds it. Skips files it has."""
        if os.path.isdir(self._name):
            return
        import huggingface_hub
        from faster_whisper.utils import _MODELS

        # Not faster_whisper.download_model: it hides the progress bars, and this is a 3 GB download.
        # Same repo and files as download_model, so WhisperModel(name) finds them in the cache.
        repo_id = self._name if "/" in self._name else _MODELS[self._name]
        huggingface_hub.snapshot_download(repo_id, allow_patterns=_WHISPER_FILES)

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
