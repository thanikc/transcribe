import type { Meeting } from "../types";
import { fileSize, mmss } from "../utils";
import { StatusBadge } from "./StatusBadge";

interface MeetingsListProps {
  meetings: Meeting[];
  currentId: string | null;
  onSelectMeeting: (meetingId: string) => void;
}

export function MeetingsList({
  meetings,
  currentId,
  onSelectMeeting,
}: MeetingsListProps) {
  return (
    <section className="sidebar-list-section" aria-labelledby="list-h">
      <h2 id="list-h">Past meetings</h2>
      <ul className="list" id="meetings">
        {meetings.map((m) => {
          const when = new Date(m.started_at).toLocaleString();
          return (
            <li key={m.id}>
              <button
                type="button"
                className="item"
                data-id={m.id}
                aria-current={m.id === currentId ? "true" : undefined}
                onClick={() => onSelectMeeting(m.id)}
              >
                <div className="t">
                  <span>{m.title || m.id}</span>
                  <StatusBadge status={m.status} progress={m.progress} />
                </div>
                <div className="m">
                  {`${when} · ${mmss(m.duration)} · ${fileSize(m.audio_bytes)}`}
                </div>
              </button>
            </li>
          );
        })}
      </ul>
      <p
        className="muted"
        id="no-meetings"
        style={{ fontSize: "var(--text-xs)", margin: "var(--sp-2) 0 0" }}
        hidden={meetings.length > 0}
      >
        No meetings yet.
      </p>
    </section>
  );
}
