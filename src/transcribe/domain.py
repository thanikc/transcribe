"""Meeting capture & transcription domain: pure logic over plain data, no I/O."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass, field, fields, replace
from datetime import datetime
from difflib import SequenceMatcher
from enum import StrEnum
from typing import Iterable, Literal

Mode = Literal["mic", "mic+system"]
Language = Literal["auto", "th", "en"]
Track = Literal["mic", "system"]

MODES: tuple[str, ...] = ("mic", "mic+system")
LANGUAGES: tuple[str, ...] = ("auto", "th", "en")
TRACKS: tuple[str, ...] = ("mic", "system")
# The speech models offered for choosing, with their download size.
MODELS: dict[str, str] = {"large-v3": "about 3 GB", "large-v3-turbo": "about 1.6 GB"}
# What to transcribe with when a model does not fit in memory: about half the size.
FALLBACK_MODELS: dict[str, str] = {"large-v3": "large-v3-turbo"}


class DomainError(Exception):
    """A refusal the user should see as-is."""


class RecordingInProgress(DomainError):
    def __init__(self) -> None:
        super().__init__("a recording is already in progress")


class NoRecording(DomainError):
    def __init__(self) -> None:
        super().__init__("no recording is in progress")


class MeetingNotFound(DomainError):
    def __init__(self, meeting_id: str) -> None:
        super().__init__(f'no meeting "{meeting_id}" exists')


class MeetingBusy(DomainError):
    """A meeting that is still recording or transcribing can't be deleted."""


class TranscriptNotReady(DomainError):
    def __init__(self, meeting_id: str, status: str) -> None:
        super().__init__(f'the transcript of "{meeting_id}" is not ready yet (status: {status})')


class UnknownSpeaker(DomainError):
    def __init__(self, speaker: str) -> None:
        super().__init__(f'there is no "{speaker}" in that meeting')


class InvalidTransition(DomainError):
    def __init__(self, old: str, new: str) -> None:
        super().__init__(f"cannot change status from {old} to {new}")


class UnknownTrack(DomainError):
    def __init__(self, meeting_id: str, track: str) -> None:
        super().__init__(f'meeting "{meeting_id}" has no track "{track}"')


class InvalidChoice(DomainError):
    """A mode, language or speech model outside the allowed values."""


class Status(StrEnum):
    RECORDING = "recording"
    TRANSCRIBING = "transcribing"
    TRANSCRIBED = "transcribed"
    FAILED = "failed"


_ALLOWED = {
    Status.RECORDING: {Status.TRANSCRIBING, Status.FAILED},
    Status.TRANSCRIBING: {Status.TRANSCRIBED, Status.FAILED},
    # Transcribing again (failed, or wrong language) restarts from transcribing.
    Status.TRANSCRIBED: {Status.TRANSCRIBING},
    Status.FAILED: {Status.TRANSCRIBING},
}


@dataclass(frozen=True)
class Segment:
    start: float
    end: float
    text: str
    speaker: str | None = None


@dataclass(frozen=True)
class SpeakerTurn:
    start: float
    end: float
    speaker: str


@dataclass(frozen=True)
class SearchHit:
    meeting_id: str
    title: str
    start: float
    speaker: str | None
    text: str


@dataclass(frozen=True)
class Meeting:
    id: str
    title: str
    mode: str
    language: str
    started_at: datetime
    status: Status
    duration: float | None = None
    error: str | None = None
    warnings: list[str] = field(default_factory=list)
    detected_languages: dict[str, str] = field(default_factory=dict)
    speaker_names: dict[str, str] = field(default_factory=dict)
    # The speech model chosen for it, then the one its transcript was made with. "" = the service default.
    model: str = ""

    @property
    def tracks(self) -> list[str]:
        return ["mic", "system"] if self.mode == "mic+system" else ["mic"]

    def to_dict(self) -> dict:
        data = asdict(self)
        data["started_at"] = self.started_at.isoformat()
        data["status"] = self.status.value
        return data

    @classmethod
    def from_dict(cls, data: dict) -> Meeting:
        known = {f.name for f in fields(cls)}
        return cls(
            **{
                # Drops keys no longer in Meeting, such as "engine" from older meetings.
                **{k: v for k, v in data.items() if k in known},
                "started_at": datetime.fromisoformat(data["started_at"]),
                "status": Status(data["status"]),
            }
        )


_TRACK_NAMES = {"mic": "microphone", "system": "system audio"}


@dataclass(frozen=True)
class TranscriptionStep:
    kind: Literal["transcribe", "diarize"]
    track: str

    @property
    def label(self) -> str:
        return f"Transcribing {_TRACK_NAMES[self.track]}" if self.kind == "transcribe" else "Detecting speakers"


def transcription_steps(mode: str) -> list[TranscriptionStep]:
    """Work done after a recording, in order. In mic+system mode the mic track is always "You"."""
    if mode == "mic+system":
        return [
            TranscriptionStep("transcribe", "mic"),
            TranscriptionStep("transcribe", "system"),
            TranscriptionStep("diarize", "system"),
        ]
    return [TranscriptionStep("transcribe", "mic"), TranscriptionStep("diarize", "mic")]


def meeting_id(title: str, started_at: datetime, existing: set[str]) -> str:
    """Start time + ASCII slug of the title, with -2, -3… if already taken."""
    slug = "-".join(re.findall(r"[a-z0-9]+", title.lower()))
    base = started_at.strftime("%Y-%m-%d-%H%M") + (f"-{slug}" if slug else "")
    candidate, n = base, 1
    while candidate in existing:
        n += 1
        candidate = f"{base}-{n}"
    return candidate


def transition(meeting: Meeting, new: Status, error: str | None = None) -> Meeting:
    if new not in _ALLOWED[meeting.status]:
        raise InvalidTransition(meeting.status, new)
    return replace(meeting, status=new, error=error if new == Status.FAILED else None)


def _overlap(segment: Segment, turn: SpeakerTurn) -> float:
    return min(segment.end, turn.end) - max(segment.start, turn.start)


def assign_speakers(segments: list[Segment], turns: list[SpeakerTurn]) -> list[str | None]:
    """Raw speaker label per segment: the turn overlapping it most (or the nearest one)."""
    if not turns:
        return [None] * len(segments)
    return [max(turns, key=lambda t: _overlap(s, t)).speaker for s in segments]


def label_track(
    segments: list[Segment], track: str, mode: str, turns: list[SpeakerTurn] | None
) -> list[Segment]:
    """Attach display speakers. `turns` is None when diarization did not run or failed."""
    if mode == "mic+system" and track == "mic":
        return [replace(s, speaker="You") for s in segments]
    if turns is None:
        fallback = "Others" if track == "system" else None
        return [replace(s, speaker=fallback) for s in segments]
    ordered = sorted(segments, key=lambda s: s.start)
    numbers: dict[str | None, str] = {}
    labelled = []
    for segment, raw in zip(ordered, assign_speakers(ordered, turns)):
        numbers.setdefault(raw, f"Speaker {len(numbers) + 1}")
        labelled.append(replace(segment, speaker=numbers[raw]))
    return labelled


def rename_speaker(
    names: dict[str, str], segments: list[Segment], speaker: str, name: str
) -> dict[str, str]:
    if speaker not in {s.speaker for s in segments}:
        raise UnknownSpeaker(speaker)
    updated = {k: v for k, v in names.items() if k != speaker}
    if name.strip():
        updated[speaker] = name.strip()
    return updated


# How far apart the two tracks' timings of one utterance can be, and how much of a mic line has to
# appear in the system audio for it to count as the mic hearing the speakers.
ECHO_WINDOW = 1.0
ECHO_SHARE = 0.6
# Shared letters count only in runs this long: stray single letters are found in any sentence.
ECHO_RUN = 3


def _letters(text: str) -> str:
    """Letters, marks (Thai vowels and tones) and digits only, case-folded: what two transcriptions of one
    utterance share regardless of punctuation and spacing."""
    return "".join(c for c in text.casefold() if unicodedata.category(c)[0] in "LMN")


def drop_echoes(mic: list[Segment], system: list[Segment]) -> tuple[list[Segment], int]:
    """Mic segments without the ones that repeat concurrent system audio, and how many were dropped.

    Without headphones the mic hears the speakers, so remote speech is transcribed from both tracks.
    """
    kept = []
    for segment in mic:
        heard = _letters(segment.text)
        nearby = "".join(
            _letters(s.text)
            for s in system
            if s.end >= segment.start - ECHO_WINDOW and s.start <= segment.end + ECHO_WINDOW
        )
        if heard and nearby:
            blocks = SequenceMatcher(None, heard, nearby, autojunk=False).get_matching_blocks()
            shared = sum(b.size for b in blocks if b.size >= ECHO_RUN)
            if shared >= ECHO_SHARE * len(heard):
                continue
        kept.append(segment)
    return kept, len(mic) - len(kept)


def merge_transcript(tracks: dict[str, list[Segment]]) -> list[Segment]:
    return sorted((s for segs in tracks.values() for s in segs), key=lambda s: s.start)


def timestamp(seconds: float) -> str:
    minutes, secs = divmod(int(seconds), 60)
    return f"[{minutes:02d}:{secs:02d}]"


def render_transcript(segments: list[Segment], speaker_names: dict[str, str]) -> str:
    lines = []
    for s in segments:
        speaker = speaker_names.get(s.speaker, s.speaker) if s.speaker else None
        lines.append(f"{timestamp(s.start)} {speaker}: {s.text}" if speaker else f"{timestamp(s.start)} {s.text}")
    return "\n".join(lines)


def search_transcripts(
    transcripts: Iterable[tuple[Meeting, list[Segment]]], query: str
) -> list[SearchHit]:
    needle = query.casefold()
    return [
        SearchHit(
            meeting.id,
            meeting.title,
            s.start,
            meeting.speaker_names.get(s.speaker, s.speaker) if s.speaker else None,
            s.text,
        )
        for meeting, segments in transcripts
        for s in segments
        if needle in s.text.casefold()
    ]

