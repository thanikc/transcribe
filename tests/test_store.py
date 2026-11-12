from dataclasses import replace
from datetime import datetime

import pytest

from transcribe.domain import (
    Meeting,
    MeetingNotFound,
    Segment,
    Status,
    TranscriptNotReady,
    UnknownTrack,
)
from transcribe.store import MeetingStore


def make_meeting(**overrides) -> Meeting:
    fields = dict(
        id="2026-11-11-1430-standup",
        title="Standup",
        mode="mic",
        language="auto",
        started_at=datetime(2026, 11, 11, 14, 30),
        status=Status.RECORDING,
    )
    return Meeting(**{**fields, **overrides})


@pytest.fixture
def store(tmp_path) -> MeetingStore:
    return MeetingStore(tmp_path / "data")


def test_creates_data_dir(store):
    assert store.data_dir.is_dir()


def test_round_trip(store):
    meeting = make_meeting(title="ประชุม", warnings=["w"], speaker_names={"Speaker 1": "Ann"})
    store.create(meeting)
    assert store.get(meeting.id) == meeting


def test_loads_meeting_saved_with_an_engine(store):
    # Meetings recorded while Gemini was an engine option still have an "engine" key.
    meeting = make_meeting()
    store.create(meeting)
    path = store.data_dir / meeting.id / "meeting.json"
    path.write_text(path.read_text(encoding="utf-8").replace('"mode"', '"engine": "gemini-cli", "mode"'), encoding="utf-8")
    assert store.get(meeting.id) == meeting


def test_create_fails_if_exists(store):
    store.create(make_meeting())
    with pytest.raises(FileExistsError):
        store.create(make_meeting())


def test_save_overwrites(store):
    meeting = make_meeting()
    store.create(meeting)
    updated = replace(meeting, status=Status.TRANSCRIBING)
    store.save(updated)
    assert store.get(meeting.id).status == Status.TRANSCRIBING
    assert [p.name for p in (store.data_dir / meeting.id).iterdir()] == ["meeting.json"]


def test_list_newest_first(store):
    early = make_meeting(id="a", started_at=datetime(2026, 11, 11, 9, 0))
    late = make_meeting(id="b", started_at=datetime(2026, 11, 11, 14, 30))
    store.create(early)
    store.create(late)
    assert [m.id for m in store.list()] == ["b", "a"]


def test_corrupt_folder_skipped_by_list_but_in_ids(store):
    store.create(make_meeting(id="good"))
    (store.data_dir / "bad").mkdir()
    (store.data_dir / "bad" / "meeting.json").write_text("{not json", encoding="utf-8")
    (store.data_dir / "empty").mkdir()
    assert [m.id for m in store.list()] == ["good"]
    assert store.ids() == {"good", "bad", "empty"}


@pytest.mark.parametrize("bad_id", ["nope", "../x", "a/b", "a\\b", "..", ""])
def test_get_unknown_or_unsafe_id(store, bad_id):
    with pytest.raises(MeetingNotFound):
        store.get(bad_id)


def test_get_corrupt_is_not_found(store):
    (store.data_dir / "bad").mkdir()
    (store.data_dir / "bad" / "meeting.json").write_text("{", encoding="utf-8")
    with pytest.raises(MeetingNotFound):
        store.get("bad")


def test_delete_removes_folder(store):
    meeting = make_meeting()
    store.create(meeting)
    store.delete(meeting.id)
    assert store.ids() == set()


def test_track_path(store):
    meeting = make_meeting(mode="mic+system")
    store.create(meeting)
    assert store.track_path(meeting.id, "system") == store.data_dir / meeting.id / "system.mp3"


def test_track_path_finds_wav_tracks_of_older_meetings(store):
    meeting = make_meeting(mode="mic+system")
    store.create(meeting)
    folder = store.data_dir / meeting.id
    (folder / "mic.wav").write_bytes(b"RIFF")
    assert store.track_path(meeting.id, "mic") == folder / "mic.wav"
    assert store.track_path(meeting.id, "system") == folder / "system.mp3"


def test_track_path_unknown_track(store):
    store.create(make_meeting())
    with pytest.raises(UnknownTrack):
        store.track_path("2026-11-11-1430-standup", "system")


def test_track_path_unknown_meeting(store):
    with pytest.raises(MeetingNotFound):
        store.track_path("nope", "mic")


def test_transcript_round_trip_is_raw_utf8(store):
    meeting = make_meeting(status=Status.TRANSCRIBED)
    store.create(meeting)
    text = "สวัสดีครับ เริ่มประชุมกันเลย"
    segments = [Segment(0.0, 2.5, text, "You"), Segment(2.5, 3.0, "ok")]
    store.save_transcript(meeting.id, segments)
    raw = (store.data_dir / meeting.id / "transcript.json").read_bytes()
    assert text.encode("utf-8") in raw
    assert b"\\u0e" not in raw
    assert store.load_transcript(meeting.id) == segments


def test_load_transcript_not_ready(store):
    store.create(make_meeting(status=Status.TRANSCRIBING))
    with pytest.raises(TranscriptNotReady, match="transcribing"):
        store.load_transcript("2026-11-11-1430-standup")


def test_load_transcript_unknown(store):
    with pytest.raises(MeetingNotFound):
        store.load_transcript("nope")


def test_audio_bytes_sums_existing_tracks(store):
    meeting = make_meeting(mode="mic+system")
    store.create(meeting)
    folder = store.data_dir / meeting.id
    (folder / "mic.wav").write_bytes(b"RIFF1234")
    (folder / "system.mp3").write_bytes(b"ID3")
    assert store.audio_bytes(meeting) == 11


def test_audio_bytes_zero_without_audio_files(store):
    meeting = make_meeting()
    store.create(meeting)
    assert store.audio_bytes(meeting) == 0
