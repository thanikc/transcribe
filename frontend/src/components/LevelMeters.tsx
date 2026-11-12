import { useEffect, useRef } from "react";
import { TRACK_LABEL } from "../utils";

const QUIET = 10 ** (-50 / 20);
const SILENT_AFTER_MS = 10000;

const fill = (level: number) =>
  Math.min(1, Math.max(0, (20 * Math.log10(level || 1e-6) + 60) / 60));

interface LevelMetersProps {
  levels: Record<string, number> | null;
}

export function LevelMeters({ levels }: LevelMetersProps) {
  const heardRef = useRef<Record<string, number>>({});

  useEffect(() => {
    if (!levels) {
      heardRef.current = {};
    }
  }, [levels]);

  if (!levels) {
    return <div id="meters" hidden />;
  }

  const now = performance.now();
  const entries = Object.entries(levels);
  for (const [track, level] of entries) {
    if (!(track in heardRef.current) || level > QUIET) {
      heardRef.current[track] = now;
    }
  }

  return (
    <div id="meters">
      {entries.map(([track, level]) => {
        const silent = now - (heardRef.current[track] ?? now) > SILENT_AFTER_MS;
        return (
          <span key={track} className="meter-item">
            <span>{TRACK_LABEL[track] || track}</span>
            <div className="bar" aria-hidden="true">
              <span style={{ width: `${Math.round(fill(level) * 100)}%` }} />
            </div>
            <span className={silent ? "quiet" : "muted"}>
              {silent ? "no sound" : ""}
            </span>
          </span>
        );
      })}
    </div>
  );
}
