// Footer: the installed version and, when a newer release exists, the button that installs it.

import { $, api, el } from "./util.js";
import { state } from "./state.js";

const RELEASES = "https://github.com/thanikc/transcribe/releases/latest";
let installing = false;
let waited = false;

export async function loadVersion() {
  if (installing) return;
  let v;
  try { v = await api("GET", "/api/version"); } catch (e) { return; }
  const parts = [`Transcribe ${v.version}`];
  if (v.update && v.can_install) {
    parts.push(" · ", el("button", { type: "button", id: "update", class: "primary", text: `Update to ${v.update}`, onclick: () => install(v.update) }));
  } else if (v.update) {
    parts.push(" · ", el("a", { href: RELEASES, target: "_blank", rel: "noopener", text: `${v.update} is available` }));
  } else if (v.error) {
    parts.push(` · ${v.error[0].toUpperCase()}${v.error.slice(1)}`);
  } else if (v.checked) {
    parts.push(" · Up to date");
  }
  $("version").replaceChildren(...parts);
  renderUpdateButton();
  // The service checks right after it starts, often just after the tray opened this page.
  if (!v.checked && !v.error && v.version !== "dev" && !waited) { waited = true; setTimeout(loadVersion, 10000); }
}

// The installer stops the app, so updating waits until the recording is stopped (the service refuses it too).
export function renderUpdateButton() {
  const button = $("update");
  if (!button || installing) return;
  button.disabled = state.recording;
  button.title = state.recording ? "Stop the recording to update" : "";
}

async function install(version) {
  installing = true;
  const button = $("update");
  button.disabled = true;
  button.textContent = `Downloading ${version}…`;
  $("update-error").textContent = "";
  try {
    await api("POST", "/api/update/install");
    $("version").replaceChildren(`The installer for ${version} is opening. Transcribe closes while it updates.`);
  } catch (e) {
    installing = false;
    $("update-error").textContent = e.message;
    loadVersion();
  }
}
