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
| **Language** | The spoken language of a meeting, chosen per recording: `th`, `en`, or `auto` (Whisper detects it once per track). One language per meeting. The **detected language** of each track is recorded. |
| **Track** | The audio from one source: the `mic` track and, in `mic+system` mode, the `system` track. Each track is its own WAV file. |
| **Speaker** | Who a segment is attributed to. In `mic+system` mode the mic track is always `You`. The system track (and the mic track in `mic` mode) is **diarized** into `Speaker 1`, `Speaker 2`, …, numbered by order of first appearance. If diarization fails, the track falls back to `Others` (system) or no label (`mic` mode). |
| **Diarization** | Splitting a track into **speaker turns** (start, end, speaker) by voice, done locally with sherpa-onnx. Each segment gets the speaker whose turns overlap it the most. |
| **Speaker name** | A display name you give a speaker label for one meeting (`Speaker 2` → `Somchai`). It changes how the transcript is rendered, not the stored segments. |
| **Segment** | One transcribed span: start/end seconds, speaker, text. |
| **Transcript** | The segments of all tracks merged in start-time order. |
| **Meeting status** | `recording` → `transcribing` → `transcribed`, or `failed` (with an error message). |
| **Search hit** | A segment whose text contains the query (case-insensitive), with its meeting id and timestamp. |

### Aggregate: Meeting

Stored as a folder `<data dir>/<meeting id>/` with `meeting.json` (metadata + status),
`mic.wav`, optional `system.wav`, and `transcript.json` once transcribed.

Invariants:
- A meeting id is unique. If the same id is generated twice in one minute, a numeric suffix is added.
- All text (meeting.json, transcript.json, API responses, console output) is UTF-8, so Thai survives Windows, whose default encodings are not UTF-8. JSON is written with `ensure_ascii=False`.
- Only one recording can be active at a time. The **recorder service** is the only process that captures audio, and starting another recording while one is active is an error.
- Audio goes to disk as it is captured, so a crash loses at most the last buffer, not the meeting.
- A transcript exists only when the status is `transcribed`.
- Diarization failure never fails a meeting: the transcript is kept with track-level labels and a warning on the meeting.
- Speaker names belong to one meeting. Transcribing again clears them, because the new diarization may number speakers differently. Giving two labels the same name is allowed (it merges them on display).
- Status changes go in one direction (`recording → transcribing → transcribed|failed`). A failed meeting keeps its audio so it can be transcribed again.
- Deleting a meeting removes its whole folder (audio, transcript, metadata) for good. A meeting that is `recording` or `transcribing` can't be deleted.

### Ports (I/O at the edge, injected)

| Port | Adapter | Responsibility | Failure modes |
|---|---|---|---|
| `AudioCapture` | `soundcard` (WASAPI mic and loopback) | Stream each track to its WAV file until stopped | No device or loopback unavailable → start fails and no meeting is left behind |
| `SpeechToText` | `faster-whisper` (local; model `large-v3` by default, CPU int8, CUDA used automatically if available) | Track WAV + language (`th`/`en`/none = detect) → segments + detected language | Model download or decoding error → meeting `failed` with the message |
| `SpeakerDiarizer` | sherpa-onnx (ONNX, no PyTorch; segmentation + speaker-embedding models downloaded on first use) | Track WAV → speaker turns | Model download or runtime error → fall back to track-level labels and record a warning |
| `MeetingStore` | Filesystem under the data dir | Persist and read meetings | Corrupt `meeting.json` → that meeting is skipped in lists, not fatal |
| Clock | `datetime.now` | Meeting start time / id | — |

Pure domain logic (no I/O): meeting id generation, assigning speakers to segments by turn overlap, numbering speakers by first appearance, applying speaker names, merging the tracks' segments into a transcript,
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
  `GET /api/status` (idle or recording: meeting id, title, mode, elapsed seconds), `POST /api/recordings/start {title, mode, language}`,
  `POST /api/recordings/stop`, `GET /api/meetings`, `GET /api/meetings/{id}` (metadata + transcript if ready),
  `GET /api/meetings/{id}/audio/{track}` (WAV), `POST /api/meetings/{id}/transcribe {language?}`, `POST /api/meetings/{id}/speakers {speaker, name}` (rename; an empty name resets it), `DELETE /api/meetings/{id}` (409 while recording or transcribing), `GET /api/search?q=`.
  `stop` returns at once. Transcription runs in a background thread, and the status is shown in the meeting listings.
  While it runs, each meeting's JSON carries `progress`: `{step, step_number, steps, fraction, elapsed}` (null otherwise).
  The steps are "Transcribing microphone", ["Transcribing system audio",] "Detecting speakers". `fraction` (0–1) is null
  until the step reports, e.g. while the model loads. Progress is kept in memory only.
- **Web UI** (`GET /`): one static HTML page with vanilla JS, which polls `/api/status` every second.
  - A recording panel: title input, mode picker, language picker (Auto / ไทย / English), Start/Stop button, a red "● Recording 12:34" indicator with the elapsed time.
  - A meetings list: newest first, with status badges that update while transcribing.
  - A meeting view: transcript with timestamps and speakers (each speaker in its own colour; click a speaker label to rename it, applied to the whole transcript), an audio player per track, the language (forced or detected), and a "Transcribe again" button with a language picker, for a failed meeting or one where auto-detection got the language wrong. A "Delete meeting" button (transcribed or failed meetings only) asks for confirmation first.
  - Fonts: a system font stack that includes Thai faces (`Leelawadee UI`, `Noto Sans Thai`) and `<meta charset="utf-8">`.
    When you press Stop, the page opens the new meeting showing the current step, "step n of N", a progress bar (animated without a percentage while the model loads) and the time spent on the step, and swaps in the transcript when it's ready (by polling). The list badge shows the percentage. The status line reads "Starting…"/"Stopping…" while the devices open or close. The transcript is shown only after recording, never live.
- **MCP shim** (`transcribe mcp`, stdio). Tools: `start_recording(title, mode, language="auto")`, `stop_recording()`, `list_meetings()`, `get_transcript(meeting_id)`, `search_transcripts(query)`, `rename_speaker(meeting_id, speaker, name)` (so Claude can name speakers it works out from context, e.g. "thanks, Somchai"), `delete_meeting(meeting_id)` (its description tells Claude to use it only when asked), each forwarded to the service.
- **CLI** (`transcribe`): `serve`, `mcp`, `record [--title] [--mode] [--language auto|th|en]` (starts a recording through the service; Ctrl+C stops it), `list`, `show <id>`, `search <query>`, `delete <id>`.

### Security (trust boundary: the HTTP API)
- The service binds to `127.0.0.1` only. There is no auth, because it's a single-user local machine.
- Requests that change state (`POST`, `DELETE`) must be `Content-Type: application/json` and come with no `Origin` header or one that matches the service's own. Without this, any website open in your browser could start a recording of you.
- `{id}` and `{track}` are validated against known meetings and tracks (no path traversal).

### Config (env vars)
- `TRANSCRIBE_DATA_DIR`: default `~/Meetings`
- `TRANSCRIBE_MODEL`: Whisper model name or a path to a CTranslate2 model dir, default `large-v3` (~3 GB download on first transcription; best Thai accuracy). Set `medium` for speed.
- `TRANSCRIBE_PORT`: service port, default `8765`

### Known limits
- Without headphones, the mic also picks up the speakers. In `mic+system` mode, remote speech can then appear twice (`You` and `Others`).
- `transcribe serve` has to be running for start/stop to work, from the web, Claude or the CLI. Otherwise clients say "recorder service not running, start it with `transcribe serve`". Reading transcripts through MCP also goes through the service.
- If the service stops during a recording, that meeting is left `recording`. On startup, the service marks such meetings `failed` ("interrupted"), and their audio can still be transcribed.
- Transcription happens after the recording, not live.
- `large-v3` on CPU takes roughly 1–2× the meeting length to transcribe. Status stays `transcribing` meanwhile, with step progress.
- The first-run model download (~3 GB for `large-v3`) has no percentage: the step shows an animated bar and a timer.
- Diarization is approximate: overlapping speech, similar voices and very short turns get mislabelled. A segment that spans a speaker change goes to whoever spoke most of it. The number of speakers is estimated, not asked for.
- Thai-English switching inside one meeting is not handled specially. The minority language may come out poorly or get translated.
