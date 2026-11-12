from datetime import datetime

import pytest

from transcribe.domain import (
    InvalidTransition,
    Meeting,
    Segment,
    SpeakerTurn,
    Status,
    UnknownSpeaker,
    Word,
    drop_echoes,
    label_track,
    meeting_id,
    merge_transcript,
    render_transcript,
    rename_speaker,
    search_transcripts,
    split_at_turns,
    transcription_steps,
    transition,
)

AT_1430 = datetime(2026, 11, 11, 14, 30)


def make_meeting(**overrides) -> Meeting:
    fields = dict(
        id="2026-11-11-1430-weekly-sync",
        title="Weekly sync",
        mode="mic",
        language="auto",
        started_at=AT_1430,
        status=Status.TRANSCRIBED,
    )
    fields.update(overrides)
    return Meeting(**fields)


# --- meeting id ---


def test_meeting_id_is_start_time_plus_ascii_slug():
    assert meeting_id("Weekly sync", AT_1430, set()) == "2026-11-11-1430-weekly-sync"


def test_thai_title_gives_timestamp_only_id():
    assert meeting_id("ประชุมทีม", AT_1430, set()) == "2026-11-11-1430"


def test_mixed_title_keeps_only_ascii_words():
    assert meeting_id("Q4 งบ Budget!", AT_1430, set()) == "2026-11-11-1430-q4-budget"


def test_same_id_in_same_minute_gets_numeric_suffix():
    at = datetime(2026, 11, 11, 9, 0)
    first = meeting_id("Standup", at, set())
    second = meeting_id("Standup", at, {first})
    third = meeting_id("Standup", at, {first, second})
    assert (first, second, third) == (
        "2026-11-11-0900-standup",
        "2026-11-11-0900-standup-2",
        "2026-11-11-0900-standup-3",
    )


# --- meeting ---


def test_meeting_tracks_follow_capture_mode():
    assert make_meeting(mode="mic").tracks == ["mic"]
    assert make_meeting(mode="mic+system").tracks == ["mic", "system"]


def test_meeting_round_trips_through_dict():
    meeting = make_meeting(
        title="ประชุมทีม",
        duration=12.5,
        warnings=["w"],
        detected_languages={"mic": "th"},
        speaker_names={"Speaker 1": "Somchai"},
    )
    assert Meeting.from_dict(meeting.to_dict()) == meeting


# --- status transitions ---


@pytest.mark.parametrize(
    "old,new",
    [
        (Status.RECORDING, Status.TRANSCRIBING),
        (Status.RECORDING, Status.FAILED),
        (Status.TRANSCRIBING, Status.TRANSCRIBED),
        (Status.TRANSCRIBING, Status.FAILED),
        (Status.FAILED, Status.TRANSCRIBING),
        (Status.TRANSCRIBED, Status.TRANSCRIBING),
    ],
)
def test_allowed_status_transitions(old, new):
    assert transition(make_meeting(status=old), new).status == new


@pytest.mark.parametrize(
    "old,new",
    [
        (Status.TRANSCRIBED, Status.RECORDING),
        (Status.FAILED, Status.TRANSCRIBED),
        (Status.RECORDING, Status.TRANSCRIBED),
    ],
)
def test_backward_status_transitions_are_refused(old, new):
    with pytest.raises(InvalidTransition):
        transition(make_meeting(status=old), new)


def test_failing_records_the_error_and_retrying_clears_it():
    failed = transition(make_meeting(status=Status.TRANSCRIBING), Status.FAILED, error="boom")
    assert failed.error == "boom"
    assert transition(failed, Status.TRANSCRIBING).error is None


# --- speakers ---


def test_segment_spanning_a_speaker_change_goes_to_majority_speaker():
    turns = [SpeakerTurn(9.0, 11.0, "A"), SpeakerTurn(11.0, 15.0, "B")]
    assert split_at_turns(Segment(10.0, 14.0, "x"), turns) == [(Segment(10.0, 14.0, "x"), "B")]


def test_segment_with_no_overlapping_turn_goes_to_nearest_turn():
    turns = [SpeakerTurn(0.0, 1.0, "A"), SpeakerTurn(6.5, 9.0, "B")]
    assert split_at_turns(Segment(5.0, 6.0, "x"), turns) == [(Segment(5.0, 6.0, "x"), "B")]


def test_online_call_mic_is_you_and_system_is_numbered_by_first_appearance():
    system = [Segment(2.0, 4.0, "Hello"), Segment(7.0, 8.0, "Agreed")]
    turns = [SpeakerTurn(1.5, 4.0, "Z"), SpeakerTurn(6.5, 9.0, "A")]
    labelled = label_track(system, "system", "mic+system", turns)
    assert [s.speaker for s in labelled] == ["Speaker 1", "Speaker 2"]
    mic = label_track([Segment(0.0, 1.0, "Hi")], "mic", "mic+system", None)
    assert mic[0].speaker == "You"


def test_diarization_failure_falls_back_to_track_labels():
    system = label_track([Segment(0.0, 1.0, "x")], "system", "mic+system", None)
    mic = label_track([Segment(0.0, 1.0, "x")], "mic", "mic", None)
    assert system[0].speaker == "Others"
    assert mic[0].speaker is None


def test_rename_speaker_and_empty_name_resets():
    segments = [Segment(0, 1, "a", "Speaker 1"), Segment(1, 2, "b", "Speaker 2")]
    names = rename_speaker({}, segments, "Speaker 2", "Somchai")
    assert names == {"Speaker 2": "Somchai"}
    assert rename_speaker(names, segments, "Speaker 2", "") == {}


def test_renaming_an_unknown_speaker_is_refused():
    segments = [Segment(0, 1, "a", "Speaker 1"), Segment(1, 2, "b", "Speaker 2")]
    with pytest.raises(UnknownSpeaker, match="Speaker 9"):
        rename_speaker({}, segments, "Speaker 9", "X")


# --- transcript ---


def test_transcript_interleaves_tracks_by_time_and_renders():
    mic = [Segment(0.0, 1.0, "Hi all", "You"), Segment(5.0, 6.0, "Sounds good", "You")]
    system = [
        Segment(2.0, 4.0, "Hello, let's start", "Speaker 1"),
        Segment(7.0, 8.0, "Agreed", "Speaker 2"),
    ]
    transcript = merge_transcript({"mic": mic, "system": system})
    assert render_transcript(transcript, {}) == (
        "[00:00] You: Hi all\n"
        "[00:02] Speaker 1: Hello, let's start\n"
        "[00:05] You: Sounds good\n"
        "[00:07] Speaker 2: Agreed"
    )


def test_render_applies_speaker_names_and_omits_missing_speaker():
    segments = [Segment(0.0, 1.0, "สวัสดีครับ"), Segment(630.0, 631.0, "hi", "Speaker 2")]
    assert render_transcript(segments, {"Speaker 2": "Somchai"}) == (
        "[00:00] สวัสดีครับ\n[10:30] Somchai: hi"
    )


# --- search ---


def test_search_is_case_insensitive_with_hits_carrying_context():
    a = make_meeting(id="a")
    b = make_meeting(id="b", speaker_names={"Speaker 1": "Nok"})
    hits = search_transcripts(
        [
            (a, [Segment(65.0, 66.0, "Budget", "You")]),
            (b, [Segment(1.0, 2.0, "budget review", "Speaker 1"), Segment(3, 4, "other")]),
        ],
        "BUDGET",
    )
    assert [(h.meeting_id, h.start, h.speaker, h.text) for h in hits] == [
        ("a", 65.0, "You", "Budget"),
        ("b", 1.0, "Nok", "budget review"),
    ]
    assert {h.title for h in hits} == {make_meeting().title}


def test_search_finds_thai_substrings():
    hits = search_transcripts([(make_meeting(), [Segment(0, 1, "งบประมาณไตรมาสหน้า")])], "งบประมาณ")
    assert len(hits) == 1


@pytest.mark.parametrize(
    "mode, labels",
    [
        ("mic", ["Transcribing microphone", "Detecting speakers"]),
        ("mic+system", ["Transcribing microphone", "Transcribing system audio", "Detecting speakers"]),
        ("file", ["Transcribing audio file", "Detecting speakers"]),
    ],
)
def test_transcription_steps_of_each_mode(mode: str, labels: list[str]) -> None:
    assert [step.label for step in transcription_steps(mode)] == labels


def test_mic_line_repeating_system_audio_at_the_same_time_is_an_echo() -> None:
    system = [Segment(3.0, 6.0, "Let's start with the budget.")]
    assert drop_echoes([Segment(3.2, 6.1, "let's start with the budget")], system) == ([], 1)


def test_echo_is_found_across_differently_split_lines() -> None:
    system = [Segment(3.0, 4.0, "Let's start"), Segment(4.0, 6.0, "with the budget.")]
    assert drop_echoes([Segment(3.1, 6.0, "let's start with the budget")], system) == ([], 1)


def test_thai_echo_is_found() -> None:
    system = [Segment(6.0, 9.0, "งบประมาณปีนี้เพิ่มขึ้น")]
    assert drop_echoes([Segment(6.1, 9.0, "งบประมาณปีนี้เพิ่มขึ้นครับ")], system) == ([], 1)


def test_my_own_words_over_system_audio_are_kept() -> None:
    mine = Segment(7.0, 8.0, "I disagree")
    assert drop_echoes([mine], [Segment(6.5, 8.5, "the numbers look fine")]) == ([mine], 0)


def test_same_words_at_another_time_are_kept() -> None:
    mine = Segment(40.0, 41.0, "sounds good")
    assert drop_echoes([mine], [Segment(10.0, 11.0, "sounds good")]) == ([mine], 0)


def test_echo_tolerates_a_second_of_timing_difference_only() -> None:
    system = [Segment(10.0, 12.0, "the deadline is Friday")]
    assert drop_echoes([Segment(12.8, 14.0, "the deadline is Friday")], system) == ([], 1)
    late = Segment(13.5, 15.0, "the deadline is Friday")
    assert drop_echoes([late], system) == ([late], 0)


def test_a_line_without_letters_is_not_an_echo() -> None:
    mine = Segment(1.0, 2.0, "...")
    assert drop_echoes([mine], [Segment(1.0, 2.0, "...")]) == ([mine], 0)


def test_a_short_line_sharing_stray_letters_is_not_an_echo() -> None:
    mine = Segment(0.0, 1.0, "Hi all")
    assert drop_echoes([mine], [Segment(2.0, 3.0, "Hello, let's start")]) == ([mine], 0)


def _words(*spans: tuple[float, float, str]) -> tuple[Word, ...]:
    return tuple(Word(start, end, text) for start, end, text in spans)


def test_a_line_spanning_two_speakers_is_split_between_them():
    words = _words((0, 0.5, " Is"), (0.5, 1, " the"), (1, 1.8, " budget"), (1.8, 2.8, " ready?"),
                   (3.1, 3.8, " Yes,"), (3.8, 4.5, " it's"), (4.5, 6, " done."))
    line = Segment(0, 6, "Is the budget ready? Yes, it's done.", words=words)
    turns = [SpeakerTurn(0, 3, "A"), SpeakerTurn(3, 6, "B")]
    assert label_track([line], "mic", "mic", turns) == [
        Segment(0, 2.8, "Is the budget ready?", "Speaker 1"),
        Segment(3.1, 6, "Yes, it's done.", "Speaker 2"),
    ]


def test_a_short_blip_of_another_speaker_does_not_split_the_line():
    words = _words((0, 2, " We"), (2, 2.6, " should"), (2.6, 4, " ship"), (4, 6, " Friday."))
    line = Segment(0, 6, "We should ship Friday.", words=words)
    turns = [SpeakerTurn(0, 2, "A"), SpeakerTurn(2, 2.6, "B"), SpeakerTurn(2.6, 6, "A")]
    assert label_track([line], "mic", "mic", turns) == [Segment(0, 6, "We should ship Friday.", "Speaker 1")]


def test_split_thai_words_are_joined_without_spaces():
    words = _words((0, 1, "งบ"), (1, 2, "ประมาณ"), (2, 3, "ปีนี้"), (3, 4, " OK"), (4, 5, " ครับ"))
    line = Segment(0, 5, "งบประมาณปีนี้ OK ครับ", words=words)
    turns = [SpeakerTurn(0, 3, "A"), SpeakerTurn(3, 5, "B")]
    assert [(s.text, s.speaker) for s in label_track([line], "mic", "mic", turns)] == [
        ("งบประมาณปีนี้", "Speaker 1"), ("OK ครับ", "Speaker 2"),
    ]


def test_a_line_without_word_times_keeps_the_whole_line_rule():
    turns = [SpeakerTurn(9.0, 11.0, "A"), SpeakerTurn(11.0, 15.0, "B")]
    assert label_track([Segment(10.0, 14.0, "x")], "mic", "mic", turns) == [Segment(10.0, 14.0, "x", "Speaker 1")]


def test_online_call_mic_lines_stay_whole_and_you():
    line = Segment(0, 6, "a b", words=_words((0, 3, " a"), (3, 6, " b")))
    assert label_track([line], "mic", "mic+system", None) == [Segment(0, 6, "a b", "You")]


def test_segments_are_stored_without_their_words():
    line = Segment(0, 1, "a", "Speaker 1", words=_words((0, 1, " a")))
    assert line.to_dict() == {"start": 0, "end": 1, "text": "a", "speaker": "Speaker 1"}


def test_an_imported_file_has_one_track_labelled_like_an_in_person_meeting():
    assert make_meeting(mode="file").tracks == ["file"]
    turns = [SpeakerTurn(0, 2, "A")]
    assert label_track([Segment(0, 1, "x")], "file", "file", turns)[0].speaker == "Speaker 1"
    assert label_track([Segment(0, 1, "x")], "file", "file", None)[0].speaker is None
