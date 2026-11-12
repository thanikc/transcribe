// Navigation by URL hash. The meeting view listens for "hashchange" (see meeting.js).

export function openMeeting(id) {
  const target = "#/meeting/" + encodeURIComponent(id);
  if (location.hash !== target) location.hash = target;
  else window.dispatchEvent(new HashChangeEvent("hashchange"));  // already there: show it again, fresh
}
