import type { MeetingStatus, TranscriptionProgress } from "../types";
import { percent, STATUS_LABEL } from "../utils";

interface StatusBadgeProps {
  status: MeetingStatus | string;
  progress?: TranscriptionProgress | null;
}

export function StatusBadge({ status, progress }: StatusBadgeProps) {
  return (
    <span className={`badge ${status}`}>
      {(STATUS_LABEL[status] || status) + percent(progress)}
    </span>
  );
}
