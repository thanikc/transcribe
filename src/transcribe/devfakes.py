"""Stand-ins for devices and models, for trying the UI with `transcribe serve --fake`."""

from __future__ import annotations

import math
import time
from pathlib import Path
from typing import Callable

from transcribe.domain import Segment, SpeakerTurn

SEGMENTS = [
    Segment(0, 3, "สวัสดีครับ เริ่มประชุมกันเลย"),
    Segment(3, 6, "Let's start with the budget."),
    Segment(6, 9, "ได้ครับ งบประมาณปีนี้เพิ่มขึ้น"),
]
TURNS = [SpeakerTurn(0, 3, "A"), SpeakerTurn(3, 6, "B"), SpeakerTurn(6, 9, "A")]


class FakeSession:
    def __init__(self, tracks: list[str]) -> None:
        self.tracks = tracks

    def stop(self) -> None:
        pass

    def levels(self) -> dict[str, float]:
        # Speech-like: loud and quiet stretches; the system track stays silent to show "no sound".
        loud = abs(math.sin(time.monotonic() * 1.7)) * 0.6
        return {t: (loud if t == "mic" else 0.0) for t in self.tracks}


class FakeCapture:
    def start(self, track_paths: dict[str, Path]) -> FakeSession:
        from transcribe.capture import Mp3Writer

        for path in track_paths.values():
            with Mp3Writer(path) as mp3:
                mp3.write([0.0] * 16000)  # a second of silence
        return FakeSession(list(track_paths))


class FakeSpeechToText:
    def has_model(self, model: str) -> bool:
        return model == "large-v3"

    def transcribe(
        self, wav: Path, language: str | None, on_progress: Callable[[float], None], model: str, vocabulary: list[str]
    ) -> tuple[list[Segment], str]:
        time.sleep(2)  # model loading: no fraction yet
        for tenth in range(1, 11):
            time.sleep(0.4)
            on_progress(tenth / 10)
        return list(SEGMENTS), language or "th"


class FakeDiarizer:
    def diarize(self, wav: Path, on_progress: Callable[[float], None]) -> list[SpeakerTurn]:
        for quarter in range(1, 5):
            time.sleep(0.4)
            on_progress(quarter / 4)
        return list(TURNS)
