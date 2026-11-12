// The meeting view on the right: loading, refreshing while in progress, and rendering the detail.

import { $, api, el, fileSize, mmss, select, fillSelect, LANG_LABEL, MODE_LABEL, TRACK_LABEL } from "./util.js";
import { state } from "./state.js";
import { badge, loadMeetings, renderList } from "./list.js";
import { defaultModel, modelOptions } from "./models.js";
import { renderTracks } from "./audio.js";
import { renderProgress } from "./progress.js";

export const inProgress = (d) => !!d && (d.meeting.status === "transcribing" || d.meeting.status === "recording");

/* ---------- routing and loading ---------- */
export function routeFromHash() {
  const m = location.hash.match(/^#\/meeting\/(.+)$/);
  if (m) { try { showMeeting(decodeURIComponent(m[1])); } catch (e) { /* bad escape */ } }
  else { clearTimeout(state.viewTimer); state.viewToken++; state.currentId = null; state.detail = null;
    $("view").replaceChildren(el("p", { class: "muted", text: "Select a meeting to see its transcript." })); renderList(); }
}

export async function showMeeting(id) {
  clearTimeout(state.viewTimer);
  const token = ++state.viewToken;
  if (state.currentId !== id) { state.detail = null; }
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

const COPY_ICON = '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h10"/></svg>';

const CHEVRON_UP = '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m6 15 6-6 6 6"/></svg>';
const CHEVRON_DOWN = '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>';
const COLLAPSED_LINES = 8;

// Whether a long transcript is shown in full; kept across re-renders, reset when another meeting opens.
let expandedFor = null;

// Small utility bar: copy the whole transcript (timestamps and speaker names), and, for a long one, collapse/expand it.
function utilBar(position, text, collapsible, collapsed) {
  const note = el("span", { class: "copy-note muted", role: "status" });
  const copy = el("button", { type: "button", class: "icon", title: "Copy transcript", "aria-label": "Copy transcript" });
  copy.innerHTML = COPY_ICON;
  let timer;
  copy.addEventListener("click", async () => {
    try { await navigator.clipboard.writeText(text); note.textContent = "Copied to clipboard"; }
    catch (e) { note.textContent = "Could not copy"; }
    clearTimeout(timer); timer = setTimeout(() => { note.textContent = ""; }, 2000);
  });
  const bar = el("div", { class: "util-bar " + position }, copy);
  if (collapsible) {
    const label = collapsed ? "Expand transcript" : "Collapse transcript";
    const tog = el("button", { type: "button", class: "icon", title: label, "aria-label": label, "aria-expanded": String(!collapsed) });
    tog.innerHTML = collapsed ? CHEVRON_DOWN : CHEVRON_UP;
    tog.addEventListener("click", () => { expandedFor = collapsed ? state.currentId : null; renderMeeting(); });
    bar.append(tog);
  }
  bar.append(note);
  return bar;
}

export function renderMeeting() {
  const { meeting: m, segments } = state.detail;
  // Build into two fragments around the audio players, so a refresh never detaches a player mid-playback.
  const head = document.createDocumentFragment(), tail = document.createDocumentFragment();
  let view = head;
  const id = m.id;
  view.append(el("h3", { style: "margin:0;font-size:1.25rem;overflow-wrap:anywhere" }, document.createTextNode(m.title || m.id), badge(m.status)));

  let lang = LANG_LABEL[m.language] || m.language;
  if (m.language === "auto") {
    const det = Object.entries(m.detected_languages || {});
    lang = "Auto" + (det.length ? " — detected: " + det.map(([t, l]) => `${TRACK_LABEL[t] || t} ${LANG_LABEL[l] || l}`).join(", ") : "");
  }
  const dl = el("dl", { class: "meta" });
  for (const [k, v] of [["Started", new Date(m.started_at).toLocaleString()], ["Duration", m.duration != null ? mmss(m.duration) : "—"],
    ["Size", fileSize(m.audio_bytes)],
    ["Mode", MODE_LABEL[m.mode] || m.mode], ["Language", lang], ...(m.model ? [["Speech model", m.model]] : [])]) {
    dl.append(el("dt", { text: k }), el("dd", { text: v }));
  }
  view.append(dl);
  for (const w of m.warnings || []) view.append(el("p", { class: "warn", text: "Warning: " + w }));
  if (m.status === "failed") view.append(el("div", { class: "err", role: "alert", text: "Transcription failed: " + (m.error || "unknown error") }));

  let tracks = null;
  if (m.status !== "recording") {
    const key = id + "|" + (m.tracks || []).join(",");
    tracks = $("tracks");
    if (!tracks || tracks.dataset.key !== key) tracks = renderTracks(id, m.tracks || [], key);
  }
  view = tail;

  if (m.status === "recording") {
    view.append(el("p", { class: "muted", text: "Recording in progress. The transcript appears after you stop." }));
  } else if (m.status === "transcribing") {
    view.append(renderProgress(m.progress));
  } else if (m.status === "transcribed" && segments) {
    if (!segments.length) view.append(el("p", { class: "muted", text: "No speech was found." }));
    const collapsible = segments.length > COLLAPSED_LINES;
    const collapsed = collapsible && expandedFor !== id;
    const text = state.detail.transcript;
    if (segments.length) view.append(utilBar("top", text, collapsible, collapsed));
    const ol = el("ol", { class: "transcript", "aria-label": "Transcript" });
    for (const s of collapsed ? segments.slice(0, COLLAPSED_LINES) : segments) {
      const li = el("li", null, el("span", { class: "ts", text: `[${mmss(s.start)}]` }));
      if (s.speaker) {
        const shown = (m.speaker_names || {})[s.speaker] || s.speaker;
        const b = el("button", { type: "button", class: "spk", title: "Rename this speaker", text: shown, onclick: () => renameSpeaker(s.speaker, shown) });
        b.style.color = colourOf(s.speaker);
        li.append(b);
      }
      li.append(el("span", { text: s.text }));
      ol.append(li);
    }
    view.append(ol);
    if (collapsible) view.append(utilBar("bottom", text, collapsible, collapsed));
  }

  if (m.status !== "recording") {
    const again = el("div", { class: "again" }, el("h4", { style: "margin:0 0 4px", text: "Transcribe again" }));
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
    view.append(again);
  }

  if (m.status === "transcribed" || m.status === "failed") {
    const btn = el("button", { type: "button", class: "danger", text: "Delete meeting" });
    const errBox = el("div", { class: "err", role: "alert" });
    btn.addEventListener("click", async () => {
      if (!confirm(`Delete "${m.title || id}"? Its audio and transcript are removed for good.`)) return;
      btn.disabled = true; errBox.textContent = "";
      try {
        await api("DELETE", `/api/meetings/${encodeURIComponent(id)}`, {});
        await loadMeetings();
        location.hash = "";
      } catch (e) { errBox.textContent = e.message; btn.disabled = false; }
    });
    view.append(el("div", { class: "again" }, btn, errBox));
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
}
