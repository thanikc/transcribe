import type { SpeechModelInfo, TranscriptionProgress } from "./types";

export const STATUS_LABEL: Record<string, string> = {
  recording: "recording",
  transcribing: "transcribing",
  transcribed: "transcribed",
  failed: "failed",
};

export const TRACK_LABEL: Record<string, string> = {
  mic: "Microphone",
  system: "System audio",
  file: "Audio file",
};

export const LANG_LABEL: Record<string, string> = {
  th: "ไทย",
  en: "English",
  auto: "Auto",
};

export const MODE_LABEL: Record<string, string> = {
  mic: "In person (mic)",
  "mic+system": "Online call (mic + system audio)",
  file: "Imported file",
};

export const SHORT_MODE: Record<string, string> = {
  mic: "Mic",
  "mic+system": "Mic + Sys",
};

export const MODEL_NOTE: Record<string, string> = {
  "large-v3": "most accurate, slower",
  "large-v3-turbo": "faster, needs about half the memory",
};

export function mmss(sec?: number | null): string {
  const s = Math.max(0, Math.floor(sec || 0));
  return (
    String(Math.floor(s / 60)).padStart(2, "0") +
    ":" +
    String(s % 60).padStart(2, "0")
  );
}

export function fileSize(bytes?: number | null): string {
  if (!bytes) return "—";
  const units = ["B", "KB", "MB", "GB"];
  let val = bytes;
  let i = 0;
  while (val >= 1024 && i < units.length - 1) {
    val /= 1024;
    i++;
  }
  return (i === 0 ? String(val) : val.toFixed(1)) + " " + units[i];
}

export function percent(p?: TranscriptionProgress | null): string {
  return p && p.fraction != null ? ` ${Math.round(p.fraction * 100)}%` : "";
}

export function formatModelOption(m: SpeechModelInfo): string {
  const note = MODEL_NOTE[m.name] ? ` — ${MODEL_NOTE[m.name]}` : "";
  const dl = m.downloaded
    ? ""
    : ` (downloads${m.size ? " " + m.size : ""} on first use)`;
  return `${m.name}${note}${dl}`;
}

export function defaultModelName(models: SpeechModelInfo[]): string {
  return models.find((m) => m.default)?.name || "";
}

export function openMeetingHash(id: string): void {
  const target = "#/meeting/" + encodeURIComponent(id);
  if (window.location.hash !== target) {
    window.location.hash = target;
  } else {
    window.dispatchEvent(new HashChangeEvent("hashchange"));
  }
}

export function parseMeetingIdFromHash(hash: string): string | null {
  const m = hash.match(/^#\/meeting\/(.+)$/);
  if (!m) return null;
  try {
    return decodeURIComponent(m[1]);
  } catch {
    return null;
  }
}
