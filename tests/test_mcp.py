"""MCP tool scenarios: tools call the real service API in-process, fake ports, synchronous jobs."""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from fakes import FakeCapture, FakeDiarizer, FakeSpeechToText
from transcribe.client import ServiceClient, httpx
from transcribe.domain import Segment, SpeakerTurn
from transcribe.mcp_server import build_server
from transcribe.recorder import Recorder
from transcribe.store import MeetingStore
from transcribe.web import create_app

SEGMENTS = [Segment(0, 1, "สวัสดีครับ เริ่มประชุมกันเลย"), Segment(3, 4, "Budget looks fine")]
TURNS = [SpeakerTurn(0, 2, "A"), SpeakerTurn(2.5, 4, "B")]


class Rig:
    def __init__(self, tmp_path: Path) -> None:
        self.recorder = Recorder(
            MeetingStore(tmp_path),
            FakeCapture(),
            FakeSpeechToText(SEGMENTS),
            FakeDiarizer(TURNS),
            clock=lambda: datetime(2026, 11, 11, 14, 30),
            run_in_background=lambda job: job(),
        )
        http = TestClient(create_app(self.recorder, allowed_hosts=["testserver"]))
        self.server = build_server(lambda: ServiceClient(http))

    def call(self, tool: str, **arguments: str) -> str:
        result = asyncio.run(self.server.call_tool(tool, arguments))
        return result.content[0].text


@pytest.fixture
def rig(tmp_path: Path) -> Rig:
    return Rig(tmp_path)


def test_start_stop_then_list(rig: Rig) -> None:
    started = rig.call("start_recording", title="Design review", mode="mic+system")
    assert "Design review" in started
    stopped = rig.call("stop_recording")
    assert "2026-11-11-1430-design-review" in stopped and "transcription has started" in stopped.lower()
    listing = rig.call("list_meetings")
    assert listing.splitlines() == ["2026-11-11-1430-design-review  Design review  2026-11-11 14:30  00:00  transcribed"]


def test_meeting_without_title_is_shown_by_its_id(rig: Rig) -> None:
    assert rig.call("start_recording", title="", mode="mic") == 'Recording started: "2026-11-11-1430" (id 2026-11-11-1430).'
    rig.call("stop_recording")
    assert rig.call("list_meetings") == "2026-11-11-1430  2026-11-11-1430  2026-11-11 14:30  00:00  transcribed"
    assert rig.call("get_transcript", meeting_id="2026-11-11-1430").startswith("2026-11-11-1430\nDate:")


def test_stop_recording_started_from_the_web_page(rig: Rig) -> None:
    rig.recorder.start("From the web", "mic")
    assert "2026-11-11-1430-from-the-web" in rig.call("stop_recording")


def test_stop_without_recording_reports_the_refusal(rig: Rig) -> None:
    assert rig.call("stop_recording") == "no recording is in progress"


def test_get_transcript_has_header_and_thai(rig: Rig) -> None:
    rig.call("start_recording", title="Weekly", mode="mic")
    rig.call("stop_recording")
    text = rig.call("get_transcript", meeting_id="2026-11-11-1430-weekly")
    assert text.startswith("Weekly")
    assert "[00:00] Speaker 1: สวัสดีครับ เริ่มประชุมกันเลย" in text


def test_rename_speaker_shows_in_transcript(rig: Rig) -> None:
    rig.call("start_recording", title="Weekly", mode="mic")
    rig.call("stop_recording")
    rig.call("rename_speaker", meeting_id="2026-11-11-1430-weekly", speaker="Speaker 1", name="Khun Nok")
    text = rig.call("get_transcript", meeting_id="2026-11-11-1430-weekly")
    assert "Khun Nok: สวัสดีครับ" in text and "Speaker 1" not in text


def test_search_lines_and_no_matches(rig: Rig) -> None:
    rig.call("start_recording", title="Weekly", mode="mic")
    rig.call("stop_recording")
    assert rig.call("search_transcripts", query="budget") == "2026-11-11-1430-weekly [00:03] Speaker 2: Budget looks fine"
    assert rig.call("search_transcripts", query="zzz") == "no matches"


def test_transcript_not_ready_and_unknown(rig: Rig) -> None:
    rig.recorder.start("Live", "mic")
    assert rig.call("get_transcript", meeting_id="2026-11-11-1430-live") == (
        'the transcript of "2026-11-11-1430-live" is not ready yet (status: recording)'
    )
    assert rig.call("get_transcript", meeting_id="nope") == 'no meeting "nope" exists'


def test_service_not_running() -> None:
    server = build_server(lambda: ServiceClient(httpx.Client(base_url="http://127.0.0.1:1")))
    text = asyncio.run(server.call_tool("list_meetings", {})).content[0].text
    assert "recorder service not running" in text and "transcribe serve" in text


def test_delete_meeting(rig: Rig) -> None:
    rig.call("start_recording", title="Weekly", mode="mic")
    rig.call("stop_recording")
    assert rig.call("delete_meeting", meeting_id="2026-11-11-1430-weekly") == 'Deleted "2026-11-11-1430-weekly".'
    assert rig.call("list_meetings") == "no meetings yet"
    assert rig.call("delete_meeting", meeting_id="nope") == 'no meeting "nope" exists'


def test_rename_meeting(rig: Rig) -> None:
    rig.call("start_recording", title="Weekly sync", mode="mic")
    rig.call("stop_recording")
    reply = rig.call("rename_meeting", meeting_id="2026-11-11-1430-weekly-sync", title="Budget review")
    assert reply == '"2026-11-11-1430-weekly-sync" is now called "Budget review".'
    assert "Budget review" in rig.call("list_meetings")
    assert rig.call("rename_meeting", meeting_id="nope", title="x") == 'no meeting "nope" exists'


def test_save_meeting_notes_shows_in_transcript(rig: Rig) -> None:
    rig.call("start_recording", title="Weekly sync", mode="mic")
    rig.call("stop_recording")
    reply = rig.call("save_meeting_notes", meeting_id="2026-11-11-1430-weekly-sync", notes="Summary: budget OK\n- Somchai: send figures")
    assert reply == 'Saved notes for "2026-11-11-1430-weekly-sync".'
    transcript = rig.call("get_transcript", meeting_id="2026-11-11-1430-weekly-sync")
    assert "(detected: en)\n\nNotes:\nSummary: budget OK\n- Somchai: send figures\n\nTranscript:\n[00:00]" in transcript
    assert rig.call("save_meeting_notes", meeting_id="2026-11-11-1430-weekly-sync", notes="") == 'Removed the notes of "2026-11-11-1430-weekly-sync".'
    assert "Notes:" not in rig.call("get_transcript", meeting_id="2026-11-11-1430-weekly-sync")
    assert rig.call("save_meeting_notes", meeting_id="nope", notes="x") == 'no meeting "nope" exists'
