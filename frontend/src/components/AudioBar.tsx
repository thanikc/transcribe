import {
  useCallback,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
  type Ref,
} from "react";
import { mmss, TRACK_LABEL } from "../utils";

const SINK_KEY = "transcribe.audioOutput";
const RATE_KEY = "transcribe.playbackRate";
const RATES = [1, 1.25, 1.5, 2];
const SKIP_SECONDS = 10;
const KEY_SEEK_SECONDS = 5;
// a follower further than this from the first track is re-seeked
const DRIFT_SECONDS = 0.2;

function savedRate(): number {
  try {
    const r = Number(localStorage.getItem(RATE_KEY));
    return RATES.includes(r) ? r : 1;
  } catch {
    return 1;
  }
}

/** Sets the position, waiting for metadata if the element has none yet. */
function seekElement(a: HTMLAudioElement, t: number): void {
  if (a.readyState === 0) {
    a.addEventListener(
      "loadedmetadata",
      () => {
        a.currentTime = t;
      },
      { once: true },
    );
  } else {
    a.currentTime = t;
  }
}

const isTyping = (el: Element | null): boolean =>
  !!el &&
  (["INPUT", "SELECT", "BUTTON", "TEXTAREA"].includes(el.tagName) ||
    (el as HTMLElement).isContentEditable);

export interface AudioBarHandle {
  playFrom: (seconds: number) => void;
  toggle: () => void;
}

const canPickOutput = (): boolean =>
  typeof navigator !== "undefined" &&
  !!navigator.mediaDevices &&
  typeof HTMLMediaElement !== "undefined" &&
  "setSinkId" in HTMLMediaElement.prototype;

function savedSink(): string {
  try {
    return localStorage.getItem(SINK_KEY) || "";
  } catch {
    return "";
  }
}

function saveSink(v: string): void {
  try {
    localStorage.setItem(SINK_KEY, v);
  } catch {
    /* private window */
  }
}

type MediaElementWithSink = HTMLAudioElement & {
  setSinkId?: (sinkId: string) => Promise<void>;
};

interface AudioBarProps {
  ref?: Ref<AudioBarHandle>;
  meetingId: string;
  tracks: string[];
  /** The meeting's length, used until the audio's own is known. */
  duration: number | null;
  onTimeUpdate: (currentTime: number) => void;
}

/**
 * One player for all of a meeting's tracks: they play, pause, seek and change
 * speed together. The first track leads; the others follow it.
 */
export function AudioBar({
  ref,
  meetingId,
  tracks,
  duration: meetingDuration,
  onTimeUpdate,
}: AudioBarProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const audiosRef = useRef<Record<string, HTMLAudioElement | null>>({});
  const [playing, setPlaying] = useState(false);
  const [time, setTime] = useState(0);
  const [mediaDuration, setMediaDuration] = useState<number | null>(null);
  const [rate, setRate] = useState(savedRate);
  const [muted, setMuted] = useState<Record<string, boolean>>({});
  const duration = mediaDuration ?? meetingDuration ?? 0;

  const elements = useCallback(
    () =>
      tracks
        .map((t) => audiosRef.current[t])
        .filter((a): a is HTMLAudioElement => !!a),
    [tracks],
  );
  const leader = useCallback(() => audiosRef.current[tracks[0]] ?? null, [tracks]);

  const seek = useCallback(
    (t: number) => {
      const target = Math.max(0, duration ? Math.min(t, duration) : t);
      for (const a of elements()) {
        // a shorter track stays at its end rather than looping back
        const end = Number.isFinite(a.duration) ? a.duration : Infinity;
        seekElement(a, Math.min(target, end));
      }
      setTime(target);
      onTimeUpdate(target);
    },
    [duration, elements, onTimeUpdate],
  );

  const play = useCallback(() => {
    const lead = leader();
    const t = lead ? lead.currentTime : 0;
    for (const a of elements()) {
      if (a !== lead && Number.isFinite(a.duration) && t >= a.duration) continue;
      a.play().catch(() => {
        /* browser refused playback */
      });
    }
  }, [elements, leader]);

  const pause = useCallback(() => {
    for (const a of elements()) a.pause();
  }, [elements]);

  const toggle = useCallback(() => {
    const lead = leader();
    if (!lead) return;
    if (lead.paused) play();
    else pause();
  }, [leader, play, pause]);

  const playFrom = useCallback(
    (seconds: number) => {
      seek(seconds);
      play();
    },
    [seek, play],
  );

  useImperativeHandle(ref, () => ({ playFrom, toggle }), [playFrom, toggle]);

  useEffect(() => {
    for (const a of elements()) a.playbackRate = rate;
  }, [elements, rate]);

  useEffect(() => {
    for (const t of tracks) {
      const a = audiosRef.current[t];
      if (a) a.muted = !!muted[t];
    }
  }, [tracks, muted]);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.ctrlKey || e.metaKey || e.altKey || isTyping(document.activeElement)) return;
      const lead = leader();
      if (!lead) return;
      if (e.key === " ") {
        e.preventDefault();
        toggle();
      } else if (e.key === "ArrowLeft") {
        e.preventDefault();
        seek(lead.currentTime - KEY_SEEK_SECONDS);
      } else if (e.key === "ArrowRight") {
        e.preventDefault();
        seek(lead.currentTime + KEY_SEEK_SECONDS);
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [leader, toggle, seek]);

  const handleLeaderTime = () => {
    const lead = leader();
    if (!lead) return;
    const t = lead.currentTime;
    setTime(t);
    onTimeUpdate(t);
    if (lead.paused) return;
    for (const a of elements()) {
      if (a === lead || a.ended) continue;
      if (Number.isFinite(a.duration) && t >= a.duration) continue;
      if (Math.abs(a.currentTime - t) > DRIFT_SECONDS) a.currentTime = t;
    }
  };

  const handleRate = (r: number) => {
    setRate(r);
    try {
      localStorage.setItem(RATE_KEY, String(r));
    } catch {
      /* private window */
    }
  };
  const [sinkId, setSinkId] = useState<string>(() => savedSink());
  const [outputDevices, setOutputDevices] = useState<MediaDeviceInfo[]>([]);
  const [outputError, setOutputError] = useState("");
  const supportsSink = canPickOutput();

  const applySink = useCallback(
    (targetSink: string) => {
      if (!supportsSink || !containerRef.current) return;
      const players =
        containerRef.current.querySelectorAll<MediaElementWithSink>("audio");
      for (const a of players) {
        if (typeof a.setSinkId === "function") {
          a.setSinkId(targetSink).catch(() => {
            a.setSinkId?.("").catch(() => {});
          });
        }
      }
    },
    [supportsSink],
  );

  const loadOutputs = useCallback(async () => {
    if (!supportsSink || !navigator.mediaDevices?.enumerateDevices) return;
    try {
      const all = await navigator.mediaDevices.enumerateDevices();
      setOutputDevices(
        all.filter((d) => d.kind === "audiooutput" && d.deviceId),
      );
    } catch {
      setOutputDevices([]);
    }
  }, [supportsSink]);

  useEffect(() => {
    applySink(sinkId);
  }, [applySink, sinkId, tracks, meetingId]);

  useEffect(() => {
    if (!supportsSink) return;
    loadOutputs();
    const handler = () => loadOutputs();
    navigator.mediaDevices?.addEventListener?.("devicechange", handler);
    return () => {
      navigator.mediaDevices?.removeEventListener?.("devicechange", handler);
    };
  }, [supportsSink, loadOutputs]);

  const handleRequestDeviceNames = async () => {
    setOutputError("");
    try {
      const md = navigator.mediaDevices as MediaDevices & {
        selectAudioOutput?: () => Promise<{ deviceId: string }>;
      };
      if (md.selectAudioOutput) {
        const d = await md.selectAudioOutput();
        saveSink(d.deviceId);
        setSinkId(d.deviceId);
      } else {
        const s = await navigator.mediaDevices.getUserMedia({ audio: true });
        s.getTracks().forEach((tr) => tr.stop());
      }
    } catch (e) {
      setOutputError(
        "Could not list output devices: " +
          (e instanceof Error ? e.message : String(e)),
      );
    }
    loadOutputs();
  };

  const nonDefaultOutputs = outputDevices.filter(
    (d) => d.deviceId !== "default",
  );
  const hasSavedMissing =
    Boolean(sinkId) && !nonDefaultOutputs.some((d) => d.deviceId === sinkId);
  const allHaveLabels =
    outputDevices.length > 0 && outputDevices.every((d) => Boolean(d.label));

  const dataKey = `${meetingId}|${tracks.join(",")}`;

  return (
    <div ref={containerRef} className="tracks" id="tracks" data-key={dataKey}>
      {tracks.map((t, i) => (
        <audio
          key={t}
          id={`audio-${t}`}
          ref={(el) => {
            audiosRef.current[t] = el;
          }}
          preload="none"
          src={`/api/meetings/${encodeURIComponent(meetingId)}/audio/${encodeURIComponent(t)}`}
          {...(i === 0
            ? {
                onTimeUpdate: handleLeaderTime,
                onSeeked: handleLeaderTime,
                onPlay: () => setPlaying(true),
                onPause: () => setPlaying(false),
                onEnded: () => {
                  pause();
                  setPlaying(false);
                },
                onLoadedMetadata: (e) => {
                  const d = e.currentTarget.duration;
                  if (Number.isFinite(d) && d > 0) setMediaDuration(d);
                },
              }
            : {})}
        />
      ))}

      {tracks.length > 0 && (
        <div className="player" role="group" aria-label="Audio player">
          <button
            type="button"
            className="icon"
            aria-label={`Back ${SKIP_SECONDS} seconds`}
            title={`Back ${SKIP_SECONDS} s`}
            onClick={() => seek((leader()?.currentTime ?? time) - SKIP_SECONDS)}
          >
            −{SKIP_SECONDS}
          </button>
          <button
            type="button"
            className="icon play-toggle"
            aria-label={playing ? "Pause" : "Play"}
            title={playing ? "Pause (Space)" : "Play (Space)"}
            onClick={toggle}
          >
            {playing ? (
              <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true">
                <rect x="6" y="4" width="4" height="16" fill="currentColor" />
                <rect x="14" y="4" width="4" height="16" fill="currentColor" />
              </svg>
            ) : (
              <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true">
                <path d="M7 4v16l13-8Z" fill="currentColor" />
              </svg>
            )}
          </button>
          <button
            type="button"
            className="icon"
            aria-label={`Forward ${SKIP_SECONDS} seconds`}
            title={`Forward ${SKIP_SECONDS} s`}
            onClick={() => seek((leader()?.currentTime ?? time) + SKIP_SECONDS)}
          >
            +{SKIP_SECONDS}
          </button>
          <input
            type="range"
            className="seek"
            aria-label="Position"
            min={0}
            max={Math.max(duration, 0.01)}
            step={0.1}
            value={Math.min(time, duration || time)}
            onChange={(e) => seek(Number(e.target.value))}
          />
          <span className="time">{`${mmss(time)} / ${mmss(duration)}`}</span>
          <label className="sr-only" htmlFor="playback-rate">
            Speed
          </label>
          <select
            id="playback-rate"
            className="rate"
            title="Speed"
            value={rate}
            onChange={(e) => handleRate(Number(e.target.value))}
          >
            {RATES.map((r) => (
              <option key={r} value={r}>{`${r}×`}</option>
            ))}
          </select>
          {tracks.length > 1 && (
            <span className="mutes">
              {tracks.map((t) => (
                <button
                  key={t}
                  type="button"
                  className="filter-pill mute"
                  aria-pressed={!muted[t]}
                  title={muted[t] ? `Unmute ${TRACK_LABEL[t] || t}` : `Mute ${TRACK_LABEL[t] || t}`}
                  onClick={() => setMuted((m) => ({ ...m, [t]: !m[t] }))}
                >
                  {TRACK_LABEL[t] || t}
                </button>
              ))}
            </span>
          )}
        </div>
      )}

      {supportsSink && tracks.length > 0 && (
        <details className="popover output-popover">
          <summary title="Choose audio output device">Play through</summary>
          <div className="popover-body">
            <label htmlFor="audio-output">Play through</label>
            <div className="row">
              <div>
                <select
                  id="audio-output"
                  value={sinkId}
                  onChange={(e) => {
                    const val = e.target.value;
                    saveSink(val);
                    setSinkId(val);
                  }}
                >
                  <option value="">Windows default output</option>
                  {nonDefaultOutputs.map((d, i) => (
                    <option key={d.deviceId} value={d.deviceId}>
                      {d.label || `Output device ${i + 1}`}
                    </option>
                  ))}
                  {hasSavedMissing && (
                    <option value={sinkId}>Previously chosen device</option>
                  )}
                </select>
              </div>
              <button
                type="button"
                hidden={allHaveLabels}
                title="The browser only shows output device names after you allow it"
                onClick={handleRequestDeviceNames}
              >
                Show device names
              </button>
            </div>
            <div className="err" role="alert">
              {outputError}
            </div>
          </div>
        </details>
      )}
    </div>
  );
}
