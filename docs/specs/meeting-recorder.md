# Meeting recorder — domain spec

## Bounded context: Meeting capture & transcription

Record a meeting on the local Windows machine, transcribe it locally, and make the
transcripts readable by Claude Desktop over MCP. A local web page starts and stops
recordings and shows them.

### Ubiquitous language

| Term | Meaning |
|---|---|
| **Meeting** | One recording session plus everything derived from it. Identified by a **meeting id** (`2026-11-11-1430-weekly-sync`: start time + ASCII title slug; a title with no ASCII letters, e.g. Thai, gives just `2026-11-11-1430`). The full title is kept in metadata. |
| **Capture mode** | `mic` (in-person: microphone only) or `mic+system` (online call: microphone + Windows loopback of what the speakers play). |
| **Imported file** | Capture mode `file`: a meeting made from an existing audio file (a phone recording, another app's) rather than recorded here. It has one track, `file`, converted to the same 16 kHz mono MP3, and is transcribed and diarized like a `mic` meeting. Its start time is when it was imported. A recording can't be started in this mode. |
| **Language** | The spoken language of a meeting, chosen per recording: `th`, `en`, or `auto` (Whisper detects it once per track). One language per meeting. The **detected language** of each track is recorded. |
| **Track** | The audio from one source: the `mic` track and, in `mic+system` mode, the `system` track. Each track is its own MP3 file (16 kHz mono, 64 kbps); meetings recorded before MP3 keep their WAV files, which still play and transcribe. |
| **Speaker** | Who a segment is attributed to. In `mic+system` mode the mic track is always `You`. The system track (and the mic track in `mic` mode) is **diarized** into `Speaker 1`, `Speaker 2`, …, numbered by order of first appearance. If diarization fails, the track falls back to `Others` (system) or no label (`mic` mode). |
| **Diarization** | Splitting a track into **speaker turns** (start, end, speaker) by voice, done locally with sherpa-onnx. Whisper gives word times, so a segment whose words fall in different speakers' turns is split there; a stretch under 1 s is not split off, since diarization flickers. A segment without word times, or not split, gets the speaker whose turns overlap it the most. |
| **Speaker name** | A display name you give a speaker label for one meeting (`Speaker 2` → `Somchai`). It changes how the transcript is rendered, not the stored segments. |
| **Level** | While recording, the loudest sample (0–1) of a track's last half second of audio. Kept in memory only. |
| **Segment** | One transcribed span: start/end seconds, speaker, text. |
| **Echo** | In `mic+system` mode, a mic segment that repeats the system audio of the same moment: without headphones the mic hears the speakers. Echoes are left out of the transcript. |
| **Transcript** | The segments of all tracks merged in start-time order. |
| **Meeting status** | `recording` → `transcribing` → `transcribed`, or `failed` (with an error message). |
| **Notes** | Free text kept with a meeting, such as a summary and action items Claude wrote. Not part of the transcript or search. |
| **Vocabulary** | Names and words Whisper should expect (teammates, customers, products, jargon): `<data dir>/vocabulary.txt`, one per line, `#` lines left out. Given to Whisper as hotwords for every transcription, as many whole words as fit in 800 characters. |
| **Audio source** | The device a track is recorded from: a microphone, or the speaker whose loopback is the system audio. Chosen in Settings, saved in `<data dir>/sources.json`, used by every recording; none chosen = the Windows default. See `audio-sources.md`. |
| **Search hit** | A segment whose text contains the query (case-insensitive), with its meeting id and timestamp. |

### Aggregate: Meeting

Stored as a folder `<data dir>/<meeting id>/` with `meeting.json` (metadata + status),
`mic.mp3`, optional `system.mp3`, and `transcript.json` once transcribed.

Invariants:
- A meeting id is unique. If the same id is generated twice in one minute, a numeric suffix is added.
- All text (meeting.json, transcript.json, API responses, console output) is UTF-8, so Thai survives Windows, whose default encodings are not UTF-8. JSON is written with `ensure_ascii=False`.
- Only one recording can be active at a time. The **recorder service** is the only process that captures audio, and starting another recording while one is active is an error.
- Audio goes to disk as it is captured, so a crash loses at most the last buffer, not the meeting.
- A transcript exists only when the status is `transcribed`.
- A mic segment is an echo only if system segments within 1 s of it contain at least 60% of its letters (Thai marks and digits included; punctuation, spacing and case ignored), counting shared runs of 3 or more. The meeting gets the warning "left out N microphone lines that repeated the system audio".
- Diarization failure never fails a meeting: the transcript is kept with track-level labels and a warning on the meeting.
- Speaker names belong to one meeting. Transcribing again clears them, because the new diarization may number speakers differently. Giving two labels the same name is allowed (it merges them on display).
- Status changes go in one direction (`recording → transcribing → transcribed|failed`). A failed meeting keeps its audio so it can be transcribed again.
- A meeting's id never changes, but its title can (an empty title leaves it untitled, shown by its id). A rename made while it records or is transcribed is kept.
- Notes belong to one meeting (`notes.md` in its folder). Transcribing again keeps them; saving empty notes removes them.
- Deleting a meeting removes its whole folder (audio, transcript, metadata) for good. A meeting that is `recording` or `transcribing` can't be deleted.

### Ports (I/O at the edge, injected)

| Port | Adapter | Responsibility | Failure modes |
|---|---|---|---|
| `AudioCapture` | `soundcard` (WASAPI mic and loopback) | Stream each track to its MP3 file until stopped, reporting each track's level | No device or loopback unavailable → start fails and no meeting is left behind |
| `SpeechToText` | `faster-whisper` (local; model `large-v3` by default, CPU int8, CUDA used automatically if available) | Track audio + language (`th`/`en`/none = detect) + vocabulary → segments with word times + detected language. Word times are used for splitting only and are not stored | Model download or decoding error → meeting `failed` with the message. Out of memory → the model is unloaded and the meeting is transcribed with `large-v3-turbo` instead (see Speech model) |
| `AudioConverter` | PyAV (FFmpeg) | Any audio file → the `file` track's MP3; returns its length | Not audio, or no sound → the import is refused with "could not read the file as audio" and no meeting is left behind |
| `SpeakerDiarizer` | sherpa-onnx (ONNX, no PyTorch; segmentation + speaker-embedding models downloaded on first use) | Track audio → speaker turns, on up to 4 CPU threads | Model download or runtime error → fall back to track-level labels and record a warning |
| `MeetingStore` | Filesystem under the data dir | Persist and read meetings | Corrupt `meeting.json` → that meeting is skipped in lists, not fatal |
| Clock | `datetime.now` | Meeting start time / id | — |

Pure domain logic (no I/O): meeting id generation, assigning speakers to segments by turn overlap and splitting segments at speaker changes, numbering speakers by first appearance, applying speaker names, dropping echoes, merging the tracks' segments into a transcript,
rendering a transcript as text, searching transcripts, status transitions.

### Interfaces

One long-running **recorder service** owns the Recorder. Everything else is a client of its HTTP API.

```
transcribe serve  (http://127.0.0.1:8765, owns the Recorder)
   ├── Web UI (browser)          → HTTP
   ├── transcribe mcp (Claude)   → HTTP   (stdio MCP shim launched by Claude Desktop)
   └── transcribe record (CLI)   → HTTP
```

- **Recorder service** (`transcribe serve`): Starlette + uvicorn, which are already dependencies of `mcp`. JSON API:
  `GET /api/status` (idle or recording: meeting id, title, mode, elapsed seconds, `levels` per track), `POST /api/recordings/start {title, mode, language, model?}`,
  `POST /api/recordings/stop`, `POST /api/meetings/import?title=&language=&model=` (body: the file's bytes as `application/octet-stream`; 201 with the meeting, now `transcribing`), `GET /api/meetings`, `GET /api/meetings/{id}` (metadata + transcript if ready),
  `GET /api/meetings/{id}/audio/{track}` (MP3, or WAV for older meetings), `POST /api/meetings/{id}/transcribe {language?, model?}`, `POST /api/meetings/{id}/speakers {speaker, name}` (rename; an empty name resets it), `POST /api/meetings/{id}/notes {notes}` (replace; empty removes; the meeting JSON carries `notes`), `POST /api/meetings/{id}/title {title}` (rename; the id stays), `DELETE /api/meetings/{id}` (409 while recording or transcribing), `GET /api/search?q=`, `GET /api/models` (the speech models to choose from: `{name, size, downloaded, default}`), `GET /api/sources` and `POST /api/sources {track, device|null}` (the microphone and the speaker for system audio; see `audio-sources.md`).
  `stop` returns at once. Transcription runs on one background thread, one meeting at a time in the order asked for, and the status is shown in the meeting listings.
  A meeting waiting its turn is `transcribing` with no `progress` yet.
  Requests that read the disk or wait for the recorder run in a thread pool, so status polls are answered while a recording starts or a search runs.
  While it runs, each meeting's JSON carries `progress`: `{step, step_number, steps, fraction, elapsed}` (null otherwise).
  The steps are "Transcribing microphone", ["Transcribing system audio",] "Detecting speakers". `fraction` (0–1) is null
  until the step reports, e.g. while the model loads. Progress is kept in memory only.
- **Web UI** (`GET /`): one static HTML page with vanilla JS split into ES modules under `/static/js/` (no build step), which polls `/api/status` every second while its tab is visible. A hidden tab asks nothing and refreshes when it is shown again. After three failed status checks in a row the page shows "Disconnected" and an alert that it can't reach the recorder, with Start disabled; the first answer after that clears it and reloads the meetings and speech models.
  - A recording panel: title input (after Start it holds the recording's title, and changing it and pressing Enter or leaving the field renames the recording, Escape restores it; emptied after Stop), a two-option mode switch beside Start ("In person" = microphone only, "Online call" = microphone + what the speakers play; remembered in the browser; while recording it is locked and shows the mode being recorded), and behind a "Settings" popover a language picker (Auto / ไทย / English), speech model picker (remembered in the browser; a model not yet on the computer says how much it downloads on first use), Start/Stop button, an "Import audio file" panel with its own title field (empty uses the file name) that uses the chosen language and model and says which,  a red "● Recording 12:34" indicator with the elapsed time, and under it a level meter per track (-60…0 dB) that says "no sound" once a track has stayed below -50 dB for 10 seconds.
  - Layout: the recording panel on top; below it the sidebar (search, meetings list) and the meeting view scroll separately, so the search box and list stay in reach in a long transcript; the audio bar stays pinned at the bottom of the meeting view. On a narrow window (≤ 820 px) the page scrolls as one column.
  - Search: hits show the matched words marked and "Searching…" while the request runs; clicking a hit opens its meeting (`#/meeting/<id>?t=<start>`) scrolled to the line nearest that time and briefly highlighted, clearing a speaker filter or collapse that hid it; it does not start playback.
  - A meetings list: newest first, with status badges that update while transcribing.
  - With no meeting open, the view says to select one, or, when there are none yet, how to make one (Start recording or Import audio). A meeting that takes more than 0.3 s to load shows "Loading…".
  - A meeting view: its title (click it or its pencil to rename it in place: Enter or leaving the field saves, Escape cancels, a refused title keeps the field open with the reason), its notes (plain text, above the transcript), transcript with timestamps and speakers (each speaker in its own colour, given in order of first appearance so it is the same every time the meeting is opened; click a speaker label to rename it in a small box under it, applied to the whole transcript: Enter or Save saves, Escape cancels, "Reset to Speaker n" removes the name; click a timestamp to play that line's track from there, pausing the other; the line being played is highlighted), an audio player per track (kept playing while progress refreshes) with a "Play through" output-device picker (the browser default follows the Windows default output; the choice is remembered in the browser; hidden where the browser can't switch outputs), the language (forced or detected), the speech model, and an "Actions" menu beside the title (not while recording) holding a "Transcribe again" button with a language picker and a speech model picker, for a failed meeting, one where auto-detection got the language wrong, or to try the other model, and a "Delete meeting" button (transcribed or failed meetings only) that asks for confirmation in place first (naming the meeting, Cancel focused). The page uses no browser dialogs (prompt, alert, confirm). A failed meeting's error message has a "Transcribe again…" button that opens that menu.
  - Fonts: only fonts already on the computer, no web fonts: on Windows Segoe UI, Leelawadee UI for Thai, and Cascadia Mono (`Noto Sans Thai` elsewhere), with `<meta charset="utf-8">`.
    When you press Stop, the page opens the new meeting showing the current step, "step n of N", a progress bar (animated without a percentage while the model loads) and the time spent on the step, and swaps in the transcript when it's ready (by polling). The list badge shows the percentage. The status line reads "Starting…"/"Stopping…" while the devices open or close. The transcript is shown only after recording, never live.
- **MCP shim** (`transcribe mcp`, stdio). Tools: `start_recording(title, mode, language="auto")`, `stop_recording()`, `list_meetings()`, `get_transcript(meeting_id)`, `search_transcripts(query)`, `rename_speaker(meeting_id, speaker, name)` (so Claude can name speakers it works out from context, e.g. "thanks, Somchai"), `rename_meeting(meeting_id, title)`, `save_meeting_notes(meeting_id, notes)` (so a summary and action items Claude writes stay with the meeting; `get_transcript` returns them between the header and the transcript), `delete_meeting(meeting_id)` (its description tells Claude to use it only when asked), each forwarded to the service.
- **CLI** (`transcribe`): `serve`, `mcp`, `record [--title] [--mode] [--language auto|th|en]` (starts a recording through the service; Ctrl+C stops it), `import <file> [--title] [--language]` (the title defaults to the file name), `list`, `show <id>`, `search <query>`, `rename <id> <title...>`, `delete <id>`, `download-models` (fetch the Whisper and speaker models ahead of time; the Windows installer runs it, see `windows-installer.md`).

### Speech model
- Each meeting is transcribed with one speech model, stored on the meeting. The choices are `large-v3` (most accurate) and `large-v3-turbo` (faster, about half the memory), plus the default if `TRANSCRIBE_MODEL` names another one.
- The page picks the model when recording and when transcribing again. Recordings started from Claude Desktop or the CLI use the default. Any other model name is refused.
- A model that is not on the computer yet downloads on first use. The service keeps one model loaded at a time.
- If `large-v3` does not fit in free memory, the meeting is transcribed with `large-v3-turbo` instead, for all of its tracks, and carries the warning "not enough free memory for large-v3, so this was transcribed with large-v3-turbo". The meeting then shows `large-v3-turbo` as its model.
- If `large-v3-turbo` does not fit either, the meeting is `failed` with a message to close other apps and transcribe again. Its audio is kept.

### Security (trust boundary: the HTTP API)
- The service binds to `127.0.0.1` only. There is no auth, because it's a single-user local machine.
- Requests that change state (`POST`, `DELETE`) must be `Content-Type: application/json` (an import: `application/octet-stream`, which a page of another site also can't send without a preflight) and come with no `Origin` header or one that matches the service's own. Without this, any website open in your browser could start a recording of you.
- `{id}` and `{track}` are validated against known meetings and tracks (no path traversal).

### Config (env vars)
- `TRANSCRIBE_DATA_DIR`: default `~/Meetings`
- `TRANSCRIBE_MODEL`: the default speech model: a Whisper model name or a path to a CTranslate2 model dir, default `large-v3` (~3 GB download on first transcription; best Thai accuracy). Set `medium` for speed.
- `TRANSCRIBE_PORT`: service port, default `8765`

### Known limits
- Without headphones, the mic also picks up the speakers. In `mic+system` mode such echoes are left out by matching text and time, so an echo Whisper heard very differently on the two tracks can still appear twice, and a reply that repeats the other side word for word at the same moment is left out.
- `transcribe serve` has to be running for start/stop to work, from the web, Claude or the CLI. Otherwise clients say "recorder service not running, start it with `transcribe serve`". Reading transcripts through MCP also goes through the service.
- If the service stops during a recording, that meeting is left `recording`. On startup, the service marks such meetings `failed` ("interrupted"), and their audio can still be transcribed.
- Transcription happens after the recording, not live.
- Meetings are transcribed one at a time. One asked for while another runs waits, and the page says so.
- `large-v3` on CPU takes roughly 1–2× the meeting length to transcribe. Status stays `transcribing` meanwhile, with step progress.
- Without the installer or `download-models`, the first-run model download (~3 GB for `large-v3`) has no percentage: the step shows an animated bar and a timer.
- Diarization is approximate: overlapping speech, similar voices and very short turns get mislabelled. A speaker change is split at word level, so a reply shorter than a second stays with the line it interrupts. The number of speakers is estimated, not asked for.
- Thai-English switching inside one meeting is not handled specially. The minority language may come out poorly or get translated. Names and terms in the vocabulary come out better, but a long vocabulary can also make Whisper write them where they were not said.
