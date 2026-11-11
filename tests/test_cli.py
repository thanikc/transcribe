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
from transcribe.client import ServiceClient, httpx
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


def test_list_show_search(recorder: Recorder, capsys: pytest.CaptureFixture[str]) -> None:
    recorder.start("Weekly", "mic")
    recorder.stop()
    assert cli.main(["list"]) == 0
    assert "2026-11-11-1430-weekly  Weekly  2026-11-11 14:30  00:00  transcribed" in capsys.readouterr().out
    assert cli.main(["show", "2026-11-11-1430-weekly"]) == 0
    assert "[00:00] Speaker 1: สวัสดีครับ เริ่มประชุมกันเลย" in capsys.readouterr().out
    assert cli.main(["search", "budget"]) == 0
    assert "2026-11-11-1430-weekly [00:03] Speaker 2: Budget looks fine" in capsys.readouterr().out


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
