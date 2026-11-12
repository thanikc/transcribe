// The audio devices recordings use: two selects in Settings. The service keeps the choice for every recording.

import { $, api, fillSelect } from "./util.js";

function render(sources) {
  for (const [track, { chosen, devices }] of Object.entries(sources)) {
    const fallback = devices.find((d) => d.default);
    const options = [["", "Windows default" + (fallback ? ` (${fallback.name})` : "")],
      ...devices.map((d) => [d.id, d.name])];
    // A chosen device that is unplugged stays shown, so the refusal to record makes sense.
    if (chosen && !devices.some((d) => d.id === chosen.id)) options.push([chosen.id, `${chosen.name} (not connected)`]);
    fillSelect($(`source-${track}`), options, chosen ? chosen.id : "");
  }
}

async function loadSources() {
  try { render((await api("GET", "/api/sources")).sources); $("source-error").textContent = ""; }
  catch (e) { $("source-error").textContent = e.message; }
}

async function chooseSource(track) {
  try {
    render((await api("POST", "/api/sources", { track, device: $(`source-${track}`).value || null })).sources);
    $("source-error").textContent = "";
  } catch (e) { $("source-error").textContent = e.message; loadSources(); }
}

export function initSources() {
  for (const track of ["mic", "system"]) $(`source-${track}`).addEventListener("change", () => chooseSource(track));
  // Listed again on every opening: a headset plugged in since shows up.
  $("settings-drawer").addEventListener("toggle", () => { if ($("settings-drawer").open) loadSources(); });
  loadSources();
}
