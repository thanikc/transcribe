import subprocess
import sys

import pytest


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
        def transcribe(self, wav, language, vad_filter, word_timestamps, hotwords):
            assert word_timestamps
            segs = (SimpleNamespace(start=s, end=s + 5, text=f" part {s} ", words=None) for s in (0, 5))
            return segs, SimpleNamespace(language="th", duration=20.0)

    stt = WhisperSpeechToText()
    stt._model, stt._loaded = Model(), "tiny"
    seen = []
    segments, language = stt.transcribe(tmp_path / "mic.wav", None, seen.append, "tiny", [])
    assert segments == [Segment(0, 5, "part 0"), Segment(5, 10, "part 5")]
    assert language == "th"
    assert seen == [0.25, 0.5, 1.0]


def test_whisper_logs_how_long_it_took_and_on_which_device(tmp_path, caplog):
    import logging
    from types import SimpleNamespace

    from transcribe.stt import WhisperSpeechToText

    class Model:
        def transcribe(self, wav, language, vad_filter, word_timestamps, hotwords):
            return iter(()), SimpleNamespace(language="en", duration=125.0)

    stt = WhisperSpeechToText()
    stt._model, stt._loaded, stt._device = Model(), "tiny", "cuda (float16)"
    with caplog.at_level(logging.INFO, logger="transcribe.stt"):
        stt.transcribe(tmp_path / "mic.wav", None, lambda f: None, "tiny", [])
    [message] = caplog.messages
    assert message.startswith("transcribed mic.wav (2m05s of audio) with tiny in ")
    assert message.endswith("s on cuda (float16)")


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


def test_whisper_download_fetches_the_named_model_once_into_the_shared_cache(monkeypatch, tmp_path):
    from types import ModuleType

    from transcribe.stt import WhisperSpeechToText

    fetched = []
    hub = ModuleType("huggingface_hub")
    hub.snapshot_download = lambda repo_id, allow_patterns: fetched.append((repo_id, allow_patterns))
    monkeypatch.setitem(sys.modules, "huggingface_hub", hub)
    stt = WhisperSpeechToText()
    stt.download("large-v3")
    stt.download("me/my-whisper")
    stt.download(str(tmp_path))  # a local model dir needs no download
    files = ["config.json", "preprocessor_config.json", "model.bin", "tokenizer.json", "vocabulary.*"]
    assert fetched == [("Systran/faster-whisper-large-v3", files), ("me/my-whisper", files)]


def test_whisper_download_matches_what_faster_whisper_loads():
    import inspect

    from faster_whisper import utils

    from transcribe import stt

    # If faster-whisper changes which files it fetches, the installer's download would miss some.
    for pattern in stt._WHISPER_FILES:
        assert f'"{pattern}"' in inspect.getsource(utils.download_model)


def test_speaker_models_download_once_and_unpack(monkeypatch, tmp_path):
    import io
    import tarfile

    from transcribe import diarize

    def fake_download(url, dest):
        if url == diarize.SEGMENTATION_URL:
            with tarfile.open(dest, "w:bz2") as tar:
                info = tarfile.TarInfo("sherpa-onnx-pyannote-segmentation-3-0/model.onnx")
                info.size = 4
                tar.addfile(info, io.BytesIO(b"onnx"))
        else:
            dest.write_bytes(b"emb")

    monkeypatch.setattr(diarize, "_download", fake_download)
    segmentation, embedding = diarize.SherpaDiarizer(tmp_path / ".models").ensure_models()
    assert segmentation.read_bytes() == b"onnx" and embedding.read_bytes() == b"emb"
    assert sorted(p.name for p in (tmp_path / ".models").iterdir()) == sorted(
        ["sherpa-onnx-pyannote-segmentation-3-0", diarize.EMBEDDING_FILE]
    )

    def no_network(url, dest):
        raise AssertionError("downloaded again")

    monkeypatch.setattr(diarize, "_download", no_network)
    assert diarize.SherpaDiarizer(tmp_path / ".models").ensure_models() == (segmentation, embedding)


def test_the_installers_model_choices_are_models_faster_whisper_can_download():
    from pathlib import Path

    from faster_whisper.utils import _MODELS

    from transcribe.domain import FALLBACK_MODELS, MODELS

    installer = (Path(__file__).parent.parent / "installer" / "transcribe.iss").read_text(encoding="utf-8")
    assert set(MODELS) == {"large-v3", "large-v3-turbo"}
    assert set(FALLBACK_MODELS.values()) <= set(MODELS)
    for name in MODELS:
        assert name in _MODELS
        assert f"'{name}'" in installer


def _write_wav(path, rate: int, channels: int, samples) -> None:
    import wave

    import numpy as np

    with wave.open(str(path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(np.asarray(samples, dtype="<i2").tobytes())


def _tone(seconds: float, rate: int = 16000, hz: float = 440.0, level: float = 0.3):
    import numpy as np

    t = np.arange(int(seconds * rate)) / rate
    return (level * np.sin(2 * np.pi * hz * t)).astype("float32")


def test_mp3_writer_encodes_blocks_at_64_kbps_and_reads_back_at_16k(tmp_path):
    import numpy as np

    from transcribe.capture import Mp3Writer
    from transcribe.diarize import _read_mono

    path = tmp_path / "mic.mp3"
    tone = _tone(10)
    with Mp3Writer(path) as mp3:
        for i in range(0, len(tone), 8000):  # half-second blocks, as capture writes them
            mp3.write(tone[i : i + 8000])
    assert path.read_bytes()[:3] == b"ID3" or path.read_bytes()[0] == 0xFF
    assert 70_000 < path.stat().st_size < 90_000  # 10 s at 64 kbps = 80 kB
    back = _read_mono(path, 16000)
    assert back.dtype == np.float32
    assert abs(len(back) - len(tone)) < 1600
    assert np.sqrt(np.mean(back**2)) == pytest.approx(0.3 / np.sqrt(2), rel=0.05)


def test_mp3_writer_clips_out_of_range_samples(tmp_path):
    import numpy as np

    from transcribe.capture import Mp3Writer
    from transcribe.diarize import _read_mono

    with Mp3Writer(tmp_path / "loud.mp3") as mp3:
        mp3.write(_tone(1, level=5.0))
    assert np.abs(_read_mono(tmp_path / "loud.mp3", 16000)).max() < 1.2


def test_read_mono_still_reads_wav_tracks_of_older_meetings(tmp_path):
    import numpy as np

    from transcribe.diarize import _read_mono

    stereo = np.column_stack([np.full(48000, 1000), np.full(48000, 3000)]).ravel()
    _write_wav(tmp_path / "s.wav", 48000, 2, stereo)
    mono = _read_mono(tmp_path / "s.wav", 16000)
    assert abs(len(mono) - 16000) < 64
    np.testing.assert_allclose(mono[100:-100], 2000 / 32768, atol=1e-4)


def test_mp3_of_a_killed_recording_keeps_almost_all_its_audio(tmp_path):
    from transcribe.diarize import _read_mono

    path = tmp_path / "killed.mp3"
    code = (
        "import os, numpy as np\n"
        "from transcribe.capture import Mp3Writer\n"
        f"m = Mp3Writer({str(path)!r})\n"
        "for _ in range(20): m.write((np.sin(np.arange(8000) / 3) * 0.3).astype('float32'))\n"
        "os._exit(0)\n"  # no close(): what a crash or a killed service leaves
    )
    subprocess.run([sys.executable, "-c", code], check=True)
    assert len(_read_mono(path, 16000)) / 16000 > 9.0  # of 10 s


def test_whisper_out_of_memory_is_reported_as_such_and_drops_the_model(tmp_path) -> None:
    import pytest

    from transcribe.recorder import OutOfMemory
    from transcribe.stt import WhisperSpeechToText

    class Model:
        def transcribe(self, path, language, vad_filter, word_timestamps, hotwords):
            raise RuntimeError("mkl_malloc: failed to allocate memory")

    stt = WhisperSpeechToText()
    stt._model, stt._loaded = Model(), "large-v3"
    with pytest.raises(OutOfMemory, match="not enough free memory for the large-v3 speech model"):
        stt.transcribe(tmp_path / "mic.mp3", "th", lambda fraction: None, "large-v3", [])
    assert stt._model is None and stt._loaded == ""


def test_whisper_other_errors_pass_through(tmp_path) -> None:
    import pytest

    from transcribe.stt import WhisperSpeechToText

    class Model:
        def transcribe(self, path, language, vad_filter, word_timestamps, hotwords):
            raise RuntimeError("boom")

    stt = WhisperSpeechToText()
    stt._model, stt._loaded = Model(), "large-v3"
    with pytest.raises(RuntimeError, match="^boom$"):
        stt.transcribe(tmp_path / "mic.mp3", "th", lambda fraction: None, "large-v3", [])
    assert stt._model is not None


def test_whisper_swaps_the_loaded_model_when_another_is_asked_for(monkeypatch, tmp_path) -> None:
    from types import ModuleType, SimpleNamespace

    from transcribe.stt import WhisperSpeechToText

    loaded = []

    class Model:
        def __init__(self, name, device, compute_type):
            loaded.append((name, device, compute_type))

        def transcribe(self, path, language, vad_filter, word_timestamps, hotwords):
            return iter(()), SimpleNamespace(language="en", duration=1.0)

    whisper = ModuleType("faster_whisper")
    whisper.WhisperModel = Model
    ct2 = ModuleType("ctranslate2")
    ct2.get_cuda_device_count = lambda: 0
    monkeypatch.setitem(sys.modules, "faster_whisper", whisper)
    monkeypatch.setitem(sys.modules, "ctranslate2", ct2)
    stt = WhisperSpeechToText()
    for name in ("large-v3", "large-v3", "large-v3-turbo"):
        stt.transcribe(tmp_path / "mic.mp3", None, lambda fraction: None, name, [])
    assert loaded == [("large-v3", "cpu", "int8"), ("large-v3-turbo", "cpu", "int8")]


def test_whisper_knows_which_models_are_already_downloaded(monkeypatch, tmp_path) -> None:
    from types import ModuleType

    from transcribe.stt import WhisperSpeechToText

    hub = ModuleType("huggingface_hub")
    cached = {"Systran/faster-whisper-large-v3": "/cache/model.bin"}
    hub.try_to_load_from_cache = lambda repo_id, filename: cached.get(repo_id)
    monkeypatch.setitem(sys.modules, "huggingface_hub", hub)
    stt = WhisperSpeechToText()
    assert stt.has_model("large-v3")
    assert not stt.has_model("large-v3-turbo")
    assert not stt.has_model("no-such-model")
    assert stt.has_model(str(tmp_path))  # a local model dir


@pytest.mark.parametrize("cores, threads", [(1, 1), (2, 2), (16, 4), (None, 1)])
def test_diarizer_runs_its_models_on_up_to_four_threads(monkeypatch, tmp_path, cores, threads) -> None:
    from types import ModuleType, SimpleNamespace

    from transcribe import diarize

    so = ModuleType("sherpa_onnx")
    for name in (
        "OfflineSpeakerDiarizationConfig",
        "OfflineSpeakerSegmentationModelConfig",
        "OfflineSpeakerSegmentationPyannoteModelConfig",
        "SpeakerEmbeddingExtractorConfig",
        "FastClusteringConfig",
    ):
        setattr(so, name, lambda *args, **kwargs: SimpleNamespace(**kwargs))
    so.OfflineSpeakerDiarization = lambda config: config
    monkeypatch.setitem(sys.modules, "sherpa_onnx", so)
    monkeypatch.setattr(diarize.os, "cpu_count", lambda: cores)
    diarizer = diarize.SherpaDiarizer(tmp_path)
    monkeypatch.setattr(diarizer, "ensure_models", lambda: (tmp_path / "seg.onnx", tmp_path / "emb.onnx"))
    config = diarizer._load()
    assert (config.segmentation.num_threads, config.embedding.num_threads) == (threads, threads)


def test_whisper_passes_word_times_on(tmp_path):
    from types import SimpleNamespace

    from transcribe.domain import Word
    from transcribe.stt import WhisperSpeechToText

    class Model:
        def transcribe(self, wav, language, vad_filter, word_timestamps, hotwords):
            words = [SimpleNamespace(start=0.0, end=0.4, word=" Hi"), SimpleNamespace(start=0.4, end=1.0, word=" all")]
            return iter([SimpleNamespace(start=0.0, end=1.0, text=" Hi all", words=words)]), SimpleNamespace(language="en", duration=1.0)

    stt = WhisperSpeechToText()
    stt._model, stt._loaded = Model(), "tiny"
    [segment], _ = stt.transcribe(tmp_path / "mic.wav", None, lambda f: None, "tiny", [])
    assert segment.words == (Word(0.0, 0.4, " Hi"), Word(0.4, 1.0, " all"))


@pytest.mark.parametrize(("vocabulary", "hotwords"), [(["Somchai", "Kubernetes"], "Somchai, Kubernetes"), ([], None)])
def test_whisper_is_given_the_vocabulary_as_hotwords(tmp_path, vocabulary, hotwords):
    from types import SimpleNamespace

    from transcribe.stt import WhisperSpeechToText

    given = []

    class Model:
        def transcribe(self, wav, **options):
            given.append(options["hotwords"])
            return iter(()), SimpleNamespace(language="en", duration=1.0)

    stt = WhisperSpeechToText()
    stt._model, stt._loaded = Model(), "tiny"
    stt.transcribe(tmp_path / "mic.wav", None, lambda f: None, "tiny", vocabulary)
    assert given == [hotwords]
