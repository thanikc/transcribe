# transcribe

Record meetings on your Windows PC, transcribe them locally (Thai or English), and read the
transcripts from Claude Desktop.

- **Record** from a local web page (http://127.0.0.1:8765), from Claude Desktop, or from the CLI.
- **Two capture modes:** `mic` for in-person meetings, and `mic+system` for online calls (microphone plus what your speakers play).
- **Transcribe** locally with Whisper (`large-v3`); audio never leaves the machine.
- **Speakers** are told apart by voice (sherpa-onnx), and you can give them names.
- **Storage:** everything is kept under `~/Meetings/<meeting id>/` (MP3 audio, `meeting.json`, `transcript.json`).

## Install (Windows)

1. Download `Transcribe-Setup-<version>.exe` from the [Releases page](https://github.com/thanikc/transcribe/releases).
2. Run it. If Windows says "Windows protected your PC", click **More info**, then **Run anyway** (the installer isn't code-signed).
3. Click through it. On the **Speech model** page, choose:
   - **large-v3** (default): the most accurate, and best for Thai. It's a 3 GB download and needs about 4 GB of free memory while
     transcribing. Without an NVIDIA graphics card it takes about 1–2× the meeting length to transcribe.
   - **large-v3-turbo**: half the download (1.6 GB), about 2 GB of free memory, and several times faster. It makes
     a few more mistakes, noticeably more in Thai than in English. Pick it on an 8 GB computer.

   To switch later, run the installer again and pick the other one.

   Setup then downloads the speech libraries (~500 MB), and the model in a window that shows its progress.
   Keep the computer online, and expect it to take a while on a slow connection.
4. When it finishes, Transcribe opens the recorder page in your browser. A microphone icon appears in the
   notification area (by the clock; it may be under the **^** arrow). It turns red while a recording runs.

Right-click the icon for:

- **Open recorder**: the recorder page (a left click does the same)
- **Start at login**: on by default
- **Connect to Claude Desktop**: see [Claude Desktop](#claude-desktop)
- **Open log**, **Open meetings folder**
- **Quit**: stops the recorder. A recording that's running is stopped first. A meeting still being transcribed
  shows as failed ("interrupted") next time, and **Transcribe again** finishes it.

To upgrade, run a newer installer. To uninstall, use Windows Settings → Apps. Your recordings in `~/Meetings` are
kept, and so is the Whisper model (`%USERPROFILE%\.cache\huggingface`, 1.6–3 GB). Delete that folder to free the space.

## Developer setup (Windows)

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

The page has a **Speech model** picker, when recording and under "Transcribe again": `large-v3` (most accurate)
or `large-v3-turbo` (faster, about half the memory; downloads ~1.6 GB on first use). If `large-v3` does not fit in
free memory, the meeting is transcribed with `large-v3-turbo` instead and says so.

**Use headphones on calls.** Without them, the microphone also picks up remote speech, which then
appears twice in the transcript (`You` and the remote speaker).

### Optional: start at login

Press Win+R, type `shell:startup` and create a shortcut there with this target:

```
cmd /c "cd /d C:\path\to\transcribe && uv run transcribe serve"
```

For a repo in WSL, use `\\wsl.localhost\<distro>\...\transcribe\transcribe.cmd serve` as the target.

## Claude Desktop

This works in the Chat tab only. The Code tab runs Claude Code, which ignores this file.

**If you used the installer:** right-click the tray icon, choose **Connect to Claude Desktop**, then quit Claude
Desktop from its own tray icon and start it again. This adds a `transcribe` entry to Claude Desktop's config file and
keeps everything else in it. The old file is saved next to it as `claude_desktop_config.json.bak`.

**Developer setup:** add the entry yourself, as follows.

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

Claude gets these tools: `start_recording`, `stop_recording`, `list_meetings`, `get_transcript`,
`search_transcripts`, `rename_speaker` and `delete_meeting`. `transcribe serve` must be running. If
it isn't, Claude tells you to start it.

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

## Limits

- Transcription runs after the recording, not live. On CPU, `large-v3` takes about 1–2× the meeting length.
- Speaker detection is approximate.
- One language per meeting.
- The service listens on 127.0.0.1 only and has no login.
