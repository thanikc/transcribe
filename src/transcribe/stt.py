"""Local speech-to-text adapter: faster-whisper."""

from __future__ import annotations

import gc
import logging
import os
import threading
import time
from pathlib import Path
from typing import Callable

from transcribe.domain import Segment
from transcribe.recorder import OutOfMemory

log = logging.getLogger(__name__)

# The files faster_whisper.download_model fetches.
_WHISPER_FILES = ["config.json", "preprocessor_config.json", "model.bin", "tokenizer.json", "vocabulary.*"]

# How CTranslate2 (Intel MKL), the C++ runtime and NumPy word a failed allocation.
_OUT_OF_MEMORY = ("failed to allocate memory", "bad allocation", "bad_alloc", "unable to allocate", "out of memory")


def _is_out_of_memory(error: Exception) -> bool:
    return isinstance(error, MemoryError) or any(sign in str(error).lower() for sign in _OUT_OF_MEMORY)


def _repo_id(model: str) -> str:
    from faster_whisper.utils import _MODELS

    return model if "/" in model else _MODELS[model]


class WhisperSpeechToText:
    """Keeps one model loaded at a time: asking for another one drops it first."""

    def __init__(self) -> None:
        self._model = None
        self._loaded = ""
        self._device = ""
        self._lock = threading.Lock()

    def download(self, model: str) -> None:
        """Fetch the model into the Hugging Face cache, where WhisperModel(name) finds it. Skips files it has."""
        if os.path.isdir(model):
            return
        import huggingface_hub

        # Not faster_whisper.download_model: it hides the progress bars, and this is a 3 GB download.
        # Same repo and files as download_model, so WhisperModel(name) finds them in the cache.
        huggingface_hub.snapshot_download(_repo_id(model), allow_patterns=_WHISPER_FILES)

    def has_model(self, model: str) -> bool:
        if os.path.isdir(model):
            return True
        try:
            import huggingface_hub

            return isinstance(huggingface_hub.try_to_load_from_cache(_repo_id(model), "model.bin"), str)
        except Exception:  # unknown name, unreadable cache: it would have to be downloaded
            return False

    def _unload(self) -> None:
        self._model, self._loaded = None, ""
        gc.collect()  # the weights are freed now, not whenever the collector gets to them

    def _load(self, model: str):
        with self._lock:
            if self._loaded != model:
                self._unload()
                import ctranslate2
                from faster_whisper import WhisperModel

                cuda = ctranslate2.get_cuda_device_count() > 0
                device, compute_type = ("cuda", "float16") if cuda else ("cpu", "int8")
                self._model = WhisperModel(model, device=device, compute_type=compute_type)
                self._loaded = model
                self._device = f"{device} ({compute_type})"
            return self._model

    def transcribe(
        self, wav: Path, language: str | None, on_progress: Callable[[float], None], model: str
    ) -> tuple[list[Segment], str]:
        try:
            return self._transcribe(wav, language, on_progress, model)
        except Exception as e:
            if not _is_out_of_memory(e):
                raise
            with self._lock:
                self._unload()  # give the memory back, so the next try starts clean
            raise OutOfMemory(model) from e

    def _transcribe(
        self, wav: Path, language: str | None, on_progress: Callable[[float], None], model: str
    ) -> tuple[list[Segment], str]:
        started = time.monotonic()
        # Lazy generator: the decoding happens while iterating, so progress follows it.
        segments, info = self._load(model).transcribe(str(wav), language=language, vad_filter=True)
        result = []
        for s in segments:
            result.append(Segment(s.start, s.end, s.text.strip()))
            if info.duration:
                on_progress(s.end / info.duration)
        on_progress(1.0)
        minutes, seconds = divmod(round(info.duration or 0), 60)
        log.info(
            "transcribed %s (%dm%02ds of audio) with %s in %.1fs on %s",
            wav.name, minutes, seconds, model, time.monotonic() - started, self._device,
        )
        return result, info.language
