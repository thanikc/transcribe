# Plan: meeting recorder

Spec: `docs/specs/meeting-recorder.md` · Scenarios: `docs/features/meeting-recorder.feature`

## Stack
- Python 3.12, pinned with `.python-version`. Python 3.14 is too new for the `ctranslate2`/`faster-whisper` wheels. uv downloads 3.12 on both WSL and Windows.
- Dependencies: `sherpa-onnx` for diarization. No new ones for Gemini (it uses the `gemini` CLI as a subprocess, and PyAV comes with faster-whisper). `mcp` (official SDK; it already brings `starlette`, `uvicorn` and `httpx`, so the web service and HTTP client add nothing), `faster-whisper`, `soundcard`, `numpy`. Dev: `pytest`.
- The adapters import `soundcard`/`faster_whisper` lazily, so all tests run in WSL without audio devices or models.
- Web UI: one static `index.html` with vanilla JS and CSS. No build step and no frontend framework.

## Layout
```
src/transcribe/
  domain.py      # Meeting, Segment, Status, meeting id, merge/render/search: pure
  store.py       # MeetingStore: filesystem
  recorder.py    # Recorder service: start/stop/transcribe/recover orchestration over the ports
  capture.py     # soundcard adapter (AudioCapture)
  stt.py         # faster-whisper adapter (SpeechToText)
  web.py         # Starlette app: JSON API + origin guard + serves static/index.html
  static/index.html, static/js/*.js   # ES modules: state, api/util, recording, list, meeting, audio, search
  client.py      # httpx client for the service API (used by the MCP shim and `record`)
  mcp_server.py  # FastMCP stdio tools → client
  cli.py         # argparse: serve/mcp/record/list/show/search
tests/           # pytest with fake capture/STT; Starlette TestClient for the API
```

## Steps
0. **Gemini CLI check (with you, ~10 min)**: you install Gemini CLI on **Windows** (`npm i -g @google/gemini-cli`), run `gemini` once to sign in with Google, and record a ~30s Thai clip. I run `gemini -p` on it from WSL through Windows interop (`cmd.exe /c gemini -p … --output-format json`) and check three things: it works without a terminal on your subscription login, it reads the audio, and the Thai text and timestamps are good enough.
   Verify: a JSON transcript of the clip. **If this fails, drop the `gemini-cli` parts of steps 2, 4 and 8. Nothing else changes.**
   **Outcome (2026-11-11): failed.** The Gemini CLI no longer accepts a subscription login (subscriptions now go through the Antigravity CLI, `agy`, which can't ingest audio). The `gemini-cli` engine was removed, and the engine choice with it.
1. **Scaffold**: `pyproject.toml` (uv, `transcribe` script entry point), `.python-version`, `.gitignore`.
   Verify: `uv sync && uv run pytest` runs.
2. **Domain** (TDD): meeting id + dedup suffix (ASCII slug, timestamp-only for Thai titles), language (`auto|th|en`), merge segments with speakers, render `[mm:ss] Speaker: text`, search (including Thai substrings), status transitions, chunk boundaries + timestamp offsets, validating engine segments, speaker assignment by turn overlap + numbering by first appearance, speaker names.
   Verify: the id, transcript, in-person, language and search scenarios pass.
3. **Store** (TDD): save/load as UTF-8 (`encoding="utf-8"`, `ensure_ascii=False`), list newest first, skip corrupt folders, get transcript (not ready / unknown).
   Verify: the listing and get-transcript scenarios pass.
4. **Recorder** (TDD, fakes): start/stop, one active recording, device failure leaves nothing behind, background transcription, failed → re-transcribe, interrupted-recording recovery, engine choice per meeting, Gemini chunk retry and failure, diarization + fallback on failure, names cleared on re-transcribe (with fake engine and diarizer).
   Verify: the recording, transcription, engine and recovery scenarios pass.
5. **Web API** (TDD, Starlette TestClient): all endpoints including speaker rename, origin guard (403), id/track validation (404).
   Verify: the API, security and "started elsewhere" scenarios pass.
6. **Web UI**: `index.html` (recording panel with elapsed timer, meetings list with live status, meeting view with colour-coded speakers, click-to-rename, audio players and a re-transcribe button).
   Verify: run `transcribe serve` in WSL with fake capture/STT (a `--fake` dev flag) and drive the page in a browser: start → timer runs → stop → meeting view shows "Transcribing…" → transcript + players appear without reload. I'll attach a screenshot.
7. **MCP shim + client** (TDD): call the tools in-process against the TestClient app, plus the "service not running" message.
   Verify: the Claude Desktop scenarios pass.
8. **Real adapters + CLI**: soundcard capture (one thread per track, written to WAV as it streams), faster-whisper STT (`large-v3`, passes `language` or detects it, returns the detected language), Gemini CLI STT (PyAV Opus encode + 10-minute chunks, `gemini -p` subprocess resolved with `shutil.which` so `gemini.cmd` works on Windows, JSON parse with validation), sherpa-onnx diarizer (models downloaded on first use to `<data dir>/.models`), argparse CLI with UTF-8 stdout.
   Verify (Gemini): a real `gemini -p` run on the step-0 clip through the adapter.
   Verify: `uv run transcribe --help`. The real audio and model **can't be verified from WSL**.
9. **Docs**: README (Windows setup, `transcribe serve`, Claude Desktop config snippet, optional start-at-login shortcut) and AGENTS.md (commands + architecture, which CLAUDE.md imports).
10. **Windows smoke test (you)**: `uv run transcribe serve` in PowerShell, open http://127.0.0.1:8765, record 30s in `mic+system` mode in Thai and 30s in English, transcribe one again with Gemini, record a call with 2+ other people to check how accurate speaker detection is, then connect Claude Desktop. The first transcription downloads `large-v3` (~3 GB).

## Running from Windows against this WSL repo
Windows `uv` runs on the `\\wsl.localhost\...` path, with `UV_PROJECT_ENVIRONMENT` pointing to a Windows-side venv
(e.g. `%LOCALAPPDATA%\transcribe\venv`), so the Windows and WSL venvs don't overwrite each other's `.venv`.

## Skipped (not requested)
Live transcription, Thai-English switching within one meeting, an Antigravity/agent-driven transcription path, the Gemini API (API key), Thai fine-tuned Whisper models (they can be plugged in later via `TRANSCRIBE_MODEL=<path>`), live audio level meters, a speaker-count hint per recording, recognising the same voice across meetings, a tray app, auth/remote access (localhost only), auto-starting the service from Claude Desktop, AI summaries (Claude Desktop can do these from the transcript).
