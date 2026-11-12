// The "Past meetings" list.

import { $, api, el, fileSize, mmss, percent, STATUS_LABEL } from "./util.js";
import { state } from "./state.js";
import { openMeeting } from "./nav.js";

export function badge(status, progress) {
  return el("span", { class: "badge " + status, text: (STATUS_LABEL[status] || status) + percent(progress) });
}

export function renderList() {
  const ul = $("meetings"); ul.replaceChildren();
  $("no-meetings").hidden = state.meetings.length > 0;
  for (const m of state.meetings) {
    const when = new Date(m.started_at).toLocaleString();
    const b = el("button", { type: "button", class: "item", "data-id": m.id, onclick: () => openMeeting(m.id) },
      el("div", { class: "t" }, document.createTextNode(m.title || m.id), badge(m.status, m.progress)),
      el("div", { class: "m", text: `${when} · ${mmss(m.duration)} · ${fileSize(m.audio_bytes)}` }));
    if (m.id === state.currentId) b.setAttribute("aria-current", "true");
    ul.append(el("li", null, b));
  }
}

export async function loadMeetings() {
  try {
    const data = await api("GET", "/api/meetings");
    state.meetings = data.meetings.slice().sort((a, b) => (a.started_at < b.started_at ? 1 : -1));
    renderList();
  } catch (e) { /* ignore */ }
}

export function initList() {
  setInterval(() => {
    if (document.hidden) return;
    if (state.meetings.some((m) => m.status === "recording" || m.status === "transcribing")) loadMeetings();
  }, 2000);
}
