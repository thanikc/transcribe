// Speech model choices: the select in the recording panel and the options for "Transcribe again".

import { $, api, el, fillSelect } from "./util.js";
import { state } from "./state.js";

const MODEL_NOTE = { "large-v3": "most accurate, slower", "large-v3-turbo": "faster, needs about half the memory" };
const MODEL_KEY = "transcribe.model";

export function modelOptions() {
  return state.models.map((m) => [m.name, m.name + (MODEL_NOTE[m.name] ? ` — ${MODEL_NOTE[m.name]}` : "")
    + (m.downloaded ? "" : ` (downloads${m.size ? " " + m.size : ""} on first use)`)]);
}

export function defaultModel() { return (state.models.find((m) => m.default) || {}).name || ""; }

// Resolves true once the list is loaded.
export async function loadModels() {
  try { state.models = (await api("GET", "/api/models")).models; } catch (e) { return false; }
  let saved = "";
  try { saved = localStorage.getItem(MODEL_KEY) || ""; } catch (e) { /* private window */ }
  // The choice is remembered in this browser; without one, the service default (the installer's choice) applies.
  fillSelect($("model"), modelOptions(), state.models.some((m) => m.name === saved) ? saved : defaultModel());
  return true;
}

export function initModels() {
  $("model").addEventListener("change", () => {
    try { localStorage.setItem(MODEL_KEY, $("model").value); } catch (e) { /* private window */ }
  });
}
