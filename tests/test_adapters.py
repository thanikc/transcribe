import subprocess
import sys


def test_importing_adapters_does_not_load_heavy_libraries():
    code = (
        "import sys, transcribe.capture, transcribe.stt, transcribe.diarize;"
        "bad = [m for m in ('soundcard', 'faster_whisper', 'sherpa_onnx', 'av') if m in sys.modules];"
        "sys.exit(','.join(bad) or 0)"
    )
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr


def test_capture_reports_a_failed_library_import_instead_of_timing_out(monkeypatch, tmp_path):
    import pytest

    from transcribe.capture import SoundcardCapture
    from transcribe.recorder import CaptureError

    monkeypatch.setitem(sys.modules, "numpy", None)  # import numpy -> ImportError
    with pytest.raises(CaptureError, match="could not open the mic device"):
        SoundcardCapture().start({"mic": tmp_path / "mic.wav"})


def test_whisper_reports_how_far_through_the_audio_it_is(tmp_path):
    from types import SimpleNamespace

    from transcribe.domain import Segment
    from transcribe.stt import WhisperSpeechToText

    class Model:
        def transcribe(self, wav, language, vad_filter):
            segs = (SimpleNamespace(start=s, end=s + 5, text=f" part {s} ") for s in (0, 5))
            return segs, SimpleNamespace(language="th", duration=20.0)

    stt = WhisperSpeechToText("tiny")
    stt._model = Model()
    seen = []
    segments, language = stt.transcribe(tmp_path / "mic.wav", None, seen.append)
    assert segments == [Segment(0, 5, "part 0"), Segment(5, 10, "part 5")]
    assert language == "th"
    assert seen == [0.25, 0.5, 1.0]


def test_diarizer_reports_processed_chunks(tmp_path):
    import wave
    from types import SimpleNamespace

    from transcribe.diarize import SherpaDiarizer

    wav = tmp_path / "mic.wav"
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * 1600)

    class Engine:
        sample_rate = 16000

        def process(self, samples, callback):
            assert callback(1, 4) == 0 and callback(4, 4) == 0
            return SimpleNamespace(sort_by_start_time=lambda: [SimpleNamespace(start=0.0, end=0.1, speaker=0)])

    diarizer = SherpaDiarizer(tmp_path)
    diarizer._engine = Engine()
    seen = []
    turns = diarizer.diarize(wav, seen.append)
    assert [t.speaker for t in turns] == ["spk0"]
    assert seen == [0.25, 1.0]
