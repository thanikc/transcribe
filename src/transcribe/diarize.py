"""Speaker diarization adapter: sherpa-onnx with pyannote segmentation + 3D-Speaker embeddings."""

from __future__ import annotations

import tarfile
import threading
import urllib.request
import wave
from pathlib import Path

from transcribe.domain import SpeakerTurn

_BASE = "https://github.com/k2-fsa/sherpa-onnx/releases/download"
SEGMENTATION_URL = f"{_BASE}/speaker-segmentation-models/sherpa-onnx-pyannote-segmentation-3-0.tar.bz2"
EMBEDDING_FILE = "3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx"
EMBEDDING_URL = f"{_BASE}/speaker-recongition-models/{EMBEDDING_FILE}"


def _download(url: str, dest: Path) -> None:
    part = dest.with_name(dest.name + ".part")
    urllib.request.urlretrieve(url, part)
    part.rename(dest)


def _read_mono(wav: Path, rate: int):
    import numpy as np

    with wave.open(str(wav), "rb") as w:
        src_rate, channels = w.getframerate(), w.getnchannels()
        data = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2")
    mono = data.reshape(-1, channels).mean(axis=1).astype("float32") / 32768
    if src_rate != rate:
        n = int(len(mono) * rate / src_rate)
        mono = np.interp(np.linspace(0, len(mono) - 1, n), np.arange(len(mono)), mono).astype("float32")
    return mono


class SherpaDiarizer:
    def __init__(self, models_dir: Path) -> None:
        self._dir = models_dir
        self._engine = None
        self._lock = threading.Lock()

    def _load(self):
        with self._lock:
            if self._engine is None:
                import sherpa_onnx as so

                self._dir.mkdir(parents=True, exist_ok=True)
                segmentation = self._dir / "sherpa-onnx-pyannote-segmentation-3-0" / "model.onnx"
                if not segmentation.exists():
                    archive = self._dir / "segmentation.tar.bz2"
                    _download(SEGMENTATION_URL, archive)
                    with tarfile.open(archive) as tar:
                        tar.extractall(self._dir, filter="data")
                    archive.unlink()
                embedding = self._dir / EMBEDDING_FILE
                if not embedding.exists():
                    _download(EMBEDDING_URL, embedding)
                config = so.OfflineSpeakerDiarizationConfig(
                    segmentation=so.OfflineSpeakerSegmentationModelConfig(
                        pyannote=so.OfflineSpeakerSegmentationPyannoteModelConfig(model=str(segmentation))
                    ),
                    embedding=so.SpeakerEmbeddingExtractorConfig(model=str(embedding)),
                    clustering=so.FastClusteringConfig(num_clusters=-1, threshold=0.5),
                )
                self._engine = so.OfflineSpeakerDiarization(config)
            return self._engine

    def diarize(self, wav: Path) -> list[SpeakerTurn]:
        engine = self._load()
        result = engine.process(_read_mono(wav, engine.sample_rate)).sort_by_start_time()
        return [SpeakerTurn(r.start, r.end, f"spk{r.speaker}") for r in result]
