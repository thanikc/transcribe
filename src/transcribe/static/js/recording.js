// The recording panel: start/stop, the status line and the status poll.

import { $, api, el, mmss, TRACK_LABEL } from "./util.js";
import { state } from "./state.js";
import { loadMeetings } from "./list.js";
import { openMeeting } from "./nav.js";
import { renderUpdateButton } from "./version.js";

export function renderStatus() {
  const s = $("status"), btn = $("toggle");
  if (state.busy) {
    // Opening or closing audio devices can take a few seconds.
    s.className = ""; s.textContent = state.recording ? "Stopping…" : "Starting…";
  } else if (state.recording) {
    const elapsed = state.elapsed + (performance.now() - state.elapsedAt) / 1000;
    s.className = "rec";
    s.textContent = `● Recording ${mmss(elapsed)}` + (state.recTitle ? ` — ${state.recTitle}` : "");
  } else {
    s.className = ""; s.textContent = "Not recording";
  }
  btn.textContent = state.recording ? "Stop recording" : "Start recording";
  btn.className = state.recording ? "stop" : "primary";
  btn.disabled = state.busy;
  renderUpdateButton();
}

// Per track, when it last had sound, so a silent device (wrong default, muted headset) shows as such.
const QUIET = 10 ** (-50 / 20), SILENT_AFTER_MS = 10000;
let heard = {};

// The level as a share of a -60…0 dB scale: speech then fills about half the bar instead of a sliver.
const fill = (level) => Math.min(1, Math.max(0, (20 * Math.log10(level || 1e-6) + 60) / 60));

function renderMeters(levels) {
  const box = $("meters");
  if (!levels) { box.hidden = true; box.replaceChildren(); heard = {}; return; }
  const now = performance.now();
  const rows = [];
  for (const [track, level] of Object.entries(levels)) {
    if (!(track in heard) || level > QUIET) heard[track] = now;
    const silent = now - heard[track] > SILENT_AFTER_MS;
    const bar = el("div", { class: "bar", "aria-hidden": "true" }, el("span", { style: `width:${Math.round(fill(level) * 100)}%` }));
    rows.push(el("span", { text: TRACK_LABEL[track] || track }), bar,
      el("span", { class: silent ? "quiet" : "muted", text: silent ? "no sound" : "" }));
  }
  box.replaceChildren(...rows);
  box.hidden = false;
}

function showRecError(msg) { $("rec-error").textContent = msg || ""; }

export async function pollStatus() {
  try {
    const st = await api("GET", "/api/status");
    const wasRec = state.recording;
    state.recording = !!st.recording;
    if (st.recording) {
      state.recId = st.meeting_id; state.recTitle = st.title || st.meeting_id;
      state.elapsed = st.elapsed || 0; state.elapsedAt = performance.now();
    }
    if (wasRec !== state.recording) loadMeetings();
    renderStatus();
    renderMeters(st.recording ? st.levels : null);
  } catch (e) { /* transient; try again next tick */ }
}

async function toggleRecording() {
  if (state.busy) return;
  state.busy = true; showRecError(""); renderStatus();
  try {
    if (state.recording) {
      const r = await api("POST", "/api/recordings/stop", {});
      state.recording = false;
      await loadMeetings();
      openMeeting(r.meeting.id);
    } else {
      const r = await api("POST", "/api/recordings/start", {
        title: $("title").value, mode: $("mode").value, language: $("language").value,
        model: $("model").value || null,
      });
      state.recording = true; state.recId = r.meeting.id; state.recTitle = r.meeting.title || r.meeting.id;
      state.elapsed = 0; state.elapsedAt = performance.now();
      loadMeetings();
    }
  } catch (e) { showRecError(e.message); }
  state.busy = false; renderStatus(); pollStatus();
}

export function initRecording() {
  $("toggle").addEventListener("click", toggleRecording);
  // A hidden tab asks the service nothing: during an hour-long call that is thousands of requests,
  // each list one reading every meeting from disk. Showing the tab again refreshes at once.
  setInterval(() => { if (!document.hidden) pollStatus(); }, 1000);
  setInterval(() => { if (state.recording && !document.hidden) renderStatus(); }, 250);
}
