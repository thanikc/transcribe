# App version and updates — spec

## Bounded context: Desktop installation

Show which version of Transcribe is installed, notice when a newer one is released, and let the user
download and run its installer from the recorder page or the tray. Recording and transcription are unchanged;
see `meeting-recorder.md` and `windows-installer.md`.

### Ubiquitous language

| Term | Meaning |
|---|---|
| **Installed version** | The installer's version (`1.2.3`, or `1.2.3-4-gabc1234` for a build after a tag). The workflow writes it to `build\VERSION` and the installer puts it in the package as `transcribe/VERSION`. Without that file (running from a git checkout) the installed version is `dev`. |
| **Release** | The latest GitHub release of `thanikc/transcribe` that has a `Transcribe-Setup-<version>.exe` asset. Its version is the tag without a leading `v`. |
| **Update** | A release whose `major.minor.patch` is greater than the installed version's. A build after a tag (`0.3.1-4-g…`) counts as its tag (`0.3.1`). |
| **Update check** | Asking GitHub for the latest release. The service runs one at start and then every 6 hours. A failed check (offline, rate-limited) is logged and kept as "couldn't check"; it is retried at the next check. |
| **Installing an update** | Download the release's installer to `%TEMP%\transcribe-update\`, verify its SHA-256 against the release's digest, then start it as a separate process. The usual setup wizard opens with the previous choices preselected. It stops the running app before replacing files. |

### Invariants

- Installing an update is refused while a recording runs or a meeting is transcribing, because the installer stops
  the app. The refusal says so.
- Only an installer whose SHA-256 matches the release digest is started. A release without a digest, a download
  from anywhere but `https://github.com/thanikc/transcribe/releases/download/`, a size mismatch or a checksum
  mismatch is refused, and the downloaded file is deleted.
- The download URL is never taken from the request: the service finds it in the release itself.
- Installing an update only runs on Windows with an installed version (not `dev`).
- A `dev` installed version is never offered an update and the service doesn't ask GitHub.
- The tray shows one notification per newly found update, not one per check.

### Ports (I/O at the edge)

| Port | Adapter | Failure modes |
|---|---|---|
| Latest release | `httpx2` GET `api.github.com/repos/thanikc/transcribe/releases/latest` | Network error, HTTP error, no setup asset → "couldn't check" |
| Installer download | `httpx2` streaming GET, following GitHub's redirect | Network error, size or digest mismatch → error shown, partial file removed |
| Installer launch | `subprocess.Popen` detached (Windows) | OSError → error shown |

Pure logic (tested on Linux): parsing and comparing versions, picking the setup asset from a release, deciding
whether an install may start.

### Known limits

- No code signing, so the downloaded installer is trusted through GitHub's TLS and the release digest only.
- GitHub allows 60 unauthenticated API calls per hour per IP address; 4 checks a day stay well inside that.
- The busy check runs when the update starts. A recording started while the setup wizard is open is cut off when the
  wizard stops the app; its audio so far survives and can be transcribed.
- The page and the tray only see a new release at the next check (up to 6 hours), or after restarting Transcribe.
