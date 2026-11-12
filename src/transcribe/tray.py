"""Tray app (Windows): runs the recorder service in-process behind a notification-area icon.

Started as `transcribe-tray.exe` (windowless). `--background` (used at sign-in) skips opening the page.
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import time
import webbrowser
from logging.handlers import RotatingFileHandler
from pathlib import Path

from transcribe import cli
from transcribe.client import ServiceClient, httpx
from transcribe.desktop import claude_config_files, connect_claude, icon_image, port_owner, tray_state
from transcribe.updates import UpdateError, UpdateService

log = logging.getLogger(__name__)

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE = "Transcribe"


def _logs_dir() -> Path:
    return Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "transcribe" / "logs"


def _scripts_dir() -> Path:
    # The venv's Scripts folder, which holds transcribe.exe and transcribe-tray.exe.
    return Path(sys.executable).parent


def _setup_logging() -> Path:
    logs = _logs_dir()
    logs.mkdir(parents=True, exist_ok=True)
    log_file = logs / "transcribe.log"
    handler = RotatingFileHandler(log_file, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    logging.basicConfig(level=logging.INFO, handlers=[handler], format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    # pythonw has no console: print() would fail, and tracebacks from threads would vanish.
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(logs / "errors.log", "a", encoding="utf-8", buffering=1)
    return log_file


def _message_box(text: str) -> None:
    """A blocking error dialog, for failures before the tray icon exists."""
    import ctypes

    ctypes.windll.user32.MessageBoxW(None, text, "Transcribe", 0x10)  # MB_ICONERROR


class WinregLoginStartup:
    """Start at login: the HKCU Run value that the installer also writes."""

    def __init__(self, command: str) -> None:
        self.command = command

    def enabled(self) -> bool:
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
                winreg.QueryValueEx(key, RUN_VALUE)
            return True
        except FileNotFoundError:
            return False

    def enable(self) -> None:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, RUN_VALUE, 0, winreg.REG_SZ, self.command)

    def disable(self) -> None:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            try:
                winreg.DeleteValue(key, RUN_VALUE)
            except FileNotFoundError:
                pass


def _start_service(recorder, port: int, updates: UpdateService):
    """The recorder service on a background thread. Returns the server, or None if it couldn't listen."""
    import uvicorn

    from transcribe.web import create_app

    config = uvicorn.Config(create_app(recorder, updates=updates), host="127.0.0.1", port=port, log_level="warning", log_config=None)
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, name="recorder-service", daemon=True)
    thread.start()
    while not server.started:
        if not thread.is_alive():  # uvicorn exits when it can't bind the port
            return None
        time.sleep(0.05)
    return server


def main() -> None:
    log_file = _setup_logging()
    background = "--background" in sys.argv[1:]
    port = cli._port()
    url = f"http://127.0.0.1:{port}"

    owner = port_owner(ServiceClient(httpx.Client(base_url=url, timeout=5)))
    if owner == "recorder":
        log.info("recorder already running on port %d", port)
        if not background:
            webbrowser.open(url)
        return
    port_busy = f"Port {port} is in use by another program, so Transcribe can't start.\nClose that program and try again."
    if owner == "other":
        _message_box(port_busy)
        return

    try:
        recorder, data_dir = cli.build_recorder()
        for meeting_id in recorder.recover_interrupted():
            log.info('marked interrupted recording "%s" as failed (its audio can still be transcribed)', meeting_id)
        updates = UpdateService()
        server = _start_service(recorder, port, updates)
    except Exception:
        log.exception("the recorder service failed to start")
        _message_box(f"Transcribe couldn't start. Details are in\n{log_file}")
        return
    if server is None:
        _message_box(port_busy)
        return
    log.info("recorder service on %s, data in %s, version %s", url, data_dir, updates.installed)

    import pystray

    startup = WinregLoginStartup(f'"{_scripts_dir() / "transcribe-tray.exe"}" --background')
    images = {False: icon_image(recording=False), True: icon_image(recording=True)}
    stopping = threading.Event()
    stop_checking: list[threading.Event] = []

    def open_page(icon=None, item=None) -> None:
        webbrowser.open(url)

    def toggle_startup(icon, item) -> None:
        try:
            startup.disable() if startup.enabled() else startup.enable()
        except OSError as error:
            icon.notify(f"Couldn't change start at login: {error}", "Transcribe")

    def connect(icon, item) -> None:
        def env_path(name: str) -> Path | None:
            return Path(os.environ[name]) if os.environ.get(name) else None

        files = claude_config_files(env_path("APPDATA"), env_path("LOCALAPPDATA"))
        try:
            result = connect_claude(files, str(_scripts_dir() / "transcribe.exe"))
        except OSError as error:
            icon.notify(f"Couldn't update Claude Desktop's settings: {error}", "Transcribe")
            return
        log.info("connect to Claude Desktop: connected %s, unreadable %s", result.connected, result.unreadable)
        icon.notify(result.message(), "Transcribe")

    def open_meetings(icon, item) -> None:
        data_dir.mkdir(parents=True, exist_ok=True)
        os.startfile(data_dir)

    def recording_action(icon, action, failure: str) -> None:
        def work() -> None:  # opening or closing audio devices takes seconds; the menu must not hang meanwhile
            try:
                action()
            except Exception as error:
                log.exception(failure)
                icon.notify(f"{failure}: {error}", "Transcribe")
            icon.update_menu()

        threading.Thread(target=work, name="tray-recording", daemon=True).start()

    def start_recording(mode: str):
        return lambda icon, item: recording_action(icon, lambda: recorder.start("", mode), "Couldn't start recording")

    def stop_recording(icon, item) -> None:
        recording_action(icon, recorder.stop, "Couldn't stop recording")

    def edit_vocabulary(icon, item) -> None:
        os.startfile(recorder.store.vocabulary_file())

    def quit_app(icon, item) -> None:
        stopping.set()
        for stop in stop_checking:
            stop.set()
        if recorder.status()["recording"]:
            try:
                recorder.stop()  # closes the audio files; the unfinished transcription is marked interrupted next start
            except Exception:
                log.exception("stopping the recording on quit failed")
        server.should_exit = True
        icon.stop()

    def install_update(icon, item) -> None:
        def work() -> None:  # the download takes a while; the menu must not hang meanwhile
            blocker = recorder.update_blocker()
            if blocker:
                icon.notify(blocker[0].upper() + blocker[1:] + ".", "Transcribe")
                return
            release = updates.update()
            if release is not None:
                icon.notify(f"Downloading Transcribe {release.version}…", "Transcribe")
            try:
                updates.install()
            except UpdateError as error:
                icon.notify(f"Couldn't install the update: {error}", "Transcribe")

        threading.Thread(target=work, name="update-install", daemon=True).start()

    def follow_recorder(icon) -> None:
        shown = None
        while not stopping.is_set():
            state = tray_state(recorder.status())
            if state != shown:
                icon.icon, icon.title = images[state[0]], state[1]
                if shown is None or state[0] != shown[0]:
                    icon.update_menu()  # "Install update" is disabled while recording
                shown = state
            stopping.wait(1)

    def announce(icon, release) -> None:
        icon.update_menu()  # shows the "Install update" item
        icon.notify(f"Transcribe {release.version} is available. Install it from this icon's menu or the recorder page.", "Transcribe")

    def setup(icon) -> None:
        icon.visible = True
        updates.on_update = lambda release: announce(icon, release)
        stop_checking.append(updates.start_checking())
        threading.Thread(target=follow_recorder, args=(icon,), name="tray-state", daemon=True).start()
        if not background:
            open_page()

    def idle(item) -> bool:
        return not recorder.status()["recording"]

    menu = pystray.Menu(
        pystray.MenuItem("Open recorder", open_page, default=True),
        pystray.MenuItem("Start recording (online call)", start_recording("mic+system"), visible=idle),
        pystray.MenuItem("Start recording (in person)", start_recording("mic"), visible=idle),
        pystray.MenuItem("Stop recording", stop_recording, visible=lambda item: not idle(item)),
        pystray.MenuItem("Start at login", toggle_startup, checked=lambda item: startup.enabled()),
        pystray.MenuItem("Connect to Claude Desktop", connect),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Open log", lambda icon, item: os.startfile(log_file)),
        pystray.MenuItem("Open meetings folder", open_meetings),
        pystray.MenuItem("Edit vocabulary", edit_vocabulary),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(f"Version {updates.installed}", lambda icon, item: None, enabled=False),
        pystray.MenuItem(
            lambda item: f"Install update {updates.update().version}" if updates.update() else "Install update",
            install_update,
            enabled=lambda item: not recorder.status()["recording"],
            visible=lambda item: updates.update() is not None,
        ),
        pystray.MenuItem("Quit", quit_app),
    )
    pystray.Icon("transcribe", images[False], "Transcribe: idle", menu).run(setup=setup)


if __name__ == "__main__":
    main()
