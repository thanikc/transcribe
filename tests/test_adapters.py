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
