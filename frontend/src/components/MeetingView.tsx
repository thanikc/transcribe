import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api";
import type { MeetingDetail, SpeechModelInfo } from "../types";
import {
  fileSize,
  LANG_LABEL,
  mmss,
  groupTurns,
  MODE_LABEL,
  nearestSegment,
  speakerPalette,
  TRACK_LABEL,
} from "../utils";
import { AudioBar } from "./AudioBar";
import { InlineEdit, PencilIcon } from "./InlineEdit";
import { MeetingActions } from "./MeetingActions";
import { ProgressBox } from "./ProgressBox";
import { StatusBadge } from "./StatusBadge";
import { trackOf, TranscriptList } from "./TranscriptList";
import { TranscriptToolbar } from "./TranscriptToolbar";

const COLLAPSED_TURNS = 4;

interface MeetingViewProps {
  currentId: string | null;
  hasMeetings: boolean;
  detail: MeetingDetail | null;
  detailAt: number;
  focus: { t: number; nonce: number } | null;
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
  focus,
  error,
  models,
  onDetailUpdated,
  onRefreshMeeting,
  onMeetingsChanged,
  onClearSelection,
}: MeetingViewProps) {
  const [activeSpeaker, setActiveSpeaker] = useState<string | null>(null);
  const [collapsedFor, setCollapsedFor] = useState<string | null>(null);
  const [editingTitle, setEditingTitle] = useState(false);
  const [playingPosition, setPlayingPosition] = useState<{
    track: string;
    time: number;
  } | null>(null);
  const turns = useMemo(
    () =>
      detail?.segments
        ? groupTurns(detail.segments, (s) => trackOf(detail.meeting, s))
        : [],
    [detail],
  );
  const palette = useMemo(
    () => speakerPalette(detail?.segments),
    [detail?.segments],
  );

  const [focusAt, setFocusAt] = useState<{
    index: number;
    nonce: number;
  } | null>(null);
  const sectionRef = useRef<HTMLElement>(null);
  const actionsRef = useRef<HTMLDetailsElement>(null);

  useEffect(() => {
    setActiveSpeaker(null);
    setPlayingPosition(null);
    setEditingTitle(false);
    setFocusAt(null);
    sectionRef.current?.scrollTo?.({ top: 0 });
  }, [currentId]);

  // a search hit: reveal its line if the filter or collapse hides it, then scroll to it
  const handledFocusRef = useRef(0);
  useEffect(() => {
    const segments = detail?.segments;
    if (!focus || !segments?.length || detail?.meeting.id !== currentId) return;
    if (handledFocusRef.current === focus.nonce) return;
    handledFocusRef.current = focus.nonce;
    const index = nearestSegment(segments, focus.t);
    const turnIndex = turns.findIndex((t) =>
      t.lines.some((l) => l.index === index),
    );
    if (activeSpeaker && turns[turnIndex].speaker !== activeSpeaker) {
      setActiveSpeaker(null);
    }
    if (turnIndex >= COLLAPSED_TURNS) setCollapsedFor(null);
    setFocusAt({ index, nonce: focus.nonce });
  }, [focus, detail, turns, currentId, activeSpeaker]);

  const colourOf = (label: string): string => `var(--sp${palette[label] ?? 0})`;

  const handleRenameMeeting = async (nextTitle: string) => {
    if (!currentId) return;
    const updated = await api<MeetingDetail>(
      "POST",
      `/api/meetings/${encodeURIComponent(currentId)}/title`,
      { title: nextTitle },
    );
    onDetailUpdated(updated);
    onMeetingsChanged();
  };

  const handleRenameSpeaker = async (raw: string, nextName: string) => {
    if (!currentId) return;
    const updated = await api<MeetingDetail>(
      "POST",
      `/api/meetings/${encodeURIComponent(currentId)}/speakers`,
      { speaker: raw, name: nextName },
    );
    onDetailUpdated(updated);
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

    const collapsible = turns.length > COLLAPSED_TURNS;
    const collapsed = collapsible && collapsedFor === m.id;
    const visibleTurns = collapsed ? turns.slice(0, COLLAPSED_TURNS) : turns;

    return (
      <>
        <div className="meeting-header">
          <h3 className="meeting-title-row">
            {editingTitle ? (
              <InlineEdit
                className="title-form"
                label="Meeting title"
                placeholder={m.id}
                initial={m.title}
                onLeave="save"
                onSave={handleRenameMeeting}
                onClose={() => setEditingTitle(false)}
              />
            ) : (
              <button
                type="button"
                className="title-edit"
                title="Rename this meeting"
                onClick={() => setEditingTitle(true)}
              >
                {m.title || m.id}
                <PencilIcon />
              </button>
            )}
            <StatusBadge status={m.status} />
          </h3>
          {m.status !== "recording" && (
            <MeetingActions
              detailsRef={actionsRef}
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
          <div className="err failed-box" role="alert">
            <span>
              {"Transcription failed: " + (m.error || "unknown error")}
            </span>
            <button
              type="button"
              onClick={(e) => {
                // keep the document's outside-click handler from closing it again
                e.stopPropagation();
                if (actionsRef.current) actionsRef.current.open = true;
                actionsRef.current?.querySelector("select")?.focus();
              }}
            >
              Transcribe again…
            </button>
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
                  turns={visibleTurns}
                  activeSpeaker={activeSpeaker}
                  focusAt={focusAt}
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
