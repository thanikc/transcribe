"""Fake ports shared by service-level tests."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from transcribe.domain import Segment, SpeakerTurn
from transcribe.recorder import OutOfMemory


class FakeSession:
    def stop(self) -> None:
        pass

    def levels(self) -> dict[str, float]:
        return {}


class FakeCapture:
    def start(self, track_paths: dict[str, Path]) -> FakeSession:
        for path in track_paths.values():
            path.touch()
        return FakeSession()


class FakeConverter:
    """Reads any file as 42 seconds of audio, except one starting with "not audio"."""

    def convert(self, source: Path, dest: Path) -> float:
        if source.read_bytes().startswith(b"not audio"):
            raise ValueError("Invalid data found when processing input")
        dest.write_bytes(b"mp3")
        return 42.0


class FakeSpeechToText:
    def __init__(self, segments: list[Segment] | None = None, detected: str = "en") -> None:
        self.segments = segments or []
        self.detected = detected
        self.error: Exception | None = None
        self.during: Callable[[Callable[[float], None]], None] = lambda on_progress: None
        self.too_big: set[str] = set()  # models that don't fit in memory
        self.downloaded: set[str] = {"large-v3"}
        self.used: list[str] = []

    def has_model(self, model: str) -> bool:
        return model in self.downloaded

    def transcribe(
        self, wav: Path, language: str | None, on_progress: Callable[[float], None], model: str, vocabulary: list[str]
    ) -> tuple[list[Segment], str]:
        self.used.append(model)
        if model in self.too_big:
            raise OutOfMemory(model)
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
