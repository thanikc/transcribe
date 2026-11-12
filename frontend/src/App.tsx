import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";
import { MeetingView } from "./components/MeetingView";
import { Sidebar } from "./components/Sidebar";
import { TopDock } from "./components/TopDock";
import type {
  Meeting,
  MeetingDetail,
  RecorderStatus,
  SpeechModelInfo,
} from "./types";
import {
  defaultModelName,
  openMeetingHash,
  parseMeetingIdFromHash,
} from "./utils";

const MODEL_KEY = "transcribe.model";
const MODE_KEY = "transcribe.mode";

function savedMode(): string {
  try {
    const v = localStorage.getItem(MODE_KEY);
    return v === "mic" || v === "mic+system" ? v : "mic";
  } catch {
    return "mic";
  }
}
const OFFLINE_AFTER = 3;

export const inProgress = (d: MeetingDetail | null): boolean =>
  !!d &&
  (d.meeting.status === "transcribing" || d.meeting.status === "recording");

export function App() {
  // Recording state
  const [recording, setRecording] = useState(false);
  const [recTitle, setRecTitle] = useState("");
  const [elapsed, setElapsed] = useState(0);
  const [elapsedAt, setElapsedAt] = useState(0);
  const [levels, setLevels] = useState<Record<string, number> | null>(null);
  const [busy, setBusy] = useState(false);
  const [recError, setRecError] = useState("");
  const recordingRef = useRef(false);
  const busyRef = useRef(false);
  const [offline, setOffline] = useState(false);
  const failedPollsRef = useRef(0);

  // Recording settings
  const [title, setTitleState] = useState("");
  const titleRef = useRef("");
  const setTitle = useCallback((t: string) => {
    titleRef.current = t;
    setTitleState(t);
  }, []);
  // the recording's title as the service has it, and its meeting id
  const liveTitleRef = useRef("");
  const recIdRef = useRef<string | null>(null);
  const renamingRef = useRef(false);
  const [mode, setMode] = useState(savedMode);
  const [recMode, setRecMode] = useState("");
  const [language, setLanguage] = useState("auto");
  const [models, setModels] = useState<SpeechModelInfo[]>([]);
  const [model, setModel] = useState("");

  // Meetings & selected meeting detail
  const [meetings, setMeetings] = useState<Meeting[]>([]);
  const meetingsRef = useRef<Meeting[]>([]);
  const [currentId, setCurrentId] = useState<string | null>(() =>
    parseMeetingIdFromHash(window.location.hash),
  );
  const currentIdRef = useRef<string | null>(currentId);
  const [detail, setDetail] = useState<MeetingDetail | null>(null);
  const detailRef = useRef<MeetingDetail | null>(null);
  const [detailAt, setDetailAt] = useState(0);
  const [viewError, setViewError] = useState("");
  const viewTokenRef = useRef(0);
  const viewTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Version refresh trigger
  const [versionRefreshTick, setVersionRefreshTick] = useState(0);

  const loadMeetings = useCallback(async () => {
    try {
      const data = await api<{ meetings: Meeting[] }>("GET", "/api/meetings");
      const sorted = data.meetings
        .slice()
        .sort((a, b) => (a.started_at < b.started_at ? 1 : -1));
      meetingsRef.current = sorted;
      setMeetings(sorted);
    } catch {
      /* ignore */
    }
  }, []);

  const loadModels = useCallback(async () => {
    try {
      const data = await api<{ models: SpeechModelInfo[] }>(
        "GET",
        "/api/models",
      );
      setModels(data.models);
      let saved = "";
      try {
        saved = localStorage.getItem(MODEL_KEY) || "";
      } catch {
        /* private window */
      }
      const chosen = data.models.some((m) => m.name === saved)
        ? saved
        : defaultModelName(data.models);
      setModel(chosen);
    } catch {
      /* ignore */
    }
  }, []);

  const pollStatus = useCallback(async () => {
    try {
      const st = await api<RecorderStatus>("GET", "/api/status");
      const wasRec = recordingRef.current;
      const nowRec = !!st.recording;
      recordingRef.current = nowRec;
      setRecording(nowRec);
      if (nowRec) {
        recIdRef.current = st.meeting_id || null;
        liveTitleRef.current = st.title || "";
        // don't overwrite what is being typed
        if (!renamingRef.current && document.activeElement?.id !== "title") {
          setTitle(st.title || "");
        }
        setRecTitle(st.title || st.meeting_id || "");
        setRecMode(st.mode || "");
        setElapsed(st.elapsed || 0);
        setElapsedAt(performance.now());
        setLevels(st.levels || null);
      } else {
        setLevels(null);
        if (wasRec) setTitle("");
      }
      if (wasRec !== nowRec) {
        loadMeetings();
      }
      if (failedPollsRef.current >= OFFLINE_AFTER) {
        loadMeetings();
        loadModels();
      }
      failedPollsRef.current = 0;
      setOffline(false);
    } catch {
      // one miss is transient; several in a row mean the service is gone
      failedPollsRef.current++;
      if (failedPollsRef.current >= OFFLINE_AFTER) setOffline(true);
    }
  }, [loadMeetings, loadModels, setTitle]);

  const handleModeChange = (nextMode: string) => {
    setMode(nextMode);
    try {
      localStorage.setItem(MODE_KEY, nextMode);
    } catch {
      /* private window */
    }
  };

  const handleModelChange = (nextModel: string) => {
    setModel(nextModel);
    try {
      localStorage.setItem(MODEL_KEY, nextModel);
    } catch {
      /* private window */
    }
  };

  const showMeeting = useCallback(
    async (id: string) => {
      if (viewTimerRef.current) clearTimeout(viewTimerRef.current);
      const token = ++viewTokenRef.current;
      if (currentIdRef.current !== id) {
        detailRef.current = null;
        setDetail(null);
      }
      currentIdRef.current = id;
      setCurrentId(id);
      setViewError("");

      const applyDetail = (d: MeetingDetail, tok: number) => {
        detailRef.current = d;
        setDetail(d);
        setDetailAt(performance.now());
        setViewError("");
        if (inProgress(d)) {
          viewTimerRef.current = setTimeout(
            () => refreshDetail(d.meeting.id, tok),
            2000,
          );
        }
        const listed = meetingsRef.current.find((m) => m.id === d.meeting.id);
        if (listed && listed.status === d.meeting.status) {
          const updatedList = meetingsRef.current.map((m) =>
            m.id === d.meeting.id ? { ...m, progress: d.meeting.progress } : m,
          );
          meetingsRef.current = updatedList;
          setMeetings(updatedList);
        } else {
          loadMeetings();
        }
      };

      const refreshDetail = async (meetingId: string, tok: number) => {
        if (tok !== viewTokenRef.current || document.hidden) return;
        try {
          const d = await api<MeetingDetail>(
            "GET",
            "/api/meetings/" + encodeURIComponent(meetingId),
          );
          if (tok === viewTokenRef.current) applyDetail(d, tok);
        } catch {
          if (tok === viewTokenRef.current) {
            viewTimerRef.current = setTimeout(
              () => refreshDetail(meetingId, tok),
              2000,
            );
          }
        }
      };

      try {
        const d = await api<MeetingDetail>(
          "GET",
          "/api/meetings/" + encodeURIComponent(id),
        );
        if (token !== viewTokenRef.current) return;
        applyDetail(d, token);
      } catch (e) {
        if (token !== viewTokenRef.current) return;
        setViewError(e instanceof Error ? e.message : String(e));
      }
    },
    [loadMeetings],
  );

  const routeFromHash = useCallback(() => {
    const id = parseMeetingIdFromHash(window.location.hash);
    if (id) {
      showMeeting(id);
    } else {
      if (viewTimerRef.current) clearTimeout(viewTimerRef.current);
      viewTokenRef.current++;
      currentIdRef.current = null;
      detailRef.current = null;
      setCurrentId(null);
      setDetail(null);
      setViewError("");
    }
  }, [showMeeting]);

  useEffect(() => {
    pollStatus();
    loadMeetings();
    loadModels();
    routeFromHash();

    window.addEventListener("hashchange", routeFromHash);
    return () => {
      window.removeEventListener("hashchange", routeFromHash);
      if (viewTimerRef.current) clearTimeout(viewTimerRef.current);
    };
  }, [pollStatus, loadMeetings, loadModels, routeFromHash]);

  useEffect(() => {
    const onVisibilityChange = () => {
      if (document.hidden) return;
      pollStatus();
      loadMeetings();
      setVersionRefreshTick((t) => t + 1);
      if (currentIdRef.current && inProgress(detailRef.current)) {
        showMeeting(currentIdRef.current);
      }
    };
    document.addEventListener("visibilitychange", onVisibilityChange);
    return () =>
      document.removeEventListener("visibilitychange", onVisibilityChange);
  }, [pollStatus, loadMeetings, showMeeting]);

  useEffect(() => {
    const statusInterval = setInterval(() => {
      if (!document.hidden) pollStatus();
    }, 1000);
    const listInterval = setInterval(() => {
      if (document.hidden) return;
      if (
        meetingsRef.current.some(
          (m) => m.status === "recording" || m.status === "transcribing",
        )
      ) {
        loadMeetings();
      }
    }, 2000);
    return () => {
      clearInterval(statusInterval);
      clearInterval(listInterval);
    };
  }, [pollStatus, loadMeetings]);

  const handleToggleRecording = async () => {
    if (busyRef.current) return;
    busyRef.current = true;
    setBusy(true);
    setRecError("");
    try {
      if (recordingRef.current) {
        const r = await api<{ meeting: Meeting }>(
          "POST",
          "/api/recordings/stop",
          {},
        );
        recordingRef.current = false;
        setRecording(false);
        setLevels(null);
        setTitle("");
        await loadMeetings();
        openMeetingHash(r.meeting.id);
      } else {
        const r = await api<{ meeting: Meeting }>(
          "POST",
          "/api/recordings/start",
          {
            title,
            mode,
            language,
            model: model || null,
          },
        );
        recordingRef.current = true;
        setRecording(true);
        setRecTitle(r.meeting.title || r.meeting.id);
        setTitle(r.meeting.title || "");
        liveTitleRef.current = r.meeting.title || "";
        recIdRef.current = r.meeting.id;
        setRecMode(r.meeting.mode);
        setElapsed(0);
        setElapsedAt(performance.now());
        loadMeetings();
      }
    } catch (e) {
      setRecError(e instanceof Error ? e.message : String(e));
    } finally {
      busyRef.current = false;
      setBusy(false);
      pollStatus();
    }
  };

  const handleCommitLiveTitle = async () => {
    const id = recIdRef.current;
    const next = titleRef.current.trim();
    if (!recordingRef.current || !id || renamingRef.current) return;
    if (next === liveTitleRef.current) return;
    renamingRef.current = true;
    setRecError("");
    try {
      const r = await api<MeetingDetail>(
        "POST",
        `/api/meetings/${encodeURIComponent(id)}/title`,
        { title: next },
      );
      liveTitleRef.current = r.meeting.title || "";
      setTitle(r.meeting.title || "");
      setRecTitle(r.meeting.title || r.meeting.id);
      loadMeetings();
      if (currentIdRef.current === id) showMeeting(id);
    } catch (e) {
      setRecError(e instanceof Error ? e.message : String(e));
    } finally {
      renamingRef.current = false;
    }
  };

  const handleImported = async (meetingId: string) => {
    await loadMeetings();
    openMeetingHash(meetingId);
  };

  return (
    <div className="app-shell">
      <TopDock
        recording={recording}
        busy={busy}
        offline={offline}
        recTitle={recTitle}
        elapsed={elapsed}
        elapsedAt={elapsedAt}
        levels={levels}
        recError={recError}
        title={title}
        onTitleChange={setTitle}
        onCommitTitle={handleCommitLiveTitle}
        onRevertTitle={() => setTitle(liveTitleRef.current)}
        mode={recording && recMode ? recMode : mode}
        onModeChange={handleModeChange}
        language={language}
        onLanguageChange={setLanguage}
        model={model}
        onModelChange={handleModelChange}
        models={models}
        onToggleRecording={handleToggleRecording}
        onImported={handleImported}
      />

      <main>
        <Sidebar
          meetings={meetings}
          currentId={currentId}
          recording={recording}
          versionRefreshTick={versionRefreshTick}
          onSelectMeeting={openMeetingHash}
        />

        <MeetingView
          currentId={currentId}
          hasMeetings={meetings.length > 0}
          detail={detail}
          detailAt={detailAt}
          error={viewError}
          models={models}
          onDetailUpdated={(updated) => {
            detailRef.current = updated;
            setDetail(updated);
          }}
          onRefreshMeeting={() => {
            if (currentIdRef.current) return showMeeting(currentIdRef.current);
          }}
          onMeetingsChanged={loadMeetings}
          onClearSelection={() => {
            window.location.hash = "";
          }}
        />
      </main>
    </div>
  );
}
