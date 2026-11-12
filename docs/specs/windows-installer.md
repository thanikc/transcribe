# Windows installer and tray app — spec

## Bounded context: Desktop installation

Let someone who has never opened a terminal install the meeting recorder, keep its service
running, and connect it to Claude Desktop. The recorder itself (meetings, transcription) is
unchanged; see `meeting-recorder.md`.

### Ubiquitous language

| Term | Meaning |
|---|---|
| **Installer** | `Transcribe-Setup-<version>.exe`, an Inno Setup installer for the current user only (no admin rights). The version is the latest git tag (`1.2.3` or `v1.2.3`); a build made after the tag is `1.2.3-<commits since>-g<commit>`. It carries `uv.exe`, a standalone CPython 3.12 (plain files, ~30 MB) and the app's source plus `uv.lock`. |
| **Install dir** | `%LOCALAPPDATA%\Programs\Transcribe`. Holds the app, `uv.exe`, the bundled Python (`runtime\`) and the virtualenv (`venv\`). |
| **Component download** | During install, `uv sync --frozen --no-dev --no-editable --python runtime\python.exe` fetches the pinned libraries (~500 MB) into the install dir. Python is bundled, not downloaded, because a uv-managed Python adds a junction that Inno Setup 6.7's RedirectionGuard (left on) blocks with os error 448. For the same reason the model download uses copies, not symlinks, in the Hugging Face cache. |
| **Speech model choice** | An installer page offering `large-v3` (default: most accurate, best for Thai, ~3 GB download, slower) or `large-v3-turbo` (~1.6 GB download, several times faster, a little less accurate, with a larger gap for Thai than for English). The page also states the free memory each needs while transcribing (about 4 GB and about 2 GB; estimates from the model sizes, not measurements) and recommends turbo for 8 GB computers. The choice is stored as the per-user environment variable `TRANSCRIBE_MODEL`, the existing setting, and it is remembered for the next upgrade. |
| **Model download** | During install, right after the component download, `transcribe download-models` fetches the chosen Whisper model (~3 GB or ~1.6 GB) into the Hugging Face cache (`~/.cache/huggingface`, where faster-whisper looks for it) and the sherpa-onnx speaker models into `~/Meetings/.models`. It runs in a visible console window so its progress bars show. Files already downloaded are skipped, so it is safe to run again. |
| **Tray app** | `transcribe-tray.exe` (a windowless gui-script). It runs the **recorder service** in-process and shows a **tray icon**. It replaces `transcribe serve` for end users. |
| **Tray icon** | A notification-area icon: grey when idle, red while a recording runs. Its tooltip names the recording ("Recording: Weekly sync"). |
| **Start at login** | A per-user `HKCU\...\CurrentVersion\Run` value named `Transcribe`: `"<install dir>\venv\Scripts\transcribe-tray.exe" --background`. `--background` means no browser page opens at sign-in. |
| **Claude connection** | A `transcribe` entry under `mcpServers` in a Claude Desktop config file. It runs `<install dir>\venv\Scripts\transcribe.exe mcp`. |
| **Claude config file** | `claude_desktop_config.json` in `%APPDATA%\Claude\` (installer build) and/or `%LOCALAPPDATA%\Claude-Data\claude_<id>\` (Store build). A **Claude config dir** is one of those folders that exists. |
| **Log file** | `%LOCALAPPDATA%\transcribe\logs\transcribe.log` (rotating). The tray app has no console, so the service logs go here. |

### Invariants

- One recorder service per machine. If the tray app starts while a service already answers on the
  port, it opens the recorder page and exits. If something else holds the port, it says so and exits.
- Connecting to Claude Desktop never loses the user's settings: every other key is kept, the
  previous file is copied to `claude_desktop_config.json.bak` first, and a file that isn't valid
  JSON is left untouched (the user is told).
- Connecting writes to every Claude config dir that exists. If none exists, nothing is written and
  the user is told to install Claude Desktop first.
- When the installer finishes without errors, the first transcription starts at once, with nothing left to download.
  If the model download fails, the user can **Retry** or **Skip**. Skip finishes the install, and the models
  then download on the first transcription, as they do today. A failed model download never leaves a half-written model in place.
- The model the installer downloads is the model the app uses. The installer sets `TRANSCRIBE_MODEL` in its own
  process before the download and the first launch, and in `HKCU\Environment` for every later start.
- Uninstalling removes the install dir, the shortcuts, the start-at-login value and `TRANSCRIBE_MODEL`. It **keeps**
  `~/Meetings` (recordings and speaker models), the Whisper model in the Hugging Face cache (so reinstalling
  doesn't download 3 GB again) and the Claude config entry. The uninstaller says where the Whisper model is, in case you want to free the space.
- The tray icon is red whenever the recorder is recording. It never shows idle while the mic is live.

### Ports (I/O at the edge)

| Port | Adapter | Failure modes |
|---|---|---|
| `LoginStartup` (enabled / enable / disable) | `winreg` (stdlib), HKCU Run key | Registry write denied → notification with the error |
| Claude config dirs | Filesystem lookup from `APPDATA` / `LOCALAPPDATA` | None found → "install Claude Desktop first" |
| Tray UI | `pystray` + Pillow (Windows only, imported lazily) | — |
| Model fetch | `huggingface_hub.snapshot_download` with faster-whisper's repo and file list (its own `download_model` hides progress) + the diarizer's `ensure_models` | Network error → non-zero exit + message; the installer offers Retry / Skip |
| Service runner | uvicorn `Server` in a background thread, same app as `transcribe serve` | Port busy → notification, exit |

Pure logic (tested on Linux): merging the Claude connection into a config dict, the tray state
(icon colour + tooltip) from `Recorder.status()`, choosing the Claude config files from the dirs
that exist, and the icon image.

### Known limits

- Installing needs internet and about 4.5 GB of free space (components ~500 MB plus the Whisper model: ~3 GB for `large-v3`, ~1.6 GB for turbo), and takes a while on a slow connection.
- The installer's choice is the default model. To change the default later, run the installer again and pick the other one. Changing `TRANSCRIBE_MODEL` by hand works too, but then the new model downloads on first use. The page can also pick the model per meeting (see `meeting-recorder.md`).
- The installer offers only these two models. Others (e.g. `medium`) are available through `TRANSCRIBE_MODEL`.
- No code signing. Windows SmartScreen shows "Windows protected your PC" → *More info* → *Run anyway*.
- Updates are offered and installed from the page or the tray (see `app-update.md`), or by running a newer installer over the old one.
- GPU (CUDA) libraries are not bundled. Transcription runs on CPU unless CUDA is already installed.
