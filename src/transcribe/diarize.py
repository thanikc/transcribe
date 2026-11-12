"""Speaker diarization adapter: sherpa-onnx with pyannote segmentation + 3D-Speaker embeddings."""

from __future__ import annotations

import shutil
import tarfile
import threading
import urllib.request
import wave
from pathlib import Path
from typing import Callable

from transcribe.domain import SpeakerTurn

_BASE = "https://github.com/k2-fsa/sherpa-onnx/releases/download"
SEGMENTATION_URL = f"{_BASE}/speaker-segmentation-models/sherpa-onnx-pyannote-segmentation-3-0.tar.bz2"
EMBEDDING_FILE = "3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx"
EMBEDDING_URL = f"{_BASE}/speaker-recongition-models/{EMBEDDING_FILE}"


def _download(url: str, dest: Path) -> None:
    part = dest.with_name(dest.name + ".part")
    urllib.request.urlretrieve(url, part)
    part.replace(dest)  # replace, not rename: Windows refuses to rename over a leftover file


_CHUNK_FRAMES = 1 << 20


def _read_mono(wav: Path, rate: int):
    """The WAV as float32 mono at `rate`. Reads in chunks: only the result is held whole in memory."""
    import numpy as np

    with wave.open(str(wav), "rb") as w:
        src_rate, channels, total = w.getframerate(), w.getnchannels(), w.getnframes()
        step = src_rate / rate
        out = np.empty(int(total / step), dtype="float32")
        written = 0
        offset = 0  # source index of chunk[0]
        carry = None  # last sample of the previous chunk, to interpolate across the boundary
        while written < len(out):
            raw = w.readframes(_CHUNK_FRAMES)
            if not raw:
                break
            chunk = np.frombuffer(raw, dtype="<i2").reshape(-1, channels).mean(axis=1, dtype="float32") / 32768
            if carry is not None:
                chunk, offset = np.concatenate(([carry], chunk)), offset - 1
            # Output samples whose source position falls inside this chunk.
            last = offset + len(chunk) - 1
            stop = min(len(out), int(last / step) + 1)
            positions = np.arange(written, stop) * step - offset
            out[written:stop] = np.interp(positions, np.arange(len(chunk)), chunk)
            written, offset, carry = stop, last + 1, chunk[-1]
    return out[:written]


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
                config = so.OfflineSpeakerDiarizationConfig(
                    segmentation=so.OfflineSpeakerSegmentationModelConfig(
                        pyannote=so.OfflineSpeakerSegmentationPyannoteModelConfig(model=str(segmentation))
                    ),
                    embedding=so.SpeakerEmbeddingExtractorConfig(model=str(embedding)),
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
