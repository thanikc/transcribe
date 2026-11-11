"""Stand-ins for devices and models, for trying the UI with `transcribe serve --fake`."""

from __future__ import annotations

import time
import wave
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
    def stop(self) -> None:
        pass


class FakeCapture:
    def start(self, track_paths: dict[str, Path]) -> FakeSession:
        for path in track_paths.values():
            with wave.open(str(path), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(16000)
                w.writeframes(b"\x00\x00" * 16000)
        return FakeSession()


class FakeSpeechToText:
    def transcribe(
        self, wav: Path, language: str | None, on_progress: Callable[[float], None]
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
