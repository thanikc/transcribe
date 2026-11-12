// Entry point: wires the modules together and starts the page.

import { state } from "./state.js";
import { initModels, loadModels } from "./models.js";
import { initRecording, pollStatus } from "./recording.js";
import { initList, loadMeetings } from "./list.js";
import { initMeeting, inProgress, renderMeeting, routeFromHash, showMeeting } from "./meeting.js";
import { initProgress } from "./progress.js";
import { initAudio } from "./audio.js";
import { initSearch } from "./search.js";
import { initSources } from "./sources.js";
import { initUpload } from "./upload.js";
import { loadVersion } from "./version.js";

initModels(); initRecording(); initList(); initMeeting(); initProgress(); initAudio(); initSearch(); initUpload(); initSources();

document.addEventListener("visibilitychange", () => {
  if (document.hidden) return;
  pollStatus(); loadMeetings(); loadVersion();
  if (state.currentId && inProgress(state.detail)) showMeeting(state.currentId);
});

pollStatus(); loadMeetings(); routeFromHash(); loadVersion();
// The "Transcribe again" picker uses the model list, so redraw an open meeting once it has loaded.
loadModels().then((ok) => { if (ok && state.detail) renderMeeting(); });
