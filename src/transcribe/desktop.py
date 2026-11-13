"""Desktop integration logic for the tray app: icon state, Claude Desktop connection, single instance.

No Windows imports here, so it is tested anywhere. `tray.py` wires it to the real tray and registry.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from collections.abc import Mapping
from pathlib import Path
from typing import Literal

from transcribe.client import ServiceClient, ServiceError, ServiceUnavailable

CLAUDE_CONFIG_NAME = "claude_desktop_config.json"
_TOOLTIP_MAX = 127  # Windows truncates or rejects longer notification-area tooltips


def tray_state(status: dict) -> tuple[bool, str]:
    """(recording?, tooltip) from the recorder's status."""
    if not status.get("recording"):
        return False, "Transcribe: idle"
    tooltip = f"Recording: {status.get('title', '')}"
    if len(tooltip) > _TOOLTIP_MAX:
        tooltip = tooltip[: _TOOLTIP_MAX - 1] + "…"
    return True, tooltip


_APP_BROWSERS = (Path("Microsoft/Edge/Application/msedge.exe"), Path("Google/Chrome/Application/chrome.exe"))
_PROGRAM_ROOTS = ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA")


def app_window_command(url: str, env: Mapping[str, str]) -> list[str] | None:
    """The command that opens `url` as an Edge (else Chrome) app window, or None if neither is installed."""
    for browser in _APP_BROWSERS:
        for root in _PROGRAM_ROOTS:
            if env.get(root) and (exe := Path(env[root]) / browser).is_file():
                return [str(exe), f"--app={url}"]
    return None


def icon_image(recording: bool):
    """A round badge with a microphone: red while recording, grey when idle."""
    from PIL import Image, ImageDraw

    size = 64
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((2, 2, size - 3, size - 3), fill=(220, 38, 38) if recording else (100, 110, 125))
    white = (255, 255, 255)
    draw.rounded_rectangle((25, 13, 39, 37), radius=7, fill=white)  # capsule
    draw.arc((18, 22, 46, 44), start=0, end=180, fill=white, width=3)  # holder
    draw.line((32, 44, 32, 51), fill=white, width=3)  # stem
    draw.line((24, 51, 40, 51), fill=white, width=3)  # base
    return image


def claude_config_files(appdata: Path | None, localappdata: Path | None) -> list[Path]:
    """Config files of the Claude Desktop builds that are installed (their folder exists)."""
    dirs = []
    if appdata and (appdata / "Claude").is_dir():
        dirs.append(appdata / "Claude")  # installer build
    if localappdata and (localappdata / "Claude-Data").is_dir():
        dirs += sorted(p for p in (localappdata / "Claude-Data").glob("claude_*") if p.is_dir())  # Store build
    return [d / CLAUDE_CONFIG_NAME for d in dirs]


@dataclass
class ClaudeConnection:
    connected: list[Path] = field(default_factory=list)
    unreadable: list[Path] = field(default_factory=list)

    def message(self) -> str:
        if not self.connected and not self.unreadable:
            return "Claude Desktop was not found. Please install Claude Desktop first, then try again."
        lines = []
        if self.connected:
            lines.append(
                "Connected to Claude Desktop. Now quit Claude Desktop from its tray icon and start it again."
            )
        for path in self.unreadable:
            lines.append(f"Couldn't read {path}, so it was left unchanged. Fix or delete it and try again.")
        return "\n".join(lines)


def _read_config(path: Path) -> dict | None:
    """The parsed config, {} for a missing file, or None if it can't be safely updated."""
    if not path.exists():
        return {}
    try:
        config = json.loads(path.read_text(encoding="utf-8-sig"))  # -sig: Notepad may add a BOM
    except (ValueError, OSError):
        return None
    if not isinstance(config, dict) or not isinstance(config.get("mcpServers", {}), dict):
        return None
    return config


def connect_claude(files: list[Path], command: str) -> ClaudeConnection:
    """Add the transcribe MCP server to each config, keeping every other key and a .bak of the old file."""
    result = ClaudeConnection()
    for path in files:
        config = _read_config(path)
        if config is None:
            result.unreadable.append(path)
            continue
        servers = {**config.get("mcpServers", {}), "transcribe": {"command": command, "args": ["mcp"]}}
        if path.exists():
            shutil.copy2(path, path.with_name(path.name + ".bak"))
        part = path.with_name(path.name + ".part")
        part.write_text(json.dumps({**config, "mcpServers": servers}, indent=2, ensure_ascii=False), encoding="utf-8")
        part.replace(path)
        result.connected.append(path)
    return result


def port_owner(client: ServiceClient) -> Literal["recorder", "other", "free"]:
    """Who answers on the service port: a running recorder service, some other program, or nobody."""
    try:
        status = client.status()
    except ServiceUnavailable:
        return "free"
    except (ServiceError, ValueError):
        return "other"
    return "recorder" if isinstance(status, dict) and "recording" in status else "other"
