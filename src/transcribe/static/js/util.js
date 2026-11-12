// Small helpers shared by every module: DOM building, formatting, labels and the API client.

export const $ = (id) => document.getElementById(id);

export const STATUS_LABEL = { recording: "recording", transcribing: "transcribing", transcribed: "transcribed", failed: "failed" };
export const TRACK_LABEL = { mic: "Microphone", system: "System audio", file: "Audio file" };
export const LANG_LABEL = { th: "ไทย", en: "English", auto: "Auto" };
export const MODE_LABEL = { mic: "In person (mic)", "mic+system": "Online call (mic + system audio)", file: "Imported file" };

export function el(tag, props, ...kids) {
  const e = document.createElement(tag);
  if (props) for (const [k, v] of Object.entries(props)) {
    if (k === "class") e.className = v; else if (k === "text") e.textContent = v;
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v); else e.setAttribute(k, v);
  }
  for (const kid of kids) if (kid != null) e.append(kid);
  return e;
}

export const mmss = (sec) => {
  sec = Math.max(0, Math.floor(sec || 0));
  return String(Math.floor(sec / 60)).padStart(2, "0") + ":" + String(sec % 60).padStart(2, "0");
};

export const fileSize = (bytes) => {
  if (!bytes) return "—";
  const units = ["B", "KB", "MB", "GB"];
  let i = 0;
  while (bytes >= 1024 && i < units.length - 1) { bytes /= 1024; i++; }
  return (i === 0 ? bytes : bytes.toFixed(1)) + " " + units[i];
};

export const percent = (p) => (p && p.fraction != null ? ` ${Math.round(p.fraction * 100)}%` : "");

export function fillSelect(sel, options, value) {
  sel.replaceChildren(...options.map(([v, t]) => el("option", { value: v, text: t })));
  sel.value = value;
  if (sel.selectedIndex < 0) sel.selectedIndex = 0;
}

export function select(id, options, value) {
  const s = el("select", { id });
  for (const [v, t] of options) s.append(el("option", { value: v, text: t }));
  s.value = value; return s;
}

export async function api(method, path, body) {
  const opts = { method, headers: {} };
  if (method !== "GET") { opts.headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(body || {}); }
  let res;
  try { res = await fetch(path, opts); } catch (e) { throw new Error("Cannot reach the recorder service."); }
  let data = null;
  try { data = await res.json(); } catch (e) { /* non-JSON */ }
  if (!res.ok) throw new Error((data && data.error) || `Request failed (${res.status})`);
  return data;
}
