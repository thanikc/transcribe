import os
from dataclasses import replace
from datetime import datetime

import pytest

from transcribe.domain import (
    AudioDevice,
    Meeting,
    MeetingNotFound,
    Segment,
    Status,
    TranscriptNotReady,
    UnknownTrack,
    search_transcripts,
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


def test_list_reads_the_data_dir_once_however_many_meetings(store, monkeypatch):
    for n in range(5):
        store.create(make_meeting(id=f"m{n}"))
    listings = []
    real = os.listdir
    monkeypatch.setattr(os, "listdir", lambda path: listings.append(path) or real(path))
    assert len(store.list()) == 5
    assert len(listings) == 1


# Text that JSON stores with escapes, text whose case folds to other letters, and plain Thai.
SPOKEN = [
    'She said "hello" twice',
    "path C:\\Users\\me",
    "line one\nline two\ttabbed",
    "Die Straße ist lang",
    "งบประมาณไตรมาสหน้า",
    "Budget looks fine",
]


@pytest.mark.parametrize(
    "query",
    ['"hello"', 'said "', "c:\\users", "\\", "one\nline", "two\tt", "STRASSE", "straße", "งบประมาณ", "BUDGET", "s", "zzz"],
)
def test_transcripts_for_search_never_drop_a_meeting_that_has_a_hit(store, query):
    for n, text in enumerate(SPOKEN):
        meeting = make_meeting(id=f"m{n}", status=Status.TRANSCRIBED)
        store.create(meeting)
        store.save_transcript(meeting.id, [Segment(0, 1, "filler"), Segment(1, 2, text)])
    everything = [(store.get(f"m{n}"), store.load_transcript(f"m{n}")) for n in range(len(SPOKEN))]
    expected = sorted(h.text for h in search_transcripts(everything, query))
    assert sorted(h.text for h in search_transcripts(store.transcripts(mentioning=query), query)) == expected


def test_transcripts_for_search_skip_what_cannot_match(store):
    for meeting_id, text in [("a", "Budget review"), ("b", "Holiday plans")]:
        store.create(make_meeting(id=meeting_id, status=Status.TRANSCRIBED))
        store.save_transcript(meeting_id, [Segment(0, 1, text)])
    store.create(make_meeting(id="c", status=Status.TRANSCRIBING))
    assert [m.id for m, _ in store.transcripts(mentioning="BUDGET")] == ["a"]


def test_transcripts_for_search_read_files_written_with_unicode_escapes(store):
    # Not how this store writes, but valid JSON: the raw file then lacks the Thai text.
    store.create(make_meeting(status=Status.TRANSCRIBED))
    path = store.data_dir / "2026-11-11-1430-standup" / "transcript.json"
    path.write_text('[{"start": 0, "end": 1, "text": "\\u0e07\\u0e1a", "speaker": null}]', encoding="utf-8")
    assert [segments[0].text for _, segments in store.transcripts(mentioning="งบ")] == ["งบ"]


def test_transcripts_for_search_leave_out_an_unreadable_transcript(store):
    store.create(make_meeting(id="lost", status=Status.TRANSCRIBED))  # no transcript.json
    store.create(make_meeting(id="broken", status=Status.TRANSCRIBED))
    (store.data_dir / "broken" / "transcript.json").write_text("[{", encoding="utf-8")
    store.create(make_meeting(id="fine", status=Status.TRANSCRIBED))
    store.save_transcript("fine", [Segment(0, 1, "hello")])
    assert [m.id for m, _ in store.transcripts(mentioning="hello")] == ["fine"]


def test_audio_bytes_ignores_a_folder_named_like_a_track(store):
    meeting = make_meeting()
    store.create(meeting)
    (store.data_dir / meeting.id / "mic.mp3").mkdir()
    assert store.audio_bytes(meeting) == 0


def test_notes_round_trip_replace_and_remove(store):
    store.create(make_meeting())
    assert store.load_notes("2026-11-11-1430-standup") is None
    store.save_notes("2026-11-11-1430-standup", "## สรุป\n- Budget approved\n")
    store.save_notes("2026-11-11-1430-standup", "## สรุป\n- Budget approved, ship Friday\n")
    path = store.data_dir / "2026-11-11-1430-standup" / "notes.md"
    assert path.read_text(encoding="utf-8") == "## สรุป\n- Budget approved, ship Friday\n"
    assert store.load_notes("2026-11-11-1430-standup") == "## สรุป\n- Budget approved, ship Friday\n"
    store.save_notes("2026-11-11-1430-standup", "  \n")
    assert not path.exists() and store.load_notes("2026-11-11-1430-standup") is None
    store.save_notes("2026-11-11-1430-standup", "")  # nothing to remove: fine


def test_notes_of_unknown_meeting(store):
    with pytest.raises(MeetingNotFound):
        store.save_notes("nope", "x")
    with pytest.raises(MeetingNotFound):
        store.load_notes("../x")


def test_vocabulary_is_read_from_the_data_dir(store):
    assert store.vocabulary() == []
    (store.data_dir / "vocabulary.txt").write_text("# teammates\nSomchai\n\n  Kubernetes  \n# products\nสมชาย\n", encoding="utf-8")
    assert store.vocabulary() == ["Somchai", "Kubernetes", "สมชาย"]


def test_vocabulary_keeps_only_whole_words_that_fit(store):
    words = [f"word{n:03d}" for n in range(200)]  # 7 letters + ", " each: 9 apiece
    (store.data_dir / "vocabulary.txt").write_text("\n".join(words), encoding="utf-8")
    kept = store.vocabulary()
    assert kept == words[: len(kept)] and len(", ".join(kept)) <= 800 < len(", ".join(words[: len(kept) + 1]))


def test_vocabulary_file_is_created_with_a_how_to_and_never_overwritten(store):
    path = store.vocabulary_file()
    assert path == store.data_dir / "vocabulary.txt"
    assert path.read_text(encoding="utf-8").startswith("# ") and store.vocabulary() == []
    path.write_text("Somchai\n", encoding="utf-8")
    assert store.vocabulary_file().read_text(encoding="utf-8") == "Somchai\n"
    assert store.list() == []  # not mistaken for a meeting


def test_no_audio_sources_are_chosen_at_first(store):
    assert store.load_sources() == {}


def test_chosen_audio_sources_survive_a_restart(store):
    store.save_sources({"mic": AudioDevice("{0.0.1}.webcam", "Webcam ไมค์")})
    assert MeetingStore(store.data_dir).load_sources() == {"mic": AudioDevice("{0.0.1}.webcam", "Webcam ไมค์")}
    assert "ไมค์" in (store.data_dir / "sources.json").read_text(encoding="utf-8")


def test_a_corrupt_sources_file_means_the_windows_defaults(store):
    (store.data_dir / "sources.json").write_text("{not json", encoding="utf-8")
    assert store.load_sources() == {}


def test_the_sources_file_is_not_a_meeting(store):
    store.save_sources({"mic": AudioDevice("w", "Webcam")})
    store.create(make_meeting())
    assert [m.id for m in store.list()] == ["2026-11-11-1430-standup"]
