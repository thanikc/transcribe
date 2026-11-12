# App version and updates — plan

Spec: `docs/specs/app-update.md`. Scenarios: `docs/features/app-update.feature`.

1. **Stamp the version.** The workflow writes the installer version to `build\VERSION`. `transcribe.iss` copies it
   to `{app}\app\src\transcribe\VERSION`, so the wheel `uv sync` builds includes it.
   Verify: read the workflow and the .iss; check the next tag's build on Windows.
2. **Pure update logic** in new `src/transcribe/updates.py`: `installed_version()`, `parse_version`,
   `Release` (version, url, size, sha256), `release_from_github(json)`, `is_newer(release, installed)`.
   Verify: unit tests for each version and release scenario.
3. **`UpdateService`** in `updates.py`: `check()` (cached latest release, or "couldn't check"),
   `state()` for the API, `install(busy_reason)` (download → size and SHA-256 check → launch). Fetch, download
   and launch are injected; the real adapters (httpx2, `subprocess.Popen`) sit in the same module and import lazily.
   Verify: tests with fake fetch/download/launch: offline, dev, corrupted download, no digest, success.
4. **Web API.** `create_app(recorder, updates=None)`: `GET /api/version` returns the installed version and the
   update state; `POST /api/update/install` refuses with 409 while recording or transcribing, otherwise installs.
   Verify: TestClient tests for both, including the 409 refusals.
5. **Page.** A footer line in `index.html`: "Transcribe 0.3.1 · Up to date" / "Update to 0.4.0" button /
   "Couldn't check for updates". New `static/js/version.js`, loaded from `main.js`.
   Verify: `serve --fake` with a fake update service, check the page in a browser.
6. **Tray and CLI.** `tray.py` creates the `UpdateService`, runs `check()` at start and every 6 hours on a thread,
   notifies once per new version, and its menu shows "Version 0.3.1" (disabled) and "Install update 0.4.0" when one
   exists. `cli serve` uses the same service. `transcribe --version` prints the installed version.
   Verify: the pure "notify once" decision is tested; the tray itself on Windows.
7. **Docs.** AGENTS.md architecture line for `updates.py`; replace "No auto-update" in `windows-installer.md`.
   Verify: `uv run pytest -q`.

Skipped: silent installs, code signing, a setting to turn update checks off.
