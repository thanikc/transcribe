"""Update scenarios: installed version, update check and installing an update. No network, no Windows."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from transcribe.updates import (
    Release,
    UpdateError,
    UpdateService,
    installed_version,
    is_newer,
    parse_version,
    release_from_github,
)

SETUP = b"setup bytes"
SETUP_SHA = hashlib.sha256(SETUP).hexdigest()
URL = "https://github.com/thanikc/transcribe/releases/download/0.4.0/Transcribe-Setup-0.4.0.exe"


def github_release(tag: str = "0.4.0", digest: str | None = f"sha256:{SETUP_SHA}", assets: list | None = None) -> dict:
    asset = {"name": f"Transcribe-Setup-{tag.removeprefix('v')}.exe", "browser_download_url": URL, "size": len(SETUP)}
    if digest is not None:
        asset["digest"] = digest
    return {"tag_name": tag, "assets": [asset] if assets is None else assets}


class Rig:
    def __init__(self, tmp_path: Path, installed: str = "0.3.1", release: dict | None = None, served: bytes = SETUP):
        self.release = github_release() if release is None else release
        self.served = served
        self.fetches = 0
        self.downloads: list[str] = []
        self.launched: list[Path] = []
        self.announced: list[str] = []
        self.download_dir = tmp_path / "update"
        self.service = UpdateService(
            installed=installed,
            fetch_latest=self.fetch,
            download=self.download,
            launch=self.launched.append,
            download_dir=self.download_dir,
            can_install=True,
            on_update=lambda release: self.announced.append(release.version),
        )

    def fetch(self) -> dict:
        self.fetches += 1
        if isinstance(self.release, Exception):
            raise self.release
        return self.release

    def download(self, url: str, path: Path) -> None:
        self.downloads.append(url)
        path.write_bytes(self.served)


# --- installed version ---------------------------------------------------------


def test_installed_version_comes_from_the_version_file(tmp_path: Path) -> None:
    (tmp_path / "VERSION").write_text("0.3.1\n", encoding="utf-8")
    assert installed_version(tmp_path / "VERSION") == "0.3.1"


def test_without_a_version_file_the_version_is_dev(tmp_path: Path) -> None:
    assert installed_version(tmp_path / "VERSION") == "dev"


@pytest.mark.parametrize(
    ("text", "parsed"),
    [("0.3.1", (0, 3, 1)), ("v1.2.3", (1, 2, 3)), ("0.3.1-4-gabc1234", (0, 3, 1)), ("dev", None), ("0.0.0-dev", (0, 0, 0))],
)
def test_parse_version(text: str, parsed: tuple | None) -> None:
    assert parse_version(text) == parsed


# --- the release ---------------------------------------------------------------


def test_release_from_github() -> None:
    assert release_from_github(github_release("v0.4.0")) == Release("0.4.0", URL, len(SETUP), SETUP_SHA)


def test_a_release_without_a_setup_file_is_ignored() -> None:
    assert release_from_github(github_release(assets=[{"name": "notes.txt", "browser_download_url": URL, "size": 1}])) is None


def test_a_release_with_an_odd_tag_is_ignored() -> None:
    assert release_from_github(github_release(tag="0.4.0/../../x")) is None


def test_a_release_without_a_digest_has_no_checksum() -> None:
    assert release_from_github(github_release(digest=None)).sha256 is None


@pytest.mark.parametrize(
    ("release", "installed", "newer"),
    [("0.4.0", "0.3.1", True), ("0.3.1", "0.3.1", False), ("0.3.1", "0.3.1-4-gabc1234", False),
     ("0.3.2", "0.3.1-4-gabc1234", True), ("0.3.0", "0.3.1", False), ("0.4.0", "dev", False)],
)
def test_is_newer(release: str, installed: str, newer: bool) -> None:
    assert is_newer(Release(release, URL, 1, SETUP_SHA), installed) is newer


# --- update check --------------------------------------------------------------


def test_a_newer_release_is_offered(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    rig.service.check()
    assert rig.service.state() == {"version": "0.3.1", "update": "0.4.0", "checked": True, "error": None, "can_install": True}
    assert rig.announced == ["0.4.0"]


def test_the_installed_release_is_not_offered(tmp_path: Path) -> None:
    rig = Rig(tmp_path, release=github_release("0.3.1"))
    rig.service.check()
    assert rig.service.state()["update"] is None
    assert rig.service.state()["checked"] is True
    assert rig.announced == []


def test_an_update_is_announced_once(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    rig.service.check()
    rig.service.check()
    assert rig.fetches == 2
    assert rig.announced == ["0.4.0"]


def test_offline_the_check_fails_quietly(tmp_path: Path) -> None:
    rig = Rig(tmp_path, release=OSError("no network"))
    rig.service.check()
    assert rig.service.state()["error"] == "couldn't check for updates"
    assert rig.service.state()["update"] is None


def test_a_dev_install_never_asks_github(tmp_path: Path) -> None:
    rig = Rig(tmp_path, installed="dev")
    rig.service.check()
    assert rig.fetches == 0
    assert rig.service.state() == {"version": "dev", "update": None, "checked": False, "error": None, "can_install": True}


# --- installing an update ------------------------------------------------------


def test_installing_downloads_verifies_and_starts_the_setup(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    rig.service.check()
    assert rig.service.install() == "0.4.0"
    setup = rig.download_dir / "Transcribe-Setup-0.4.0.exe"
    assert rig.downloads == [URL]
    assert rig.launched == [setup]
    assert setup.read_bytes() == SETUP


def test_a_damaged_download_is_deleted_and_not_started(tmp_path: Path) -> None:
    rig = Rig(tmp_path, served=b"tampered!!!")  # same size, different bytes
    rig.service.check()
    with pytest.raises(UpdateError, match="damaged"):
        rig.service.install()
    assert rig.launched == []
    assert list(rig.download_dir.iterdir()) == []


def test_a_release_without_a_checksum_is_not_installed(tmp_path: Path) -> None:
    rig = Rig(tmp_path, release=github_release(digest=None))
    rig.service.check()
    with pytest.raises(UpdateError, match="can't be verified"):
        rig.service.install()
    assert rig.downloads == []


def test_a_setup_file_hosted_elsewhere_is_not_downloaded(tmp_path: Path) -> None:
    release = github_release()
    release["assets"][0]["browser_download_url"] = "https://example.com/Transcribe-Setup-0.4.0.exe"
    rig = Rig(tmp_path, release=release)
    rig.service.check()
    with pytest.raises(UpdateError):
        rig.service.install()
    assert rig.downloads == []


def test_a_failed_download_leaves_no_file(tmp_path: Path) -> None:
    rig = Rig(tmp_path)

    def broken(url: str, path: Path) -> None:
        path.write_bytes(b"part")
        raise OSError("connection reset")

    rig.service.download = broken
    rig.service.check()
    with pytest.raises(UpdateError, match="connection reset"):
        rig.service.install()
    assert list(rig.download_dir.iterdir()) == []


def test_nothing_to_install_without_an_update(tmp_path: Path) -> None:
    rig = Rig(tmp_path, release=github_release("0.3.1"))
    rig.service.check()
    with pytest.raises(UpdateError, match="up to date"):
        rig.service.install()


def test_installing_needs_an_installed_copy_on_windows(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    rig.service.can_install = False
    rig.service.check()
    with pytest.raises(UpdateError, match="Windows"):
        rig.service.install()
