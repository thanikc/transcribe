import { useState } from "react";
import type { Meeting, TranscriptSegment } from "../types";
import { mmss } from "../utils";
import { InlineEdit, PencilIcon } from "./InlineEdit";

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
  /** Throws when the rename is refused. An empty name resets it. */
  onRenameSpeaker: (rawSpeaker: string, name: string) => Promise<void>;
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
  const [editingAt, setEditingAt] = useState<number | null>(null);
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
              <span className="spk-wrap">
                <button
                  type="button"
                  className="spk"
                  title="Rename this speaker"
                  aria-expanded={editingAt === idx}
                  style={{ color: colourOf(s.speaker) }}
                  onClick={() => setEditingAt(editingAt === idx ? null : idx)}
                >
                  {shownSpeaker}
                  <PencilIcon />
                </button>
                {editingAt === idx && (
                  <InlineEdit
                    className="spk-popover"
                    label={`Name for ${s.speaker}`}
                    placeholder={s.speaker}
                    initial={shownSpeaker === s.speaker ? "" : shownSpeaker}
                    onLeave="cancel"
                    showSave
                    resetLabel={
                      shownSpeaker !== s.speaker
                        ? `Reset to ${s.speaker}`
                        : undefined
                    }
                    onSave={(name) => onRenameSpeaker(s.speaker!, name)}
                    onClose={() => setEditingAt(null)}
                  />
                )}
              </span>
            )}
            <span className="seg-text">{s.text}</span>
          </li>
        );
      })}
    </ol>
  );
}
