import { useEffect, useRef, useState } from "react";
import type { Meeting, TranscriptSegment } from "../types";
import { mmss, type Turn } from "../utils";
import { InlineEdit, PencilIcon } from "./InlineEdit";

const FOLLOW_PAUSE_MS = 5000;
const SCROLL_KEYS = ["ArrowUp", "ArrowDown", "PageUp", "PageDown", "Home", "End"];

export function trackOf(m: Meeting, s: TranscriptSegment): string {
  if (m.mode === "mic+system") return s.speaker === "You" ? "mic" : "system";
  return (m.tracks || ["mic"])[0];
}

interface TranscriptListProps {
  meeting: Meeting;
  turns: Turn[];
  activeSpeaker: string | null;
  /** `index` is a line's place in the whole transcript. */
  focusAt: { index: number; nonce: number } | null;
  /** The line being played, as a place in the whole transcript. */
  playingIndex: number | null;
  onPlayFrom: (start: number) => void;
  /** Throws when the rename is refused. An empty name resets it. */
  onRenameSpeaker: (rawSpeaker: string, name: string) => Promise<void>;
  colourOf: (speaker: string) => string;
}

export function TranscriptList({
  meeting,
  turns,
  activeSpeaker,
  focusAt,
  playingIndex,
  onPlayFrom,
  onRenameSpeaker,
  colourOf,
}: TranscriptListProps) {
  const [editingAt, setEditingAt] = useState<number | null>(null);
  const [flashAt, setFlashAt] = useState<number | null>(null);
  const listRef = useRef<HTMLOListElement>(null);
  const userScrolledAtRef = useRef(0);

  // follow the playing line, except for a while after the reader scrolls
  useEffect(() => {
    const scrolled = () => {
      userScrolledAtRef.current = Date.now();
    };
    const onKey = (e: KeyboardEvent) => {
      if (SCROLL_KEYS.includes(e.key)) scrolled();
    };
    document.addEventListener("wheel", scrolled, { passive: true });
    document.addEventListener("touchmove", scrolled, { passive: true });
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("wheel", scrolled);
      document.removeEventListener("touchmove", scrolled);
      document.removeEventListener("keydown", onKey);
    };
  }, []);

  useEffect(() => {
    if (playingIndex === null) return;
    if (Date.now() - userScrolledAtRef.current < FOLLOW_PAUSE_MS) return;
    listRef.current
      ?.querySelector<HTMLElement>(`[data-index="${playingIndex}"]`)
      ?.scrollIntoView?.({ block: "nearest" });
  }, [playingIndex]);

  useEffect(() => {
    if (!focusAt) return;
    setFlashAt(focusAt.index);
    const line = listRef.current?.querySelector<HTMLElement>(
      `[data-index="${focusAt.index}"]`,
    );
    line?.scrollIntoView?.({ block: "center" });
    const timer = setTimeout(() => setFlashAt(null), 2000);
    return () => clearTimeout(timer);
  }, [focusAt]);

  return (
    <ol className="transcript" aria-label="Transcript" ref={listRef}>
      {turns.map((turn, turnIdx) => {
        const raw = turn.speaker;
        const shownSpeaker = raw ? meeting.speaker_names?.[raw] || raw : null;
        return (
          <li
            key={`${turn.start}-${turn.lines[0].index}`}
            className={raw ? "turn" : "turn no-speaker"}
            data-track={turn.track}
            data-start={turn.start}
            style={raw ? { borderLeftColor: colourOf(raw) } : undefined}
            hidden={Boolean(activeSpeaker && raw !== activeSpeaker)}
          >
            <div className="turn-head">
              {raw && shownSpeaker && (
                <span className="spk-wrap">
                  <button
                    type="button"
                    className="spk"
                    title="Rename this speaker"
                    aria-expanded={editingAt === turnIdx}
                    style={{ color: colourOf(raw) }}
                    onClick={() =>
                      setEditingAt(editingAt === turnIdx ? null : turnIdx)
                    }
                  >
                    {shownSpeaker}
                    <PencilIcon />
                  </button>
                  {editingAt === turnIdx && (
                    <InlineEdit
                      className="spk-popover"
                      label={`Name for ${raw}`}
                      placeholder={raw}
                      initial={shownSpeaker === raw ? "" : shownSpeaker}
                      onLeave="cancel"
                      showSave
                      resetLabel={
                        shownSpeaker !== raw ? `Reset to ${raw}` : undefined
                      }
                      onSave={(name) => onRenameSpeaker(raw, name)}
                      onClose={() => setEditingAt(null)}
                    />
                  )}
                </span>
              )}
              <button
                type="button"
                className="ts"
                title="Play from here"
                onClick={() => onPlayFrom(turn.start)}
              >
                {`[${mmss(turn.start)}]`}
              </button>
            </div>
            <p className="turn-text">
              {turn.lines.map(({ segment: s, index }, i) => {
                const playing = playingIndex === index;
                const classes = [
                  "seg",
                  playing ? "playing" : "",
                  flashAt === index ? "focus" : "",
                ]
                  .filter(Boolean)
                  .join(" ");
                return (
                  <span key={index}>
                    {i > 0 && " "}
                    <span
                      className={classes}
                      data-index={index}
                      data-start={s.start}
                      data-end={s.end}
                      title={`Play from ${mmss(s.start)}`}
                      onClick={() => {
                        // a click that ends a text selection is for copying, not playing
                        const sel = window.getSelection();
                        if (sel && !sel.isCollapsed) return;
                        onPlayFrom(s.start);
                      }}
                    >
                      {s.text}
                    </span>
                  </span>
                );
              })}
            </p>
          </li>
        );
      })}
    </ol>
  );
}
