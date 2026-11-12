"""CLI scenarios: reading commands against the real service API in-process."""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from fakes import FakeCapture, FakeDiarizer, FakeSpeechToText
from transcribe import cli
from transcribe.client import ServiceClient, httpx, meeting_line, transcript_text
from transcribe.domain import Segment, SpeakerTurn
from transcribe.recorder import Recorder
from transcribe.store import MeetingStore
from transcribe.web import create_app

SEGMENTS = [Segment(0, 1, "สวัสดีครับ เริ่มประชุมกันเลย"), Segment(3, 4, "Budget looks fine")]


@pytest.fixture
def recorder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Recorder:
    recorder = Recorder(
        MeetingStore(tmp_path),
        FakeCapture(),
        FakeSpeechToText(SEGMENTS),
        FakeDiarizer([SpeakerTurn(0, 2, "A"), SpeakerTurn(2.5, 4, "B")]),
        clock=lambda: datetime(2026, 11, 11, 14, 30),
        run_in_background=lambda job: job(),
    )
    http = TestClient(create_app(recorder, allowed_hosts=["testserver"]))
    monkeypatch.setattr(cli, "_client", lambda: ServiceClient(http))
    return recorder


def test_help_runs() -> None:
    result = subprocess.run([sys.executable, "-m", "transcribe.cli", "--help"], capture_output=True, text=True)
    assert result.returncode == 0 and "serve" in result.stdout


def test_version_of_a_git_checkout_is_dev() -> None:
    result = subprocess.run([sys.executable, "-m", "transcribe.cli", "--version"], capture_output=True, text=True)
    assert result.returncode == 0 and result.stdout.strip() == "transcribe dev"


def test_list_show_search(recorder: Recorder, capsys: pytest.CaptureFixture[str]) -> None:
    recorder.start("Weekly", "mic")
    recorder.stop()
    assert cli.main(["list"]) == 0
    assert "2026-11-11-1430-weekly  Weekly  2026-11-11 14:30  00:00  transcribed" in capsys.readouterr().out
    assert cli.main(["show", "2026-11-11-1430-weekly"]) == 0
    assert "[00:00] Speaker 1: สวัสดีครับ เริ่มประชุมกันเลย" in capsys.readouterr().out
    assert cli.main(["search", "budget"]) == 0
    assert "2026-11-11-1430-weekly [00:03] Speaker 2: Budget looks fine" in capsys.readouterr().out


def test_search_hit_without_a_speaker_has_no_label() -> None:
    from transcribe.client import hit_line

    hit = {"meeting_id": "m1", "timestamp": "[00:01]", "speaker": None, "text": "hello"}
    assert hit_line(hit) == "m1 [00:01] hello"
    assert hit_line({**hit, "speaker": "You"}) == "m1 [00:01] You: hello"


def test_show_not_ready_prints_message(recorder: Recorder, capsys: pytest.CaptureFixture[str]) -> None:
    recorder.start("Live", "mic")
    assert cli.main(["show", "2026-11-11-1430-live"]) == 0
    assert "is not ready yet (status: recording)" in capsys.readouterr().out


def test_unknown_meeting_is_an_error(recorder: Recorder, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["show", "nope"]) == 1
    assert 'no meeting "nope" exists' in capsys.readouterr().err


def test_service_not_running(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(cli, "_client", lambda: ServiceClient(httpx.Client(base_url="http://127.0.0.1:1")))
    assert cli.main(["list"]) == 1
    assert "transcribe serve" in capsys.readouterr().err


def test_serve_refuses_a_windows_virtualenv_on_a_wsl_path(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sys, "prefix", r"\\?\UNC\wsl.localhost\Ubuntu\home\me\transcribe\.venv")
    assert cli.main(["serve"]) == 1
    err = capsys.readouterr().err
    assert "network path" in err and "transcribe.cmd" in err


def _transcribing(progress: dict | None) -> dict:
    return {
        "id": "2026-11-11-1430-call",
        "title": "Call",
        "started_at": "2026-11-11T14:30:00",
        "duration": 60.0,
        "status": "transcribing",
        "progress": progress,
    }


STEP = {"step": "Transcribing system audio", "step_number": 2, "steps": 3, "elapsed": 12.0}


def test_not_ready_message_names_the_step() -> None:
    meeting = _transcribing({**STEP, "fraction": 0.4})
    assert transcript_text({"meeting": meeting, "transcript": None}) == (
        'the transcript of "2026-11-11-1430-call" is not ready yet '
        "(status: transcribing; Transcribing system audio, step 2 of 3, 40%)"
    )
    assert meeting_line(meeting).endswith("transcribing (step 2 of 3, 40%)")


def test_step_without_a_fraction_yet() -> None:
    meeting = _transcribing({**STEP, "fraction": None})
    assert transcript_text({"meeting": meeting, "transcript": None}).endswith(
        "(status: transcribing; Transcribing system audio, step 2 of 3)"
    )
    assert meeting_line(_transcribing(None)).endswith("  transcribing")


def test_delete(recorder: Recorder, capsys: pytest.CaptureFixture[str]) -> None:
    recorder.start("Weekly", "mic")
    recorder.stop()
    assert cli.main(["delete", "2026-11-11-1430-weekly"]) == 0
    assert 'deleted "2026-11-11-1430-weekly"' in capsys.readouterr().out
    assert recorder.store.list() == []


def test_delete_refusal_is_an_error(recorder: Recorder, capsys: pytest.CaptureFixture[str]) -> None:
    recorder.start("Live", "mic")
    assert cli.main(["delete", "2026-11-11-1430-live"]) == 1
    assert "stop the recording first" in capsys.readouterr().err


def test_download_models_fetches_whisper_and_speaker_models(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from transcribe.diarize import SherpaDiarizer
    from transcribe.stt import WhisperSpeechToText

    fetched = []
    monkeypatch.setenv("TRANSCRIBE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("TRANSCRIBE_MODEL", "medium")
    monkeypatch.setattr(WhisperSpeechToText, "download", lambda self, name: fetched.append(name))
    monkeypatch.setattr(SherpaDiarizer, "ensure_models", lambda self: fetched.append(self._dir))
    assert cli.main(["download-models"]) == 0
    assert fetched == ["medium", tmp_path / ".models"]
    out = capsys.readouterr().out
    assert "Downloading the Whisper model medium…" in out and "Models ready" in out

    monkeypatch.setenv("TRANSCRIBE_MODEL", "large-v3-turbo")
    assert cli.main(["download-models"]) == 0
    assert "Downloading the Whisper model large-v3-turbo (about 1.6 GB)…" in capsys.readouterr().out


def test_download_models_failure_is_an_error(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    from transcribe.stt import WhisperSpeechToText

    def offline(self, name):
        raise OSError("connection reset")

    monkeypatch.setattr(WhisperSpeechToText, "download", offline)
    assert cli.main(["download-models"]) == 1
    assert "model download failed: connection reset" in capsys.readouterr().err


def test_rename(recorder: Recorder, capsys: pytest.CaptureFixture[str]) -> None:
    recorder.start("Weekly", "mic")
    recorder.stop()
    assert cli.main(["rename", "2026-11-11-1430-weekly", "Budget", "review"]) == 0
    assert capsys.readouterr().out.strip() == '"2026-11-11-1430-weekly" is now called "Budget review"'
    assert recorder.store.get("2026-11-11-1430-weekly").title == "Budget review"
    assert cli.main(["rename", "nope", "x"]) == 1
