import type { Meeting, TranscriptSegment } from "../types";
import { mmss } from "../utils";

export function trackOf(m: Meeting, s: TranscriptSegment): string {
  if (m.mode === "mic+system") return s.speaker === "You" ? "mic" : "system";
  return (m.tracks || ["mic"])[0];
}

interface TranscriptListProps {
  meeting: Meeting;
  segments: TranscriptSegment[];
  activeSpeaker: string | null;
  playingPosition: { track: string; time: number } | null;
  onPlayFrom: (track: string, start: number) => void;
  onRenameSpeaker: (rawSpeaker: string, currentShown: string) => void;
  colourOf: (speaker: string) => string;
}

export function TranscriptList({
  meeting,
  segments,
  activeSpeaker,
  playingPosition,
  onPlayFrom,
  onRenameSpeaker,
  colourOf,
}: TranscriptListProps) {
  return (
    <ol className="transcript" aria-label="Transcript">
      {segments.map((s, idx) => {
        const track = trackOf(meeting, s);
        const isPlaying =
          playingPosition !== null &&
          playingPosition.track === track &&
          playingPosition.time >= s.start &&
          playingPosition.time < s.end;
        const classes = [
          s.speaker ? "" : "no-speaker",
          isPlaying ? "playing" : "",
        ]
          .filter(Boolean)
          .join(" ");
        const shownSpeaker = s.speaker
          ? meeting.speaker_names?.[s.speaker] || s.speaker
          : null;

        return (
          <li
            key={`${s.start}-${s.end}-${idx}`}
            className={classes}
            data-track={track}
            data-start={s.start}
            data-end={s.end}
            hidden={Boolean(activeSpeaker && s.speaker !== activeSpeaker)}
          >
            <button
              type="button"
              className="ts"
              title="Play from here"
              onClick={() => onPlayFrom(track, s.start)}
            >
              {`[${mmss(s.start)}]`}
            </button>
            {s.speaker && shownSpeaker && (
              <button
                type="button"
                className="spk"
                title="Rename this speaker"
                style={{ color: colourOf(s.speaker) }}
                onClick={() => onRenameSpeaker(s.speaker!, shownSpeaker)}
              >
                {shownSpeaker}
              </button>
            )}
            <span className="seg-text">{s.text}</span>
          </li>
        );
      })}
    </ol>
  );
}
