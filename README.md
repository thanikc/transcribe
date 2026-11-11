# transcribe

Record meetings on your Windows PC, transcribe them locally (Thai or English), and read the
transcripts from Claude Desktop.

- **Record** from a local web page (http://127.0.0.1:8765), from Claude Desktop, or from the CLI.
- **Two capture modes:** `mic` for in-person meetings, and `mic+system` for online calls (microphone plus what your speakers play).
- **Transcribe** locally with Whisper (`large-v3`); audio never leaves the machine.
- **Speakers** are told apart by voice (sherpa-onnx), and you can give them names.
- **Storage:** everything is kept under `~/Meetings/<meeting id>/` (WAV audio, `meeting.json`, `transcript.json`).

## Windows setup

1. Install [uv](https://docs.astral.sh/uv/): `winget install astral-sh.uv`
2. Get the code and install the dependencies, which also downloads Python 3.12:
   ```powershell
   cd C:\path\to\transcribe
   uv sync
   ```
   **If the repo lives in WSL**, don't run `uv` directly from Windows: it would put a Windows
   virtualenv in the WSL `.venv`, and Windows cannot load native extension DLLs (numpy,
   ctranslate2, onnxruntime) from a `\\wsl.localhost` path. Recording then fails with
   `DLL load failed ... The parameter is incorrect`. Use the `transcribe.cmd` launcher in the repo
   instead. It keeps the virtualenv in `%LOCALAPPDATA%\transcribe\venv` and installs on first run:
   ```powershell
   \\wsl.localhost\<distro>\home\<you>\dev\projects\transcribe\transcribe.cmd serve
   ```
3. Start the recorder service and open the page:
   ```powershell
   uv run transcribe serve
   ```
   Then open http://127.0.0.1:8765.

The first transcription downloads Whisper `large-v3` (~3 GB). The first speaker detection
downloads the small sherpa-onnx models into `~/Meetings/.models`.

**Use headphones on calls.** Without them, the microphone also picks up remote speech, which then
appears twice in the transcript (`You` and the remote speaker).

### Optional: start at login

Press Win+R, type `shell:startup` and create a shortcut there with this target:

```
cmd /c "cd /d C:\path\to\transcribe && uv run transcribe serve"
```

For a repo in WSL, use `\\wsl.localhost\<distro>\...\transcribe\transcribe.cmd serve` as the target.

## Claude Desktop

Add this to `%APPDATA%\Claude\claude_desktop_config.json`, then restart Claude Desktop:

```json
{
  "mcpServers": {
    "transcribe": {
      "command": "uv",
      "args": ["run", "--project", "C:\\path\\to\\transcribe", "transcribe", "mcp"]
    }
  }
}
```

If the repo lives in WSL, use the `\\\\wsl.localhost\\...` path as the project, and add
`"env": {"UV_PROJECT_ENVIRONMENT": "C:\\Users\\<you>\\AppData\\Local\\transcribe\\venv"}`.

Claude gets these tools: `start_recording`, `stop_recording`, `list_meetings`, `get_transcript`,
`search_transcripts` and `rename_speaker`. `transcribe serve` must be running. If it isn't, Claude
tells you to start it.

## CLI

```
transcribe serve [--port 8765]     # recorder service + web page (must be running for everything else)
transcribe record --title "Weekly sync" --mode mic+system --language th   # Ctrl+C stops
transcribe list
transcribe show <meeting id>
transcribe search <query>
transcribe mcp                     # stdio MCP server (launched by Claude Desktop)
```

## Configuration

| Env var | Default | Meaning |
|---|---|---|
| `TRANSCRIBE_DATA_DIR` | `~/Meetings` | Where meetings are stored |
| `TRANSCRIBE_MODEL` | `large-v3` | Whisper model name or a CTranslate2 model directory (`medium` is faster) |
| `TRANSCRIBE_PORT` | `8765` | Service port |

## Limits

- Transcription runs after the recording, not live. On CPU, `large-v3` takes about 1–2× the meeting length.
- Speaker detection is approximate.
- One language per meeting.
- The service listens on 127.0.0.1 only and has no login.
