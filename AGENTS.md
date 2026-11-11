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

The real capture (soundcard/WASAPI loopback), Whisper and sherpa-onnx can only be verified on Windows.

## Architecture

```
src/transcribe/
  domain.py      pure: Meeting, Segment, Status, ids, transitions, speakers, merge/render/search
  store.py       MeetingStore: <data dir>/<id>/{meeting.json, mic.wav, system.wav, transcript.json}
  recorder.py    port Protocols (AudioCapture, SpeechToText, SpeakerDiarizer) + Recorder orchestration
  capture.py     soundcard adapter      stt.py      faster-whisper adapter
  diarize.py     sherpa-onnx adapter
  web.py         Starlette JSON API + static/index.html; origin/content-type guard on POST/DELETE, trusted hosts
  client.py      HTTP client + text formatting shared by the MCP shim and the CLI
  mcp_server.py  stdio MCP tools -> client
  cli.py         serve | mcp | record | list | show | search | delete
  devfakes.py    fakes for `serve --fake`
```

- `transcribe serve` is the only process that captures audio. Everything else talks to it over HTTP.
- Domain logic stays pure. I/O goes behind the ports and is injected into `Recorder`.
- Adapters import their heavy libraries lazily, so tests run without them.
- All text is UTF-8, and JSON is written with `ensure_ascii=False`, so Thai survives Windows.
- Tests use fakes from `tests/fakes.py`, import them with `from fakes import ...`, and use Starlette's `TestClient`.
- mcp 2.x provides `MCPServer` (`mcp.server.mcpserver`) and ships httpx as `httpx2`.
