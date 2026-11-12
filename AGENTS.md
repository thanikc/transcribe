# AGENTS.md

Local meeting recorder for Windows: a web page, Claude Desktop (MCP) and a CLI drive one recorder
service. It transcribes with faster-whisper and detects speakers with sherpa-onnx.
The spec is in `docs/specs/meeting-recorder.md` and the scenarios in
`docs/features/meeting-recorder.feature`.

## Commands

```
uv sync                                  # install (Python 3.12, pinned in .python-version)
uv run pytest -q                         # all tests; no audio devices or models needed
uv run transcribe serve --fake --port 8799   # service with fake capture/STT, for UI work in WSL
uv run transcribe --help
```

The real capture (soundcard/WASAPI loopback), Whisper, sherpa-onnx, the tray icon and the installer can only be
verified on Windows. Tray tests use a fake `pystray` and `winreg`. The installer spec is in
`docs/specs/windows-installer.md`.

## Architecture

```
src/transcribe/
  domain.py      pure: Meeting, Segment, Status, ids, transitions, speakers, speech models, merge/render/search
  store.py       MeetingStore: <data dir>/<id>/{meeting.json, mic.mp3, system.mp3, transcript.json}
  recorder.py    port Protocols (AudioCapture, SpeechToText, SpeakerDiarizer) + Recorder orchestration + the one-at-a-time job worker
  capture.py     soundcard adapter      stt.py      faster-whisper adapter
  diarize.py     sherpa-onnx adapter
  web.py         Starlette JSON API + static/index.html and static/js/*.js (plain ES modules, no build step);
                 origin/content-type guard on POST/DELETE, trusted hosts
  client.py      HTTP client + text formatting shared by the MCP shim and the CLI
  mcp_server.py  stdio MCP tools -> client
  cli.py         serve | mcp | record | list | show | search | delete | download-models
  desktop.py     pure tray logic: icon state/image, Claude Desktop config merge, single-instance check
  tray.py        Windows tray app (pystray, winreg), runs the service in-process; `transcribe-tray` gui-script
  devfakes.py    fakes for `serve --fake`
installer/       Inno Setup script + the .cmd steps it runs (uv sync, download-models)
.github/workflows/windows-installer.yml   builds Transcribe-Setup-<version>.exe; the version is the latest git tag (1.2.3 or v1.2.3)
```

- `transcribe serve` is the only process that captures audio. Everything else talks to it over HTTP.
- Domain logic stays pure. I/O goes behind the ports and is injected into `Recorder`.
- Adapters import their heavy libraries lazily, so tests run without them.
- Web handlers that read the disk or call a locking `Recorder` method are plain `def` (Starlette runs them in its
  thread pool) or use `run_in_threadpool` after reading the body. Only `/api/status` runs on the event loop.
- Transcriptions run one at a time, on the `OneAtATime` worker.
- All text is UTF-8, and JSON is written with `ensure_ascii=False`, so Thai survives Windows.
- Tests use fakes from `tests/fakes.py`, import them with `from fakes import ...`, and use Starlette's `TestClient`.
- mcp 2.x provides `MCPServer` (`mcp.server.mcpserver`) and ships httpx as `httpx2`.
