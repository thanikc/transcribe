"""Command line: `transcribe serve|mcp|record|import|list|show|search|rename|delete|download-models`."""

from __future__ import annotations

import argparse
import logging
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import TYPE_CHECKING

from transcribe.client import (
    ServiceClient,
    ServiceError,
    ServiceUnavailable,
    connect,
    hit_line,
    meeting_line,
    transcript_text,
)
from transcribe.domain import LANGUAGES, MODES
from transcribe.updates import UpdateService, installed_version

if TYPE_CHECKING:
    from transcribe.recorder import Recorder

DEFAULT_PORT = 8765


def _port() -> int:
    return int(os.environ.get("TRANSCRIBE_PORT", DEFAULT_PORT))


# Seam for tests: how commands reach the service.
def _client() -> ServiceClient:
    return connect(_port())


def _venv_on_network_path() -> bool:
    # Windows cannot load native extension DLLs (numpy, ctranslate2, onnxruntime) from a UNC path,
    # which is where a virtualenv inside a WSL checkout ends up.
    return sys.platform == "win32" and sys.prefix.startswith("\\\\")


def _data_dir(fake: bool = False) -> Path:
    configured = os.environ.get("TRANSCRIBE_DATA_DIR")
    if configured:
        return Path(configured)
    return Path(tempfile.mkdtemp(prefix="transcribe-")) if fake else Path.home() / "Meetings"


def _model_name() -> str:
    return os.environ.get("TRANSCRIBE_MODEL", "large-v3")


def build_recorder(fake: bool = False) -> tuple[Recorder, Path]:
    """The recorder service's Recorder (shared by `serve` and the tray app) and its data dir."""
    from transcribe.recorder import Recorder
    from transcribe.store import MeetingStore

    data_dir = _data_dir(fake)
    store = MeetingStore(data_dir)
    if fake:
        from transcribe import devfakes

        from transcribe.capture import AudioFileConverter

        recorder = Recorder(
            store,
            devfakes.FakeCapture(),
            devfakes.FakeSpeechToText(),
            devfakes.FakeDiarizer(),
            converter=AudioFileConverter(),
        )
    else:
        from transcribe.capture import AudioFileConverter, SoundcardCapture
        from transcribe.diarize import SherpaDiarizer
        from transcribe.stt import WhisperSpeechToText

        recorder = Recorder(
            store,
            SoundcardCapture(),
            WhisperSpeechToText(),
            SherpaDiarizer(data_dir / ".models"),
            default_model=_model_name(),
            converter=AudioFileConverter(),
        )
    return recorder, data_dir


def _serve(port: int, fake: bool) -> int:
    if not fake and _venv_on_network_path():
        print(
            f"The virtualenv is on a network path ({sys.prefix}), where Windows cannot load numpy.\n"
            "Start the service with transcribe.cmd from the repo, or set UV_PROJECT_ENVIRONMENT "
            "to a folder on a Windows drive (see the README).",
            file=sys.stderr,
        )
        return 1
    import uvicorn

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    from transcribe.web import create_app

    recorder, data_dir = build_recorder(fake)
    for meeting_id in recorder.recover_interrupted():
        print(f'marked interrupted recording "{meeting_id}" as failed (its audio can still be transcribed)')
    print(f"Data directory: {data_dir}")
    print(f"Recorder service: http://127.0.0.1:{port}")
    updates = UpdateService()
    updates.start_checking()  # a git checkout (version "dev") never checks
    uvicorn.run(create_app(recorder, updates=updates), host="127.0.0.1", port=port, log_level="warning")
    return 0


def _download_models() -> int:
    from transcribe.diarize import SherpaDiarizer
    from transcribe.domain import MODELS
    from transcribe.stt import WhisperSpeechToText

    name = _model_name()
    size = f" ({MODELS[name]})" if name in MODELS else ""
    # The Hub's "set a HF_TOKEN for higher rate limits" notice alarms people in the installer's window.
    logging.getLogger("huggingface_hub.utils._http").setLevel(logging.ERROR)
    try:
        print(f"Downloading the Whisper model {name}{size}…", flush=True)
        WhisperSpeechToText().download(name)
        print("Downloading the speaker models…", flush=True)
        SherpaDiarizer(_data_dir() / ".models").ensure_models()
    except Exception as error:  # network, disk full, HF hub: all end the same way for the installer
        print(f"model download failed: {error}", file=sys.stderr)
        return 1
    print("Models ready")
    return 0


def _record(args: argparse.Namespace) -> int:
    client = _client()
    meeting = client.start(args.title, args.mode, args.language)
    print(f'Started "{meeting["title"] or meeting["id"]}" ({meeting["id"]}). Recording… press Ctrl+C to stop')
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    stopped = client.stop()
    print(f'Stopped {stopped["id"]}. Transcription has started; see it with `transcribe show {stopped["id"]}`')
    return 0


def _import(args: argparse.Namespace) -> int:
    path = Path(args.file)
    if not path.is_file():
        print(f"no such file: {path}", file=sys.stderr)
        return 1
    meeting = _client().import_audio(path, path.stem if args.title is None else args.title, args.language)
    name = meeting["title"] or meeting["id"]
    print(f'Imported "{name}" ({meeting["id"]}). Transcription has started; see it with `transcribe show {meeting["id"]}`')
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="transcribe", description="Local meeting recorder and transcriber.")
    parser.add_argument("--version", action="version", version=f"transcribe {installed_version()}")
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve", help="run the recorder service and web page")
    serve.add_argument("--port", type=int, default=_port())
    serve.add_argument("--fake", action="store_true", help="dev only: fake devices and models")
    commands.add_parser("mcp", help="run the MCP server for Claude Desktop (stdio)")
    record = commands.add_parser("record", help="record a meeting until Ctrl+C")
    record.add_argument("--title", default="Meeting")
    record.add_argument("--mode", choices=MODES, default="mic")
    record.add_argument("--language", choices=LANGUAGES, default="auto")
    imported = commands.add_parser("import", help="transcribe an existing audio file (m4a, mp3, wav…) as a meeting")
    imported.add_argument("file")
    imported.add_argument("--title", help="default: the file name without its extension")
    imported.add_argument("--language", choices=LANGUAGES, default="auto")
    commands.add_parser("list", help="list meetings, newest first")
    show = commands.add_parser("show", help="print a meeting's transcript")
    show.add_argument("id")
    search = commands.add_parser("search", help="search all transcripts")
    search.add_argument("query")
    rename = commands.add_parser("rename", help="give a meeting a new title (its id stays)")
    rename.add_argument("id")
    rename.add_argument("title", nargs="*", help="the new title; none makes it untitled")
    delete = commands.add_parser("delete", help="permanently delete a meeting: audio, transcript and all")
    delete.add_argument("id")
    commands.add_parser("download-models", help="download the Whisper and speaker models now (the installer runs this)")
    return parser


def main(argv: list[str] | None = None) -> int:
    # Windows consoles default to a legacy code page, which breaks Thai.
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    args = _build_parser().parse_args(argv)
    try:
        match args.command:
            case "serve":
                return _serve(args.port, args.fake)
            case "mcp":
                from transcribe import mcp_server

                mcp_server.main()
            case "record":
                return _record(args)
            case "import":
                return _import(args)
            case "list":
                print("\n".join(meeting_line(m) for m in _client().meetings()) or "no meetings yet")
            case "show":
                print(transcript_text(_client().meeting(args.id)))
            case "search":
                print("\n".join(hit_line(h) for h in _client().search(args.query)) or "no matches")
            case "rename":
                title = _client().rename(args.id, " ".join(args.title))["meeting"]["title"]
                print(f'"{args.id}" is now called "{title}"' if title else f'"{args.id}" is now untitled')
            case "delete":
                _client().delete(args.id)
                print(f'deleted "{args.id}"')
            case "download-models":
                return _download_models()
    except (ServiceUnavailable, ServiceError) as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
