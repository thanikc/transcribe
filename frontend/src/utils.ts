import type {
  SpeechModelInfo,
  TranscriptionProgress,
  TranscriptSegment,
} from "./types";

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

export function openMeetingHash(id: string, start?: number): void {
  const target =
    "#/meeting/" +
    encodeURIComponent(id) +
    (start != null ? `?t=${start}` : "");
  if (window.location.hash !== target) {
    window.location.hash = target;
  } else {
    window.dispatchEvent(new HashChangeEvent("hashchange"));
  }
}

/** `#/meeting/<id>[?t=<seconds>]`; the id is URI-encoded, so `?` is unambiguous. */
export function parseMeetingHash(
  hash: string,
): { id: string; t: number | null } | null {
  const m = hash.match(/^#\/meeting\/([^?]+)(?:\?(.*))?$/);
  if (!m) return null;
  let id: string;
  try {
    id = decodeURIComponent(m[1]);
  } catch {
    return null;
  }
  const raw = new URLSearchParams(m[2] || "").get("t");
  const t = raw !== null && raw !== "" ? Number(raw) : NaN;
  return { id, t: Number.isFinite(t) ? t : null };
}

export function parseMeetingIdFromHash(hash: string): string | null {
  return parseMeetingHash(hash)?.id ?? null;
}

/** Splits text into plain and matched parts (case-insensitive) for <mark>. */
export function markMatches(
  text: string,
  query: string,
): { text: string; match: boolean }[] {
  const q = query.trim();
  if (!q) return [{ text, match: false }];
  const escaped = q.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return text
    .split(new RegExp(`(${escaped})`, "gi"))
    .map((part, i) => ({ text: part, match: i % 2 === 1 }))
    .filter((p) => p.text !== "");
}

/** Index of the segment whose start is nearest `t`. */
export function nearestSegment(
  segments: { start: number }[],
  t: number,
): number {
  let best = -1;
  for (let i = 0; i < segments.length; i++) {
    if (best < 0 || Math.abs(segments[i].start - t) < Math.abs(segments[best].start - t)) {
      best = i;
    }
  }
  return best;
}

/** Colour index per raw speaker label, in order of first appearance. */
export function speakerPalette(
  segments: TranscriptSegment[] | null | undefined,
): Record<string, number> {
  const palette: Record<string, number> = {};
  let next = 0;
  for (const s of segments || []) {
    if (s.speaker && !(s.speaker in palette)) palette[s.speaker] = next++ % 6;
  }
  return palette;
}

export const TURN_MAX_SECONDS = 60;
export const TURN_PAUSE_SECONDS = 2;

/** Consecutive lines of one speaker on one track; `index` is the line's place in the transcript. */
export interface Turn {
  speaker: string | null;
  track: string;
  start: number;
  lines: { segment: TranscriptSegment; index: number }[];
}

/**
 * Groups lines into speaker turns. A turn is closed early once it has run
 * 60 s or at a pause over 2 s, so long monologues read as paragraphs.
 */
export function groupTurns(
  segments: TranscriptSegment[],
  trackOf: (s: TranscriptSegment) => string,
): Turn[] {
  const turns: Turn[] = [];
  let current: Turn | null = null;
  let currentEnd = 0;
  segments.forEach((segment, index) => {
    const speaker = segment.speaker ?? null;
    const track = trackOf(segment);
    const joins =
      current !== null &&
      current.speaker === speaker &&
      current.track === track &&
      segment.start - currentEnd <= TURN_PAUSE_SECONDS &&
      segment.start - current.start < TURN_MAX_SECONDS;
    if (joins && current) {
      current.lines.push({ segment, index });
    } else {
      current = { speaker, track, start: segment.start, lines: [{ segment, index }] };
      turns.push(current);
    }
    currentEnd = segment.end;
  });
  return turns;
}
