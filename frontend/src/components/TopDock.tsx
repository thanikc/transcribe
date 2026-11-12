import { useEffect, useState } from "react";
import type { SpeechModelInfo } from "../types";
import { mmss } from "../utils";
import { ImportDrawer } from "./ImportDrawer";
import { LevelMeters } from "./LevelMeters";
import { SettingsDrawer } from "./SettingsDrawer";

interface TopDockProps {
  recording: boolean;
  busy: boolean;
  offline: boolean;
  recTitle: string;
  elapsed: number;
  elapsedAt: number;
  levels: Record<string, number> | null;
  recError: string;
  title: string;
  onTitleChange: (title: string) => void;
  mode: string;
  onModeChange: (mode: string) => void;
  language: string;
  onLanguageChange: (language: string) => void;
  model: string;
  onModelChange: (model: string) => void;
  models: SpeechModelInfo[];
  onToggleRecording: () => void;
  onImported: (meetingId: string) => Promise<void> | void;
}

export function TopDock({
  recording,
  busy,
  offline,
  recTitle,
  elapsed,
  elapsedAt,
  levels,
  recError,
  title,
  onTitleChange,
  mode,
  onModeChange,
  language,
  onLanguageChange,
  model,
  onModelChange,
  models,
  onToggleRecording,
  onImported,
}: TopDockProps) {
  const [, setTick] = useState(0);

  useEffect(() => {
    if (!recording || busy || offline) return;
    const id = setInterval(() => {
      if (!document.hidden) setTick((t) => t + 1);
    }, 250);
    return () => clearInterval(id);
  }, [recording, busy, offline]);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        for (const d of document.querySelectorAll<HTMLDetailsElement>(
          "details.popover[open]",
        )) {
          d.open = false;
        }
      }
    };
    const onClick = (e: MouseEvent) => {
      // the path, not contains(): the clicked button may already be re-rendered away
      const path = e.composedPath();
      for (const d of document.querySelectorAll<HTMLDetailsElement>(
        "details.popover[open]",
      )) {
        if (!path.includes(d)) {
          d.open = false;
        }
      }
    };
    document.addEventListener("keydown", onKeyDown);
    document.addEventListener("click", onClick);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.removeEventListener("click", onClick);
    };
  }, []);

  let statusText = "Not recording";
  let statusClass = "";
  if (offline) {
    statusText = "Disconnected";
  } else if (busy) {
    statusText = recording ? "Stopping…" : "Starting…";
  } else if (recording) {
    const currentElapsed =
      elapsed + Math.max(0, (performance.now() - elapsedAt) / 1000);
    statusClass = "rec";
    statusText =
      `● Recording ${mmss(currentElapsed)}` +
      (recTitle ? ` — ${recTitle}` : "");
  }

  return (
    <header className="top-dock" aria-labelledby="rec-h">
      <h2 id="rec-h" className="sr-only">
        Recording
      </h2>
      <div className="dock-inner">
        <div className="brand-group">
          <h1>Meetings</h1>
          <p id="status" role="status" aria-live="polite" className={statusClass}>
            {statusText}
          </p>
        </div>

        <div className="rec-controls">
          <label htmlFor="title" className="sr-only">
            Title
          </label>
          <input
            type="text"
            id="title"
            className="title-input"
            placeholder="Meeting title…"
            autoComplete="off"
            value={title}
            onChange={(e) => onTitleChange(e.target.value)}
          />
          <button
            type="button"
            id="toggle"
            className={recording ? "stop" : "primary"}
            disabled={busy || offline}
            onClick={onToggleRecording}
          >
            {recording ? "Stop recording" : "Start recording"}
          </button>
          <LevelMeters levels={recording ? levels : null} />
        </div>

        <div className="dock-drawers">
          <SettingsDrawer
            mode={mode}
            onModeChange={onModeChange}
            language={language}
            onLanguageChange={onLanguageChange}
            model={model}
            onModelChange={onModelChange}
            models={models}
          />
          <ImportDrawer
            title={title}
            language={language}
            model={model}
            onImported={onImported}
          />
        </div>
      </div>
      {offline && (
        <div className="offline-banner" role="alert">
          Can't reach the recorder. Check that Transcribe is running; this page
          reconnects by itself.
        </div>
      )}
      <div id="rec-error" className="err" role="alert">
        {recError}
      </div>
    </header>
  );
}
