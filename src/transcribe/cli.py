"""Command line: `transcribe serve|mcp|record|list|show|search|delete`."""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
import time
from pathlib import Path

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

    from transcribe.recorder import Recorder
    from transcribe.store import MeetingStore
    from transcribe.web import create_app

    configured = os.environ.get("TRANSCRIBE_DATA_DIR")
    if configured:
        data_dir = Path(configured)
    else:
        data_dir = Path(tempfile.mkdtemp(prefix="transcribe-")) if fake else Path.home() / "Meetings"
    store = MeetingStore(data_dir)
    if fake:
        from transcribe import devfakes

        recorder = Recorder(
            store,
            devfakes.FakeCapture(),
            devfakes.FakeSpeechToText(),
            devfakes.FakeDiarizer(),
        )
    else:
        from transcribe.capture import SoundcardCapture
        from transcribe.diarize import SherpaDiarizer
        from transcribe.stt import WhisperSpeechToText

        recorder = Recorder(
            store,
            SoundcardCapture(),
            WhisperSpeechToText(os.environ.get("TRANSCRIBE_MODEL", "large-v3")),
            SherpaDiarizer(data_dir / ".models"),
        )
    for meeting_id in recorder.recover_interrupted():
        print(f'marked interrupted recording "{meeting_id}" as failed (its audio can still be transcribed)')
    print(f"Data directory: {data_dir}")
    print(f"Recorder service: http://127.0.0.1:{port}")
    uvicorn.run(create_app(recorder), host="127.0.0.1", port=port, log_level="warning")
    return 0


def _record(args: argparse.Namespace) -> int:
    client = _client()
    meeting = client.start(args.title, args.mode, args.language)
    print(f'Started "{meeting["title"]}" ({meeting["id"]}). Recording… press Ctrl+C to stop')
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    stopped = client.stop()
    print(f'Stopped {stopped["id"]}. Transcription has started; see it with `transcribe show {stopped["id"]}`')
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="transcribe", description="Local meeting recorder and transcriber.")
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve", help="run the recorder service and web page")
    serve.add_argument("--port", type=int, default=_port())
    serve.add_argument("--fake", action="store_true", help="dev only: fake devices and models")
    commands.add_parser("mcp", help="run the MCP server for Claude Desktop (stdio)")
    record = commands.add_parser("record", help="record a meeting until Ctrl+C")
    record.add_argument("--title", default="Meeting")
    record.add_argument("--mode", choices=MODES, default="mic")
    record.add_argument("--language", choices=LANGUAGES, default="auto")
    commands.add_parser("list", help="list meetings, newest first")
    show = commands.add_parser("show", help="print a meeting's transcript")
    show.add_argument("id")
    search = commands.add_parser("search", help="search all transcripts")
    search.add_argument("query")
    delete = commands.add_parser("delete", help="permanently delete a meeting: audio, transcript and all")
    delete.add_argument("id")
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
            case "list":
                print("\n".join(meeting_line(m) for m in _client().meetings()) or "no meetings yet")
            case "show":
                print(transcript_text(_client().meeting(args.id)))
            case "search":
                print("\n".join(hit_line(h) for h in _client().search(args.query)) or "no matches")
            case "delete":
                _client().delete(args.id)
                print(f'deleted "{args.id}"')
    except (ServiceUnavailable, ServiceError) as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
