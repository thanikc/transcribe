"""Web API scenarios: real Recorder and store, fake ports, synchronous background jobs."""

from __future__ import annotations

import asyncio
import hashlib
import threading
from datetime import datetime
from pathlib import Path

import httpx2 as httpx
import pytest
from starlette.testclient import TestClient

from fakes import FakeCapture, FakeConverter, FakeDiarizer, FakeSpeechToText
from transcribe.domain import Segment, SpeakerTurn
from transcribe.recorder import Recorder
from transcribe.store import MeetingStore
from transcribe.updates import UpdateService
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
            converter=FakeConverter(),
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


def test_index_loads_its_scripts_as_modules(rig: Rig) -> None:
    page = rig.client.get("/").text
    assert 'src="/static/js/main.js"' in page
    script = rig.client.get("/static/js/main.js")
    assert script.status_code == 200
    assert script.headers["content-type"] == "text/javascript; charset=utf-8"
    assert len(script.text) > 100


def test_scripts_route_serves_only_script_files(rig: Rig) -> None:
    assert rig.client.get("/static/js/missing.js").status_code == 404
    assert rig.client.get("/static/js/..%2Findex.html").status_code == 404
    assert rig.client.get("/static/js/%2e%2e%2f%2e%2e%2fweb.py").status_code == 404


def test_index_loads_its_stylesheets(rig: Rig) -> None:
    page = rig.client.get("/").text
    assert 'href="/static/css/main.css"' in page
    css = rig.client.get("/static/css/main.css")
    assert css.status_code == 200
    assert css.headers["content-type"] == "text/css; charset=utf-8"


def test_styles_route_serves_only_style_files(rig: Rig) -> None:
    assert rig.client.get("/static/css/missing.css").status_code == 404
    assert rig.client.get("/static/css/..%2Findex.html").status_code == 404
    assert rig.client.get("/static/css/%2e%2e%2f%2e%2e%2fweb.py").status_code == 404


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
    assert status["recording"] is True and status["title"] == "From the CLI" and status["levels"] == {}


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
    rig.recorder.store.track_path(meeting_id, "mic").write_bytes(b"ID3data")
    response = rig.client.get(f"/api/meetings/{meeting_id}/audio/mic")
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/mpeg"
    assert response.content == b"ID3data"


def test_meetings_report_audio_size(rig: Rig) -> None:
    meeting_id = rig.record()
    rig.recorder.store.track_path(meeting_id, "mic").write_bytes(b"ID3data")
    assert rig.client.get("/api/meetings").json()["meetings"][0]["audio_bytes"] == 7
    assert rig.client.get(f"/api/meetings/{meeting_id}").json()["meeting"]["audio_bytes"] == 7


def test_wav_audio_of_older_meetings_served(rig: Rig) -> None:
    meeting_id = rig.record()
    folder = rig.recorder.store.track_path(meeting_id, "mic").parent
    (folder / "mic.mp3").unlink()
    (folder / "mic.wav").write_bytes(b"RIFFdata")
    response = rig.client.get(f"/api/meetings/{meeting_id}/audio/mic")
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
    rig.recorder.capture.start = lambda paths, sources: (_ for _ in ()).throw(OSError("busy"))
    assert rig.client.post("/api/recordings/start", json={"title": "x", "mode": "mic"}).status_code == 503


def test_lists_the_audio_sources(rig: Rig) -> None:
    sources = rig.client.get("/api/sources").json()["sources"]
    assert sources["mic"]["chosen"] is None
    assert sources["mic"]["devices"][0] == {"id": "mic-headset", "name": "Headset", "default": True}
    assert [d["name"] for d in sources["system"]["devices"]] == ["Speakers", "Headphones"]


def test_choosing_an_audio_source_is_used_by_the_next_recording(rig: Rig) -> None:
    chosen = rig.client.post("/api/sources", json={"track": "mic", "device": "mic-webcam"})
    assert chosen.status_code == 200
    assert chosen.json()["sources"]["mic"]["chosen"] == {"id": "mic-webcam", "name": "Webcam"}
    rig.record()
    assert rig.recorder.capture.sources == {"mic": "mic-webcam"}
    cleared = rig.client.post("/api/sources", json={"track": "mic", "device": None})
    assert cleared.json()["sources"]["mic"]["chosen"] is None


@pytest.mark.parametrize(
    "body", [{"track": "file", "device": None}, {"track": "mic", "device": "gone"}, {"track": "mic", "device": 3}, {}]
)
def test_a_bad_audio_source_choice_is_400(rig: Rig, body: dict) -> None:
    assert rig.client.post("/api/sources", json=body).status_code == 400


def test_an_unplugged_chosen_device_refuses_to_start_with_503(rig: Rig) -> None:
    rig.client.post("/api/sources", json={"track": "mic", "device": "mic-webcam"})
    rig.recorder.capture.connected["mic"] = []
    refused = rig.client.post("/api/recordings/start", json={"title": "x", "mode": "mic"})
    assert refused.status_code == 503
    assert refused.json()["error"] == 'the microphone "Webcam" is not connected; choose another in Settings'


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


def test_delete_meeting(rig: Rig) -> None:
    meeting_id = rig.record()
    response = rig.client.request("DELETE", f"/api/meetings/{meeting_id}", json={})
    assert response.status_code == 200
    assert response.json() == {"deleted": meeting_id}
    assert rig.client.get("/api/meetings").json()["meetings"] == []
    assert rig.client.get(f"/api/meetings/{meeting_id}").status_code == 404


def test_delete_recording_meeting_conflicts(rig: Rig) -> None:
    meeting_id = rig.client.post("/api/recordings/start", json={"title": "Live", "mode": "mic"}).json()["meeting"]["id"]
    response = rig.client.request("DELETE", f"/api/meetings/{meeting_id}", json={})
    assert response.status_code == 409
    assert "stop the recording first" in response.json()["error"]


def test_delete_unknown_meeting_is_404(rig: Rig) -> None:
    assert rig.client.request("DELETE", "/api/meetings/nope", json={}).status_code == 404


def test_delete_from_foreign_origin_or_without_json_is_refused(rig: Rig) -> None:
    meeting_id = rig.record()
    foreign = rig.client.request(
        "DELETE", f"/api/meetings/{meeting_id}", json={}, headers={"Origin": "https://evil.example"}
    )
    assert foreign.status_code == 403
    assert rig.client.request("DELETE", f"/api/meetings/{meeting_id}").status_code == 415
    assert rig.client.get(f"/api/meetings/{meeting_id}").status_code == 200


def test_models_endpoint_lists_the_choices(rig: Rig) -> None:
    assert rig.client.get("/api/models").json() == {
        "models": [
            {"name": "large-v3", "size": "about 3 GB", "downloaded": True, "default": True},
            {"name": "large-v3-turbo", "size": "about 1.6 GB", "downloaded": False, "default": False},
        ]
    }


def test_model_can_be_chosen_when_recording_and_when_transcribing_again(rig: Rig) -> None:
    started = rig.client.post(
        "/api/recordings/start", json={"title": "Weekly sync", "mode": "mic", "model": "large-v3-turbo"}
    )
    assert started.json()["meeting"]["model"] == "large-v3-turbo"
    meeting_id = rig.client.post("/api/recordings/stop", json={}).json()["meeting"]["id"]
    again = rig.client.post(f"/api/meetings/{meeting_id}/transcribe", json={"model": "large-v3"})
    assert again.status_code == 200
    assert rig.client.get(f"/api/meetings/{meeting_id}").json()["meeting"]["model"] == "large-v3"
    assert rig.stt.used == ["large-v3-turbo", "large-v3"]

    refused = rig.client.post(f"/api/meetings/{meeting_id}/transcribe", json={"model": "huge"})
    assert refused.status_code == 400
    assert "model must be one of" in refused.json()["error"]


def test_out_of_memory_fallback_shows_as_a_warning(rig: Rig) -> None:
    rig.stt.too_big = {"large-v3"}
    meeting = rig.client.get(f"/api/meetings/{rig.record()}").json()["meeting"]
    assert meeting["status"] == "transcribed"
    assert meeting["model"] == "large-v3-turbo"
    assert meeting["warnings"] == ["not enough free memory for large-v3, so this was transcribed with large-v3-turbo"]


def test_requests_are_answered_while_a_recording_is_still_starting(tmp_path: Path) -> None:
    """Opening audio devices takes seconds, with the recorder locked. Nothing else may wait on the event loop."""
    devices_open = threading.Event()
    opening = threading.Event()

    class SlowCapture(FakeCapture):
        def start(self, track_paths, sources):
            opening.set()
            devices_open.wait(timeout=10)
            return super().start(track_paths, sources)

    recorder = Recorder(
        MeetingStore(tmp_path), SlowCapture(), FakeSpeechToText(SEGMENTS), FakeDiarizer(TURNS), run_in_background=lambda job: job()
    )
    first = TestClient(create_app(recorder, allowed_hosts=["testserver"]))
    devices_open.set()
    first.post("/api/recordings/start", json={"title": "Earlier", "mode": "mic"})
    earlier = first.post("/api/recordings/stop", json={}).json()["meeting"]["id"]
    devices_open.clear()
    opening.clear()
    # Lets the test end with a failure instead of hanging if the event loop does get blocked.
    rescue = threading.Timer(5, devices_open.set)
    rescue.start()

    async def scenario() -> list[int]:
        transport = httpx.ASGITransport(app=create_app(recorder, allowed_hosts=["testserver"]))
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            start = asyncio.create_task(client.post("/api/recordings/start", json={"title": "Next", "mode": "mic"}))
            await asyncio.to_thread(opening.wait, 5)
            # This one needs the recorder's lock, so it can only finish after the devices opened.
            again = asyncio.create_task(client.post(f"/api/meetings/{earlier}/transcribe", json={}))
            await asyncio.sleep(0.05)
            answered = [
                (await client.get("/api/status")).status_code,
                (await client.get("/api/meetings")).status_code,
                (await client.get(f"/api/meetings/{earlier}")).status_code,
                (await client.get("/api/search", params={"q": "budget"})).status_code,
            ]
            still_opening = not devices_open.is_set()
            devices_open.set()
            return [*answered, still_opening, (await start).status_code, (await again).status_code]

    try:
        assert asyncio.run(scenario()) == [200, 200, 200, 200, True, 201, 200]
    finally:
        rescue.cancel()


# --- version and updates ---------------------------------------------------------


class UpdateRig(Rig):
    def __init__(self, tmp_path: Path) -> None:
        super().__init__(tmp_path)
        setup = b"setup"
        self.launched: list[Path] = []
        self.downloads = 0

        def download(url: str, path: Path) -> None:
            self.downloads += 1
            path.write_bytes(setup)

        self.updates = UpdateService(
            installed="0.3.1",
            fetch_latest=lambda: {
                "tag_name": "0.4.0",
                "assets": [{
                    "name": "Transcribe-Setup-0.4.0.exe",
                    "browser_download_url": "https://github.com/thanikc/transcribe/releases/download/0.4.0/Transcribe-Setup-0.4.0.exe",
                    "size": len(setup),
                    "digest": "sha256:" + hashlib.sha256(setup).hexdigest(),
                }],
            },
            download=download,
            launch=self.launched.append,
            download_dir=tmp_path / "update",
            can_install=True,
        )
        self.client = TestClient(create_app(self.recorder, allowed_hosts=["testserver"], updates=self.updates))


def test_version_without_an_update_service(rig: Rig) -> None:
    body = rig.client.get("/api/version").json()
    assert body["version"] == "dev" and body["update"] is None


def test_version_offers_a_checked_update(tmp_path: Path) -> None:
    rig = UpdateRig(tmp_path)
    assert rig.client.get("/api/version").json()["update"] is None  # not checked yet
    rig.updates.check()
    assert rig.client.get("/api/version").json() == {
        "version": "0.3.1", "update": "0.4.0", "checked": True, "error": None, "can_install": True,
    }


def test_install_update_starts_the_setup(tmp_path: Path) -> None:
    rig = UpdateRig(tmp_path)
    rig.updates.check()
    response = rig.client.post("/api/update/install", json={})
    assert response.status_code == 200 and response.json() == {"launched": "0.4.0"}
    assert rig.launched == [tmp_path / "update" / "Transcribe-Setup-0.4.0.exe"]


def test_install_update_refused_while_recording(tmp_path: Path) -> None:
    rig = UpdateRig(tmp_path)
    rig.updates.check()
    rig.client.post("/api/recordings/start", json={"title": "Weekly sync", "mode": "mic"})
    response = rig.client.post("/api/update/install", json={})
    assert response.status_code == 409
    assert "stop the recording" in response.json()["error"]
    assert rig.downloads == 0


def test_install_update_refused_while_transcribing(tmp_path: Path) -> None:
    rig = UpdateRig(tmp_path)
    rig.recorder.run_in_background = lambda job: None
    rig.record()
    rig.updates.check()
    response = rig.client.post("/api/update/install", json={})
    assert response.status_code == 409
    assert "transcription" in response.json()["error"]
    assert rig.downloads == 0


def test_install_update_without_an_update_is_409(tmp_path: Path) -> None:
    rig = UpdateRig(tmp_path)
    assert rig.client.post("/api/update/install", json={}).status_code == 409


def test_install_update_from_a_foreign_origin_is_refused(tmp_path: Path) -> None:
    rig = UpdateRig(tmp_path)
    rig.updates.check()
    response = rig.client.post("/api/update/install", json={}, headers={"Origin": "https://evil.example"})
    assert response.status_code == 403 and rig.downloads == 0


def test_rename_meeting(rig: Rig) -> None:
    meeting_id = rig.record()
    response = rig.client.post(f"/api/meetings/{meeting_id}/title", json={"title": "Budget review"})
    assert response.status_code == 200
    assert (response.json()["meeting"]["id"], response.json()["meeting"]["title"]) == (meeting_id, "Budget review")
    assert response.json()["transcript"] is not None
    assert rig.client.get("/api/meetings").json()["meetings"][0]["title"] == "Budget review"
    assert rig.client.post("/api/meetings/nope/title", json={"title": "x"}).status_code == 404
    assert rig.client.post(f"/api/meetings/{meeting_id}/title", json={}).status_code == 400


def test_meeting_notes(rig: Rig) -> None:
    meeting_id = rig.record()
    assert rig.client.get(f"/api/meetings/{meeting_id}").json()["notes"] is None
    response = rig.client.post(f"/api/meetings/{meeting_id}/notes", json={"notes": "- ส่งงบ\n"})
    assert response.status_code == 200 and response.json()["notes"] == "- ส่งงบ\n"
    assert rig.client.get(f"/api/meetings/{meeting_id}").json()["notes"] == "- ส่งงบ\n"
    assert rig.client.post("/api/meetings/nope/notes", json={"notes": "x"}).status_code == 404



def _import(rig: Rig, body: bytes = b"ID3 audio", **headers: str):
    return rig.client.post(
        "/api/meetings/import",
        params={"title": "Standup", "language": "th"},
        content=body,
        headers={"Content-Type": "application/octet-stream", **headers},
    )


def test_import_audio_file(rig: Rig) -> None:
    response = _import(rig)
    assert response.status_code == 201
    meeting = response.json()["meeting"]
    assert (meeting["title"], meeting["mode"], meeting["tracks"], meeting["language"]) == ("Standup", "file", ["file"], "th")
    assert rig.client.get(f"/api/meetings/{meeting['id']}").json()["meeting"]["status"] == "transcribed"
    assert rig.client.get(f"/api/meetings/{meeting['id']}/audio/file").content == b"mp3"


def test_import_refuses_what_is_not_audio(rig: Rig) -> None:
    response = _import(rig, b"not audio at all")
    assert response.status_code == 400 and "could not read the file as audio" in response.json()["error"]
    assert rig.client.get("/api/meetings").json()["meetings"] == []


def test_import_refuses_other_websites_and_forms(rig: Rig) -> None:
    assert _import(rig, Origin="https://evil.example").status_code == 403
    form = rig.client.post("/api/meetings/import", content=b"x", headers={"Content-Type": "multipart/form-data; boundary=x"})
    assert form.status_code == 415
    # Raw bytes are only accepted where a file is expected.
    raw = rig.client.post("/api/recordings/start", content=b"{}", headers={"Content-Type": "application/octet-stream"})
    assert raw.status_code == 415
    assert rig.client.get("/api/meetings").json()["meetings"] == []
