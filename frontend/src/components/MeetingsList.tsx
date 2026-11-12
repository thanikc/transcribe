import type { Meeting } from "../types";
import { groupByDay, mmss } from "../utils";
import { StatusBadge } from "./StatusBadge";

interface MeetingsListProps {
  meetings: Meeting[];
  currentId: string | null;
  onSelectMeeting: (meetingId: string) => void;
}

const timeOf = (d: Date) =>
  d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });

const dateOf = (d: Date) =>
  d.toLocaleDateString(undefined, { day: "numeric", month: "short" });

export function MeetingsList({
  meetings,
  currentId,
  onSelectMeeting,
}: MeetingsListProps) {
  const groups = groupByDay(meetings, new Date());
  return (
    <section className="sidebar-list-section" aria-labelledby="list-h">
      <h2 id="list-h">Meetings</h2>
      <div id="meetings">
        {groups.map((g) => {
          const recent = g.label === "Today" || g.label === "Yesterday";
          return (
            <section key={g.label} className="list-group" aria-label={g.label}>
              <h3>{g.label}</h3>
              <ul className="list">
                {g.meetings.map((m) => {
                  const started = new Date(m.started_at);
                  const when = recent
                    ? timeOf(started)
                    : `${dateOf(started)} ${timeOf(started)}`;
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
                          {m.status !== "transcribed" && (
                            <StatusBadge status={m.status} progress={m.progress} />
                          )}
                        </div>
                        <div className="m">{`${when} · ${mmss(m.duration)}`}</div>
                      </button>
                    </li>
                  );
                })}
              </ul>
            </section>
          );
        })}
      </div>
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
