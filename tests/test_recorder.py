"""Recorder service scenarios, with fake ports and a real store."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from transcribe.domain import (
    InvalidChoice,
    InvalidTransition,
    Meeting,
    MeetingNotFound,
    NoRecording,
    RecordingInProgress,
    Segment,
    SpeakerTurn,
    Status,
    TranscriptNotReady,
    UnknownSpeaker,
    render_transcript,
)
from transcribe.recorder import CaptureError, Recorder
from transcribe.store import MeetingStore

T0 = datetime(2026, 11, 11, 14, 30)


class FakeClock:
    def __init__(self, now: datetime = T0) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


class FakeSession:
    def __init__(self, fail: Exception | None = None) -> None:
        self.stopped = False
        self.fail = fail

    def stop(self) -> None:
        self.stopped = True
        if self.fail:
            raise self.fail


class FakeCapture:
    def __init__(self) -> None:
        self.error: Exception | None = None
        self.stop_error: Exception | None = None
        self.paths: dict[str, Path] = {}

    def start(self, track_paths: dict[str, Path]) -> FakeSession:
        if self.error:
            raise self.error
        self.paths = track_paths
        for path in track_paths.values():
            path.touch()
        return FakeSession(self.stop_error)


class FakeSTT:
    def __init__(self, by_track: dict[str, list[Segment]] | None = None, detected: str = "en") -> None:
        self.by_track = by_track or {}
        self.detected = detected
        self.error: Exception | None = None
        self.calls: list[tuple[str, str | None]] = []

    def transcribe(self, wav: Path, language: str | None) -> tuple[list[Segment], str]:
        self.calls.append((wav.stem, language))
        if self.error:
            raise self.error
        return self.by_track.get(wav.stem, []), self.detected


class FakeDiarizer:
    def __init__(self, turns: dict[str, list[SpeakerTurn]] | None = None) -> None:
        self.turns = turns or {}
        self.error: Exception | None = None
        self.calls: list[str] = []

    def diarize(self, wav: Path) -> list[SpeakerTurn]:
        self.calls.append(wav.stem)
        if self.error:
            raise self.error
        return self.turns.get(wav.stem, [])


class Rig:
    def __init__(self, tmp_path: Path) -> None:
        self.store = MeetingStore(tmp_path)
        self.clock = FakeClock()
        self.capture = FakeCapture()
        self.whisper = FakeSTT()
        self.diarizer = FakeDiarizer()
        self.jobs: list = []
        self.recorder = Recorder(
            self.store,
            self.capture,
            self.whisper,
            self.diarizer,
            clock=self.clock,
            run_in_background=self.jobs.append,
        )

    def run_jobs(self) -> None:
        while self.jobs:
            self.jobs.pop(0)()

    def record(self, title: str = "Weekly sync", mode: str = "mic", **kw) -> Meeting:
        self.recorder.start(title, mode, **kw)
        return self.recorder.stop()

    def transcribed(self, meeting: Meeting) -> Meeting:
        self.run_jobs()
        return self.store.get(meeting.id)


@pytest.fixture
def rig(tmp_path: Path) -> Rig:
    return Rig(tmp_path)


def test_mic_meeting_is_transcribing_after_stop(rig: Rig) -> None:
    started = rig.recorder.start("Weekly sync", "mic")
    assert started.id == "2026-11-11-1430-weekly-sync"
    assert started.status == Status.RECORDING
    assert set(rig.capture.paths) == {"mic"}
    rig.clock.now = T0 + timedelta(seconds=90)
    meeting = rig.recorder.stop()
    assert meeting.status == Status.TRANSCRIBING
    assert meeting.duration == 90
    assert len(rig.jobs) == 1
    assert rig.store.get(meeting.id).status == Status.TRANSCRIBING
    assert rig.recorder.status() == {"recording": False}


def test_mic_and_system_has_both_tracks(rig: Rig) -> None:
    meeting = rig.record("Client call", "mic+system")
    assert set(rig.capture.paths) == {"mic", "system"}
    assert meeting.tracks == ["mic", "system"]


def test_second_start_refused(rig: Rig) -> None:
    rig.recorder.start("One", "mic")
    with pytest.raises(RecordingInProgress):
        rig.recorder.start("Two", "mic")
    assert len(rig.store.ids()) == 1


def test_stop_without_recording(rig: Rig) -> None:
    with pytest.raises(NoRecording):
        rig.recorder.stop()


def test_capture_failure_leaves_nothing(rig: Rig) -> None:
    rig.capture.error = CaptureError("could not open loopback device")
    with pytest.raises(CaptureError, match="loopback"):
        rig.recorder.start("Call", "mic+system")
    assert rig.store.ids() == set()
    assert rig.recorder.status() == {"recording": False}


def test_unexpected_capture_error_is_wrapped(rig: Rig) -> None:
    rig.capture.error = OSError("device busy")
    with pytest.raises(CaptureError, match="device busy"):
        rig.recorder.start("Call", "mic")
    assert rig.store.ids() == set()


def test_same_title_same_minute_gets_suffix(rig: Rig) -> None:
    rig.clock.now = datetime(2026, 11, 11, 9, 0)
    first = rig.record("Standup")
    second = rig.record("Standup")
    assert (first.id, second.id) == ("2026-11-11-0900-standup", "2026-11-11-0900-standup-2")


def test_empty_title_is_timestamp_only(rig: Rig) -> None:
    assert rig.recorder.start("  ", "mic").id == "2026-11-11-1430"


def test_online_call_transcript(rig: Rig) -> None:
    rig.whisper.by_track = {
        "mic": [Segment(0.0, 1.0, "Hi all"), Segment(5.0, 6.0, "Sounds good")],
        "system": [Segment(2.0, 3.0, "Hello, let's start"), Segment(7.0, 8.0, "Agreed")],
    }
    rig.diarizer.turns = {"system": [SpeakerTurn(1.5, 4.0, "A"), SpeakerTurn(6.5, 9.0, "B")]}
    meeting = rig.transcribed(rig.record("Call", "mic+system"))
    assert meeting.status == Status.TRANSCRIBED
    assert rig.diarizer.calls == ["system"]
    assert render_transcript(rig.store.load_transcript(meeting.id), {}) == (
        "[00:00] You: Hi all\n"
        "[00:02] Speaker 1: Hello, let's start\n"
        "[00:05] You: Sounds good\n"
        "[00:07] Speaker 2: Agreed"
    )


def test_in_person_diarized_labels(rig: Rig) -> None:
    rig.whisper.by_track = {"mic": [Segment(0.0, 1.0, "Let's begin"), Segment(3.0, 4.0, "Okay")]}
    rig.diarizer.turns = {"mic": [SpeakerTurn(0.0, 2.5, "X"), SpeakerTurn(2.8, 4.0, "Y")]}
    meeting = rig.transcribed(rig.record())
    assert render_transcript(rig.store.load_transcript(meeting.id), {}) == (
        "[00:00] Speaker 1: Let's begin\n[00:03] Speaker 2: Okay"
    )


def test_diarization_failure_falls_back_with_one_warning(rig: Rig) -> None:
    rig.whisper.by_track = {"mic": [Segment(0, 1, "a")], "system": [Segment(2, 3, "b")]}
    rig.diarizer.error = RuntimeError("model download failed")
    meeting = rig.transcribed(rig.record("Call", "mic+system"))
    assert meeting.status == Status.TRANSCRIBED
    assert meeting.warnings == ["speaker detection failed: model download failed"]
    segments = rig.store.load_transcript(meeting.id)
    assert [s.speaker for s in segments] == ["You", "Others"]


def test_stt_failure_keeps_audio(rig: Rig) -> None:
    rig.whisper.error = RuntimeError("out of memory")
    meeting = rig.transcribed(rig.record("Call", "mic+system"))
    assert meeting.status == Status.FAILED
    assert meeting.error == "out of memory"
    assert all(p.exists() for p in rig.capture.paths.values())


def test_retranscribe_failed_meeting(rig: Rig) -> None:
    rig.whisper.error = RuntimeError("boom")
    meeting = rig.transcribed(rig.record())
    rig.whisper.error = None
    rig.whisper.by_track = {"mic": [Segment(0, 1, "hello")]}
    again = rig.recorder.transcribe(meeting.id)
    assert again.status == Status.TRANSCRIBING and again.error is None
    done = rig.transcribed(again)
    assert done.status == Status.TRANSCRIBED
    assert [s.text for s in rig.store.load_transcript(done.id)] == ["hello"]


def test_retranscribe_clears_speaker_names_and_warnings(rig: Rig) -> None:
    rig.whisper.by_track = {"mic": [Segment(0, 1, "hi")]}
    rig.diarizer.turns = {"mic": [SpeakerTurn(0, 1, "A")]}
    meeting = rig.transcribed(rig.record())
    rig.store.save(
        Meeting.from_dict({**meeting.to_dict(), "speaker_names": {"Speaker 1": "Nok"}, "warnings": ["w"]})
    )
    rig.recorder.transcribe(meeting.id)
    after = rig.store.get(meeting.id)
    assert after.speaker_names == {} and after.warnings == [] and after.detected_languages == {}
    assert rig.transcribed(after).speaker_names == {}


@pytest.mark.parametrize("language", ["th", "en"])
def test_language_passed_through_and_recorded(rig: Rig, language: str) -> None:
    meeting = rig.transcribed(rig.record(language=language))
    assert rig.whisper.calls == [("mic", language)]
    assert meeting.language == language


def test_auto_language_detects(rig: Rig) -> None:
    rig.whisper.detected = "th"
    meeting = rig.transcribed(rig.record(language="auto"))
    assert rig.whisper.calls == [("mic", None)]
    assert meeting.detected_languages == {"mic": "th"}


def test_retranscribe_with_language_replaces_transcript(rig: Rig) -> None:
    rig.whisper.by_track = {"mic": [Segment(0, 1, "old")]}
    meeting = rig.transcribed(rig.record(language="auto"))
    rig.whisper.by_track = {"mic": [Segment(0, 1, "new")]}
    rig.transcribed(rig.recorder.transcribe(meeting.id, language="th"))
    assert rig.whisper.calls[-1] == ("mic", "th")
    assert rig.store.get(meeting.id).language == "th"
    assert [s.text for s in rig.store.load_transcript(meeting.id)] == ["new"]


@pytest.mark.parametrize(
    "kwargs",
    [{"mode": "video"}, {"mode": "mic", "language": "fr"}],
)
def test_invalid_choices(rig: Rig, kwargs: dict) -> None:
    with pytest.raises(InvalidChoice):
        rig.recorder.start("x", **kwargs)
    assert rig.store.ids() == set()


def test_retranscribe_validates_and_guards(rig: Rig) -> None:
    meeting = rig.transcribed(rig.record())
    with pytest.raises(InvalidChoice):
        rig.recorder.transcribe(meeting.id, language="fr")
    with pytest.raises(MeetingNotFound):
        rig.recorder.transcribe("missing")
    active = rig.recorder.start("Live", "mic")
    with pytest.raises(InvalidTransition):
        rig.recorder.transcribe(active.id)


def test_stop_failure_still_finishes_meeting(rig: Rig) -> None:
    rig.capture.stop_error = RuntimeError("device lost")
    rig.recorder.start("x", "mic")
    meeting = rig.recorder.stop()
    assert meeting.status == Status.FAILED and meeting.error == "device lost"
    assert rig.recorder.status() == {"recording": False}
    assert rig.capture.paths["mic"].exists()


def test_recover_interrupted(rig: Rig) -> None:
    crashed = Meeting("crashed", "c", "mic", "auto", T0, Status.RECORDING)
    stuck = Meeting("stuck", "s", "mic", "auto", T0, Status.TRANSCRIBING)
    done = Meeting("done", "d", "mic", "auto", T0, Status.TRANSCRIBED)
    for m in (crashed, stuck, done):
        rig.store.create(m)
    assert sorted(rig.recorder.recover_interrupted()) == ["crashed", "stuck"]
    assert rig.store.get("crashed").status == Status.FAILED
    assert rig.store.get("crashed").error == "interrupted"
    assert rig.store.get("done").status == Status.TRANSCRIBED
    assert rig.transcribed(rig.recorder.transcribe("crashed")).status == Status.TRANSCRIBED


def test_recover_skips_active_recording(rig: Rig) -> None:
    active = rig.recorder.start("Live", "mic")
    assert rig.recorder.recover_interrupted() == []
    assert rig.store.get(active.id).status == Status.RECORDING


def test_status_reports_elapsed(rig: Rig) -> None:
    meeting = rig.recorder.start("Live", "mic", language="th")
    rig.clock.now = T0 + timedelta(seconds=12.5)
    assert rig.recorder.status() == {
        "recording": True,
        "meeting_id": meeting.id,
        "title": "Live",
        "mode": "mic",
        "language": "th",
        "elapsed": 12.5,
    }


def _two_speaker_meeting(rig: Rig) -> Meeting:
    rig.whisper.by_track = {"mic": [Segment(0, 1, "Let's begin"), Segment(3, 4, "Okay")]}
    rig.diarizer.turns = {"mic": [SpeakerTurn(0, 2.5, "X"), SpeakerTurn(2.8, 4, "Y")]}
    return rig.transcribed(rig.record())


def test_rename_speaker_persists_and_resets(rig: Rig) -> None:
    meeting = _two_speaker_meeting(rig)
    renamed = rig.recorder.rename_speaker(meeting.id, "Speaker 2", "Somchai")
    assert renamed.speaker_names == {"Speaker 2": "Somchai"}
    assert rig.store.get(meeting.id).speaker_names == {"Speaker 2": "Somchai"}
    assert rig.recorder.rename_speaker(meeting.id, "Speaker 2", "").speaker_names == {}


def test_rename_speaker_guards(rig: Rig) -> None:
    meeting = _two_speaker_meeting(rig)
    with pytest.raises(UnknownSpeaker):
        rig.recorder.rename_speaker(meeting.id, "Speaker 9", "x")
    pending = rig.record("Other")
    with pytest.raises(TranscriptNotReady):
        rig.recorder.rename_speaker(pending.id, "Speaker 1", "x")


def test_search_covers_transcribed_meetings_newest_first(rig: Rig) -> None:
    rig.whisper.by_track = {"mic": [Segment(2, 3, "Budget review")]}
    first = rig.transcribed(rig.record("A"))
    rig.clock.now = T0 + timedelta(hours=1)
    second = rig.transcribed(rig.record("B"))
    rig.record("C")  # still transcribing: skipped
    hits = rig.recorder.search("BUDGET")
    assert [h.meeting_id for h in hits] == [second.id, first.id]
    assert rig.recorder.search("nothing") == []
