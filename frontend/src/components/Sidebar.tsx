import type { Meeting } from "../types";
import { MeetingsList } from "./MeetingsList";
import { SearchPanel } from "./SearchPanel";
import { VersionFooter } from "./VersionFooter";

interface SidebarProps {
  meetings: Meeting[];
  currentId: string | null;
  recording: boolean;
  versionRefreshTick: number;
  onSelectMeeting: (meetingId: string, start?: number) => void;
}

export function Sidebar({
  meetings,
  currentId,
  recording,
  versionRefreshTick,
  onSelectMeeting,
}: SidebarProps) {
  return (
    <aside className="sidebar">
      <SearchPanel onSelectMeeting={onSelectMeeting} />
      <MeetingsList
        meetings={meetings}
        currentId={currentId}
        onSelectMeeting={onSelectMeeting}
      />
      <VersionFooter recording={recording} refreshTick={versionRefreshTick} />
    </aside>
  );
}
