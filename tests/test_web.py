"""Web API scenarios: real Recorder and store, fake ports, synchronous background jobs."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from fakes import FakeCapture, FakeDiarizer, FakeSpeechToText
from transcribe.domain import Segment, SpeakerTurn
from transcribe.recorder import Recorder
from transcribe.store import MeetingStore
from transcribe.web import create_app

SEGMENTS = [Segment(0, 1, "สวัสดีครับ เริ่มประชุมกันเลย"), Segment(3, 4, "Budget looks fine")]
TURNS = [SpeakerTurn(0, 2, "A"), SpeakerTurn(2.5, 4, "B")]


class Rig:
    def __init__(self, tmp_path: Path) -> None:
        self.stt = FakeSpeechToText(SEGMENTS)
        self.recorder = Recorder(
            MeetingStore(tmp_path),
            FakeCapture(),
            self.stt,
            FakeDiarizer(TURNS),
            clock=lambda: datetime(2026, 11, 11, 14, 30),
            run_in_background=lambda job: job(),
        )
        self.client = TestClient(create_app(self.recorder, allowed_hosts=["testserver"]))

    def record(self, title: str = "Weekly sync") -> str:
        self.client.post("/api/recordings/start", json={"title": title, "mode": "mic"})
        return self.client.post("/api/recordings/stop", json={}).json()["meeting"]["id"]


@pytest.fixture
def rig(tmp_path: Path) -> Rig:
    return Rig(tmp_path)


def test_index_page(rig: Rig) -> None:
    response = rig.client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/html; charset=utf-8"
    assert "<title>" in response.text


def test_start_stop_round_trip(rig: Rig) -> None:
    started = rig.client.post("/api/recordings/start", json={"title": "Weekly sync", "mode": "mic", "language": "th"})
    assert started.status_code == 201
    meeting = started.json()["meeting"]
    assert meeting["status"] == "recording" and meeting["tracks"] == ["mic"] and meeting["language"] == "th"
    assert rig.client.get("/api/status").json()["recording"] is True
    stopped = rig.client.post("/api/recordings/stop", json={})
    assert stopped.status_code == 200
    assert stopped.json()["meeting"]["id"] == meeting["id"]
    # Background jobs run synchronously here, so the meeting is already transcribed.
    listing = rig.client.get("/api/meetings").json()["meetings"]
    assert [(m["id"], m["status"]) for m in listing] == [(meeting["id"], "transcribed")]
    assert rig.client.get("/api/status").json() == {"recording": False}


def test_status_shows_recording_started_elsewhere(rig: Rig) -> None:
    rig.recorder.start("From the CLI", "mic")
    status = rig.client.get("/api/status").json()
    assert status["recording"] is True and status["title"] == "From the CLI"


def test_second_start_and_stop_without_recording_conflict(rig: Rig) -> None:
    assert rig.client.post("/api/recordings/stop", json={}).status_code == 409
    rig.client.post("/api/recordings/start", json={"title": "One", "mode": "mic"})
    again = rig.client.post("/api/recordings/start", json={"title": "Two", "mode": "mic"})
    assert again.status_code == 409
    assert again.json() == {"error": "a recording is already in progress"}


def test_meetings_newest_first(rig: Rig) -> None:
    rig.recorder.clock = lambda: datetime(2026, 11, 11, 9, 0)
    first = rig.record("Early")
    rig.recorder.clock = lambda: datetime(2026, 11, 11, 15, 0)
    second = rig.record("Late")
    ids = [m["id"] for m in rig.client.get("/api/meetings").json()["meetings"]]
    assert ids == [second, first]


def test_meeting_while_transcribing_has_no_transcript(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    rig.recorder.run_in_background = lambda job: None
    meeting_id = rig.record()
    body = rig.client.get(f"/api/meetings/{meeting_id}").json()
    assert body["meeting"]["status"] == "transcribing"
    assert body["segments"] is None and body["transcript"] is None


def test_transcribed_meeting_detail(rig: Rig) -> None:
    body = rig.client.get(f"/api/meetings/{rig.record()}").json()
    assert body["segments"][0] == {"start": 0, "end": 1, "text": "สวัสดีครับ เริ่มประชุมกันเลย", "speaker": "Speaker 1"}
    assert body["transcript"].splitlines()[0] == "[00:00] Speaker 1: สวัสดีครับ เริ่มประชุมกันเลย"


def test_thai_is_raw_utf8(rig: Rig) -> None:
    response = rig.client.get(f"/api/meetings/{rig.record()}")
    assert "สวัสดีครับ เริ่มประชุมกันเลย".encode() in response.content
    assert b"\\u0e2a" not in response.content


def test_unknown_meeting_404(rig: Rig) -> None:
    for path in ("/api/meetings/nope", "/api/meetings/nope/audio/mic"):
        response = rig.client.get(path)
        assert response.status_code == 404 and "error" in response.json()


@pytest.mark.parametrize(
    "path",
    [
        "/api/meetings/{id}/audio/secrets",
        "/api/meetings/{id}/audio/system",
        "/api/meetings/../../Windows/audio/mic",
        "/api/meetings/..%2F..%2FWindows/audio/mic",
        "/api/meetings/{id}/audio/..%2F..%2FWindows",
        "/api/meetings/{id}/audio/../../Windows",
    ],
)
def test_audio_rejects_unknown_ids_and_tracks(rig: Rig, path: str) -> None:
    response = rig.client.get(path.replace("{id}", rig.record()))
    assert response.status_code == 404


def test_audio_missing_file_404(rig: Rig) -> None:
    meeting_id = rig.record()
    (rig.recorder.store.track_path(meeting_id, "mic")).unlink()
    assert rig.client.get(f"/api/meetings/{meeting_id}/audio/mic").status_code == 404


def test_audio_served(rig: Rig) -> None:
    meeting_id = rig.record()
    rig.recorder.store.track_path(meeting_id, "mic").write_bytes(b"RIFFdata")
    response = rig.client.get(f"/api/meetings/{meeting_id}/audio/mic")
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"
    assert response.content == b"RIFFdata"


def test_foreign_origin_is_refused_and_does_not_run(rig: Rig) -> None:
    response = rig.client.post(
        "/api/recordings/start", json={"title": "x", "mode": "mic"}, headers={"Origin": "https://evil.example"}
    )
    assert response.status_code == 403
    assert rig.recorder.status() == {"recording": False}


def test_same_origin_allowed(rig: Rig) -> None:
    response = rig.client.post(
        "/api/recordings/start", json={"title": "x", "mode": "mic"}, headers={"Origin": "http://testserver"}
    )
    assert response.status_code == 201


def test_non_json_content_type_is_415(rig: Rig) -> None:
    response = rig.client.post(
        "/api/recordings/start", content='{"title": "x", "mode": "mic"}', headers={"Content-Type": "text/plain"}
    )
    assert response.status_code == 415
    assert rig.recorder.status() == {"recording": False}


def test_unknown_host_is_refused(rig: Rig) -> None:
    rig.record()
    assert rig.client.get("/api/meetings", headers={"Host": "evil.example"}).status_code == 400


@pytest.mark.parametrize(
    "body",
    [b"not json", b"[]", b'{"mode": "mic"}', b'{"title": 5, "mode": "mic"}', b'{"title": "x", "mode": "mic", "language": 3}'],
)
def test_bad_request_bodies_400(rig: Rig, body: bytes) -> None:
    response = rig.client.post("/api/recordings/start", content=body, headers={"Content-Type": "application/json"})
    assert response.status_code == 400 and "error" in response.json()
    assert rig.recorder.status() == {"recording": False}


def test_invalid_choice_400_and_capture_error_503(rig: Rig) -> None:
    bad = rig.client.post("/api/recordings/start", json={"title": "x", "mode": "video"})
    assert bad.status_code == 400
    rig.recorder.capture.start = lambda paths: (_ for _ in ()).throw(OSError("busy"))
    assert rig.client.post("/api/recordings/start", json={"title": "x", "mode": "mic"}).status_code == 503


def test_rename_speaker(rig: Rig) -> None:
    meeting_id = rig.record()
    response = rig.client.post(f"/api/meetings/{meeting_id}/speakers", json={"speaker": "Speaker 2", "name": "Somchai"})
    assert response.status_code == 200
    assert response.json()["meeting"]["speaker_names"] == {"Speaker 2": "Somchai"}
    assert "[00:03] Somchai: Budget looks fine" in response.json()["transcript"]
    assert "Somchai" in rig.client.get(f"/api/meetings/{meeting_id}").json()["transcript"]
    reset = rig.client.post(f"/api/meetings/{meeting_id}/speakers", json={"speaker": "Speaker 2", "name": ""})
    assert reset.json()["meeting"]["speaker_names"] == {}


def test_rename_unknown_speaker_400(rig: Rig) -> None:
    response = rig.client.post(f"/api/meetings/{rig.record()}/speakers", json={"speaker": "Speaker 9", "name": "X"})
    assert response.status_code == 400
    assert response.json() == {"error": 'there is no "Speaker 9" in that meeting'}


def test_rename_before_transcript_is_409(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    rig.recorder.run_in_background = lambda job: None
    meeting_id = rig.record()
    response = rig.client.post(f"/api/meetings/{meeting_id}/speakers", json={"speaker": "Speaker 1", "name": "X"})
    assert response.status_code == 409


def test_retranscribe_failed_meeting(rig: Rig) -> None:
    rig.stt.error = RuntimeError("boom")
    meeting_id = rig.record()
    assert rig.client.get(f"/api/meetings/{meeting_id}").json()["meeting"]["status"] == "failed"
    rig.stt.error = None
    response = rig.client.post(f"/api/meetings/{meeting_id}/transcribe", json={"language": "th"})
    assert response.status_code == 200
    assert response.json()["meeting"]["status"] == "transcribing"
    detail = rig.client.get(f"/api/meetings/{meeting_id}").json()
    assert detail["meeting"]["status"] == "transcribed" and detail["meeting"]["language"] == "th"


def test_transcribe_accepts_empty_body_and_unknown_meeting_404(rig: Rig) -> None:
    assert rig.client.post("/api/meetings/nope/transcribe", json={}).status_code == 404
    meeting_id = rig.record()
    response = rig.client.post(f"/api/meetings/{meeting_id}/transcribe", content=b"", headers={"Content-Type": "application/json"})
    assert response.status_code == 200


def test_search_thai_and_case_insensitive(rig: Rig) -> None:
    meeting_id = rig.record("Weekly sync")
    thai = rig.client.get("/api/search", params={"q": "เริ่มประชุม"}).json()["hits"]
    assert thai == [
        {
            "meeting_id": meeting_id,
            "title": "Weekly sync",
            "start": 0,
            "timestamp": "[00:00]",
            "speaker": "Speaker 1",
            "text": "สวัสดีครับ เริ่มประชุมกันเลย",
        }
    ]
    assert [h["text"] for h in rig.client.get("/api/search", params={"q": "BUDGET"}).json()["hits"]] == [
        "Budget looks fine"
    ]


def test_search_requires_query(rig: Rig) -> None:
    assert rig.client.get("/api/search").status_code == 400
    assert rig.client.get("/api/search", params={"q": "  "}).status_code == 400


def test_transcribing_meeting_shows_progress_in_detail_and_list(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    jobs: list = []
    rig.recorder.run_in_background = jobs.append
    meeting_id = rig.record()
    seen = []

    def look(on_progress) -> None:
        on_progress(0.4)
        seen.append(rig.client.get(f"/api/meetings/{meeting_id}").json()["meeting"]["progress"])
        seen.append(rig.client.get("/api/meetings").json()["meetings"][0]["progress"])

    rig.stt.during = look
    jobs.pop()()
    step = {"step": "Transcribing microphone", "step_number": 1, "steps": 2, "fraction": 0.4, "elapsed": 0}
    assert seen == [step, step]
    assert rig.client.get(f"/api/meetings/{meeting_id}").json()["meeting"]["progress"] is None
