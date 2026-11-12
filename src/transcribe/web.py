"""HTTP API and static page of the recorder service.

Handlers that read the disk or wait for the recorder's lock are plain functions, which Starlette runs in
its thread pool, or hand that part to the pool after reading the request body. The event loop stays free
for the status polls.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
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
    MeetingBusy,
    MeetingNotFound,
    NoRecording,
    RecordingInProgress,
    Status,
    TranscriptNotReady,
    UnknownTrack,
    UnreadableAudio,
    render_transcript,
    timestamp,
)
from transcribe.recorder import CaptureError, Recorder
from transcribe.updates import UpdateError, UpdateService

STATIC_DIR = Path(__file__).parent / "static"
INDEX_HTML = STATIC_DIR / "index.html"
SCRIPT_NAME = re.compile(r"[a-z]+\.js")
IMPORT_PATH = "/api/meetings/import"
# Raw audio, not form data: a browser sends it cross-site only after a preflight, which this service never answers.
AUDIO_UPLOAD = "application/octet-stream"


class BadRequest(DomainError):
    """A malformed request body."""


_STATUS_CODES: tuple[tuple[type[DomainError], int], ...] = (
    (MeetingNotFound, 404),
    (UnknownTrack, 404),
    (RecordingInProgress, 409),
    (NoRecording, 409),
    (InvalidTransition, 409),
    (MeetingBusy, 409),
    (TranscriptNotReady, 409),
    (CaptureError, 503),
    (UpdateError, 409),
)


def _error(message: str, status: int) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=status)


async def _domain_error(request: Request, exc: Exception) -> Response:
    status = next((code for kind, code in _STATUS_CODES if isinstance(exc, kind)), 400)
    return _error(str(exc), status)


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


def create_app(recorder: Recorder, allowed_hosts: list[str] | None = None, updates: UpdateService | None = None) -> Starlette:
    # Without one (tests, `serve`), the version comes from the package and no update is ever offered.
    updates = updates or UpdateService(can_install=False)

    def _meeting_json(meeting: Meeting) -> dict:
        return {
            **meeting.to_dict(),
            "tracks": meeting.tracks,
            "audio_bytes": recorder.store.audio_bytes(meeting),
            "progress": recorder.progress(meeting.id),
        }

    def detail(meeting_id: str) -> dict:
        meeting = recorder.store.get(meeting_id)
        notes = recorder.store.load_notes(meeting_id)
        if meeting.status != Status.TRANSCRIBED:
            return {"meeting": _meeting_json(meeting), "notes": notes, "segments": None, "transcript": None}
        segments = recorder.store.load_transcript(meeting_id)
        return {
            "meeting": _meeting_json(meeting),
            "notes": notes,
            "segments": [s.to_dict() for s in segments],
            "transcript": render_transcript(segments, meeting.speaker_names),
        }

    async def index(request: Request) -> Response:
        return FileResponse(INDEX_HTML, media_type="text/html; charset=utf-8")

    def script(request: Request) -> Response:
        # Served with an explicit type: browsers refuse module scripts that arrive as text/plain,
        # which is what Windows can guess for .js from its registry.
        name = request.path_params["name"]
        path = STATIC_DIR / "js" / name
        if not SCRIPT_NAME.fullmatch(name) or not path.is_file():
            return _error("not found", 404)
        return FileResponse(path, media_type="text/javascript; charset=utf-8")

    async def status(request: Request) -> Response:
        return JSONResponse(recorder.status())

    async def start(request: Request) -> Response:
        data = await _body(request, required=("title", "mode"), optional=("language", "model"))

        def work() -> dict:  # opening audio devices can take seconds
            meeting = recorder.start(data["title"], data["mode"], data.get("language") or "auto", data.get("model"))
            return {"meeting": _meeting_json(meeting)}

        return JSONResponse(await run_in_threadpool(work), status_code=201)

    async def import_audio(request: Request) -> Response:
        params = request.query_params
        # Streamed to disk: a phone recording of a long meeting can be hundreds of MB.
        fd, name = tempfile.mkstemp(suffix=".upload")
        upload = Path(name)
        try:
            with os.fdopen(fd, "wb") as file:
                async for chunk in request.stream():
                    await run_in_threadpool(file.write, chunk)

            def work() -> dict:
                meeting = recorder.import_audio(
                    upload, params.get("title", ""), params.get("language") or "auto", params.get("model") or None
                )
                return {"meeting": _meeting_json(meeting)}

            return JSONResponse(await run_in_threadpool(work), status_code=201)
        finally:
            upload.unlink(missing_ok=True)

    def stop(request: Request) -> Response:
        return JSONResponse({"meeting": _meeting_json(recorder.stop())})

    def meetings(request: Request) -> Response:
        return JSONResponse({"meetings": [_meeting_json(m) for m in recorder.store.list()]})

    def meeting(request: Request) -> Response:
        return JSONResponse(detail(request.path_params["id"]))

    def delete(request: Request) -> Response:
        recorder.delete(request.path_params["id"])
        return JSONResponse({"deleted": request.path_params["id"]})

    def audio(request: Request) -> Response:
        # track_path validates both the meeting id and the track name.
        path = recorder.store.track_path(request.path_params["id"], request.path_params["track"])
        if not path.is_file():
            return _error("that recording has no audio file", 404)
        return FileResponse(path, media_type="audio/wav" if path.suffix == ".wav" else "audio/mpeg")

    async def transcribe(request: Request) -> Response:
        data = await _body(request, optional=("language", "model"))
        meeting_id = request.path_params["id"]

        def work() -> dict:
            return {"meeting": _meeting_json(recorder.transcribe(meeting_id, data.get("language"), data.get("model")))}

        return JSONResponse(await run_in_threadpool(work))

    def models(request: Request) -> Response:
        # Looking in the model cache imports the speech libraries the first time, which takes a moment.
        return JSONResponse({"models": recorder.models()})

    def sources(request: Request) -> Response:
        return JSONResponse({"sources": recorder.sources()})

    async def choose_source(request: Request) -> Response:
        data = await _body(request, required=("track",), optional=("device",))

        def work() -> dict:
            recorder.choose_source(data["track"], data.get("device"))
            return {"sources": recorder.sources()}

        return JSONResponse(await run_in_threadpool(work))

    async def speakers(request: Request) -> Response:
        data = await _body(request, required=("speaker", "name"))
        meeting_id = request.path_params["id"]

        def work() -> dict:
            recorder.rename_speaker(meeting_id, data["speaker"], data["name"])
            return detail(meeting_id)

        return JSONResponse(await run_in_threadpool(work))

    async def title(request: Request) -> Response:
        data = await _body(request, required=("title",))
        meeting_id = request.path_params["id"]

        def work() -> dict:
            recorder.rename(meeting_id, data["title"])
            return detail(meeting_id)

        return JSONResponse(await run_in_threadpool(work))

    async def notes(request: Request) -> Response:
        data = await _body(request, required=("notes",))
        meeting_id = request.path_params["id"]

        def work() -> dict:
            recorder.save_notes(meeting_id, data["notes"])
            return detail(meeting_id)

        return JSONResponse(await run_in_threadpool(work))

    def search(request: Request) -> Response:
        query = request.query_params.get("q", "").strip()
        if not query:
            return _error('query parameter "q" is required', 400)
        hits = [
            {
                "meeting_id": h.meeting_id,
                "title": h.title,
                "start": h.start,
                "timestamp": timestamp(h.start),
                "speaker": h.speaker,
                "text": h.text,
            }
            for h in recorder.search(query)
        ]
        return JSONResponse({"hits": hits})

    async def version(request: Request) -> Response:
        return JSONResponse(updates.state())

    def install_update(request: Request) -> Response:
        # Downloads ~30 MB, so it runs in the thread pool like the other blocking handlers.
        blocker = recorder.update_blocker()
        if blocker:
            raise MeetingBusy(blocker)
        return JSONResponse({"launched": updates.install()})

    async def not_found(request: Request, exc: Exception) -> Response:
        return _error("not found", 404)

    async def same_origin_json(request: Request, call_next):
        """Keep other websites from driving the API through the browser."""
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            expected = AUDIO_UPLOAD if request.url.path == IMPORT_PATH else "application/json"
            if request.headers.get("content-type", "").split(";")[0].strip().lower() != expected:
                return _error(f"Content-Type must be {expected}", 415)
            origin = request.headers.get("origin")
            if origin is not None and origin != f"{request.url.scheme}://{request.headers.get('host', '')}":
                return _error("cross-origin requests are not allowed", 403)
        return await call_next(request)

    routes = [
        Route("/", index),
        Route("/static/js/{name}", script),
        Route("/api/status", status),
        Route("/api/recordings/start", start, methods=["POST"]),
        Route("/api/recordings/stop", stop, methods=["POST"]),
        Route("/api/meetings", meetings),
        Route(IMPORT_PATH, import_audio, methods=["POST"]),
        Route("/api/meetings/{id}", meeting),
        Route("/api/meetings/{id}", delete, methods=["DELETE"]),
        Route("/api/meetings/{id}/audio/{track}", audio),
        Route("/api/meetings/{id}/transcribe", transcribe, methods=["POST"]),
        Route("/api/meetings/{id}/speakers", speakers, methods=["POST"]),
        Route("/api/meetings/{id}/title", title, methods=["POST"]),
        Route("/api/meetings/{id}/notes", notes, methods=["POST"]),
        Route("/api/models", models),
        Route("/api/sources", sources),
        Route("/api/sources", choose_source, methods=["POST"]),
        Route("/api/search", search),
        Route("/api/version", version),
        Route("/api/update/install", install_update, methods=["POST"]),
    ]
    return Starlette(
        routes=routes,
        middleware=[
            Middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts or ["127.0.0.1", "localhost"]),
            Middleware(BaseHTTPMiddleware, dispatch=same_origin_json),
        ],
        exception_handlers={DomainError: _domain_error, 404: not_found},
    )
