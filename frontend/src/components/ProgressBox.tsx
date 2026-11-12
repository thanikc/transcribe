import { useEffect, useState } from "react";
import type { TranscriptionProgress } from "../types";
import { mmss, percent } from "../utils";

interface ProgressBoxProps {
  progress: TranscriptionProgress | null;
  detailAt: number;
}

export function ProgressBox({ progress, detailAt }: ProgressBoxProps) {
  const [, setTick] = useState(0);

  useEffect(() => {
    if (!progress) return;
    const id = setInterval(() => {
      if (!document.hidden) setTick((t) => t + 1);
    }, 500);
    return () => clearInterval(id);
  }, [progress]);

  if (!progress) {
    return (
      <div className="progress">
        <p role="status">
          Waiting to start. Meetings are transcribed one at a time.
        </p>
      </div>
    );
  }

  const elapsedSec =
    progress.elapsed + Math.max(0, (performance.now() - detailAt) / 1000);
  const t = mmss(elapsedSec);
  const stepTimeText =
    progress.fraction == null
      ? `${t} · preparing (the first use of a model downloads it, which can take several minutes)`
      : t;

  return (
    <div className="progress">
      <p>
        <strong role="status">{progress.step}</strong>
        <span className="muted">
          {` · step ${progress.step_number} of ${progress.steps}`}
          {progress.fraction != null ? ` ·${percent(progress)}` : ""}
        </span>
      </p>
      {progress.fraction != null ? (
        <progress
          max={1}
          value={progress.fraction}
          aria-label={progress.step}
        />
      ) : (
        <progress max={1} aria-label={progress.step} />
      )}
      <p className="muted" id="step-time">
        {stepTimeText}
      </p>
    </div>
  );
}
