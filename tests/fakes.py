"""Fake ports shared by service-level tests."""

from __future__ import annotations

from pathlib import Path

from transcribe.domain import Segment, SpeakerTurn


class FakeSession:
    def stop(self) -> None:
        pass


class FakeCapture:
    def start(self, track_paths: dict[str, Path]) -> FakeSession:
        for path in track_paths.values():
            path.touch()
        return FakeSession()


class FakeSpeechToText:
    def __init__(self, segments: list[Segment] | None = None, detected: str = "en") -> None:
        self.segments = segments or []
        self.detected = detected
        self.error: Exception | None = None

    def transcribe(self, wav: Path, language: str | None) -> tuple[list[Segment], str]:
        if self.error:
            raise self.error
        return list(self.segments), self.detected


class FakeDiarizer:
    def __init__(self, turns: list[SpeakerTurn] | None = None, error: Exception | None = None) -> None:
        self.turns = turns or []
        self.error = error

    def diarize(self, wav: Path) -> list[SpeakerTurn]:
        if self.error:
            raise self.error
        return list(self.turns)
