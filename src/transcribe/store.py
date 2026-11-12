"""Filesystem store: one folder per meeting holding meeting.json, transcript.json and audio."""

from __future__ import annotations

import json
import os
import re
import shutil
import stat
from pathlib import Path
from typing import Iterator

from transcribe.domain import (
    Meeting,
    MeetingNotFound,
    Segment,
    Status,
    TranscriptNotReady,
    UnknownTrack,
)

# What JSON writes as an escape even with ensure_ascii=False: a query holding one of these
# does not appear in the file the way it was typed.
_JSON_ESCAPED = re.compile(r'[\x00-\x1f"\\]')


def _file_size(path: Path) -> int | None:
    """Size of a regular file, None if there is none. One stat call."""
    try:
        info = os.stat(path)
    except OSError:
        return None
    return info.st_size if stat.S_ISREG(info.st_mode) else None


def _segments(raw: str) -> list[Segment]:
    return [Segment(**item) for item in json.loads(raw)]


class MeetingStore:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def _folder(self, meeting_id: str) -> Path:
        # Only exact child folder names are accepted, which rules out path traversal.
        if meeting_id not in os.listdir(self.data_dir):
            raise MeetingNotFound(meeting_id)
        return self.data_dir / meeting_id

    def _write_json(self, path: Path, data: object) -> None:
        # Write-then-rename so a crash never leaves a half-written file.
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)

    def create(self, meeting: Meeting) -> None:
        (self.data_dir / meeting.id).mkdir()
        self.save(meeting)

    def save(self, meeting: Meeting) -> None:
        self._write_json(self.data_dir / meeting.id / "meeting.json", meeting.to_dict())

    def _read(self, folder_name: str) -> Meeting:
        """The meeting in a folder of the data dir. The name must come from a listing, or be checked first."""
        try:
            data = json.loads((self.data_dir / folder_name / "meeting.json").read_text(encoding="utf-8"))
            return Meeting.from_dict(data)
        except (OSError, ValueError, KeyError, TypeError):
            raise MeetingNotFound(folder_name) from None

    def get(self, meeting_id: str) -> Meeting:
        self._folder(meeting_id)
        return self._read(meeting_id)

    def _scan(self) -> list[tuple[str, Meeting]]:
        """(folder name, meeting) for every readable meeting, newest first, from one listing of the data dir."""
        found = []
        for name in os.listdir(self.data_dir):
            try:
                found.append((name, self._read(name)))
            except MeetingNotFound:  # a stray file, the models folder, a corrupt meeting.json
                continue
        return sorted(found, key=lambda entry: entry[1].started_at, reverse=True)

    def list(self) -> list[Meeting]:
        return [meeting for _, meeting in self._scan()]

    def ids(self) -> set[str]:
        return {p.name for p in self.data_dir.iterdir() if p.is_dir()}

    def delete(self, meeting_id: str) -> None:
        shutil.rmtree(self._folder(meeting_id))

    def track_path(self, meeting_id: str, track: str) -> Path:
        meeting = self.get(meeting_id)
        if track not in meeting.tracks:
            raise UnknownTrack(meeting_id, track)
        return self._track_file(meeting_id, track)

    def _track_file(self, meeting_id: str, track: str) -> Path:
        folder = self.data_dir / meeting_id
        # Meetings recorded before the switch to MP3 have WAV tracks.
        legacy = folder / f"{track}.wav"
        mp3 = folder / f"{track}.mp3"
        return legacy if legacy.exists() and not mp3.exists() else mp3

    def audio_bytes(self, meeting: Meeting) -> int:
        """Total size of the meeting's audio files on disk; missing tracks count as 0."""
        folder = self.data_dir / meeting.id
        total = 0
        for track in meeting.tracks:
            size = _file_size(folder / f"{track}.mp3")
            if size is None:  # a meeting from before MP3
                size = _file_size(folder / f"{track}.wav")
            total += size or 0
        return total

    def save_notes(self, meeting_id: str, notes: str) -> None:
        """Replace the meeting's notes.md; blank notes remove it."""
        path = self._folder(meeting_id) / "notes.md"
        if notes.strip():
            tmp = path.with_name(path.name + ".tmp")
            tmp.write_text(notes, encoding="utf-8")
            os.replace(tmp, path)
        else:
            path.unlink(missing_ok=True)

    def load_notes(self, meeting_id: str) -> str | None:
        try:
            return (self._folder(meeting_id) / "notes.md").read_text(encoding="utf-8")
        except FileNotFoundError:
            return None

    def save_transcript(self, meeting_id: str, segments: list[Segment]) -> None:
        folder = self._folder(meeting_id)
        self._write_json(folder / "transcript.json", [s.to_dict() for s in segments])

    def load_transcript(self, meeting_id: str) -> list[Segment]:
        meeting = self.get(meeting_id)
        if meeting.status != Status.TRANSCRIBED:
            raise TranscriptNotReady(meeting_id, meeting.status.value)
        return _segments((self.data_dir / meeting_id / "transcript.json").read_text(encoding="utf-8"))

    def transcripts(self, mentioning: str) -> Iterator[tuple[Meeting, list[Segment]]]:
        """Every transcribed meeting with its segments, newest first, for searching.

        Leaves out transcripts that cannot contain `mentioning` in any letter case, judged from the raw
        file, so a search parses only the files that can match. A transcript that can't be read is left out.
        """
        needle = mentioning.casefold()
        for name, meeting in self._scan():
            if meeting.status != Status.TRANSCRIBED:
                continue
            try:
                raw = (self.data_dir / name / "transcript.json").read_text(encoding="utf-8")
                # Segment text is in the file as spoken, apart from JSON escapes. Without any in the query
                # or \u ones in the file, a query missing from the file is missing from every segment.
                if not _JSON_ESCAPED.search(needle) and "\\u" not in raw and needle not in raw.casefold():
                    continue
                yield meeting, _segments(raw)
            except (OSError, ValueError, TypeError):
                continue
