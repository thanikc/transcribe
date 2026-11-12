# Plan: architecture and performance

Scenarios: `docs/features/meeting-recorder.feature` (search, transcription queue, model release)

Goal: the service stays responsive with hundreds of meetings, transcription uses the machine
better, and the tray app does not sit on gigabytes of memory while idle. No change to the HTTP
API, the stored files or the ports' meaning, except one new port method (`release`).

## Measured before (Linux, 4 cores; 500 meetings of 700 segments each)

| What | Before | Cause |
|---|---|---|
| `GET /api/meetings` (polled every 2 s) | 143 ms | `store.get` lists the data dir for every meeting (60 ms), 4 file checks per track (25 ms) |
| `GET /api/search` | 2.0 s | every transcript is parsed and built into segments; each `meeting.json` is read three times |
| Speaker detection, 7.6 min of speech | 111 s | sherpa-onnx runs on 1 thread by default |

Both requests run on the event loop, so the page's status polls wait behind them. The
handlers for transcribe, rename and delete also take the recorder lock on the event loop; `start`
holds that lock for up to 10 s while audio devices open, which freezes every request meanwhile.

Two more findings from reading the code:
- Each transcription runs on its own thread. Two at once share the CPU, and with different
  speech models both are in memory together.
- The Whisper model stays loaded after a transcription for as long as the service runs
  (the tray app starts at sign-in), and during speaker detection, which needs memory itself.

## Steps

1. **Store: one directory listing per request.** `list()` reads the folders it just listed
   instead of validating each id against a fresh listing. `audio_bytes` stats each track file
   once. New `transcripts(mentioning)` yields the transcribed meetings with their segments,
   skipping any transcript whose raw text cannot contain the query, so search parses only
   the files that can match. `get(id)` keeps the exact-name check that rules out path traversal.
   Verify: store tests (prefilter never drops a real hit: quotes, backslashes, Thai, case);
   benchmark again.
2. **Domain + API: search hits carry the title.** `SearchHit.title` comes from the meeting
   the search already holds, so the search endpoint stops listing every meeting a second time.
   `timestamp()` is shared by the domain and the API instead of being written twice.
   Verify: domain and web tests.
3. **Web: nothing slow on the event loop.** Every handler that reads the disk or takes the
   recorder lock runs in the thread pool. `/api/status` stays on the loop (no lock, no disk).
   Verify: a web test where a slow `start` is in flight and `/api/status`, the list and a
   transcribe request still answer.
4. **Recorder: one transcription at a time.** The default `run_in_background` becomes a
   single worker thread with a queue, so jobs run in the order they were asked for. A waiting
   meeting is `transcribing` with no progress yet; the page says it is waiting for its turn.
   Verify: recorder test with the real worker (two jobs never overlap, both finish).
5. **Ports: release the speech model when its work is done.** New `SpeechToText.release()`.
   The recorder calls it after the last transcribe step (before speaker detection) and when
   a job ends, failed or not. Cost: the model loads again for the next meeting (seconds,
   against minutes of transcription).
   Verify: recorder tests (released before diarizing, released after a failure); adapter test.
6. **Speaker detection on up to 4 threads.** Measured here: 111 s → 69 s (2 threads) → 46 s
   (4 threads), same 86 turns and speakers. 4 is what Whisper already uses, so this step asks
   no more of the machine than the step before it.
   Verify: adapter test for the config; timing re-run.
7. **Page: less polling work.** No polling while the tab is hidden (one refresh when it shows
   again), and the list is rebuilt only when its data changed.
   Verify: `serve --fake` in a browser (Playwright): request counts hidden vs visible, the
   record → transcribe → transcript flow still works.
8. **Docs.** Spec (interfaces, speech model, known limits), feature scenarios, `AGENTS.md`.

## Looked at and left alone

- **Whisper thread count.** faster-whisper uses 4 threads by default. On this 4-core machine
  `tiny` took 17 s with 2 threads and 35 s with 4, so more is not simply faster. Needs
  measuring with `large-v3` on the Windows machine before changing anything.
- **Batched Whisper inference** (`BatchedInferencePipeline`). Roughly 2× on CPU by the
  library's own numbers, but it needs more memory (the meeting already falls back to turbo
  when memory is short) and changes how segments are cut, which speaker assignment depends on.
  Worth a separate change, measured on Windows with Thai audio.
- **Caching `meeting.json` in memory.** After step 1 reading 500 of them takes 13 ms against
  4 ms for checking them unchanged. Not worth the invalidation rules.
- **Caching parsed transcripts for search.** 250 KB of memory per hour-long transcript, 125 MB
  for 500. The prefilter in step 1 gets most of the gain with none of it.
- **Moving the ports out of `recorder.py`.** Adapters import two error types from it; the
  dependency points the right way (the recorder imports no adapter). Churn without effect.
- **Opening devices outside the recorder lock.** After step 3 the wait no longer blocks
  other requests' threads from being served; it only delays a transcribe or delete asked for
  in those same seconds.
- **Running speaker detection alongside Whisper.** They would share the same cores, and the
  step-by-step progress would need a new design.
