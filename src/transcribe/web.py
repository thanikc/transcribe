"""HTTP API and static page of the recorder service."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import Route

from transcribe.domain import (
    DomainError,
    InvalidTransition,
    Meeting,
    MeetingNotFound,
    NoRecording,
    RecordingInProgress,
    Status,
    TranscriptNotReady,
    UnknownTrack,
    render_transcript,
)
from transcribe.recorder import CaptureError, Recorder

INDEX_HTML = Path(__file__).parent / "static" / "index.html"


class BadRequest(DomainError):
    """A malformed request body."""


_STATUS_CODES: tuple[tuple[type[DomainError], int], ...] = (
    (MeetingNotFound, 404),
    (UnknownTrack, 404),
    (RecordingInProgress, 409),
    (NoRecording, 409),
    (InvalidTransition, 409),
    (TranscriptNotReady, 409),
    (CaptureError, 503),
)


def _error(message: str, status: int) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=status)


async def _domain_error(request: Request, exc: Exception) -> Response:
    status = next((code for kind, code in _STATUS_CODES if isinstance(exc, kind)), 400)
    return _error(str(exc), status)


def _timestamp(seconds: float) -> str:
    minutes, secs = divmod(int(seconds), 60)
    return f"[{minutes:02d}:{secs:02d}]"


async def _body(request: Request, required: tuple[str, ...] = (), optional: tuple[str, ...] = ()) -> dict:
    """Parsed JSON object holding string fields. An empty body counts as {}."""
    raw = await request.body()
    try:
        data = json.loads(raw) if raw.strip() else {}
    except ValueError:
        raise BadRequest("request body is not valid JSON") from None
    if not isinstance(data, dict):
        raise BadRequest("request body must be a JSON object")
    for key in required:
        if not isinstance(data.get(key), str):
            raise BadRequest(f'"{key}" is required and must be a string')
    for key in optional:
        if data.get(key) is not None and not isinstance(data[key], str):
            raise BadRequest(f'"{key}" must be a string')
    return data


def create_app(recorder: Recorder, allowed_hosts: list[str] | None = None) -> Starlette:
    def _meeting_json(meeting: Meeting) -> dict:
        return {**meeting.to_dict(), "tracks": meeting.tracks, "progress": recorder.progress(meeting.id)}

    def detail(meeting_id: str) -> dict:
        meeting = recorder.store.get(meeting_id)
        if meeting.status != Status.TRANSCRIBED:
            return {"meeting": _meeting_json(meeting), "segments": None, "transcript": None}
        segments = recorder.store.load_transcript(meeting_id)
        return {
            "meeting": _meeting_json(meeting),
            "segments": [asdict(s) for s in segments],
            "transcript": render_transcript(segments, meeting.speaker_names),
        }

    async def index(request: Request) -> Response:
        return FileResponse(INDEX_HTML, media_type="text/html; charset=utf-8")

    async def status(request: Request) -> Response:
        return JSONResponse(recorder.status())

    async def start(request: Request) -> Response:
        data = await _body(request, required=("title", "mode"), optional=("language",))
        # Opening audio devices can take seconds; keep the event loop free for status polling.
        meeting = await run_in_threadpool(
            recorder.start, data["title"], data["mode"], data.get("language") or "auto"
        )
        return JSONResponse({"meeting": _meeting_json(meeting)}, status_code=201)

    async def stop(request: Request) -> Response:
        return JSONResponse({"meeting": _meeting_json(await run_in_threadpool(recorder.stop))})

    async def meetings(request: Request) -> Response:
        return JSONResponse({"meetings": [_meeting_json(m) for m in recorder.store.list()]})

    async def meeting(request: Request) -> Response:
        return JSONResponse(detail(request.path_params["id"]))

    async def audio(request: Request) -> Response:
        # track_path validates both the meeting id and the track name.
        path = recorder.store.track_path(request.path_params["id"], request.path_params["track"])
        if not path.is_file():
            return _error("that recording has no audio file", 404)
        return FileResponse(path, media_type="audio/wav")

    async def transcribe(request: Request) -> Response:
        data = await _body(request, optional=("language",))
        updated = recorder.transcribe(request.path_params["id"], data.get("language"))
        return JSONResponse({"meeting": _meeting_json(updated)})

    async def speakers(request: Request) -> Response:
        data = await _body(request, required=("speaker", "name"))
        recorder.rename_speaker(request.path_params["id"], data["speaker"], data["name"])
        return JSONResponse(detail(request.path_params["id"]))

    async def search(request: Request) -> Response:
        query = request.query_params.get("q", "").strip()
        if not query:
            return _error('query parameter "q" is required', 400)
        titles = {m.id: m.title for m in recorder.store.list()}
        hits = [
            {
                "meeting_id": h.meeting_id,
                "title": titles.get(h.meeting_id, ""),
                "start": h.start,
                "timestamp": _timestamp(h.start),
                "speaker": h.speaker,
                "text": h.text,
            }
            for h in recorder.search(query)
        ]
        return JSONResponse({"hits": hits})

    async def not_found(request: Request, exc: Exception) -> Response:
        return _error("not found", 404)

    async def same_origin_json(request: Request, call_next):
        """Keep other websites from driving the API through the browser."""
        if request.method == "POST":
            if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
                return _error("Content-Type must be application/json", 415)
            origin = request.headers.get("origin")
            if origin is not None and origin != f"{request.url.scheme}://{request.headers.get('host', '')}":
                return _error("cross-origin requests are not allowed", 403)
        return await call_next(request)

    routes = [
        Route("/", index),
        Route("/api/status", status),
        Route("/api/recordings/start", start, methods=["POST"]),
        Route("/api/recordings/stop", stop, methods=["POST"]),
        Route("/api/meetings", meetings),
        Route("/api/meetings/{id}", meeting),
        Route("/api/meetings/{id}/audio/{track}", audio),
        Route("/api/meetings/{id}/transcribe", transcribe, methods=["POST"]),
        Route("/api/meetings/{id}/speakers", speakers, methods=["POST"]),
        Route("/api/search", search),
    ]
    return Starlette(
        routes=routes,
        middleware=[
            Middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts or ["127.0.0.1", "localhost"]),
            Middleware(BaseHTTPMiddleware, dispatch=same_origin_json),
        ],
        exception_handlers={DomainError: _domain_error, 404: not_found},
    )
