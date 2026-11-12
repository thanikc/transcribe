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
    MeetingBusy,
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
    transcription_steps,
    transition,
)
from transcribe.store import MeetingStore


class CaptureError(DomainError):
    """An audio device could not be opened."""


class CaptureSession(Protocol):
    def stop(self) -> None:
        """Stop all tracks and close their audio files."""


class AudioCapture(Protocol):
    def start(self, track_paths: dict[str, Path]) -> CaptureSession:
        """Start streaming each track to its audio file. Raises CaptureError if a device can't open."""


# Called from the worker thread with the share of the work done so far, 0.0 to 1.0.
ProgressCallback = Callable[[float], None]


class SpeechToText(Protocol):
    def transcribe(
        self, wav: Path, language: str | None, on_progress: ProgressCallback
    ) -> tuple[list[Segment], str]:
        """Track audio + language (None = detect) -> (segments without speakers, detected language)."""


class SpeakerDiarizer(Protocol):
    def diarize(self, wav: Path, on_progress: ProgressCallback) -> list[SpeakerTurn]:
        """Track audio -> speaker turns with raw labels."""


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
        # In memory only: a restart marks running jobs failed, so there is nothing to resume.
        self._progress: dict[str, dict] = {}
        # Separate from _lock, which is held while audio devices open; page polls must not wait on that.
        self._progress_lock = threading.Lock()

    def _check_language(self, language: str) -> None:
        if language not in LANGUAGES:
            raise InvalidChoice(f'language must be one of {", ".join(LANGUAGES)}, not "{language}"')

    def status(self) -> dict:
        # No lock: start() holds _lock while devices open, and the page polls this every second.
        # _active is swapped as one tuple, so reading it once gives a consistent snapshot.
        active = self._active
        if active is None:
            return {"recording": False}
        meeting = active[0]
        return {
            "recording": True,
            "meeting_id": meeting.id,
            "title": meeting.title,
            "mode": meeting.mode,
            "language": meeting.language,
            "elapsed": (self.clock() - meeting.started_at).total_seconds(),
        }

    def progress(self, meeting_id: str) -> dict | None:
        """Current step of a running transcription, or None when none is running."""
        with self._progress_lock:
            current = self._progress.get(meeting_id)
            if current is None:
                return None
            started_at = current["started_at"]
        return {
            **{k: v for k, v in current.items() if k != "started_at"},
            "elapsed": (self.clock() - started_at).total_seconds(),
        }

    def _begin_step(self, meeting_id: str, label: str, number: int, total: int) -> None:
        with self._progress_lock:
            self._progress[meeting_id] = {
                "step": label,
                "step_number": number,
                "steps": total,
                "fraction": None,
                "started_at": self.clock(),
            }

    def _report_fraction(self, meeting_id: str, fraction: float) -> None:
        with self._progress_lock:
            if meeting_id in self._progress:
                self._progress[meeting_id] = {
                    **self._progress[meeting_id],
                    "fraction": min(max(fraction, 0.0), 1.0),
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

    def delete(self, meeting_id: str) -> None:
        # Locked so a recording or transcription can't start on it mid-delete.
        with self._lock:
            status = self.store.get(meeting_id).status
            if status == Status.RECORDING:
                raise MeetingBusy(f'"{meeting_id}" is still recording; stop the recording first')
            if status == Status.TRANSCRIBING:
                raise MeetingBusy(f'"{meeting_id}" is being transcribed; wait until transcription finishes')
            self.store.delete(meeting_id)

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
        finally:
            with self._progress_lock:
                self._progress.pop(meeting_id, None)

    def _run_transcription(self, meeting: Meeting) -> None:
        language = None if meeting.language == "auto" else meeting.language
        detected: dict[str, str] = {}
        warnings: list[str] = []
        segments: dict[str, list[Segment]] = {}
        turns: dict[str, list[SpeakerTurn]] = {}
        steps = transcription_steps(meeting.mode)
        report = lambda fraction: self._report_fraction(meeting.id, fraction)  # noqa: E731
        for number, step in enumerate(steps, start=1):
            self._begin_step(meeting.id, step.label, number, len(steps))
            wav = self.store.track_path(meeting.id, step.track)
            if step.kind == "transcribe":
                segments[step.track], detected[step.track] = self.stt.transcribe(wav, language, report)
                continue
            try:
                turns[step.track] = self.diarizer.diarize(wav, report)
            except Exception as e:
                warnings.append(f"speaker detection failed: {e}")
        labelled = {
            track: label_track(segs, track, meeting.mode, turns.get(track)) for track, segs in segments.items()
        }
        self.store.save_transcript(meeting.id, merge_transcript(labelled))
        done = transition(meeting, Status.TRANSCRIBED)
        self.store.save(replace(done, detected_languages=detected, warnings=warnings))
