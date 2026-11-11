# Plan: delete a meeting

Scenarios: `docs/features/delete-meeting.feature`

`MeetingStore.delete` already exists (used to clean up a failed start). This exposes it.

1. **Domain + Recorder**: new `MeetingBusy(DomainError)` ("stop the recording first" /
   "wait until transcription finishes"). `Recorder.delete(id)` under `_lock`: refuse if status is
   `recording` or `transcribing`, else `store.delete(id)`.
   Verify: recorder tests (transcribed, failed, recording, transcribing, unknown).
2. **API**: `DELETE /api/meetings/{id}` -> 200 `{"deleted": id}`; `MeetingBusy` -> 409.
   The same-origin/JSON guard now covers every non-GET method, not only POST.
   Verify: web tests incl. foreign Origin and wrong Content-Type refused.
3. **Client, CLI, MCP**: `ServiceClient.delete(id)`; `transcribe delete <id>`;
   MCP tool `delete_meeting(meeting_id)` whose description says deletion is permanent and to
   only use it when the user asks.
   Verify: CLI + MCP tests.
4. **Web page**: Delete button in the meeting view, `confirm()` naming the meeting, then back to
   the list. Hidden while recording/transcribing.
   Verify: `serve --fake` checked in a browser (or by API if no browser available).
5. Spec: add the endpoint, tool, CLI command and the busy invariant.

Skipped: undo / trash folder, a y/N prompt in the CLI (typing the id is the confirmation),
bulk delete.
