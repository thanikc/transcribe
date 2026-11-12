"""Speaker diarization adapter: sherpa-onnx with pyannote segmentation + 3D-Speaker embeddings."""

from __future__ import annotations

import os
import shutil
import tarfile
import threading
import urllib.request
from pathlib import Path
from typing import Callable

from transcribe.domain import SpeakerTurn

_BASE = "https://github.com/k2-fsa/sherpa-onnx/releases/download"
SEGMENTATION_URL = f"{_BASE}/speaker-segmentation-models/sherpa-onnx-pyannote-segmentation-3-0.tar.bz2"
EMBEDDING_FILE = "3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx"
EMBEDDING_URL = f"{_BASE}/speaker-recongition-models/{EMBEDDING_FILE}"
# sherpa-onnx runs each model on one thread unless told otherwise. Four is what Whisper uses,
# so speaker detection asks no more of the computer than transcribing did.
MAX_THREADS = 4


def _download(url: str, dest: Path) -> None:
    part = dest.with_name(dest.name + ".part")
    urllib.request.urlretrieve(url, part)
    part.replace(dest)  # replace, not rename: Windows refuses to rename over a leftover file


def _read_mono(audio: Path, rate: int):
    """The track (MP3, or WAV from older meetings) as float32 mono at `rate`, decoded piece by piece."""
    import av
    import numpy as np

    # Planar, channels kept: averaged here, since FFmpeg's downmix adds them at -3 dB and can clip.
    resampler = av.AudioResampler(format="fltp", rate=rate)
    pieces = []

    def keep(frames) -> None:
        pieces.extend(f.to_ndarray().mean(axis=0, dtype="float32") for f in frames)

    with av.open(str(audio)) as container:
        for frame in container.decode(audio=0):
            keep(resampler.resample(frame))
    keep(resampler.resample(None))
    return np.concatenate(pieces) if pieces else np.zeros(0, dtype="float32")


class SherpaDiarizer:
    def __init__(self, models_dir: Path) -> None:
        self._dir = models_dir
        self._engine = None
        self._lock = threading.Lock()

    def ensure_models(self) -> tuple[Path, Path]:
        """Download the segmentation and embedding models unless present. Returns their paths."""
        self._dir.mkdir(parents=True, exist_ok=True)
        segmentation = self._dir / "sherpa-onnx-pyannote-segmentation-3-0" / "model.onnx"
        if not segmentation.exists():
            archive = self._dir / "segmentation.tar.bz2"
            _download(SEGMENTATION_URL, archive)
            # Unpack beside the target and move it in whole, so an interrupted unpack leaves no partial model.
            unpacking = self._dir / ".unpacking"
            shutil.rmtree(unpacking, ignore_errors=True)
            with tarfile.open(archive) as tar:
                tar.extractall(unpacking, filter="data")
            shutil.rmtree(segmentation.parent, ignore_errors=True)
            (unpacking / segmentation.parent.name).rename(segmentation.parent)
            unpacking.rmdir()
            archive.unlink()
        embedding = self._dir / EMBEDDING_FILE
        if not embedding.exists():
            _download(EMBEDDING_URL, embedding)
        return segmentation, embedding

    def _load(self):
        with self._lock:
            if self._engine is None:
                import sherpa_onnx as so

                segmentation, embedding = self.ensure_models()
                threads = min(MAX_THREADS, os.cpu_count() or 1)
                config = so.OfflineSpeakerDiarizationConfig(
                    segmentation=so.OfflineSpeakerSegmentationModelConfig(
                        pyannote=so.OfflineSpeakerSegmentationPyannoteModelConfig(model=str(segmentation)),
                        num_threads=threads,
                    ),
                    embedding=so.SpeakerEmbeddingExtractorConfig(model=str(embedding), num_threads=threads),
                    clustering=so.FastClusteringConfig(num_clusters=-1, threshold=0.5),
                )
                self._engine = so.OfflineSpeakerDiarization(config)
            return self._engine

    def diarize(self, wav: Path, on_progress: Callable[[float], None]) -> list[SpeakerTurn]:
        engine = self._load()

        def callback(done: int, total: int) -> int:
            on_progress(done / total if total else 1.0)
            return 0  # non-zero would ask sherpa-onnx to stop

        result = engine.process(_read_mono(wav, engine.sample_rate), callback=callback).sort_by_start_time()
        return [SpeakerTurn(r.start, r.end, f"spk{r.speaker}") for r in result]
