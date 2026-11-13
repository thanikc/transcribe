"""Desktop scenarios: tray state, connecting Claude Desktop, single instance. No Windows needed."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from fakes import FakeCapture, FakeDiarizer, FakeSpeechToText
from transcribe.client import ServiceClient, httpx
from transcribe.desktop import (
    app_window_command,
    claude_config_files,
    connect_claude,
    icon_image,
    port_owner,
    tray_state,
)
from transcribe.recorder import Recorder
from transcribe.store import MeetingStore
from transcribe.web import create_app

COMMAND = r"C:\Users\me\AppData\Local\Programs\Transcribe\venv\Scripts\transcribe.exe"
ENTRY = {"command": COMMAND, "args": ["mcp"]}


# --- tray icon ---------------------------------------------------------------


def test_idle_tray_state() -> None:
    assert tray_state({"recording": False}) == (False, "Transcribe: idle")


def test_recording_tray_state_names_the_meeting() -> None:
    assert tray_state({"recording": True, "title": "ประชุมทีม"}) == (True, "Recording: ประชุมทีม")


def test_tooltip_fits_the_windows_limit() -> None:
    recording, tooltip = tray_state({"recording": True, "title": "x" * 300})
    assert recording and len(tooltip) < 128 and tooltip.endswith("…")


def test_icon_is_red_only_while_recording() -> None:
    def has_red(image) -> bool:
        return any(r > 180 and g < 80 and b < 80 for _, (r, g, b, a) in image.getcolors(maxcolors=64 * 64) if a)

    assert has_red(icon_image(recording=True))
    assert not has_red(icon_image(recording=False))


# --- finding Claude Desktop ---------------------------------------------------


def test_both_claude_builds_are_found(tmp_path: Path) -> None:
    appdata, local = tmp_path / "Roaming", tmp_path / "Local"
    (appdata / "Claude").mkdir(parents=True)
    (local / "Claude-Data" / "claude_abc123").mkdir(parents=True)
    (local / "Claude-Data" / "not-a-profile").mkdir()
    assert claude_config_files(appdata, local) == [
        appdata / "Claude" / "claude_desktop_config.json",
        local / "Claude-Data" / "claude_abc123" / "claude_desktop_config.json",
    ]


def test_no_claude_desktop_found(tmp_path: Path) -> None:
    assert claude_config_files(tmp_path / "Roaming", None) == []


# --- connecting ---------------------------------------------------------------


def test_connect_keeps_other_settings_and_backs_up(tmp_path: Path) -> None:
    config = tmp_path / "claude_desktop_config.json"
    original = {"mcpServers": {"other": {"command": "x"}}, "preferences": {"theme": "dark"}}
    config.write_text(json.dumps(original), encoding="utf-8")
    result = connect_claude([config], COMMAND)
    assert result.connected == [config] and result.unreadable == []
    assert json.loads(config.read_text(encoding="utf-8")) == {
        "mcpServers": {"other": {"command": "x"}, "transcribe": ENTRY},
        "preferences": {"theme": "dark"},
    }
    assert json.loads((tmp_path / "claude_desktop_config.json.bak").read_text(encoding="utf-8")) == original
    assert "quit Claude Desktop from its tray icon" in result.message()


def test_connect_replaces_an_old_transcribe_entry(tmp_path: Path) -> None:
    config = tmp_path / "claude_desktop_config.json"
    config.write_text(json.dumps({"mcpServers": {"transcribe": {"command": "old.cmd"}}}), encoding="utf-8")
    connect_claude([config], COMMAND)
    assert json.loads(config.read_text(encoding="utf-8")) == {"mcpServers": {"transcribe": ENTRY}}


def test_connect_reads_a_file_saved_by_notepad_with_a_bom(tmp_path: Path) -> None:
    config = tmp_path / "claude_desktop_config.json"
    config.write_text('{"preferences": {}}', encoding="utf-8-sig")
    assert connect_claude([config], COMMAND).connected == [config]


def test_connect_creates_a_missing_file(tmp_path: Path) -> None:
    config = tmp_path / "claude_desktop_config.json"
    connect_claude([config], COMMAND)
    assert json.loads(config.read_text(encoding="utf-8")) == {"mcpServers": {"transcribe": ENTRY}}
    assert not (tmp_path / "claude_desktop_config.json.bak").exists()


@pytest.mark.parametrize("content", ["{not json", "[1, 2]", '{"mcpServers": "nope"}'])
def test_connect_leaves_a_broken_file_untouched(tmp_path: Path, content: str) -> None:
    good, broken = tmp_path / "a" / "claude_desktop_config.json", tmp_path / "b" / "claude_desktop_config.json"
    good.parent.mkdir()
    broken.parent.mkdir()
    broken.write_text(content, encoding="utf-8")
    result = connect_claude([good, broken], COMMAND)
    assert broken.read_text(encoding="utf-8") == content
    assert result.connected == [good] and result.unreadable == [broken]
    assert str(broken) in result.message()


def test_connect_without_claude_desktop() -> None:
    result = connect_claude([], COMMAND)
    assert result.connected == [] and "install Claude Desktop first" in result.message()


# --- single instance ----------------------------------------------------------


def test_port_owned_by_a_running_recorder(tmp_path: Path) -> None:
    recorder = Recorder(MeetingStore(tmp_path), FakeCapture(), FakeSpeechToText([]), FakeDiarizer([]))
    client = ServiceClient(TestClient(create_app(recorder, allowed_hosts=["testserver"])))
    assert port_owner(client) == "recorder"


def test_free_port() -> None:
    assert port_owner(ServiceClient(httpx.Client(base_url="http://127.0.0.1:1"))) == "free"


def test_port_owned_by_another_program() -> None:
    other = Starlette(routes=[Route("/", lambda request: PlainTextResponse("hi"))])
    assert port_owner(ServiceClient(TestClient(other))) == "other"


# --- tray adapter ---------------------------------------------------------------


def test_importing_the_tray_does_not_load_the_tray_or_heavy_libraries() -> None:
    import subprocess
    import sys

    code = (
        "import sys, transcribe.tray;"
        "bad = [m for m in ('pystray', 'faster_whisper', 'sherpa_onnx', 'soundcard') if m in sys.modules];"
        "sys.exit(','.join(bad) or 0)"
    )
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr + done.stdout


class FakeWinreg:
    """Just enough of winreg for the HKCU Run key."""

    HKEY_CURRENT_USER, KEY_SET_VALUE, REG_SZ = "HKCU", 2, 1

    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def OpenKey(self, root, path, reserved=0, access=0):
        assert (root, path) == ("HKCU", r"Software\Microsoft\Windows\CurrentVersion\Run")
        from contextlib import nullcontext

        return nullcontext(self)

    def QueryValueEx(self, key, name):
        if name not in self.values:
            raise FileNotFoundError(name)
        return self.values[name], self.REG_SZ

    def SetValueEx(self, key, name, reserved, kind, value):
        self.values[name] = value

    def DeleteValue(self, key, name):
        if name not in self.values:
            raise FileNotFoundError(name)
        del self.values[name]


def test_start_at_login_toggles_the_run_value(monkeypatch: pytest.MonkeyPatch) -> None:
    import sys

    from transcribe.tray import WinregLoginStartup

    registry = FakeWinreg()
    monkeypatch.setitem(sys.modules, "winreg", registry)
    startup = WinregLoginStartup(r'"C:\T\venv\Scripts\transcribe-tray.exe" --background')
    assert not startup.enabled()
    startup.enable()
    assert startup.enabled()
    assert registry.values == {"Transcribe": r'"C:\T\venv\Scripts\transcribe-tray.exe" --background'}
    startup.disable()
    startup.disable()  # already off: no error
    assert not startup.enabled()


def _free_port() -> int:
    import socket

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_tray_runs_the_service_shows_recording_and_quits(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import sys
    import time
    import types

    from transcribe import cli, tray

    port = _free_port()
    recorder = Recorder(MeetingStore(tmp_path / "Meetings"), FakeCapture(), FakeSpeechToText([]), FakeDiarizer([]))
    monkeypatch.setenv("TRANSCRIBE_PORT", str(port))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    monkeypatch.setattr(sys, "argv", ["transcribe-tray"])
    monkeypatch.setattr(cli, "build_recorder", lambda: (recorder, tmp_path / "Meetings"))
    opened: list[str] = []
    monkeypatch.setattr(tray.webbrowser, "open", opened.append)
    seen: dict = {}

    class Icon:
        def __init__(self, name, icon, title, menu) -> None:
            self.icon, self.title, self.menu = icon, title, menu
            self.menu_updates = 0
            self.notes: list[str] = []

        def notify(self, message, title) -> None:
            self.notes.append(message)

        def shown(self) -> list[str]:
            items = [i for i in self.menu.items if i is not FakePystray.Menu.SEPARATOR and i.visible(i)]
            return [i.text(i) if callable(i.text) else i.text for i in items]

        def choose(self, text) -> None:
            item = next(i for i in self.menu.items if getattr(i, "text", None) == text)
            item.action(self, item)

        def wait_until(self, done) -> None:
            deadline = time.monotonic() + 3
            while not done() and time.monotonic() < deadline:
                time.sleep(0.02)

        def update_menu(self) -> None:
            self.menu_updates += 1

        def run(self, setup) -> None:
            setup(self)
            assert self.shown() == [
                "Open recorder", "Start recording (online call)", "Start recording (in person)",
                "Start at login", "Connect to Claude Desktop",
                "Open log", "Open meetings folder", "Edit vocabulary", "Version dev", "Quit",
            ]
            self.choose("Start recording (in person)")
            self.wait_until(lambda: recorder.status()["recording"])
            seen["started from the tray"] = (recorder.status()["mode"], recorder.status()["title"])
            assert self.shown()[:2] == ["Open recorder", "Stop recording"]
            self.choose("Stop recording")
            self.wait_until(lambda: not recorder.status()["recording"])
            seen["stopped from the tray"] = not recorder.status()["recording"]
            refuse = recorder.capture.start
            recorder.capture.start = lambda paths, sources: (_ for _ in ()).throw(OSError("no microphone"))
            self.choose("Start recording (online call)")
            self.wait_until(lambda: self.notes)
            seen["device error"] = self.notes
            recorder.capture.start = refuse
            api = httpx.Client(base_url=f"http://127.0.0.1:{port}")
            api.post("/api/recordings/start", json={"title": "Weekly sync", "mode": "mic"}).raise_for_status()
            deadline = time.monotonic() + 3
            while self.title != "Recording: Weekly sync" and time.monotonic() < deadline:
                time.sleep(0.05)
            seen["title"] = self.title
            install = next(i for i in self.menu.items if callable(getattr(i, "text", None)))
            seen["install enabled while recording"] = install.enabled(install)
            seen["menu refreshed"] = self.menu_updates > 0
            quit_item = next(i for i in self.menu.items if getattr(i, "text", "") == "Quit")
            quit_item.action(self, quit_item)

        def stop(self) -> None:
            seen["stopped"] = True

    class FakePystray(types.ModuleType):
        class Menu:
            SEPARATOR = object()

            def __init__(self, *items) -> None:
                self.items = items

        class MenuItem:
            def __init__(self, text, action, default=False, checked=None, enabled=True, visible=True) -> None:
                self.text, self.action = text, action
                self.visible = visible if callable(visible) else lambda item: visible
                self.enabled = enabled if callable(enabled) else lambda item: enabled

    fake = FakePystray("pystray")
    fake.Icon = Icon
    monkeypatch.setitem(sys.modules, "pystray", fake)

    tray.main()

    assert seen == {
        "started from the tray": ("mic", ""),
        "stopped from the tray": True,
        "device error": ["Couldn't start recording: no microphone"],
        "title": "Recording: Weekly sync", "install enabled while recording": False, "menu refreshed": True, "stopped": True,
    }
    assert opened == [f"http://127.0.0.1:{port}"]
    assert recorder.status() == {"recording": False}
    assert (tmp_path / "Local" / "transcribe" / "logs" / "transcribe.log").exists()


def test_second_launch_only_opens_the_page(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import sys

    from transcribe import cli, tray

    monkeypatch.delenv("TRANSCRIBE_PORT", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(sys, "argv", ["transcribe-tray"])
    monkeypatch.setattr(tray, "port_owner", lambda client: "recorder")
    monkeypatch.setattr(cli, "build_recorder", lambda: pytest.fail("started a second service"))
    opened: list[str] = []
    monkeypatch.setattr(tray.webbrowser, "open", opened.append)
    tray.main()
    assert opened == ["http://127.0.0.1:8765"]


# --- app window --------------------------------------------------------------

EDGE = Path("Microsoft/Edge/Application/msedge.exe")
CHROME = Path("Google/Chrome/Application/chrome.exe")


def _install(root: Path, exe: Path) -> Path:
    (root / exe).parent.mkdir(parents=True, exist_ok=True)
    (root / exe).touch()
    return root / exe


def test_app_window_prefers_edge(tmp_path: Path) -> None:
    _install(tmp_path / "x86", CHROME)
    edge = _install(tmp_path / "local", EDGE)
    env = {"ProgramFiles(x86)": str(tmp_path / "x86"), "LOCALAPPDATA": str(tmp_path / "local")}
    assert app_window_command("http://127.0.0.1:8765", env) == [str(edge), "--app=http://127.0.0.1:8765"]


def test_app_window_uses_chrome_without_edge(tmp_path: Path) -> None:
    chrome = _install(tmp_path, CHROME)
    assert app_window_command("http://x", {"ProgramFiles": str(tmp_path)}) == [str(chrome), "--app=http://x"]


def test_no_app_window_without_edge_or_chrome(tmp_path: Path) -> None:
    assert app_window_command("http://x", {"ProgramFiles": str(tmp_path)}) is None
    assert app_window_command("http://x", {}) is None


def _launch_tray_again(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> list[str]:
    import sys

    from transcribe import tray

    monkeypatch.delenv("TRANSCRIBE_PORT", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(sys, "argv", ["transcribe-tray"])
    monkeypatch.setattr(tray, "port_owner", lambda client: "recorder")
    opened: list[str] = []
    monkeypatch.setattr(tray.webbrowser, "open", opened.append)
    return opened


def test_tray_opens_the_page_in_an_app_window(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from transcribe import tray

    edge = _install(tmp_path, EDGE)
    opened = _launch_tray_again(monkeypatch, tmp_path)
    launched: list[list[str]] = []
    monkeypatch.setattr(tray.subprocess, "Popen", launched.append)
    tray.main()
    assert launched == [[str(edge), "--app=http://127.0.0.1:8765"]]
    assert opened == []


def test_tray_falls_back_to_the_browser_when_the_app_window_fails(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from transcribe import tray

    _install(tmp_path, EDGE)
    opened = _launch_tray_again(monkeypatch, tmp_path)

    def broken(command):
        raise OSError("not a valid application")

    monkeypatch.setattr(tray.subprocess, "Popen", broken)
    tray.main()
    assert opened == ["http://127.0.0.1:8765"]


def test_installer_ships_python_instead_of_letting_uv_download_it() -> None:
    # A uv-managed Python adds a junction that Inno Setup's RedirectionGuard blocks (os error 448).
    root = Path(__file__).parent.parent / "installer"
    setup = (root / "setup.cmd").read_text(encoding="utf-8")
    assert 'UV_PYTHON_DOWNLOADS=never' in setup and r'--python "%HERE%runtime\python.exe"' in setup
    assert r'DestDir: "{app}\runtime"' in (root / "transcribe.iss").read_text(encoding="utf-8")
    assert "HF_HUB_DISABLE_SYMLINKS=1" in (root / "download-models.cmd").read_text(encoding="utf-8")
