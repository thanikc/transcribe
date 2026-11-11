# Plan: transcription progress

Scenarios: `docs/features/transcription-progress.feature`

Progress lives in memory in the Recorder (not in meeting.json): it only means something while
a job runs, and a restart marks running jobs failed anyway.

1. **Domain**: `TranscriptionStep` + `transcription_steps(mode)`, pure.
   Verify: domain tests for both modes.
2. **Ports + Recorder**: `SpeechToText.transcribe` and `SpeakerDiarizer.diarize` take an
   `on_progress(fraction)` callback. Recorder keeps `{meeting_id: progress}`, sets each step
   before running it, and clears it when the job ends. `recorder.progress(id)` returns
   `{step, step_number, steps, fraction | None, elapsed}`.
   Verify: recorder tests (mid-step via a fake that checks progress during its call, cleared on success/failure).
3. **Adapters**: Whisper reports `segment.end / info.duration` as segments arrive;
   sherpa-onnx passes `callback=(done, total)`; fakes updated (dev fake reports steps slowly).
   Verify: adapter tests with stubbed libraries.
4. **API + client**: `progress` on meeting JSON (detail and list, null when idle);
   `transcript_text` adds the step to the not-ready message (CLI `show` and MCP `get_transcript`).
   Verify: web + client tests.
5. **Web page**: step label, "step n of N", `<progress>` (indeterminate when fraction is null),
   ticking step time; percentage in the list badge; "Starting…/Stopping…" on the button.
   Verify: `serve --fake` checked manually in a browser.
6. Spec: update the web UI and Known limits sections.

Skipped: an ETA, progress for the first-time model download itself (huggingface gives no
easy hook; the step shows an indeterminate bar and a ticking timer meanwhile), and making `record` wait for the transcript.
