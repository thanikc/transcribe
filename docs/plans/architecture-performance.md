# Plan: architecture and performance

Scenarios: `docs/features/meeting-recorder.feature` (search, "Meetings are transcribed one at a time")

Goal: the service stays responsive with hundreds of meetings, and the work after a recording
uses the machine better. No change to the HTTP API, the stored files or the ports.

## Measured before (Linux, 4 cores; 500 meetings of 700 segments each)

| What | Before | Cause |
|---|---|---|
| `GET /api/meetings` (polled every 2 s) | 143 ms | `store.get` lists the data dir for every meeting (60 ms), 4 file checks per track (25 ms) |
| `GET /api/search` | 2.0 s | every transcript is parsed and built into segments; each `meeting.json` is read three times |
| Speaker detection, 7.6 min of speech | 111 s | sherpa-onnx runs on 1 thread by default |

Both requests run on the event loop, so the page's status polls wait behind them. The
handlers for transcribe, rename and delete also take the recorder lock on the event loop; `start`
holds that lock for up to 10 s while audio devices open, which freezes every request meanwhile.

One more finding from reading the code: each transcription runs on its own thread. Two at once
share the CPU, and with different speech models both are in memory together.

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
   Verify: a web test where a slow `start` is in flight and `/api/status`, the list, a meeting,
   a search and a transcribe request still answer.
4. **Recorder: one transcription at a time.** The default `run_in_background` becomes a
   single worker thread with a queue, so jobs run in the order they were asked for. A waiting
   meeting is `transcribing` with no progress yet; the page says it is waiting to start.
   Verify: recorder tests with the real worker (jobs never overlap, both meetings finish).
5. **Speaker detection on up to 4 threads.** 4 is what Whisper already uses, so this step asks
   no more of the machine than the step before it.
   Verify: adapter test for the config; the real adapter timed against a 1-thread run, turns compared.
6. **Page: no polling while the tab is hidden**, one refresh when it shows again. During an
   hour-long call in another tab that is about 5,400 requests not made.
   Verify: `serve --fake` in a browser (Playwright): request counts hidden vs visible, the
   record → transcribe → transcript flow still works.
7. **Docs.** Spec (interfaces, ports, known limits), feature scenario, `AGENTS.md`.

## Measured after (same machine and data)

| What | Before | After |
|---|---|---|
| `GET /api/meetings` | 143 ms | 46 ms |
| `GET /api/search`, query in no meeting | 1.7 s | 0.41 s |
| `GET /api/search`, query in all 500 meetings | 2.0 s | 1.3 s |
| Speaker detection, 7.6 min of speech | 112 s | 50 s, the same 88 turns |
| Requests from a hidden tab, 4 s | 8 | 0 |

The requests also no longer hold up the event loop. None of this was run on Windows, where
file access costs more than on Linux (so the listing gain should be larger there) and where
the core count decides the speaker detection gain.

## Looked at and left alone

- **Releasing the Whisper model after each meeting.** Tried and taken out again. The tray
  app holds the model for as long as it runs, so the idea was to release it once a meeting's
  tracks are transcribed. Measured here with the `small` model over six meetings in a row:
  kept loaded, the process stays at 796 MB. Released each time, it idles at 400–750 MB but
  transcribes at 1,050–1,220 MB, because every reload leaves the allocator more fragmented.
  That is a higher peak for the step that already runs out of memory with `large-v3`. The
  Windows allocator may behave differently, so this needs the same measurement on Windows
  before it is worth another look. The reload would also cost some seconds per meeting.
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
- **Rebuilding the meeting list only when it changed.** While anything is polled the list
  always differs: the audio size grows during a recording and the step time during a
  transcription. The check would never skip anything.
- **Running speaker detection alongside Whisper.** They would share the same cores, and the
  step-by-step progress would need a new design.
