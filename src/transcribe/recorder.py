"""Recorder service: start/stop/transcribe/recover orchestration over the ports."""

from __future__ import annotations

import threading
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Callable, Protocol

from transcribe.domain import (
    LANGUAGES,
    MODES,
    DomainError,
    InvalidChoice,
    InvalidTransition,
    Meeting,
    NoRecording,
    RecordingInProgress,
    SearchHit,
    Segment,
    SpeakerTurn,
    Status,
    label_track,
    meeting_id,
    merge_transcript,
    rename_speaker,
    search_transcripts,
    transition,
)
from transcribe.store import MeetingStore


class CaptureError(DomainError):
    """An audio device could not be opened."""


class CaptureSession(Protocol):
    def stop(self) -> None:
        """Stop all tracks and close their WAV files."""


class AudioCapture(Protocol):
    def start(self, track_paths: dict[str, Path]) -> CaptureSession:
        """Start streaming each track to its WAV file. Raises CaptureError if a device can't open."""


class SpeechToText(Protocol):
    def transcribe(self, wav: Path, language: str | None) -> tuple[list[Segment], str]:
        """Track WAV + language (None = detect) -> (segments without speakers, detected language)."""


class SpeakerDiarizer(Protocol):
    def diarize(self, wav: Path) -> list[SpeakerTurn]:
        """Track WAV -> speaker turns with raw labels."""


def _in_thread(job: Callable[[], None]) -> None:
    threading.Thread(target=job, daemon=True).start()


class Recorder:
    def __init__(
        self,
        store: MeetingStore,
        capture: AudioCapture,
        stt: SpeechToText,
        diarizer: SpeakerDiarizer,
        clock: Callable[[], datetime] = datetime.now,
        run_in_background: Callable[[Callable[[], None]], None] = _in_thread,
    ) -> None:
        self.store = store
        self.capture = capture
        self.stt = stt
        self.diarizer = diarizer
        self.clock = clock
        self.run_in_background = run_in_background
        self._lock = threading.Lock()
        self._active: tuple[Meeting, CaptureSession] | None = None

    def _check_language(self, language: str) -> None:
        if language not in LANGUAGES:
            raise InvalidChoice(f'language must be one of {", ".join(LANGUAGES)}, not "{language}"')

    def status(self) -> dict:
        with self._lock:
            if self._active is None:
                return {"recording": False}
            meeting = self._active[0]
            return {
                "recording": True,
                "meeting_id": meeting.id,
                "title": meeting.title,
                "mode": meeting.mode,
                "language": meeting.language,
                "elapsed": (self.clock() - meeting.started_at).total_seconds(),
            }

    def start(self, title: str, mode: str, language: str = "auto") -> Meeting:
        if mode not in MODES:
            raise InvalidChoice(f'mode must be one of {", ".join(MODES)}, not "{mode}"')
        self._check_language(language)
        with self._lock:
            if self._active is not None:
                raise RecordingInProgress()
            now = self.clock()
            title = title.strip()
            meeting = Meeting(
                meeting_id(title, now, self.store.ids()), title, mode, language, now, Status.RECORDING
            )
            self.store.create(meeting)
            try:
                session = self.capture.start(
                    {track: self.store.track_path(meeting.id, track) for track in meeting.tracks}
                )
            except Exception as e:
                self.store.delete(meeting.id)
                if isinstance(e, CaptureError):
                    raise
                raise CaptureError(str(e)) from e
            self._active = (meeting, session)
            return meeting

    def stop(self) -> Meeting:
        with self._lock:
            if self._active is None:
                raise NoRecording()
            meeting, session = self._active
            self._active = None
            duration = (self.clock() - meeting.started_at).total_seconds()
            try:
                session.stop()
            except Exception as e:
                # Keep whatever audio was written so it can be transcribed again.
                failed = replace(transition(meeting, Status.FAILED, str(e)), duration=duration)
                self.store.save(failed)
                return failed
            meeting = replace(transition(meeting, Status.TRANSCRIBING), duration=duration)
            self.store.save(meeting)
        self.run_in_background(lambda: self._transcribe_job(meeting.id))
        return meeting

    def transcribe(self, meeting_id: str, language: str | None = None) -> Meeting:
        if language is not None:
            self._check_language(language)
        # Locked so two simultaneous requests can't both start a job for the same meeting.
        with self._lock:
            meeting = self.store.get(meeting_id)
            if meeting.status == Status.RECORDING:
                # The domain allows recording -> transcribing for stop(), not for a re-run.
                raise InvalidTransition(meeting.status, Status.TRANSCRIBING)
            meeting = transition(meeting, Status.TRANSCRIBING)
            meeting = replace(
                meeting,
                language=language or meeting.language,
                speaker_names={},
                warnings=[],
                detected_languages={},
            )
            self.store.save(meeting)
        self.run_in_background(lambda: self._transcribe_job(meeting.id))
        return meeting

    def rename_speaker(self, meeting_id: str, speaker: str, name: str) -> Meeting:
        with self._lock:
            meeting = self.store.get(meeting_id)
            segments = self.store.load_transcript(meeting_id)
            names = rename_speaker(meeting.speaker_names, segments, speaker, name)
            meeting = replace(meeting, speaker_names=names)
            self.store.save(meeting)
            return meeting

    def search(self, query: str) -> list[SearchHit]:
        transcripts = [
            (m, self.store.load_transcript(m.id)) for m in self.store.list() if m.status == Status.TRANSCRIBED
        ]
        return search_transcripts(transcripts, query)

    def recover_interrupted(self) -> list[str]:
        with self._lock:
            active_id = self._active[0].id if self._active else None
            stale = [
                m
                for m in self.store.list()
                if m.status in (Status.RECORDING, Status.TRANSCRIBING) and m.id != active_id
            ]
            for m in stale:
                self.store.save(transition(m, Status.FAILED, "interrupted"))
            return [m.id for m in stale]

    def _transcribe_job(self, meeting_id: str) -> None:
        """Runs in the background: never raises, failures land on the meeting."""
        try:
            meeting = self.store.get(meeting_id)
            try:
                self._run_transcription(meeting)
            except Exception as e:
                self.store.save(transition(self.store.get(meeting_id), Status.FAILED, str(e)))
        except Exception:
            pass

    def _run_transcription(self, meeting: Meeting) -> None:
        language = None if meeting.language == "auto" else meeting.language
        detected: dict[str, str] = {}
        warnings: list[str] = []
        labelled: dict[str, list[Segment]] = {}
        for track in meeting.tracks:
            wav = self.store.track_path(meeting.id, track)
            segments, detected[track] = self.stt.transcribe(wav, language)
            turns = None
            # In mic+system mode the mic track is always "You".
            if track == "system" or meeting.mode == "mic":
                try:
                    turns = self.diarizer.diarize(wav)
                except Exception as e:
                    turns = None
                    warning = f"speaker detection failed: {e}"
                    if warning not in warnings:
                        warnings.append(warning)
            labelled[track] = label_track(segments, track, meeting.mode, turns)
        self.store.save_transcript(meeting.id, merge_transcript(labelled))
        done = transition(meeting, Status.TRANSCRIBED)
        self.store.save(replace(done, detected_languages=detected, warnings=warnings))
