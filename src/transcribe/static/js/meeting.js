// The meeting view on the right: loading, refreshing while in progress, and rendering the detail.

import { $, api, el, fileSize, mmss, select, fillSelect, LANG_LABEL, MODE_LABEL, TRACK_LABEL } from "./util.js";
import { state } from "./state.js";
import { badge, loadMeetings, renderList } from "./list.js";
import { defaultModel, modelOptions } from "./models.js";
import { renderTracks } from "./audio.js";
import { renderProgress } from "./progress.js";

export const inProgress = (d) => !!d && (d.meeting.status === "transcribing" || d.meeting.status === "recording");

// Active speaker filter and collapse state for the open meeting.
let activeSpeaker = null;
let collapsedFor = null;

/* ---------- routing and loading ---------- */
export function routeFromHash() {
  const m = location.hash.match(/^#\/meeting\/(.+)$/);
  if (m) { try { showMeeting(decodeURIComponent(m[1])); } catch (e) { /* bad escape */ } }
  else { clearTimeout(state.viewTimer); state.viewToken++; state.currentId = null; state.detail = null; activeSpeaker = null;
    $("view").replaceChildren(el("p", { class: "empty-state", text: "Select a meeting to see its transcript." })); renderList(); }
}

export async function showMeeting(id) {
  clearTimeout(state.viewTimer);
  const token = ++state.viewToken;
  if (state.currentId !== id) { state.detail = null; activeSpeaker = null; }
  state.currentId = id; renderList();
  try {
    const d = await api("GET", "/api/meetings/" + encodeURIComponent(id));
    if (token !== state.viewToken) return;
    applyDetail(d, token);
  } catch (e) {
    if (token !== state.viewToken) return;
    $("view").replaceChildren(el("div", { class: "err", role: "alert", text: e.message }));
  }
}

function applyDetail(d, token) {
  state.detail = d; state.detailAt = performance.now();
  renderMeeting();
  const s = d.meeting.status;
  if (inProgress(d)) state.viewTimer = setTimeout(() => refreshDetail(d.meeting.id, token), 2000);
  const listed = state.meetings.find((m) => m.id === d.meeting.id);
  if (listed && listed.status === s) { listed.progress = d.meeting.progress; renderList(); } else loadMeetings();
}

async function refreshDetail(id, token) {
  if (token !== state.viewToken || document.hidden) return;  // a hidden tab picks up again when it is shown
  try {
    const d = await api("GET", "/api/meetings/" + encodeURIComponent(id));
    if (token === state.viewToken) applyDetail(d, token);
  } catch (e) {
    if (token === state.viewToken) state.viewTimer = setTimeout(() => refreshDetail(id, token), 2000);
  }
}

/* ---------- rendering ---------- */
const palette = {};
function colourOf(label) {
  if (!(label in palette)) palette[label] = Object.keys(palette).length % 6;
  return `var(--sp${palette[label]})`;
}

const COPY_ICON = '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h10"/></svg>';
const DOWNLOAD_ICON = '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>';
const CHEVRON_UP = '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m6 15 6-6 6 6"/></svg>';
const CHEVRON_DOWN = '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>';
const COLLAPSED_LINES = 8;

// Compact utility toolbar: speaker filters on the left; copy, export, and collapse/expand on the right.
function utilBar(position, m, segments, text, collapsible, collapsed) {
  const bar = el("div", { class: "util-bar " + position });

  if (position === "top" && segments && segments.length) {
    const seen = [];
    for (const s of segments) if (s.speaker && !seen.includes(s.speaker)) seen.push(s.speaker);
    if (seen.length > 1) {
      const filters = el("div", { class: "speaker-filters", role: "group", "aria-label": "Filter by speaker" });
      filters.append(el("button", {
        type: "button", class: "filter-pill", "aria-pressed": String(!activeSpeaker), text: "All speakers",
        onclick: () => { activeSpeaker = null; renderMeeting(); },
      }));
      for (const raw of seen) {
        const shown = (m.speaker_names || {})[raw] || raw;
        const pill = el("button", {
          type: "button", class: "filter-pill", "aria-pressed": String(activeSpeaker === raw), text: shown,
          onclick: () => { activeSpeaker = activeSpeaker === raw ? null : raw; renderMeeting(); },
        });
        pill.style.borderLeft = `3px solid ${colourOf(raw)}`;
        filters.append(pill);
      }
      bar.append(filters);
    }
  }

  const actions = el("div", { class: "util-actions" });
  const note = el("span", { class: "copy-note muted", role: "status" });

  const copy = el("button", { type: "button", class: "icon", title: "Copy transcript", "aria-label": "Copy transcript" });
  copy.innerHTML = COPY_ICON + '<span>Copy</span>';
  let timer;
  copy.addEventListener("click", async () => {
    try { await navigator.clipboard.writeText(text); note.textContent = "Copied to clipboard"; }
    catch (e) { note.textContent = "Could not copy"; }
    clearTimeout(timer); timer = setTimeout(() => { note.textContent = ""; }, 2000);
  });
  actions.append(note, copy);

  if (position === "top") {
    const exp = el("button", { type: "button", class: "icon", title: "Export transcript (.txt)", "aria-label": "Export transcript" });
    exp.innerHTML = DOWNLOAD_ICON + '<span>Export .txt</span>';
    exp.addEventListener("click", () => {
      const blob = new Blob([text || ""], { type: "text/plain;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const a = el("a", { href: url, download: `${m.id}.txt` });
      document.body.append(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
    });
    actions.append(exp);
  }

  if (collapsible) {
    const label = collapsed ? "Expand transcript" : "Collapse transcript";
    const tog = el("button", { type: "button", class: "icon", title: label, "aria-label": label, "aria-expanded": String(!collapsed) });
    tog.innerHTML = (collapsed ? CHEVRON_DOWN : CHEVRON_UP) + `<span>${collapsed ? "Expand" : "Collapse"}</span>`;
    tog.addEventListener("click", () => { collapsedFor = collapsed ? null : state.currentId; renderMeeting(); });
    actions.append(tog);
  }

  bar.append(actions);
  return bar;
}

export function renderMeeting() {
  const { meeting: m, segments } = state.detail;
  // Build into a fragment placed before the sticky audio bar (#tracks), so refreshing never detaches a player mid-playback.
  const head = document.createDocumentFragment(), tail = document.createDocumentFragment();
  const id = m.id;
  const titleBtn = el("button", { type: "button", class: "title-edit", title: "Rename this meeting", text: m.title || m.id, onclick: () => renameMeeting(m.title) });
  head.append(el("div", { class: "meeting-header" },
    el("h3", { class: "meeting-title-row" }, titleBtn, badge(m.status))));

  let lang = LANG_LABEL[m.language] || m.language;
  if (m.language === "auto") {
    const det = Object.entries(m.detected_languages || {});
    lang = "Auto" + (det.length ? " — detected: " + det.map(([t, l]) => `${TRACK_LABEL[t] || t} ${LANG_LABEL[l] || l}`).join(", ") : "");
  }
  const dl = el("dl", { class: "meta" });
  for (const [k, v] of [["Started", new Date(m.started_at).toLocaleString()], ["Duration", m.duration != null ? mmss(m.duration) : "—"],
    ["Size", fileSize(m.audio_bytes)],
    ["Mode", MODE_LABEL[m.mode] || m.mode], ["Language", lang], ...(m.model ? [["Speech model", m.model]] : [])]) {
    dl.append(el("div", { class: "meta-pair" }, el("dt", { text: k }), el("dd", { text: v })));
  }
  head.append(dl);
  for (const w of m.warnings || []) head.append(el("p", { class: "warn", text: "Warning: " + w }));
  if (m.status === "failed") head.append(el("div", { class: "err", role: "alert", text: "Transcription failed: " + (m.error || "unknown error") }));

  if (state.detail.notes) {
    head.append(el("section", { class: "notes", "aria-label": "Notes" }, el("h4", { text: "Notes" }), el("div", { text: state.detail.notes })));
  }

  if (m.status === "recording") {
    head.append(el("p", { class: "empty-state", text: "Recording in progress. The transcript appears after you stop." }));
  } else if (m.status === "transcribing") {
    head.append(renderProgress(m.progress));
  } else if (m.status === "transcribed" && segments) {
    if (!segments.length) head.append(el("p", { class: "empty-state", text: "No speech was found." }));
    const collapsible = segments.length > COLLAPSED_LINES;
    const collapsed = collapsible && collapsedFor === id;
    const text = state.detail.transcript;
    if (segments.length) head.append(utilBar("top", m, segments, text, collapsible, collapsed));
    const ol = el("ol", { class: "transcript", "aria-label": "Transcript" });
    for (const s of collapsed ? segments.slice(0, COLLAPSED_LINES) : segments) {
      const track = trackOf(m, s);
      const li = el("li", {
        class: s.speaker ? "" : "no-speaker",
        "data-track": track, "data-start": s.start, "data-end": s.end,
      }, el("button", { type: "button", class: "ts", title: "Play from here", text: `[${mmss(s.start)}]`, onclick: () => playFrom(track, s.start) }));
      if (activeSpeaker && s.speaker !== activeSpeaker) li.hidden = true;
      if (s.speaker) {
        const shown = (m.speaker_names || {})[s.speaker] || s.speaker;
        const b = el("button", { type: "button", class: "spk", title: "Rename this speaker", text: shown, onclick: () => renameSpeaker(s.speaker, shown) });
        b.style.color = colourOf(s.speaker);
        li.append(b);
      }
      li.append(el("span", { class: "seg-text", text: s.text }));
      ol.append(li);
    }
    head.append(ol);
    if (collapsible && collapsed) head.append(utilBar("bottom", m, segments, text, collapsible, collapsed));
  }

  if (m.status !== "recording") {
    const drawer = el("details", { class: "secondary-drawer" });
    if (m.status === "failed") drawer.open = true;
    drawer.append(el("summary", { text: "Re-transcribe & meeting actions" }));

    const again = el("div", { class: "again" }, el("h4", { text: "Transcribe again" }));
    const row = el("div", { class: "row" });
    const lsel = select("again-language", [["auto", "Auto"], ["th", "ไทย"], ["en", "English"]], m.language);
    const msel = el("select", { id: "again-model" });
    fillSelect(msel, modelOptions(), m.model || defaultModel());
    const btn = el("button", { type: "button", text: "Transcribe again" });
    btn.disabled = m.status === "transcribing";
    const errBox = el("div", { class: "err", role: "alert" });
    btn.addEventListener("click", async () => {
      btn.disabled = true; errBox.textContent = "";
      try {
        await api("POST", `/api/meetings/${encodeURIComponent(id)}/transcribe`, { language: lsel.value, model: msel.value || null });
        await showMeeting(id); loadMeetings();
      } catch (e) { errBox.textContent = e.message; btn.disabled = false; }
    });
    row.append(el("div", null, el("label", { for: "again-language", text: "Language" }), lsel),
      el("div", null, el("label", { for: "again-model", text: "Speech model" }), msel),
      el("div", { style: "flex:0 0 auto" }, btn));
    again.append(row, errBox);
    drawer.append(again);

    if (m.status === "transcribed" || m.status === "failed") {
      const delBtn = el("button", { type: "button", class: "danger", text: "Delete meeting" });
      const delErr = el("div", { class: "err", role: "alert" });
      delBtn.addEventListener("click", async () => {
        if (!confirm(`Delete "${m.title || id}"? Its audio and transcript are removed for good.`)) return;
        delBtn.disabled = true; delErr.textContent = "";
        try {
          await api("DELETE", `/api/meetings/${encodeURIComponent(id)}`, {});
          await loadMeetings();
          location.hash = "";
        } catch (e) { delErr.textContent = e.message; delBtn.disabled = false; }
      });
      drawer.append(el("div", { class: "again" }, delBtn, delErr));
    }

    head.append(drawer);
  }

  let tracks = null;
  if (m.status !== "recording") {
    const key = id + "|" + (m.tracks || []).join(",");
    tracks = $("tracks");
    if (!tracks || tracks.dataset.key !== key) tracks = renderTracks(id, m.tracks || [], key);
  }

  const live = $("view");
  if (tracks && tracks.parentNode === live) {
    for (const c of [...live.childNodes]) if (c !== tracks) c.remove();
    tracks.before(head); live.append(tail);
  } else {
    live.replaceChildren(head);
    if (tracks) live.append(tracks);
    live.append(tail);
  }
}

// Which recording a line was heard on: in an online call "You" is the microphone and everyone else the system audio.
function trackOf(m, s) {
  if (m.mode === "mic+system") return s.speaker === "You" ? "mic" : "system";
  return (m.tracks || ["mic"])[0];
}

function playFrom(track, start) {
  const player = $(`audio-${track}`);
  if (!player) return;
  for (const other of document.querySelectorAll("#tracks audio")) if (other !== player) other.pause();
  // The players load nothing until asked (preload="none"); seek once the file's length is known.
  if (player.readyState === 0) player.addEventListener("loadedmetadata", () => { player.currentTime = start; }, { once: true });
  else player.currentTime = start;
  player.play().catch(() => { /* the browser refused to play; the player shows why */ });
}

// Mark the line whose time span holds the play position of the player that moved.
function highlightPlaying(e) {
  const player = e.target;
  if (!(player instanceof HTMLMediaElement) || !player.closest("#tracks")) return;
  const track = player.id.replace(/^audio-/, ""), t = player.currentTime;
  for (const li of document.querySelectorAll("ol.transcript li")) {
    const on = li.dataset.track === track && t >= +li.dataset.start && t < +li.dataset.end;
    li.classList.toggle("playing", on);
  }
}

async function renameMeeting(current) {
  const title = prompt("Meeting title (leave empty for none):", current);
  if (title === null) return;
  const id = state.currentId;
  try {
    const d = await api("POST", `/api/meetings/${encodeURIComponent(id)}/title`, { title });
    if (id === state.currentId) { state.detail = d; renderMeeting(); }
    loadMeetings();
  } catch (e) { alert(e.message); }
}

async function renameSpeaker(raw, current) {
  const name = prompt(`Name for ${raw} (leave empty to reset):`, current === raw ? "" : current);
  if (name === null) return;
  const id = state.currentId;
  try {
    const d = await api("POST", `/api/meetings/${encodeURIComponent(id)}/speakers`, { speaker: raw, name });
    if (id === state.currentId) { state.detail = d; renderMeeting(); }
  } catch (e) { alert(e.message); }
}

export function initMeeting() {
  window.addEventListener("hashchange", routeFromHash);
  document.addEventListener("timeupdate", highlightPlaying, true);  // media events don't bubble; capture them
}
