"""Fake ports shared by service-level tests."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

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
        self.during: Callable[[Callable[[float], None]], None] = lambda on_progress: None

    def transcribe(
        self, wav: Path, language: str | None, on_progress: Callable[[float], None]
    ) -> tuple[list[Segment], str]:
        self.during(on_progress)
        if self.error:
            raise self.error
        return list(self.segments), self.detected


class FakeDiarizer:
    def __init__(self, turns: list[SpeakerTurn] | None = None, error: Exception | None = None) -> None:
        self.turns = turns or []
        self.error = error

    def diarize(self, wav: Path, on_progress: Callable[[float], None]) -> list[SpeakerTurn]:
        if self.error:
            raise self.error
        return list(self.turns)
