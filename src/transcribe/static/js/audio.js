// Audio players for a meeting's tracks, and the choice of output device.

import { $, el, TRACK_LABEL } from "./util.js";

const SINK_KEY = "transcribe.audioOutput";
const canPickOutput = !!(navigator.mediaDevices && "setSinkId" in HTMLMediaElement.prototype);

function savedSink() { try { return localStorage.getItem(SINK_KEY) || ""; } catch (e) { return ""; } }
function saveSink(v) { try { localStorage.setItem(SINK_KEY, v); } catch (e) { /* private window */ } }

export function renderTracks(id, names, key) {
  const tracks = el("div", { class: "tracks", id: "tracks", "data-key": key });
  if (canPickOutput && names.length) tracks.append(renderOutputPicker());
  for (const t of names) {
    const lid = `audio-${t}`;
    tracks.append(el("div", null, el("label", { for: lid, text: TRACK_LABEL[t] || t }),
      el("audio", { id: lid, controls: "", preload: "none", src: `/api/meetings/${encodeURIComponent(id)}/audio/${encodeURIComponent(t)}` })));
  }
  applySink(tracks, savedSink());
  return tracks;
}

function renderOutputPicker() {
  const sel = el("select", { id: "audio-output" });
  const names = el("button", { type: "button", hidden: "",
    title: "The browser only shows output device names after you allow it", text: "Show device names" });
  const errBox = el("div", { class: "err", role: "alert" });
  sel.addEventListener("change", () => { saveSink(sel.value); applySink($("tracks"), sel.value); });
  names.addEventListener("click", async () => {
    errBox.textContent = "";
    try {
      if (navigator.mediaDevices.selectAudioOutput) {  // Firefox: it asks for the device itself
        const d = await navigator.mediaDevices.selectAudioOutput();
        saveSink(d.deviceId); applySink($("tracks"), d.deviceId);
      } else {  // Chrome/Edge: device names appear once microphone access is granted
        const s = await navigator.mediaDevices.getUserMedia({ audio: true });
        s.getTracks().forEach((tr) => tr.stop());
      }
    } catch (e) { errBox.textContent = "Could not list output devices: " + e.message; }
    fillOutputs(sel, names);
  });
  fillOutputs(sel, names);
  return el("div", null, el("label", { for: "audio-output", text: "Play through" }),
    el("div", { class: "row" }, el("div", null, sel), names), errBox);
}

async function fillOutputs(sel, names) {
  let outs = [];
  try { outs = (await navigator.mediaDevices.enumerateDevices()).filter((d) => d.kind === "audiooutput" && d.deviceId); }
  catch (e) { /* none listed */ }
  const want = savedSink();
  sel.replaceChildren(el("option", { value: "", text: "Windows default output" }));
  outs.filter((d) => d.deviceId !== "default").forEach((d, i) =>
    sel.append(el("option", { value: d.deviceId, text: d.label || `Output device ${i + 1}` })));
  if (want && ![...sel.options].some((o) => o.value === want)) sel.append(el("option", { value: want, text: "Previously chosen device" }));
  sel.value = want;
  names.hidden = outs.length > 0 && outs.every((d) => d.label);
}

function applySink(tracks, sinkId) {
  if (!canPickOutput || !tracks) return;
  for (const a of tracks.querySelectorAll("audio")) {
    a.setSinkId(sinkId).catch(() => {
      // The saved device is gone (unplugged); fall back to the default output.
      a.setSinkId("").catch(() => {});
    });
  }
}

export function initAudio() {
  if (!canPickOutput) return;
  navigator.mediaDevices.addEventListener("devicechange", () => {
    const sel = $("audio-output");
    if (sel) fillOutputs(sel, sel.closest(".row").querySelector("button"));
  });
}
