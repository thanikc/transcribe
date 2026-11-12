# Plan: choose the audio sources

Spec: `docs/specs/audio-sources.md`. Scenarios: `docs/features/audio-sources.feature`

1. **Domain + store**: `AudioDevice(id, name, default)` and `SOURCE_TRACKS = ("mic", "system")` in `domain.py`.
   `MeetingStore.load_sources()` / `save_sources()` on `<data dir>/sources.json` (missing or corrupt = all default).
   Verify: store tests (round trip, missing file, corrupt file, not listed as a meeting).
2. **Recorder + port**: `AudioCapture.devices()`, `start(track_paths, sources)`. `Recorder.sources()`,
   `Recorder.choose_source(track, device_id | None)` (unknown track / not connected -> `InvalidChoice`).
   `Recorder.start` passes the saved ids, and refuses with `CaptureError` naming the device if a chosen one
   is not among `capture.devices()`; no meeting is created. `tests/fakes.py` and `devfakes.py` get devices.
   Verify: recorder tests per scenario 1, 3, 4, 6, 7, 8, 9.
3. **Capture adapter**: `SoundcardCapture.devices()` from `soundcard.all_microphones()` / `all_speakers()`;
   `_open_device` opens the chosen id (mic) or the chosen speaker's loopback, else the defaults as now.
   Verify: adapter test with a fake `soundcard` module; real devices only checkable on Windows.
4. **API**: `GET /api/sources`, `POST /api/sources`. Verify: web tests (list, choose, clear, bad track,
   unknown device -> 400, start refused -> 503).
5. **Web page**: "Microphone" and "System audio from" selects in the Settings popover, filled from
   `/api/sources`, saved on change; error shown under them. Verify: `serve --fake` + API check.
6. Spec `meeting-recorder.md`: mention the endpoints and `sources.json`.

Skipped: choosing devices from the CLI/MCP/tray menu (they use the saved choice), a device per recording
(stored on the meeting), refreshing the list live when a device is plugged in (it refreshes when Settings opens).
