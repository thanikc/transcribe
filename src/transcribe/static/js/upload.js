// Importing an existing audio file (a phone recording, another app's) as a meeting.

import { $ } from "./util.js";
import { loadMeetings } from "./list.js";
import { openMeeting } from "./nav.js";

async function importFile() {
  const file = $("import-file").files[0], btn = $("import"), errBox = $("import-error");
  if (!file) return;
  btn.disabled = true; btn.textContent = "Importing…"; errBox.textContent = "";
  const params = new URLSearchParams({
    title: $("title").value.trim() || file.name.replace(/\.[^.]+$/, ""),
    language: $("language").value, model: $("model").value,
  });
  try {
    // Raw bytes, not a form: the service only takes uploads a page of another site can't send.
    const res = await fetch("/api/meetings/import?" + params, {
      method: "POST", headers: { "Content-Type": "application/octet-stream" }, body: file,
    });
    const data = await res.json().catch(() => null);
    if (!res.ok) throw new Error((data && data.error) || `Import failed (${res.status})`);
    $("import-file").value = "";
    await loadMeetings();
    openMeeting(data.meeting.id);
  } catch (e) {
    errBox.textContent = e instanceof TypeError ? "Cannot reach the recorder service." : e.message;
  }
  btn.textContent = "Import"; btn.disabled = !$("import-file").files.length;
}

export function initUpload() {
  $("import-file").addEventListener("change", () => { $("import").disabled = !$("import-file").files.length; });
  $("import").addEventListener("click", importFile);
}
