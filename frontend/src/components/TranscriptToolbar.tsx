import { useEffect, useRef, useState } from "react";
import type { Meeting, TranscriptSegment } from "../types";

interface TranscriptToolbarProps {
  position: "top" | "bottom";
  meeting: Meeting;
  segments: TranscriptSegment[];
  transcriptText: string;
  activeSpeaker: string | null;
  onSelectSpeaker: (speaker: string | null) => void;
  collapsible: boolean;
  collapsed: boolean;
  onToggleCollapse: () => void;
  colourOf: (speaker: string) => string;
}

export function TranscriptToolbar({
  position,
  meeting,
  segments,
  transcriptText,
  activeSpeaker,
  onSelectSpeaker,
  collapsible,
  collapsed,
  onToggleCollapse,
  colourOf,
}: TranscriptToolbarProps) {
  const [copyNote, setCopyNote] = useState("");
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  const seenSpeakers: string[] = [];
  if (position === "top") {
    for (const s of segments) {
      if (s.speaker && !seenSpeakers.includes(s.speaker)) {
        seenSpeakers.push(s.speaker);
      }
    }
  }

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(transcriptText);
      setCopyNote("Copied to clipboard");
    } catch {
      setCopyNote("Could not copy");
    }
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => setCopyNote(""), 2000);
  };

  const handleExport = () => {
    const blob = new Blob([transcriptText || ""], {
      type: "text/plain;charset=utf-8",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${meeting.id}.txt`;
    document.body.append(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  };

  const collapseLabel = collapsed ? "Expand transcript" : "Collapse transcript";

  return (
    <div className={`util-bar ${position}`}>
      {position === "top" && seenSpeakers.length > 1 && (
        <div
          className="speaker-filters"
          role="group"
          aria-label="Filter by speaker"
        >
          <button
            type="button"
            className="filter-pill"
            aria-pressed={!activeSpeaker}
            onClick={() => onSelectSpeaker(null)}
          >
            All speakers
          </button>
          {seenSpeakers.map((raw) => {
            const shown = meeting.speaker_names?.[raw] || raw;
            return (
              <button
                key={raw}
                type="button"
                className="filter-pill"
                aria-pressed={activeSpeaker === raw}
                style={{ borderLeft: `3px solid ${colourOf(raw)}` }}
                onClick={() =>
                  onSelectSpeaker(activeSpeaker === raw ? null : raw)
                }
              >
                {shown}
              </button>
            );
          })}
        </div>
      )}

      <div className="util-actions">
        <span className="copy-note muted" role="status">
          {copyNote}
        </span>

        <button
          type="button"
          className="icon"
          title="Copy transcript"
          aria-label="Copy transcript"
          onClick={handleCopy}
        >
          <svg
            viewBox="0 0 24 24"
            width="14"
            height="14"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <rect x="9" y="9" width="12" height="12" rx="2" />
            <path d="M5 15V5a2 2 0 0 1 2-2h10" />
          </svg>
          <span>Copy</span>
        </button>

        {position === "top" && (
          <button
            type="button"
            className="icon"
            title="Export transcript (.txt)"
            aria-label="Export transcript"
            onClick={handleExport}
          >
            <svg
              viewBox="0 0 24 24"
              width="14"
              height="14"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
              <polyline points="7 10 12 15 17 10" />
              <line x1="12" y1="15" x2="12" y2="3" />
            </svg>
            <span>Export .txt</span>
          </button>
        )}

        {collapsible && (
          <button
            type="button"
            className="icon"
            title={collapseLabel}
            aria-label={collapseLabel}
            aria-expanded={!collapsed}
            onClick={onToggleCollapse}
          >
            {collapsed ? (
              <svg
                viewBox="0 0 24 24"
                width="14"
                height="14"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <path d="m6 9 6 6 6-6" />
              </svg>
            ) : (
              <svg
                viewBox="0 0 24 24"
                width="14"
                height="14"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <path d="m6 15 6-6 6 6" />
              </svg>
            )}
            <span>{collapsed ? "Expand" : "Collapse"}</span>
          </button>
        )}
      </div>
    </div>
  );
}
