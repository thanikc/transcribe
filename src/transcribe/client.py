"""HTTP client of the recorder service, shared by the MCP shim and the CLI."""

from __future__ import annotations

from urllib.parse import quote

import httpx2 as httpx


class ServiceUnavailable(Exception):
    """The recorder service can't be reached."""


class ServiceError(Exception):
    """The service refused the request; the message is meant to be shown as-is."""


class ServiceClient:
    def __init__(self, http: httpx.Client) -> None:
        self.http = http

    def _call(self, method: str, path: str, **kwargs) -> dict:
        try:
            response = self.http.request(method, path, **kwargs)
        except httpx.TransportError:
            raise ServiceUnavailable("recorder service not running, start it with `transcribe serve`") from None
        if response.is_success:
            return response.json()
        try:
            message = response.json()["error"]
        except (ValueError, KeyError, TypeError):
            message = response.text or f"request failed ({response.status_code})"
        raise ServiceError(message)

    def _post(self, path: str, body: dict | None = None) -> dict:
        # The service insists on a JSON body for every POST.
        return self._call("POST", path, json=body or {})

    def status(self) -> dict:
        return self._call("GET", "/api/status")

    def start(self, title: str, mode: str, language: str = "auto") -> dict:
        return self._post("/api/recordings/start", {"title": title, "mode": mode, "language": language})["meeting"]

    def stop(self) -> dict:
        return self._post("/api/recordings/stop")["meeting"]

    def meetings(self) -> list[dict]:
        return self._call("GET", "/api/meetings")["meetings"]

    def meeting(self, meeting_id: str) -> dict:
        return self._call("GET", f"/api/meetings/{quote(meeting_id, safe='')}")

    def transcribe(self, meeting_id: str, language: str | None = None) -> dict:
        body = {"language": language} if language else {}
        return self._post(f"/api/meetings/{quote(meeting_id, safe='')}/transcribe", body)["meeting"]

    def rename_speaker(self, meeting_id: str, speaker: str, name: str) -> dict:
        return self._post(f"/api/meetings/{quote(meeting_id, safe='')}/speakers", {"speaker": speaker, "name": name})

    def search(self, query: str) -> list[dict]:
        return self._call("GET", "/api/search", params={"q": query})["hits"]


def connect(port: int) -> ServiceClient:
    return ServiceClient(httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=30))


def _clock(seconds: float | None) -> str:
    minutes, secs = divmod(int(seconds or 0), 60)
    return f"{minutes:02d}:{secs:02d}"


def _step(progress: dict) -> str:
    """"step 2 of 3, 40%", without the percentage until the step reports one."""
    text = f"step {progress['step_number']} of {progress['steps']}"
    return text if progress["fraction"] is None else f"{text}, {round(progress['fraction'] * 100)}%"


def meeting_line(m: dict) -> str:
    """One listing line: id, title, start time, duration, status."""
    start = m["started_at"][:16].replace("T", " ")
    status = m["status"] + (f" ({_step(m['progress'])})" if m.get("progress") else "")
    return f"{m['id']}  {m['title']}  {start}  {_clock(m['duration'])}  {status}"


def transcript_text(detail: dict) -> str:
    """Header plus the rendered transcript, or the not-ready message."""
    m = detail["meeting"]
    if detail["transcript"] is None:
        progress = m.get("progress")
        doing = f"; {progress['step']}, {_step(progress)}" if progress else ""
        return f'the transcript of "{m["id"]}" is not ready yet (status: {m["status"]}{doing})'
    language = m["language"]
    if language == "auto" and m["detected_languages"]:
        language = "auto (detected: " + ", ".join(sorted(set(m["detected_languages"].values()))) + ")"
    header = [
        m["title"],
        f"Date: {m['started_at'][:16].replace('T', ' ')}",
        f"Language: {language}",
    ]
    header += [f"Warning: {w}" for w in m["warnings"]]
    return "\n".join(header) + "\n\n" + detail["transcript"]


def hit_line(hit: dict) -> str:
    return f"{hit['meeting_id']} {hit['timestamp']} {hit['speaker']}: {hit['text']}"
