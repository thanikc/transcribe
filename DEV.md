# Developer guide

How to run Transcribe from source, connect it to Claude Desktop by hand, and use the command line.
For the code layout and test commands, see [AGENTS.md](AGENTS.md). The spec is in
[docs/specs/meeting-recorder.md](docs/specs/meeting-recorder.md).

## Setup (Windows)

1. Install [uv](https://docs.astral.sh/uv/): `winget install astral-sh.uv`
2. Get the code and install the dependencies, which also downloads Python 3.12:
   ```powershell
   cd C:\path\to\transcribe
   uv sync
   ```
   **If the repo lives in WSL**, don't run `uv` directly from Windows, even through a mapped
   drive such as `W:`: it would put a Windows
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

For UI work in WSL without audio devices or models, run `uv run transcribe serve --fake --port 8799`.

## Web page (frontend)

The recorder page is a React + TypeScript app in `frontend/`, built into `src/transcribe/static/`.
You need Node.js (npm).

```bash
npm --prefix frontend install         # once
npm --prefix frontend run build       # typecheck and build into src/transcribe/static/
npm --prefix frontend run dev         # Vite dev server on http://localhost:5173, proxies /api to port 8799
```

For `dev`, run `uv run transcribe serve --fake --port 8799` alongside it.

## Tests

None of the tests need audio devices or speech models.

```bash
uv run pytest -q                      # Python tests
npm --prefix frontend run test        # component tests (Vitest + React Testing Library)
```

### End-to-end tests

The e2e tests in `frontend/e2e/` drive the real page in Chromium with Playwright. Playwright starts
`.venv/bin/transcribe serve --fake --port 8799` itself, so run them from Linux or WSL, not Windows.

```bash
uv sync                                          # creates .venv/bin/transcribe
npm --prefix frontend install
(cd frontend && npx playwright install chromium) # once; add --with-deps on a fresh Linux/WSL
npm --prefix frontend run build                  # the service serves the built page, so rebuild after UI changes
npm --prefix frontend run test:e2e
```

- If something is already listening on port 8799 (for example your own `serve --fake`), the tests
  reuse it, except when `CI` is set.
- To use a Chromium you already have, set `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH` to it.
- To watch the browser, add `-- --headed`. Results of failed runs are in `frontend/test-results/`.

### Optional: start at login

Press Win+R, type `shell:startup` and create a shortcut there with this target:

```
cmd /c "cd /d C:\path\to\transcribe && uv run transcribe serve"
```

For a repo in WSL, use `\\wsl.localhost\<distro>\...\transcribe\transcribe.cmd serve` as the target.

## Claude Desktop (manual setup)

The installer's **Connect to Claude Desktop** tray item does this for you. From source, add the entry yourself.

Open the config file from Claude Desktop with Settings → Developer → Edit Config. That opens the file
the app actually reads. Its location depends on how Claude Desktop was installed:

- Installer from claude.ai: `%APPDATA%\Claude\claude_desktop_config.json`
- Microsoft Store (packaged): `%LOCALAPPDATA%\Claude-Data\claude_<id>\claude_desktop_config.json`.
  This build ignores `%APPDATA%\Claude`.

Add a `mcpServers` entry and keep the keys already in the file:

```json
{
  "mcpServers": {
    "transcribe": {
      "command": "C:\\Users\\<you>\\.local\\bin\\uv.exe",
      "args": ["run", "--project", "C:\\path\\to\\transcribe", "transcribe", "mcp"]
    }
  }
}
```

Give `uv.exe` its full path, because Claude Desktop may not see your shell's `PATH`.

If the repo lives in WSL, point Claude Desktop at the launcher instead, so Windows `uv` doesn't
replace the Linux `.venv`:

```json
{
  "mcpServers": {
    "transcribe": {
      "command": "\\\\wsl.localhost\\<distro>\\home\\<you>\\dev\\projects\\transcribe\\transcribe.cmd",
      "args": ["mcp"]
    }
  }
}
```

To test it in PowerShell first, run `...\transcribe.cmd mcp`. It waits silently for input, so press
Ctrl+C to quit. Don't run `uv run --project W:\...` yourself: it creates a Windows venv inside the
repo.

Quit Claude Desktop from the tray icon and start it again. Closing the window is not enough. If the
tools don't appear, read `mcp-server-transcribe.log` in `%LOCALAPPDATA%\Claude\logs` (Store build)
or `%APPDATA%\Claude\logs` (installer build).

The MCP tools are `start_recording`, `stop_recording`, `list_meetings`, `get_transcript`,
`search_transcripts`, `rename_speaker` and `delete_meeting`. `transcribe serve` must be running.

## CLI

```
transcribe serve [--port 8765]     # recorder service + web page (must be running for everything else)
transcribe record --title "Weekly sync" --mode mic+system --language th   # Ctrl+C stops
transcribe list
transcribe show <meeting id>
transcribe search <query>
transcribe mcp                     # stdio MCP server (launched by Claude Desktop)
transcribe download-models         # fetch the Whisper and speaker models now instead of on first use
transcribe-tray [--background]     # tray app: the service + notification-area icon (what the installer starts)
```

## Configuration

| Env var | Default | Meaning |
|---|---|---|
| `TRANSCRIBE_DATA_DIR` | `~/Meetings` | Where meetings are stored |
| `TRANSCRIBE_MODEL` | `large-v3` | Whisper model name or a CTranslate2 model directory (`large-v3-turbo` or `medium` are faster). It is the default; the page can pick another per meeting. The installer sets this from its Speech model page. |
| `TRANSCRIBE_PORT` | `8765` | Service port |

## Storage

Each meeting is a folder `<data dir>/<meeting id>/` holding `meeting.json`, `transcript.json` and the
audio as MP3 (`mic.mp3`, plus `system.mp3` in `mic+system` mode).

## Installer

The Windows installer is built by `.github/workflows/windows-installer.yml` from the latest git tag.
Its spec is in [docs/specs/windows-installer.md](docs/specs/windows-installer.md).
