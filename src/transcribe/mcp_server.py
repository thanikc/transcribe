"""MCP shim for Claude Desktop: stdio tools that forward to the recorder service."""

from __future__ import annotations

import os
from typing import Callable

from mcp.server.mcpserver import MCPServer

from transcribe.client import (
    ServiceClient,
    ServiceError,
    ServiceUnavailable,
    connect,
    hit_line,
    meeting_line,
    transcript_text,
)


def build_server(client_factory: Callable[[], ServiceClient]) -> MCPServer:
    server = MCPServer("transcribe")

    def forward(action: Callable[[ServiceClient], str]) -> str:
        """Run a tool against the service, turning refusals into reply text."""
        try:
            return action(client_factory())
        except (ServiceUnavailable, ServiceError) as error:
            return str(error)

    @server.tool()
    def start_recording(title: str, mode: str, language: str = "auto") -> str:
        """Start recording a meeting on this computer.

        mode: "mic" for an in-person meeting (microphone only), "mic+system" for an online call
        (microphone plus the computer's audio output, so remote speakers are captured too).
        language: "auto" (detect), "th" (Thai) or "en" (English).
        """
        return forward(
            lambda c: f'Recording started: "{(m := c.start(title, mode, language))["title"] or m["id"]}" (id {m["id"]}).'
        )

    @server.tool()
    def stop_recording() -> str:
        """Stop the current recording, including one started from the web page. Transcription then
        runs in the background; use list_meetings to see when it is done."""
        return forward(
            lambda c: f'Recording stopped (id {(m := c.stop())["id"]}). Transcription has started; '
            "the meeting shows as transcribed in list_meetings when it is ready."
        )

    @server.tool()
    def list_meetings() -> str:
        """List recorded meetings, newest first: id, title, start time, duration and status
        (recording, transcribing, transcribed, failed)."""
        return forward(lambda c: "\n".join(meeting_line(m) for m in c.meetings()) or "no meetings yet")

    @server.tool()
    def get_transcript(meeting_id: str) -> str:
        """Get the transcript of a meeting, with timestamps and speaker names. Use the id from
        list_meetings. Says so if the transcript is not ready yet."""
        return forward(lambda c: transcript_text(c.meeting(meeting_id)))

    @server.tool()
    def search_transcripts(query: str) -> str:
        """Search all transcripts for a word or phrase (case-insensitive). Returns one line per hit:
        meeting id, timestamp, speaker and text."""
        return forward(lambda c: "\n".join(hit_line(h) for h in c.search(query)) or "no matches")

    @server.tool()
    def rename_speaker(meeting_id: str, speaker: str, name: str) -> str:
        """Give a speaker a real name throughout a meeting's transcript, for example when the
        transcript shows someone being addressed ("thanks, Somchai"). speaker is the current label
        such as "Speaker 1" or "You"; an empty name resets it."""

        def rename(c: ServiceClient) -> str:
            c.rename_speaker(meeting_id, speaker, name)
            return f'"{speaker}" is now "{name}" in {meeting_id}.' if name else f'"{speaker}" name reset in {meeting_id}.'

        return forward(rename)

    @server.tool()
    def rename_meeting(meeting_id: str, title: str) -> str:
        """Give a meeting a new title, for example one that says what it was about once you have
        read its transcript. The meeting id stays the same. An empty title makes it untitled."""

        def rename(c: ServiceClient) -> str:
            new = c.rename(meeting_id, title)["meeting"]["title"]
            return f'"{meeting_id}" is now called "{new}".' if new else f'"{meeting_id}" is now untitled.'

        return forward(rename)

    @server.tool()
    def save_meeting_notes(meeting_id: str, notes: str) -> str:
        """Save notes with a meeting, such as a summary, decisions and action items you wrote from its
        transcript, so they are kept with the meeting and shown on the recorder page and by get_transcript.
        Replaces any notes it had, so include what should stay. Empty notes remove them."""

        def save(c: ServiceClient) -> str:
            c.save_notes(meeting_id, notes)
            return f'Saved notes for "{meeting_id}".' if notes.strip() else f'Removed the notes of "{meeting_id}".'

        return forward(save)

    @server.tool()
    def delete_meeting(meeting_id: str) -> str:
        """Permanently delete a meeting: its audio, transcript and metadata. This cannot be undone,
        so only call it when the user explicitly asks to delete that meeting. A meeting that is
        still recording or transcribing can't be deleted."""

        def delete(c: ServiceClient) -> str:
            c.delete(meeting_id)
            return f'Deleted "{meeting_id}".'

        return forward(delete)

    return server


def main() -> None:
    port = int(os.environ.get("TRANSCRIBE_PORT", "8765"))
    build_server(lambda: connect(port)).run("stdio")
