# Plan: Windows installer + tray app

Spec: `docs/specs/windows-installer.md` · Scenarios: `docs/features/windows-installer.feature`

1. **Shared service startup.** Split `cli._serve` into `build_recorder(fake)` (returns the
   recorder and data dir) and the uvicorn run, so `serve` and the tray app start the same service.
   `serve` keeps working as it does now.
   Verify: the existing tests plus `serve --fake` still serve the page.

1b. **`transcribe download-models`.** `WhisperSpeechToText.download()` calls
   `faster_whisper.download_model(name)`, which uses the same HF cache that `WhisperModel(name)` reads and skips
   files it already has. Split `SherpaDiarizer._load`'s file fetch into `ensure_models()`, which `_load` then calls.
   The CLI command calls both, prints "Downloading Whisper large-v3 (~3 GB)…" / "Downloading speaker models…" / "Models ready", and exits 1 with the error on failure.
   It runs in-process with no service needed.
   Verify: a CLI test with the adapters monkeypatched (calls both, exit 0; a raised error → exit 1 + message);
   an adapter test that `ensure_models` skips existing files.

2. **Pure tray logic** in `src/transcribe/desktop.py` (no Windows imports):
   - `tray_state(status) -> (recording: bool, tooltip)`
   - `with_claude_connection(config: dict, command: str) -> dict` (the merge)
   - `claude_config_files(appdata, localappdata) -> list[Path]` (from the dirs that exist)
   - `connect_claude(files, command) -> report` (backup, refuse invalid JSON, write UTF-8)
   - `icon_image(recording) -> PIL.Image` (drawn: a grey or red round mic badge)
   Verify: new `tests/test_desktop.py` covers the connect scenarios (other keys kept, .bak written,
   both builds, missing file, broken JSON, no Claude) and the tray state.

3. **Tray adapter** `src/transcribe/tray.py` with `main()`:
   - file logging to `%LOCALAPPDATA%\transcribe\logs\transcribe.log`; nothing goes to stdout (pythonw has none)
   - single instance: `GET /api/status` answers → open the page, exit; port bound by something else → notify, exit
   - uvicorn `Server` in a thread; poll `recorder.status()` every 1 s to swap the icon and tooltip
   - menu: Open recorder (default, left click) · Start at login ☑ · Connect to Claude Desktop ·
     Open log · Open meetings folder · Quit (stop an active recording, then `server.should_exit`)
   - `WinregLoginStartup` for HKCU Run
   - pyproject: `[project.gui-scripts] transcribe-tray`, plus deps `pystray; sys_platform == 'win32'`
     and `pillow` (Pillow is also used by `icon_image` in tests)
   Verify: unit tests for single-instance detection with an injected probe. The tray itself can
   only be checked on Windows (see the end of this plan).

4. **Installer** `installer/transcribe.iss` (Inno Setup 6, `PrivilegesRequired=lowest`):
   - files: `uv.exe`, `pyproject.toml`, `uv.lock`, `.python-version`, `README.md`, `src\`, `transcribe.ico`
   - `[Code]` post-install: `Exec(uv sync --frozen --no-dev --no-editable)` with
     `UV_PROJECT_ENVIRONMENT={app}\venv`, `UV_PYTHON_INSTALL_DIR={app}\python`, `UV_CACHE_DIR={app}\cache`,
     done through `installer\setup.cmd`, which logs to `{app}\install.log`; a non-zero exit shows the failure message and aborts
   - then `Exec({app}\venv\Scripts\transcribe.exe download-models)` in a **visible** console (huggingface_hub's tqdm bars show the 3 GB progress),
     with the status text "Downloading the speech model (about 3 GB)…". A non-zero exit → `MsgBox` Retry / Skip in a loop
   - welcome page note: needs internet and ~4.5 GB free
   - Start menu shortcut, a "Start Transcribe when I sign in" task (on by default) writing the same Run value, "Launch Transcribe" on the finish page
   - uninstall: `taskkill /im transcribe-tray.exe`, delete `{app}`, remove the Run value; `~/Meetings` and the HF cache untouched;
     the finish message names `%USERPROFILE%\.cache\huggingface` as the place to delete to free 3 GB
   Verify: CI build (step 5) compiles it. Installing it is checked by hand on Windows.

5. **Release workflow** `.github/workflows/windows-installer.yml`: on `v*` tags and manual
   dispatch, a `windows-latest` runner installs uv, runs the tests, downloads a pinned `uv.exe`, writes `transcribe.ico`
   from `icon_image`, runs `iscc` (preinstalled on the runner), uploads the exe as an artifact, and attaches it to a Release on tags.
   Verify: a manual dispatch run goes green and produces the exe. **Needs a push, so I'll ask before pushing.**

5b. **Speech model choice** (added after review). An Inno `CreateInputOptionPage` after the tasks page with two
   radio buttons and a short explanation; the choice is remembered with `SetPreviousData`. At `ssPostInstall`,
   before `setup.cmd`, the installer calls `SetEnvironmentVariableW` (inherited by `download-models.cmd` and the "Open Transcribe now" launch)
   and writes `HKCU\Environment\TRANSCRIBE_MODEL` (`ChangesEnvironment=yes` tells Explorer). Uninstall deletes the value.
   `download-models` prints the size of the model it is fetching.
   Verify: the CLI test for the size line, and a test that both offered names are in faster-whisper's model list. The page itself is checked on Windows.

6. **Docs.** README: a new top section "Install (no programming)" (download, SmartScreen, tray, Connect to Claude Desktop).
   The current uv/WSL instructions move under "Developer setup". AGENTS.md: add `desktop.py`/`tray.py`/`installer/`.
   Verify: read through.

**Manual Windows check (you):** install on a clean user (watch the model progress window), then: first transcription starts with no download, tray appears, page opens, record → icon red,
Connect to Claude Desktop → tools show up after a Claude restart, toggle login, Quit, uninstall keeps `~/Meetings`.

Skipped: code signing, auto-update, bundling CUDA, an offline installer, removing the Claude entry on uninstall,
a settings UI for model, port or data dir (env vars still work).
