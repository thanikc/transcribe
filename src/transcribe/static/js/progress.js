// The transcription progress box and its ticking step timer.

import { $, el, mmss, percent } from "./util.js";
import { state } from "./state.js";

export function renderProgress(p) {
  const box = el("div", { class: "progress" });
  // No step yet: another meeting is being transcribed, or this one is about to start.
  if (!p) { box.append(el("p", { role: "status", text: "Waiting to start. Meetings are transcribed one at a time." })); return box; }
  const bar = el("progress", { max: "1", "aria-label": p.step });
  if (p.fraction != null) bar.value = p.fraction;  // no value: an indeterminate, animated bar
  box.append(
    el("p", null, el("strong", { role: "status", text: p.step }),
      el("span", { class: "muted", text: ` · step ${p.step_number} of ${p.steps}` + (p.fraction != null ? ` ·${percent(p)}` : "") })),
    bar,
    el("p", { class: "muted", id: "step-time", text: stepTimeText() }));
  return box;
}

function stepTimeText() {
  const p = state.detail && state.detail.meeting.progress;
  if (!p) return "";
  const t = mmss(p.elapsed + (performance.now() - state.detailAt) / 1000);
  // Before the first percentage the model is loading; its first use downloads it (1.6–3 GB).
  return p.fraction == null ? `${t} · preparing (the first use of a model downloads it, which can take several minutes)` : t;
}

export function initProgress() {
  setInterval(() => { const t = $("step-time"); if (t && !document.hidden) t.textContent = stepTimeText(); }, 500);
}
