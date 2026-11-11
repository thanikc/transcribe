"""Audio capture adapter: soundcard mic and loopback streamed to 16-bit mono WAV files."""

from __future__ import annotations

import threading
import wave
from pathlib import Path

from transcribe.recorder import CaptureError

SAMPLE_RATE = 48000
BLOCK_FRAMES = SAMPLE_RATE // 2


class _Session:
    def __init__(self, threads: list[threading.Thread], stop: threading.Event, errors: list[Exception]):
        self._threads, self._stop, self._errors = threads, stop, errors

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


def _record(track: str, path: Path, ready: threading.Event, stop: threading.Event, errors: list[Exception]) -> None:
    try:
        import numpy as np

        # Opened in the recording thread so WASAPI handles stay on the thread that uses them.
        with _open_device(track).recorder(samplerate=SAMPLE_RATE) as rec, wave.open(str(path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(SAMPLE_RATE)
            ready.set()
            while not stop.is_set():
                block = rec.record(numframes=BLOCK_FRAMES)
                mono = block.mean(axis=1) if block.ndim > 1 else block
                wav.writeframes((np.clip(mono, -1, 1) * 32767).astype("<i2").tobytes())
    except Exception as e:  # reported by start() if the device never opened, else by stop()
        errors.append(CaptureError(f"could not open the {track} device: {e}") if not ready.is_set() else e)
        ready.set()


class SoundcardCapture:
    def start(self, track_paths: dict[str, Path]) -> _Session:
        stop, errors = threading.Event(), []
        readies = {t: threading.Event() for t in track_paths}
        threads = [
            threading.Thread(target=_record, args=(t, p, readies[t], stop, errors), daemon=True)
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
        return _Session(threads, stop, errors)
