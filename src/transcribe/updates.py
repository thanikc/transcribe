"""App version and updates: the installed version, the update check against GitHub releases, installing an update.

Pure logic first; the GitHub, download and launch adapters at the bottom are injected into UpdateService.
"""

from __future__ import annotations

import hashlib
import logging
import re
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from transcribe.domain import DomainError

log = logging.getLogger(__name__)

REPO = "thanikc/transcribe"
LATEST_RELEASE_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
DOWNLOAD_PREFIX = f"https://github.com/{REPO}/releases/download/"
VERSION_FILE = Path(__file__).parent / "VERSION"  # written by the installer build; absent in a git checkout
CHECK_INTERVAL = 6 * 3600  # seconds
SETUP_ASSET = re.compile(r"Transcribe-Setup-.+\.exe")
RELEASE_TAG = re.compile(r"v?(\d+\.\d+\.\d+)")
VERSION = re.compile(r"v?(\d+)\.(\d+)\.(\d+)")
HEADERS = {"User-Agent": "transcribe-update-check"}


class UpdateError(DomainError):
    """An update that can't be installed; the message is shown as-is."""


def installed_version(path: Path = VERSION_FILE) -> str:
    try:
        return path.read_text(encoding="utf-8").strip() or "dev"
    except FileNotFoundError:
        return "dev"


def parse_version(text: str) -> tuple[int, int, int] | None:
    """major.minor.patch; a build after a tag (1.2.3-4-gabc) counts as its tag."""
    match = VERSION.match(text)
    return tuple(int(part) for part in match.groups()) if match else None


@dataclass(frozen=True)
class Release:
    version: str
    url: str
    size: int
    sha256: str | None


def release_from_github(data: dict) -> Release | None:
    """The release's setup file, or None when it has none."""
    tag = RELEASE_TAG.fullmatch(str(data.get("tag_name", "")))
    if tag is None:
        return None
    for asset in data.get("assets") or []:
        if SETUP_ASSET.fullmatch(str(asset.get("name", ""))):
            digest = str(asset.get("digest") or "")
            sha256 = digest.removeprefix("sha256:") if digest.startswith("sha256:") else None
            return Release(tag.group(1), str(asset["browser_download_url"]), int(asset["size"]), sha256)
    return None


def is_newer(release: Release, installed: str) -> bool:
    mine, theirs = parse_version(installed), parse_version(release.version)
    return mine is not None and theirs is not None and theirs > mine


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


class UpdateService:
    def __init__(
        self,
        installed: str | None = None,
        fetch_latest: Callable[[], dict] | None = None,
        download: Callable[[str, Path], None] | None = None,
        launch: Callable[[Path], None] | None = None,
        download_dir: Path | None = None,
        can_install: bool | None = None,
        on_update: Callable[[Release], None] = lambda release: None,
    ) -> None:
        self.installed = installed_version() if installed is None else installed
        self.fetch_latest = fetch_latest or github_latest_release
        self.download = download or download_file
        self.launch = launch or launch_installer
        self.download_dir = download_dir or Path(tempfile.gettempdir()) / "transcribe-update"
        self.can_install = sys.platform == "win32" if can_install is None else can_install
        self.on_update = on_update
        self._lock = threading.Lock()
        self._install_lock = threading.Lock()
        self._update: Release | None = None
        self._checked = False
        self._error: str | None = None
        self._announced: str | None = None

    def update(self) -> Release | None:
        return self._update

    def check(self) -> None:
        """Ask GitHub for the latest release. A dev install never asks."""
        if parse_version(self.installed) is None:
            return
        try:
            release = release_from_github(self.fetch_latest())
        except Exception as error:  # network, HTTP status, unexpected JSON: all mean "try again later"
            log.warning("update check failed: %s", error)
            with self._lock:
                self._update, self._error = None, "couldn't check for updates"
            return
        update = release if release is not None and is_newer(release, self.installed) else None
        with self._lock:
            self._update, self._checked, self._error = update, True, None
            announce = update is not None and update.version != self._announced
            if announce:
                self._announced = update.version
        if announce:
            log.info("update available: %s", update.version)
            self.on_update(update)

    def start_checking(self, interval: float = CHECK_INTERVAL) -> threading.Event:
        """Checks now and then every interval on a daemon thread. Set the returned event to stop."""
        stop = threading.Event()

        def loop() -> None:
            while True:
                self.check()
                if stop.wait(interval):
                    return

        threading.Thread(target=loop, name="update-check", daemon=True).start()
        return stop

    def state(self) -> dict:
        with self._lock:
            return {
                "version": self.installed,
                "update": self._update.version if self._update else None,
                "checked": self._checked,
                "error": self._error,
                "can_install": self.can_install,
            }

    def install(self) -> str:
        """Download the update's setup file, verify it and start it. Returns the version being installed."""
        if not self.can_install or parse_version(self.installed) is None:
            raise UpdateError("updates can only be installed on Windows, into a copy installed with the installer")
        release = self._update
        if release is None:
            raise UpdateError(f"Transcribe {self.installed} is up to date")
        if release.sha256 is None:
            raise UpdateError(f"update {release.version} can't be verified: its release has no checksum")
        if not release.url.startswith(DOWNLOAD_PREFIX):
            raise UpdateError(f"update {release.version} isn't hosted on {DOWNLOAD_PREFIX}")
        if not self._install_lock.acquire(blocking=False):
            raise UpdateError(f"update {release.version} is already downloading")
        try:
            return self._download_and_launch(release)
        finally:
            self._install_lock.release()

    def _download_and_launch(self, release: Release) -> str:
        self.download_dir.mkdir(parents=True, exist_ok=True)
        setup = self.download_dir / f"Transcribe-Setup-{release.version}.exe"
        part = setup.with_name(setup.name + ".part")
        try:
            self.download(release.url, part)
            intact = part.stat().st_size == release.size and _sha256(part) == release.sha256
        except Exception as error:
            part.unlink(missing_ok=True)
            raise UpdateError(f"couldn't download update {release.version}: {error}") from None
        if not intact:
            part.unlink(missing_ok=True)
            raise UpdateError(f"the download of update {release.version} was damaged; try again")
        part.replace(setup)
        try:
            self.launch(setup)
        except OSError as error:
            raise UpdateError(f"couldn't start the installer {setup}: {error}") from None
        log.info("started the installer for %s", release.version)
        return release.version


# --- adapters -----------------------------------------------------------------


def github_latest_release() -> dict:
    import httpx2 as httpx

    headers = {**HEADERS, "Accept": "application/vnd.github+json"}
    response = httpx.get(LATEST_RELEASE_URL, headers=headers, timeout=15)
    response.raise_for_status()
    return response.json()


def download_file(url: str, path: Path) -> None:
    import httpx2 as httpx

    # GitHub redirects release downloads to its storage host.
    with httpx.stream("GET", url, headers=HEADERS, follow_redirects=True, timeout=60) as response:
        response.raise_for_status()
        with path.open("wb") as f:
            for chunk in response.iter_bytes():
                f.write(chunk)


def launch_installer(path: Path) -> None:
    # Detached, so it outlives this process: the installer stops the running app before replacing its files.
    flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen([str(path)], creationflags=flags, close_fds=True)
