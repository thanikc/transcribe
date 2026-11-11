"""Filesystem store: one folder per meeting holding meeting.json, transcript.json and audio."""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import asdict
from pathlib import Path

from transcribe.domain import (
    Meeting,
    MeetingNotFound,
    Segment,
    Status,
    TranscriptNotReady,
    UnknownTrack,
)


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

    def get(self, meeting_id: str) -> Meeting:
        folder = self._folder(meeting_id)
        try:
            data = json.loads((folder / "meeting.json").read_text(encoding="utf-8"))
            return Meeting.from_dict(data)
        except (OSError, ValueError, KeyError, TypeError):
            raise MeetingNotFound(meeting_id) from None

    def list(self) -> list[Meeting]:
        meetings = []
        for meeting_id in self.ids():
            try:
                meetings.append(self.get(meeting_id))
            except MeetingNotFound:
                continue
        return sorted(meetings, key=lambda m: m.started_at, reverse=True)

    def ids(self) -> set[str]:
        return {p.name for p in self.data_dir.iterdir() if p.is_dir()}

    def delete(self, meeting_id: str) -> None:
        shutil.rmtree(self._folder(meeting_id))

    def track_path(self, meeting_id: str, track: str) -> Path:
        meeting = self.get(meeting_id)
        if track not in meeting.tracks:
            raise UnknownTrack(meeting_id, track)
        return self.data_dir / meeting_id / f"{track}.wav"

    def save_transcript(self, meeting_id: str, segments: list[Segment]) -> None:
        folder = self._folder(meeting_id)
        self._write_json(folder / "transcript.json", [asdict(s) for s in segments])

    def load_transcript(self, meeting_id: str) -> list[Segment]:
        meeting = self.get(meeting_id)
        if meeting.status != Status.TRANSCRIBED:
            raise TranscriptNotReady(meeting_id, meeting.status.value)
        raw = json.loads((self.data_dir / meeting_id / "transcript.json").read_text(encoding="utf-8"))
        return [Segment(**item) for item in raw]
