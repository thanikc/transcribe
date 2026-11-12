import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api";
import type { MeetingDetail, SpeechModelInfo } from "../types";
import {
  fileSize,
  LANG_LABEL,
  mmss,
  MODE_LABEL,
  speakerPalette,
  TRACK_LABEL,
} from "../utils";
import { AudioBar } from "./AudioBar";
import { ProgressBox } from "./ProgressBox";
import { SecondaryActionsDrawer } from "./SecondaryActionsDrawer";
import { StatusBadge } from "./StatusBadge";
import { TranscriptList } from "./TranscriptList";
import { TranscriptToolbar } from "./TranscriptToolbar";

const COLLAPSED_LINES = 8;

interface MeetingViewProps {
  currentId: string | null;
  hasMeetings: boolean;
  detail: MeetingDetail | null;
  detailAt: number;
  error: string;
  models: SpeechModelInfo[];
  onDetailUpdated: (detail: MeetingDetail) => void;
  onRefreshMeeting: () => Promise<void> | void;
  onMeetingsChanged: () => Promise<void> | void;
  onClearSelection: () => void;
}

export function MeetingView({
  currentId,
  hasMeetings,
  detail,
  detailAt,
  error,
  models,
  onDetailUpdated,
  onRefreshMeeting,
  onMeetingsChanged,
  onClearSelection,
}: MeetingViewProps) {
  const [activeSpeaker, setActiveSpeaker] = useState<string | null>(null);
  const [collapsedFor, setCollapsedFor] = useState<string | null>(null);
  const [playingPosition, setPlayingPosition] = useState<{
    track: string;
    time: number;
  } | null>(null);
  const palette = useMemo(
    () => speakerPalette(detail?.segments),
    [detail?.segments],
  );

  const sectionRef = useRef<HTMLElement>(null);

  useEffect(() => {
    setActiveSpeaker(null);
    setPlayingPosition(null);
    sectionRef.current?.scrollTo?.({ top: 0 });
  }, [currentId]);

  const colourOf = (label: string): string => `var(--sp${palette[label] ?? 0})`;

  const handleRenameMeeting = async (currentTitle: string) => {
    if (!currentId) return;
    const nextTitle = window.prompt(
      "Meeting title (leave empty for none):",
      currentTitle,
    );
    if (nextTitle === null) return;
    try {
      const updated = await api<MeetingDetail>(
        "POST",
        `/api/meetings/${encodeURIComponent(currentId)}/title`,
        { title: nextTitle },
      );
      onDetailUpdated(updated);
      onMeetingsChanged();
    } catch (e) {
      window.alert(e instanceof Error ? e.message : String(e));
    }
  };

  const handleRenameSpeaker = async (raw: string, currentShown: string) => {
    if (!currentId) return;
    const nextName = window.prompt(
      `Name for ${raw} (leave empty to reset):`,
      currentShown === raw ? "" : currentShown,
    );
    if (nextName === null) return;
    try {
      const updated = await api<MeetingDetail>(
        "POST",
        `/api/meetings/${encodeURIComponent(currentId)}/speakers`,
        { speaker: raw, name: nextName },
      );
      onDetailUpdated(updated);
    } catch (e) {
      window.alert(e instanceof Error ? e.message : String(e));
    }
  };

  const handlePlayFrom = (track: string, start: number) => {
    const player = document.getElementById(
      `audio-${track}`,
    ) as HTMLAudioElement | null;
    if (!player) return;
    for (const other of document.querySelectorAll<HTMLAudioElement>(
      "#tracks audio",
    )) {
      if (other !== player) other.pause();
    }
    if (player.readyState === 0) {
      player.addEventListener(
        "loadedmetadata",
        () => {
          player.currentTime = start;
        },
        { once: true },
      );
    } else {
      player.currentTime = start;
    }
    player.play().catch(() => {
      /* browser refused playback */
    });
  };

  const renderContent = () => {
    if (!currentId) {
      return (
        <p className="empty-state">
          {hasMeetings
            ? "Select a meeting to see its transcript."
            : "No meetings yet. Press Start recording, or use Import audio to transcribe a file you already have."}
        </p>
      );
    }
    if (error) {
      return (
        <div className="err" role="alert">
          {error}
        </div>
      );
    }
    if (!detail) {
      return <p className="loading muted">Loading…</p>;
    }

    const { meeting: m, segments, notes, transcript } = detail;

    let lang = LANG_LABEL[m.language] || m.language;
    if (m.language === "auto") {
      const det = Object.entries(m.detected_languages || {});
      lang =
        "Auto" +
        (det.length
          ? " — detected: " +
            det
              .map(([t, l]) => `${TRACK_LABEL[t] || t} ${LANG_LABEL[l] || l}`)
              .join(", ")
          : "");
    }

    const metaPairs: [string, string][] = [
      ["Started", new Date(m.started_at).toLocaleString()],
      ["Duration", m.duration != null ? mmss(m.duration) : "—"],
      ["Size", fileSize(m.audio_bytes)],
      ["Mode", MODE_LABEL[m.mode] || m.mode],
      ["Language", lang],
      ...(m.model ? ([["Speech model", m.model]] as [string, string][]) : []),
    ];

    const collapsible = Boolean(segments && segments.length > COLLAPSED_LINES);
    const collapsed = collapsible && collapsedFor === m.id;
    const visibleSegments =
      segments && collapsed ? segments.slice(0, COLLAPSED_LINES) : segments;

    return (
      <>
        <div className="meeting-header">
          <h3 className="meeting-title-row">
            <button
              type="button"
              className="title-edit"
              title="Rename this meeting"
              onClick={() => handleRenameMeeting(m.title)}
            >
              {m.title || m.id}
            </button>
            <StatusBadge status={m.status} />
          </h3>
        </div>

        <dl className="meta">
          {metaPairs.map(([k, v]) => (
            <div key={k} className="meta-pair">
              <dt>{k}</dt>
              <dd>{v}</dd>
            </div>
          ))}
        </dl>

        {(m.warnings || []).map((w, i) => (
          <p key={i} className="warn">
            {"Warning: " + w}
          </p>
        ))}

        {m.status === "failed" && (
          <div className="err" role="alert">
            {"Transcription failed: " + (m.error || "unknown error")}
          </div>
        )}

        {notes && (
          <section className="notes" aria-label="Notes">
            <h4>Notes</h4>
            <div>{notes}</div>
          </section>
        )}

        {m.status === "recording" && (
          <p className="empty-state">
            Recording in progress. The transcript appears after you stop.
          </p>
        )}

        {m.status === "transcribing" && (
          <ProgressBox progress={m.progress} detailAt={detailAt} />
        )}

        {m.status === "transcribed" && segments && (
          <>
            {segments.length === 0 ? (
              <p className="empty-state">No speech was found.</p>
            ) : (
              <>
                <TranscriptToolbar
                  position="top"
                  meeting={m}
                  segments={segments}
                  transcriptText={transcript || ""}
                  activeSpeaker={activeSpeaker}
                  onSelectSpeaker={setActiveSpeaker}
                  collapsible={collapsible}
                  collapsed={collapsed}
                  onToggleCollapse={() =>
                    setCollapsedFor(collapsed ? null : m.id)
                  }
                  colourOf={colourOf}
                />
                <TranscriptList
                  meeting={m}
                  segments={visibleSegments || []}
                  activeSpeaker={activeSpeaker}
                  playingPosition={playingPosition}
                  onPlayFrom={handlePlayFrom}
                  onRenameSpeaker={handleRenameSpeaker}
                  colourOf={colourOf}
                />
                {collapsible && collapsed && (
                  <TranscriptToolbar
                    position="bottom"
                    meeting={m}
                    segments={segments}
                    transcriptText={transcript || ""}
                    activeSpeaker={activeSpeaker}
                    onSelectSpeaker={setActiveSpeaker}
                    collapsible={collapsible}
                    collapsed={collapsed}
                    onToggleCollapse={() =>
                      setCollapsedFor(collapsed ? null : m.id)
                    }
                    colourOf={colourOf}
                  />
                )}
              </>
            )}
          </>
        )}

        {m.status !== "recording" && (
          <SecondaryActionsDrawer
            meeting={m}
            models={models}
            onRetranscribed={async () => {
              await onRefreshMeeting();
              await onMeetingsChanged();
            }}
            onDeleted={async () => {
              await onMeetingsChanged();
              onClearSelection();
            }}
          />
        )}

        {m.status !== "recording" && (
          <AudioBar
            key={`${m.id}|${(m.tracks || []).join(",")}`}
            meetingId={m.id}
            tracks={m.tracks || []}
            onTimeUpdate={(track, time) => setPlayingPosition({ track, time })}
          />
        )}
      </>
    );
  };

  return (
    <section aria-labelledby="view-h" id="view-section" ref={sectionRef}>
      <h2 id="view-h" className="sr-only">
        Meeting
      </h2>
      <div id="view">{renderContent()}</div>
    </section>
  );
}
