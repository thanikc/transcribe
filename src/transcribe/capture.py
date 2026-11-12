"""Audio capture adapter: soundcard mic and loopback streamed to mono MP3 files; imported files converted to one."""

from __future__ import annotations

import sys
import threading
from pathlib import Path

from transcribe.domain import AudioDevice
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


class AudioFileConverter:
    """Any audio file FFmpeg reads (m4a, mp3, wav, ogg, the sound of a video…) as a track's 16 kHz mono MP3."""

    def convert(self, source: Path, dest: Path) -> float:
        import av

        # Planar, channels kept: averaged here, since FFmpeg's downmix adds them at -3 dB and can clip.
        resampler = av.AudioResampler(format="fltp", rate=SAMPLE_RATE)
        samples = 0
        try:
            container = av.open(str(source))
        except av.error.FFmpegError as e:
            raise ValueError(e.strerror) from e  # its str() names the upload's temp file
        with container, Mp3Writer(dest) as mp3:
            if not container.streams.audio:
                raise ValueError("it has no sound")

            def write(frames) -> None:
                nonlocal samples
                for frame in frames:
                    mono = frame.to_ndarray().mean(axis=0, dtype="float32")
                    mp3.write(mono)
                    samples += len(mono)

            for frame in container.decode(audio=0):
                write(resampler.resample(frame))
            write(resampler.resample(None))
        if not samples:
            raise ValueError("it has no sound")
        return samples / SAMPLE_RATE


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


def _join_com() -> None:
    """Joins the calling thread to COM's multithreaded apartment. soundcard initialises COM only on the thread
    that imports it, so a device listed on a web worker thread, or opened in a recording thread, fails with
    CO_E_NOTINITIALIZED (0x800401f0) unless its own thread has joined. Joining twice is harmless; a thread
    already in a single-threaded apartment (RPC_E_CHANGED_MODE) can use COM as it is."""
    if sys.platform == "win32":
        import ctypes

        ctypes.windll.ole32.CoInitializeEx(None, 0)  # COINIT_MULTITHREADED; left joined for the thread's life


def _open_device(track: str, device_id: str | None):
    _join_com()
    import soundcard

    if track == "mic":
        return soundcard.get_microphone(id=device_id) if device_id else soundcard.default_microphone()
    # The system audio is what a speaker plays, recorded through its loopback, which has the speaker's id.
    return soundcard.get_microphone(id=device_id or str(soundcard.default_speaker().name), include_loopback=True)


def _record(
    track: str,
    device_id: str | None,
    path: Path,
    ready: threading.Event,
    stop: threading.Event,
    errors: list[Exception],
    peaks: dict[str, float],
) -> None:
    try:
        # Opened in the recording thread so WASAPI handles stay on the thread that uses them.
        with _open_device(track, device_id).recorder(samplerate=SAMPLE_RATE) as rec, Mp3Writer(path) as mp3:
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
    def devices(self) -> dict[str, list[AudioDevice]]:
        try:
            _join_com()
            import soundcard

            mic, speaker = soundcard.default_microphone().id, soundcard.default_speaker().id
            return {
                "mic": [AudioDevice(str(m.id), m.name, m.id == mic) for m in soundcard.all_microphones()],
                "system": [AudioDevice(str(s.id), s.name, s.id == speaker) for s in soundcard.all_speakers()],
            }
        except Exception as e:
            raise CaptureError(f"could not list the audio devices: {e}") from e

    def start(self, track_paths: dict[str, Path], sources: dict[str, str]) -> _Session:
        stop, errors = threading.Event(), []
        peaks = {t: 0.0 for t in track_paths}
        readies = {t: threading.Event() for t in track_paths}
        threads = [
            threading.Thread(target=_record, args=(t, sources.get(t), p, readies[t], stop, errors, peaks), daemon=True)
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
