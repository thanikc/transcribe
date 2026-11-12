// Transcript search.

import { $, api, el } from "./util.js";
import { openMeeting } from "./nav.js";

async function search(ev) {
  ev.preventDefault();
  const q = $("q").value.trim(); const box = $("hits"); box.replaceChildren();
  if (!q) return;
  try {
    const { hits } = await api("GET", "/api/search?q=" + encodeURIComponent(q));
    if (!hits.length) { box.append(el("p", { class: "muted", style: "font-size:var(--text-xs);margin:var(--sp-1) 0 0", text: "No matches." })); return; }
    for (const h of hits) {
      box.append(el("button", { type: "button", class: "item hit", onclick: () => openMeeting(h.meeting_id) },
        el("div", { class: "m", text: `${h.timestamp} ${h.title || h.meeting_id}${h.speaker ? " · " + h.speaker : ""}` }),
        el("div", { style: "font-size:var(--text-xs);margin-top:2px", text: h.text })));
    }
  } catch (e) { box.append(el("div", { class: "err", role: "alert", text: e.message })); }
}

export function initSearch() {
  $("search-form").addEventListener("submit", search);
  $("q").addEventListener("input", () => {
    if (!$("q").value.trim()) $("hits").replaceChildren();
  });
}
