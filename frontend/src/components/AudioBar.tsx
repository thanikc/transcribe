import { useCallback, useEffect, useRef, useState } from "react";
import { TRACK_LABEL } from "../utils";

const SINK_KEY = "transcribe.audioOutput";

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
  meetingId: string;
  tracks: string[];
  onTimeUpdate: (track: string, currentTime: number) => void;
}

export function AudioBar({ meetingId, tracks, onTimeUpdate }: AudioBarProps) {
  const containerRef = useRef<HTMLDivElement>(null);
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
      {tracks.map((t) => {
        const lid = `audio-${t}`;
        return (
          <div key={t} className="track-player">
            <label htmlFor={lid}>{TRACK_LABEL[t] || t}</label>
            <audio
              id={lid}
              controls
              preload="none"
              src={`/api/meetings/${encodeURIComponent(meetingId)}/audio/${encodeURIComponent(t)}`}
              onTimeUpdate={(e) => onTimeUpdate(t, e.currentTarget.currentTime)}
            />
          </div>
        );
      })}

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
