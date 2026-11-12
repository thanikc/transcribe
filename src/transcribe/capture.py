"""Audio capture adapter: soundcard mic and loopback streamed to mono MP3 files."""

from __future__ import annotations

import threading
from pathlib import Path

from transcribe.recorder import CaptureError

# What Whisper and the speaker models work at; WASAPI resamples to it (soundcard asks for AUTOCONVERTPCM).
SAMPLE_RATE = 16000
BLOCK_FRAMES = SAMPLE_RATE // 2
BIT_RATE = 64000


class Mp3Writer:
    """Encodes float32 mono blocks to an MP3 file as they arrive. Each MP3 frame stands alone, so a killed
    process leaves a playable file that lacks only the last half second or so."""

    def __init__(self, path: Path, rate: int = SAMPLE_RATE) -> None:
        import av

        self._rate = rate
        # Our own unbuffered file: given a path, FFmpeg keeps the output in memory until close, so a killed
        # process would leave an empty file. This way at most one 4 KB buffer (half a second) is lost.
        self._file = open(path, "wb", buffering=0)
        self._container = av.open(self._file, "w", format="mp3", buffer_size=4096)
        self._stream = self._container.add_stream("libmp3lame", rate=rate, layout="mono")
        self._stream.bit_rate = BIT_RATE

    def write(self, mono) -> None:
        import av
        import numpy as np

        samples = np.clip(np.asarray(mono, dtype="float32"), -1, 1).reshape(1, -1)
        frame = av.AudioFrame.from_ndarray(samples, format="fltp", layout="mono")
        frame.sample_rate = self._rate
        self._mux(frame)

    def close(self) -> None:
        try:
            self._mux(None)  # flush the encoder
        finally:
            try:
                self._container.close()
            finally:
                self._file.close()

    def _mux(self, frame) -> None:
        for packet in self._stream.encode(frame):
            self._container.mux(packet)

    def __enter__(self) -> Mp3Writer:
        return self

    def __exit__(self, *exc) -> None:
        self.close()


class _Session:
    def __init__(
        self, threads: list[threading.Thread], stop: threading.Event, errors: list[Exception], peaks: dict[str, float]
    ):
        self._threads, self._stop, self._errors, self._peaks = threads, stop, errors, peaks

    def levels(self) -> dict[str, float]:
        return dict(self._peaks)

    def stop(self) -> None:
        self._stop.set()
        for t in self._threads:
            t.join()
        if self._errors:
            raise self._errors[0]


def _open_device(track: str):
    import soundcard

    if track == "mic":
        return soundcard.default_microphone()
    speaker = soundcard.default_speaker()
    return soundcard.get_microphone(id=str(speaker.name), include_loopback=True)


def _record(
    track: str,
    path: Path,
    ready: threading.Event,
    stop: threading.Event,
    errors: list[Exception],
    peaks: dict[str, float],
) -> None:
    try:
        # Opened in the recording thread so WASAPI handles stay on the thread that uses them.
        with _open_device(track).recorder(samplerate=SAMPLE_RATE) as rec, Mp3Writer(path) as mp3:
            ready.set()
            while not stop.is_set():
                block = rec.record(numframes=BLOCK_FRAMES)
                mono = block.mean(axis=1) if block.ndim > 1 else block
                mp3.write(mono)
                peaks[track] = min(float(abs(mono).max(initial=0.0)), 1.0)
    except Exception as e:  # reported by start() if the device never opened, else by stop()
        errors.append(CaptureError(f"could not open the {track} device: {e}") if not ready.is_set() else e)
        ready.set()


class SoundcardCapture:
    def start(self, track_paths: dict[str, Path]) -> _Session:
        stop, errors = threading.Event(), []
        peaks = {t: 0.0 for t in track_paths}
        readies = {t: threading.Event() for t in track_paths}
        threads = [
            threading.Thread(target=_record, args=(t, p, readies[t], stop, errors, peaks), daemon=True)
            for t, p in track_paths.items()
        ]
        for t in threads:
            t.start()
        for ready in readies.values():
            ready.wait(timeout=10)
        if errors or not all(r.is_set() for r in readies.values()):
            stop.set()
            for t in threads:
                t.join(timeout=5)
            raise errors[0] if errors else CaptureError("audio device did not open within 10 seconds")
        return _Session(threads, stop, errors, peaks)
