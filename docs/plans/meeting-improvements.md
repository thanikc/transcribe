# Plan: meeting improvements

Scenarios: `docs/features/{level-meter,echo-suppression,speaker-split,transcript-playback,rename-meeting,meeting-notes,import-audio,tray-recording,vocabulary}.feature`

Branch `feat/meeting-improvements`. Each feature lands with its spec text (`docs/specs/meeting-recorder.md`:
language table, invariants, ports, interfaces, known limits) and its tests. `uv run pytest -q` stays green
after every step.

## Domain model changes (bounded context: meeting capture & transcription)

| New term | Meaning |
|---|---|
| **Level** | Loudest sample (0–1) of a track's last captured block, while recording. In memory only. |
| **Echo** | A mic segment in `mic+system` mode that repeats concurrent system audio (the mic heard the speakers). Left out of the transcript. |
| **Word** | Start/end/text of one word inside a segment, from Whisper. Used to split segments at speaker changes, then not stored. |
| **Notes** | Free text kept with a meeting (`notes.md`), written by Claude or a client. Not part of the transcript. |
| **Vocabulary** | Names and jargon Whisper should expect, `<data dir>/vocabulary.txt`, one per line. |
| **Imported file** | Capture mode `file`: a meeting made from an existing audio file. One track, `file`. Cannot be started as a recording. |

Invariants added:
- A meeting's id never changes; its title can (empty = untitled). Renaming during recording or transcribing is kept.
- An echo is dropped only when its time overlaps system audio and most of its text appears in that system audio.
- Notes belong to one meeting, survive transcribing again, and go when the meeting is deleted.

## Steps

1. **Rename a meeting.** `Recorder.rename(id, title)` under `_lock`; also updates `_active` if it is
   the recording. The transcription job re-reads the title under `_lock` before its final save, so a rename
   made mid-transcription is kept. `POST /api/meetings/{id}/title {title}`, `ServiceClient.rename`,
   `transcribe rename <id> <title...>`, MCP `rename_meeting`. Page: title is a button → `prompt()`.
   Verify: recorder tests (idle, recording, transcribing, unknown), web, CLI, MCP tests.

2. **Meeting notes.** `MeetingStore.save_notes/load_notes` (`notes.md`, write-then-rename; empty deletes).
   `POST /api/meetings/{id}/notes {notes}`; the meeting detail carries `notes` (null if none).
   `transcript_text` puts a "Notes:" block after the header; also shown when the transcript isn't ready.
   MCP `save_meeting_notes(meeting_id, notes)`. Page: notes in a `pre-wrap` block above the transcript.
   Verify: store, web, MCP, CLI tests.

3. **Echo suppression.** Pure `drop_echoes(mic, system) -> (kept, dropped_count)` in `domain.py`: text
   normalised (casefold, letters/digits only); a mic segment is an echo if the system segments overlapping
   `[start-1s, end+1s]`, joined, contain ≥ 60% of its characters (difflib matching blocks, stdlib).
   Applied in `_run_transcription` for `mic+system`; a count > 0 adds a warning. Verify: domain tests per
   scenario + one recorder test.

4. **Speaker split with word times.** `Word` dataclass; `Segment.words: tuple[Word, ...] = ()`
   (not stored: `save_transcript` writes start/end/text/speaker only). Pure `split_at_turns(segments, turns)`:
   each word → turn with most overlap; consecutive words of one speaker form a piece; a piece under 1 s
   joins its neighbour; pieces are joined with "" and stripped (Whisper words carry their own spaces).
   `label_track` splits before numbering. `stt.py`: `word_timestamps=True`, fills `words`.
   Verify: domain tests per scenario; adapter test that words are passed through.

5. **Vocabulary.** `MeetingStore.vocabulary()` reads `vocabulary.txt` (skips blank and `#` lines, keeps
   whole words up to 800 chars). `SpeechToText.transcribe(..., vocabulary: list[str])`; Whisper gets
   `hotwords=", ".join(...)` or None (applies to every 30 s window, unlike `initial_prompt`).
   Fakes updated. Tray: "Edit vocabulary" creates it with a comment header, then `os.startfile`.
   Verify: store + recorder tests; adapter test of the `hotwords` argument; tray menu test.

6. **Level meter.** `CaptureSession.levels() -> dict[track, float]`; the soundcard session keeps the
   last block's peak per track; fakes return fixed / wobbling values. `Recorder.status()` adds `levels`
   while recording. Page: one small meter per track beside "● Recording" (dB scale, -60…0 dB), and
   "no sound" after 10 s below -50 dB, tracked in the page. Verify: recorder + web status tests;
   `serve --fake` in a browser.

7. **Click-to-seek + highlight.** `meeting.js`: `.ts` becomes a button; track of a line = `system` if
   `mic+system` and speaker ≠ "You", else the meeting's first track. Click pauses the other player, sets
   `currentTime`, plays. `timeupdate` marks the matching line `.playing` (CSS). No server change.
   Verify: `serve --fake` in a browser (Range requests already served by `FileResponse`).

8. **Import an audio file.** Mode `file` (not in `MODES`, so it can't be started), track `file`, steps
   "Transcribing audio file", "Detecting speakers", labelled like `mic` mode. New port
   `AudioConverter.convert(source, dest) -> duration` (PyAV decode → resample 16 kHz mono → `Mp3Writer`),
   injected into `Recorder` (optional arg; `build_recorder` passes it). `Recorder.import_audio(source,
   title, language, model)`: create meeting `transcribing`, convert outside the lock, delete it and raise
   `UnreadableAudio` (400) on failure, else queue the job. `POST /api/meetings/import?title&language&model`
   with `Content-Type: application/octet-stream` (not form-sendable cross-site; Origin still checked),
   body streamed to a temp file. CLI `transcribe import <file> [--title] [--language]` (title defaults to
   the file name without extension, no timeout). Page: "Import audio file" under the recording panel,
   using its title/language/model fields. Verify: recorder, web (incl. foreign Origin, bad file), CLI tests;
   adapter test converting a generated WAV.

9. **Tray start/stop.** Menu items "Start recording (online call)" / "Start recording (in person)",
   visible when idle; "Stop recording" when recording. Each runs in a thread (devices take seconds) and
   notifies on error. Verify: extend the fake-pystray tray test.

## Skipped (say if you want any)
- Input device picker (the meter is what catches the silent-recording failure).
- Reconnecting after a headset change mid-recording (needs real WASAPI to verify).
- An MCP tool to import a file; editing notes in the page; searching notes.
- Echo matching on the audio signal (text + time only).
- A default Thai–English prompt (risk of hallucinated text); only the user's vocabulary is used.

## Risks
- Word timestamps make transcription somewhat slower (also on the "You" track, where they aren't needed).
- Echo suppression removes lines from the transcript; the warning says how many. A real reply that repeats
  the other side word for word at the same moment would be dropped.
- Tray, capture levels, conversion of m4a and `hotwords` behaviour can only be checked on Windows / with
  real models; tests cover them with fakes.
