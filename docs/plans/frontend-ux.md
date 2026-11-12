# Plan: web page UX improvements

Sixteen independent plans from a review of `frontend/`. Each can be implemented alone unless its
"Touches" line says otherwise. Nothing here is started.

For every plan that is implemented:

- The scenarios go in the named `.feature` file first, and the Web UI paragraph of
  `docs/specs/meeting-recorder.md` (lines 85–90) is updated to match.
- `npm --prefix frontend run test`, `npm --prefix frontend run test:e2e` and `uv run pytest -q` stay green.
- `npm --prefix frontend run build` is run and the rebuilt `src/transcribe/static/` is committed (it is tracked).
- Layout and audio behaviour can't be asserted in jsdom, so those are checked in a browser against
  `transcribe serve --fake`. Its audio is one second of silence per track and its transcript has three
  segments, so real playback and long transcripts need a look on Windows with a real meeting.

Size: XS = under an hour, S = a couple of hours, M = half a day to a day, L = more than a day.

| # | Plan | Size | Backend change | Breaks existing E2E steps |
|---|---|---|---|---|
| 1 | One player for all tracks | L | no | no |
| 2 | Search hit opens the matching line | S | no | no |
| 3 | Meeting actions in the header | S | no | step 8 |
| 4 | Sidebar and transcript scroll separately | S | no | no |
| 5 | Transcript grouped into speaker turns | M | no | steps 3, 4, 5 |
| 6 | "Can't reach the recorder" banner | S | no | no |
| 7 | Mode switch beside the record button | S | no | step 1 |
| 8 | Recording shown in the tab title; clearer "no sound" | S | no | no |
| 9 | Title field: cleared, renames the live recording, separate for import | M | no | no |
| 10 | Inline rename and delete confirmation (no native dialogs) | M | no | steps 5, 6, 8 |
| 11 | Quieter, date-grouped meeting list | S | no | no |
| 12 | Stable speaker colours | XS | no | no |
| 13 | First-run and loading states | XS | no | step 1 |
| 14 | Fonts: use what is installed | XS | no | no |
| 15 | Larger click targets | XS | no | no |
| 16 | Import: drag and drop, upload progress | M | no | no |

Suggested order if several are chosen: 12, 4, 6, 13, 14 (isolated) → 3, then 10 (same header code) →
7, then 9 (same dock code) → 2 → 5 → 1 (5 and 1 both rewrite `TranscriptList`; doing 5 first means 1
highlights sentences inside turns instead of rows that are about to go away).

---

## 1. One player for all tracks

**Problem.** A `mic+system` meeting has two native `<audio>` players. Clicking a timestamp plays that
line's track and pauses the other, so a call can never be heard with both sides.

**Scenarios:** rewrite `transcript-playback.feature` scenario 2 ("the right track plays") to "both
tracks play together from that moment"; add: speed is remembered, skip back/forward 10 s, Space toggles
play, the transcript follows the playing line, a track can be muted.

1. `AudioBar` keeps one hidden `<audio id="audio-<track>">` per track (same ids and `key`, so audio still
   survives progress refreshes and "Play through" still applies to each element) and renders its own
   controls: play/pause, −10 s / +10 s, a seek slider (`<input type="range">`), `01:23 / 45:10`, a speed
   select (1×, 1.25×, 1.5×, 2×; saved as `transcribe.playbackRate`), and with two tracks a mute toggle
   per track.
2. Sync: the first track is the master. Play, pause, seek and rate are applied to every element. On the
   master's `timeupdate`, a follower more than 0.2 s off is re-seeked. A follower that has ended (tracks
   can differ slightly in length) stays paused.
3. `AudioBar` exposes `playFrom(seconds)` and `toggle()` through `useImperativeHandle`; `MeetingView`
   calls those instead of `document.getElementById`. `onTimeUpdate` reports one time, not a track.
4. Highlight: the line whose span holds the position; when lines of two tracks overlap, the one that
   started last. `TranscriptList` scrolls the highlighted line into view (`block: "nearest"`) when it
   changes, and stops following for 5 s after a wheel, touch or key scroll.
5. Keys, when focus is not in an input, select or button: Space = play/pause, ←/→ = ∓5 s.
6. Verify: Vitest with `HTMLMediaElement.prototype.play/pause` stubbed (sync, highlight choice,
   remembered speed). Browser: both tracks audible and in step after seeking, on a real call recording.

**Risk.** Without headphones the mic track also holds the far side (the echo the transcript drops), so
both tracks together sound doubled. The per-track mute is the answer; no server-side mix.

**Skipped:** waveform, a server-mixed single file, per-track volume sliders.
**Touches:** `AudioBar`, `MeetingView`, `TranscriptList`, `meeting.css`. Overlaps 5 and 15.

## 2. Search hit opens the matching line

**Problem.** A hit opens the meeting at the top; the hit's `start` is thrown away. Hits show plain
text with no sign of what matched, and there is no "searching" state.

**Scenarios:** new `search-jump.feature`: clicking a hit opens the meeting scrolled to that line,
briefly highlighted; a hidden line (speaker filter, collapsed transcript) is revealed first; the matched
words are marked in the hit; clicking the same hit twice scrolls again.

1. `utils.ts`: `openMeetingHash(id, start?)` writes `#/meeting/<id>?t=<start>`; a new
   `parseMeetingHash(hash) -> {id, t} | null` replaces `parseMeetingIdFromHash` (kept as a thin wrapper
   so its tests stay). Ids are `encodeURIComponent`-ed, so `?` is unambiguous.
2. `App` keeps `focus: {t, nonce}` from the hash and passes it to `MeetingView`.
3. `MeetingView`, once the detail has segments: clear the speaker filter and un-collapse if the target
   is hidden, then `TranscriptList` scrolls the segment whose `start` is nearest `t` to the centre and
   gives it a `.focus` class for 2 s (a fade; static under `prefers-reduced-motion`). Playback does not start.
4. `SearchPanel`: wrap case-insensitive matches of the query in `<mark>`; show "Searching…" while the
   request runs; pass `h.start` on click.
5. Verify: Vitest for `parseMeetingHash` and the `<mark>` split (Thai included); E2E step 7 extended:
   click the hit, the matching line has `.focus`.

**Skipped:** search-as-you-type, filtering the meeting list by title, in-transcript find (the browser's
Ctrl+F already works since the whole transcript is rendered).
**Touches:** `utils.ts`, `App`, `SearchPanel`, `MeetingView`, `TranscriptList`. If 5 is done, the target is a sentence inside a turn.

## 3. Meeting actions in the header

**Problem.** "Transcribe again" and "Delete meeting" sit in a drawer under the transcript, hundreds
of rows down in a long meeting.

**Scenarios:** `delete-meeting.feature` and the two re-transcribe page scenarios in
`meeting-recorder.feature`: reword "at the bottom" steps to "from the meeting's Actions menu".

1. `SecondaryActionsDrawer` becomes `MeetingActions`: a `details.popover` (the existing class, so Escape
   and outside-click already close it) at the right of `.meeting-header`, summary "Actions". Same two
   blocks inside, same rules for when each is shown or disabled.
2. A failed meeting keeps a visible way forward: the "Transcription failed" box gets a "Transcribe
   again…" button that opens the popover (today the drawer opens itself).
3. Remove the bottom drawer and its CSS.
4. Verify: Vitest (popover present for transcribed/failed/transcribing, absent while recording; delete
   absent while transcribing). E2E step 8 selectors updated.

**Open question.** "Collapse transcript" looks like it exists mainly to reach that drawer. If so it can
go in this plan (removes `collapsedFor`, the bottom toolbar and three props). Left in unless you say so.
**Touches:** `MeetingView`, `SecondaryActionsDrawer`, `meeting.css`. Do before 10.

## 4. Sidebar and transcript scroll separately

**Problem.** The whole page scrolls. In a long transcript the search box and meeting list scroll out
of reach, the list's own `overflow-y: auto` never engages, and `--header-h: 52px` is wrong whenever the
dock wraps to two lines.

**Scenarios:** none (layout only); one line in the spec.

1. `layout.css`: `.app-shell { height: 100vh }` (not `min-height`), `main { min-height: 0; overflow: hidden }`.
   `.sidebar` and `#view-section` each get `min-height: 0; overflow-y: auto`; drop both
   `min-height: calc(100vh - var(--header-h))` rules and the `--header-h` token. The dock no longer needs
   `position: sticky`; the audio bar's `position: sticky; bottom: 0` now sticks inside `#view-section`.
2. `.sidebar-list-section` gets `min-height: 0` so it is the part that scrolls and the version footer stays put.
3. At ≤ 820 px keep today's single-column page scroll (`.app-shell { height: auto }`, overflow reset).
4. `MeetingView` scrolls `#view-section` to the top when `currentId` changes (the window used to do this
   implicitly only by accident of content height).
5. Verify in a browser at 1440×900, 1024×600 and 390×800, light and dark: sidebar fixed while the
   transcript scrolls, audio bar pinned, popovers not clipped by the new `overflow` (the "Play through"
   popover opens upward inside `#view-section`; check it).

**Touches:** `layout.css`, `sidebar.css`, `meeting.css`, one effect in `MeetingView`.

## 5. Transcript grouped into speaker turns

**Problem.** Each Whisper segment is its own bordered row with the speaker repeated, so a
conversation reads like a log table.

**Scenarios:** add to `meeting-recorder.feature` ("View a meeting on the web page"): consecutive lines
of one speaker are shown as one turn with the speaker named once; a long monologue is broken into
paragraphs; clicking a sentence plays from it; filtering by speaker hides whole turns.

1. `utils.ts`, pure: `groupTurns(segments, trackOf) -> Turn[]` where a turn is consecutive segments with
   the same speaker and track. A turn is closed early after 60 s or at a pause over 2 s between
   segments, so paragraphs stay readable; unlabelled transcripts (diarization failed) group on pauses only.
2. `TranscriptList` renders `<li class="turn">`: the speaker button and the turn's start timestamp
   (a real button, as now) on top, then the segments as inline `<span class="seg" data-start>`; clicking
   a span plays from its start. The playing highlight moves from the row to the span.
3. `COLLAPSED_LINES` counts turns (4) instead of rows. Speaker filter sets `hidden` on turns.
4. CSS: drop the 3-column grid and per-row borders; a turn is a block with `--sp-4` between turns and
   the speaker colour on the left rule; body stays 16 px / 1.65 / 68ch.
5. Verify: Vitest for `groupTurns` (same speaker merges, track change splits, 60 s cap, pause split, no
   speakers). E2E steps 3–5 updated (`ol.transcript li` counts become turn counts). Copy and export are
   unchanged because that text comes from the server.

**Skipped:** editing transcript text, per-sentence timestamps on hover.
**Touches:** `TranscriptList`, `MeetingView`, `utils.ts`, `meeting.css`. Overlaps 1, 2, 15.

## 6. "Can't reach the recorder" banner

**Problem.** Failed polls are swallowed. If the service stops, the page keeps saying "Not
recording" (or keeps a recording timer running) and gives no hint. Models that failed to load at startup
are never asked for again.

**Scenarios:** add to `meeting-recorder.feature` next to "The recorder service is not running": the page
says it can't reach the recorder after three failed status checks, disables Start, and recovers by itself.

1. `App.pollStatus`: count consecutive failures in a ref; at 3 set `offline`; any success clears it and,
   if it was offline, calls `loadMeetings()` and `loadModels()`.
2. `TopDock`: when offline the status pill reads "Disconnected", the toggle is disabled, and a
   `role="alert"` strip under the dock says "Can't reach the recorder. Check that Transcribe is running;
   this page reconnects by itself." The elapsed timer stops ticking.
3. Verify: Vitest with `fetch` rejecting three times then resolving (banner appears, clears, list reloaded).

**Skipped:** a manual retry button (polling is every second), offline viewing of cached meetings.
**Touches:** `App`, `TopDock`, `layout.css`.

## 7. Mode switch beside the record button

**Problem.** Mode is the one choice that can't be fixed afterwards (recording a call as "in person"
loses the other side), and it hides in a popover labelled "Mic · Auto · large-v3". It also resets to
"mic" on every page load.

**Scenarios:** `meeting-recorder.feature` "Start and stop a recording from the web page": the mode is
chosen with a two-option switch next to Start; the last choice is remembered; it can't be changed while
recording and shows the mode being recorded.

1. `TopDock`: a radio group "In person" / "Online call" (`role="radiogroup"`, two styled
   `<input type="radio">`, arrow keys work natively) between the title and the Start button. Tooltips:
   "Microphone only" / "Microphone + what your speakers play".
2. `App`: `mode` initialised from and saved to `transcribe.mode`. While recording the switch is disabled
   and shows `status.mode` (already in `/api/status`; add `mode` to the `RecorderStatus` type).
3. `SettingsDrawer`: remove the Mode select; summary becomes `Auto · large-v3` behind a "Settings" label.
   "System audio from" is marked "(online calls)".
4. Verify: Vitest (start posts the chosen mode; restored from localStorage; disabled while recording).
   E2E step 1 updated (`#settings-summary` text).

**Touches:** `TopDock`, `SettingsDrawer`, `App`, `types.ts`, `layout.css`. Do before 9.

## 8. Recording shown in the tab title; clearer "no sound"

**Problem.** During a meeting the page is behind another window, and nothing on the tab says it is
recording. A dead microphone shows only as small red text beside a 56 px bar.

**Scenarios:** `level-meter.feature`: reword "its meter says no sound" to a warning naming the track.
New scenario in `meeting-recorder.feature`: the tab title starts with "●" while recording.

1. `App`: an effect sets `document.title` to `● Recording – Meetings` while recording, else `Meetings`.
   No timer in the title: browsers throttle hidden-tab timers to once a minute, so it would be wrong.
2. `LevelMeters`: a silent track renders a chip, "⚠ Microphone: no sound", on `--warn-bg` with
   `role="status"` so it is announced once; the 10 s / −50 dB rule is unchanged.
3. Add an inline SVG favicon in `index.html` (there is none today) and swap to a red-dot variant while recording.
4. Verify: Vitest (title while recording and after stop; chip after 10 s of silence with fake timers).

**Decision needed.** A hidden tab does not poll (spec, line 85), so if a recording is stopped from the
tray or Claude the title stays "● Recording" until the tab is shown. Either accept that, or poll every
5 s while hidden *and* last known to be recording, which changes that spec sentence. Recommended: the
slow poll, because a title that wrongly says "recording" is the worse failure.
**Touches:** `App`, `LevelMeters`, `index.html`, `layout.css`.

## 9. Title field: cleared, renames the live recording, separate for import

**Problem.** The title is never cleared after Start, so the next recording and any import silently
reuse it. During a recording the field is editable but does nothing. Import borrows the dock's title,
language and model without showing them.

**Scenarios:** `rename-meeting.feature` "Rename while recording" gains a page step (edit the title
field, press Enter). `import-audio.feature`: the import panel has its own title; empty uses the file
name; it states the language and model it will use.

1. `App`: after a successful start, the field holds the live title; after stop it is emptied.
2. `TopDock`: while recording, Enter or blur with a changed value posts
   `/api/meetings/{id}/title` (already allowed during recording). Polling does not overwrite the field
   while it has focus. Escape restores the live title. Errors show in `#rec-error`.
3. `ImportDrawer`: its own "Title" input (placeholder: the chosen file's name without extension), no
   `title` prop. The helper text becomes "Transcribed as Auto · large-v3. Change these in Settings."
   using the live values.
4. Verify: Vitest (field empty after stop; rename request on Enter while recording; import sends its own
   title, or the file name). E2E unchanged.

**Skipped:** language and model pickers inside the import panel.
**Touches:** `App`, `TopDock`, `ImportDrawer`. Shares the dock with 7.

## 10. Inline rename and delete confirmation (no native dialogs)

**Problem.** Rename meeting, rename speaker and delete use `window.prompt`, `alert` and `confirm`:
unstyled, blocking, and titled with the host name. The title and every speaker label are rename buttons
with no visible sign of it.

**Scenarios:** reword the page steps of `rename-meeting.feature`, "Rename a speaker on the web page"
and `delete-meeting.feature` (Enter saves, Escape cancels, an empty speaker name resets it, delete asks
in the page and names the meeting).

1. Title: a pencil icon beside it (visible on hover and focus, always on touch). Activating swaps the
   heading for an input holding the title; Enter or blur saves, Escape cancels; a failed save shows an
   inline `.err` and keeps the input open.
2. Speaker: the label button opens a small popover anchored to it: an input, "Save", and "Reset to
   Speaker 1" when a name is set. Same keys. One shared `InlineEdit` component serves both.
3. Delete: the button turns into "Delete "<title>"? Audio and transcript are removed for good.
   [Delete] [Cancel]" in place, focus moved to Cancel. No `<dialog>` (jsdom has no `showModal`).
4. Remove every `window.prompt/alert/confirm` call.
5. Verify: Vitest for each flow including Escape and the error path. E2E steps 5, 6 and 8 rewritten
   (they use `page.once("dialog")`).

**Skipped:** undo after delete, renaming from the meeting list.
**Touches:** `MeetingView`, `TranscriptList`, the actions component. Easier after 3; with 5 the speaker label appears once per turn.

## 11. Quieter, date-grouped meeting list

**Problem.** Every row carries a "TRANSCRIBED" badge and a file size, and a full locale date-time in
monospace. The states that matter (recording, transcribing, failed) don't stand out.

**Scenarios:** `meeting-recorder.feature` "List meetings newest first with status" page step: finished
meetings show no badge; meetings are grouped under Today, Yesterday, Earlier this week, then by month.

1. `utils.ts`, pure: `groupByDay(meetings, now) -> {label, meetings}[]` using local dates.
2. `MeetingsList`: a small heading per group. Row meta is time only under Today/Yesterday, otherwise
   short date + time, then duration. Size is dropped (still in the meeting's own details).
3. `StatusBadge` in the list only when status is not `transcribed`. Section heading "Past meetings" → "Meetings".
4. Verify: Vitest for `groupByDay` with a fixed `now` (midnight boundary, previous month); App test
   that a transcribed row has no badge and a failed one does.

**Skipped:** paging or virtualising the list, sorting options.
**Touches:** `MeetingsList`, `utils.ts`, `sidebar.css`.

## 12. Stable speaker colours

**Problem.** Colours are handed out lazily from a ref that is never reset, so a speaker's colour
depends on which meetings were opened before, and the ref is mutated during render.

**Scenarios:** add to "View a meeting on the web page": a speaker has the same colour every time the
meeting is opened.

1. `utils.ts`, pure: `speakerPalette(segments) -> Record<label, index>` in order of first appearance, mod 6.
2. `MeetingView`: `useMemo` over `segments` replaces `paletteRef`; `colourOf` reads from it. Keyed by
   the raw label, so renaming keeps the colour.
3. Verify: Vitest for `speakerPalette`; App test opening meeting A, then B, then A again.

**Touches:** `MeetingView`, `utils.ts`.

## 13. First-run and loading states

**Problem.** With no meetings the main area says "Select a meeting to see its transcript."
A meeting that is loading renders nothing at all.

**Scenarios:** add to "View a meeting on the web page": with no meetings the page says how to make one.

1. `MeetingView` takes `hasMeetings`. None: "No meetings yet. Press Start recording, or use Import
   audio to transcribe a file you already have." Otherwise the current sentence.
2. `!detail && !error`: a muted "Loading…" that fades in after 300 ms (CSS `animation-delay`), so a
   normal local load shows no flash.
3. Verify: Vitest for both empty states. E2E step 1 and the last assertion of step 8 updated (they
   expect the old sentence with zero meetings).

**Touches:** `MeetingView`, `App`, `meeting.css`.

## 14. Fonts: use what is installed

**Problem.** `tokens.css` names Inter and JetBrains Mono first, but neither is loaded, so the page
already renders in Segoe UI and Cascadia Mono, or in Inter only on machines that happen to have it.

1. Remove `"Inter"` and `"JetBrains Mono"` from `--font-sans` / `--font-mono`. Result on Windows:
   Segoe UI, Leelawadee UI for Thai, Cascadia Mono.
2. Verify: build, look at a Thai + English transcript on Windows.

**Alternative, not recommended:** bundle both as woff2. It needs a new static route in `web.py` (only
`/static/css/` and `/static/js/` are served), grows the installer, and Inter has no Thai glyphs, so Thai
would still fall back and sit beside a different Latin face.
**Touches:** `tokens.css`.

## 15. Larger click targets

**Problem.** Timestamps are bare 12 px text and filter pills are 24 px high: hard to hit, worse on touch.

1. `.ts`: padding to a 28 px tall hit area with a negative margin so the text doesn't move; `.filter-pill`
   and `button.icon` to 28 px; all three to 40 px under `@media (pointer: coarse)`.
2. Verify in a browser, including the 640 px transcript layout.

**Not doing:** making the whole row click-to-play. It would fight text selection, and people copy
quotes out of transcripts. Plan 5 gives click-a-sentence instead; if 5 is done, only the pill and icon
sizes from this plan are still needed.
**Touches:** `meeting.css`.

## 16. Import: drag and drop, upload progress

**Problem.** Import is a file picker inside a popover, and a large file shows only "Importing…" for
as long as the upload and the server-side conversion take.

**Scenarios:** `import-audio.feature`: dropping an audio or video file on the page offers to import it;
a file that is neither is refused with a message; progress is shown while uploading, then "Converting…".

1. `App`: window `dragenter/dragover/drop` listeners. While a file is dragged over the page, an overlay
   says "Drop to import". On drop, the first `audio/*` or `video/*` file is handed to `ImportDrawer`,
   which opens showing its name; other types set the import error. The file is held in state, not in the
   `<input>` (its `files` can't be set reliably).
2. `api.ts`: `uploadAudioFile` moves from `fetch` to `XMLHttpRequest` for `upload.onprogress`; same
   URL, headers and error messages, plus an `onProgress(fraction)` argument.
3. `ImportDrawer`: a `<progress>` and "Uploading 43%", then "Converting…" once the bytes are sent (the
   request returns only after the server has converted the file). The popover can't be dismissed mid-import.
4. Verify: Vitest with a stubbed `XMLHttpRequest` (progress, success, error text) and a synthetic drop
   event; E2E: `setInputFiles` import still works.

**Skipped:** several files at once, cancelling an upload.
**Touches:** `App`, `ImportDrawer`, `api.ts`, `layout.css`. Simpler after 9 (import has its own title field).
