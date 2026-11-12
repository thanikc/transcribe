# Audio sources

Context: recording (the `Recorder` service and its `AudioCapture` port).

## Language

- **Audio source**: the device a track is recorded from. The `mic` track's source is a microphone;
  the `system` track's source is a speaker (output device), recorded through its loopback.
- **Windows default**: no source chosen; the track records whatever Windows' default device is at the
  moment the recording starts (today's behaviour).
- **Chosen source**: a device id and its name, saved by the service, used by every recording until changed.

## Invariants

- One chosen source per recorded track (`mic`, `system`), or none (= Windows default).
- The choice belongs to the service, not to a browser: recordings started from the page, the tray, the CLI
  and Claude Desktop all use it.
- A recording never silently records a different device: if a chosen source is not connected when a
  recording starts, the start is refused (503, like any device that can't open) and names the device.
- Only a device that is connected can be chosen.
- A recording in progress keeps the devices it started with; a new choice applies from the next recording.

## Ports and storage

- `AudioCapture.devices() -> {"mic": [AudioDevice], "system": [AudioDevice]}`; `AudioDevice(id, name, default)`.
- `AudioCapture.start(track_paths, sources)`: `sources` maps a track to a device id, or None for the default.
- Saved in `<data dir>/sources.json`: `{"mic": {"id": ..., "name": ...} | null, "system": ... }`.

## API

- `GET /api/sources` -> `{"sources": {"mic": {"chosen": {id, name} | null, "devices": [{id, name, default}]}, "system": ...}}`
- `POST /api/sources` `{"track": "mic" | "system", "device": id | null}` -> the same shape. Unknown track or
  a device that is not connected -> 400.
