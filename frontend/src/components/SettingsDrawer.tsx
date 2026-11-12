import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { SourcesMap, SpeechModelInfo, TrackSourceConfig } from "../types";
import {
  defaultModelName,
  formatModelOption,
  LANG_LABEL,
} from "../utils";

interface SettingsDrawerProps {
  language: string;
  onLanguageChange: (language: string) => void;
  model: string;
  onModelChange: (model: string) => void;
  models: SpeechModelInfo[];
}

function buildSourceOptions(cfg?: TrackSourceConfig): [string, string][] {
  if (!cfg) return [["", "Windows default"]];
  const fallback = cfg.devices.find((d) => d.default);
  const options: [string, string][] = [
    ["", "Windows default" + (fallback ? ` (${fallback.name})` : "")],
    ...cfg.devices.map((d): [string, string] => [d.id, d.name]),
  ];
  if (cfg.chosen && !cfg.devices.some((d) => d.id === cfg.chosen?.id)) {
    options.push([cfg.chosen.id, `${cfg.chosen.name} (not connected)`]);
  }
  return options;
}

export function SettingsDrawer({
  language,
  onLanguageChange,
  model,
  onModelChange,
  models,
}: SettingsDrawerProps) {
  const detailsRef = useRef<HTMLDetailsElement>(null);
  const [sources, setSources] = useState<SourcesMap>({});
  const [sourceError, setSourceError] = useState("");

  const loadSources = useCallback(async () => {
    try {
      const res = await api<{ sources: SourcesMap }>("GET", "/api/sources");
      setSources(res.sources);
      setSourceError("");
    } catch (e) {
      setSourceError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    loadSources();
  }, [loadSources]);

  const handleChooseSource = async (track: "mic" | "system", device: string) => {
    try {
      const res = await api<{ sources: SourcesMap }>("POST", "/api/sources", {
        track,
        device: device || null,
      });
      setSources(res.sources);
      setSourceError("");
    } catch (e) {
      setSourceError(e instanceof Error ? e.message : String(e));
      loadSources();
    }
  };

  const summaryLang = LANG_LABEL[language] || language;
  const summaryModel = model || defaultModelName(models) || "model";
  const summaryText = `${summaryLang} · ${summaryModel}`;

  const micOptions = buildSourceOptions(sources.mic);
  const sysOptions = buildSourceOptions(sources.system);
  const micVal = sources.mic?.chosen?.id || "";
  const sysVal = sources.system?.chosen?.id || "";

  return (
    <details
      ref={detailsRef}
      className="popover"
      id="settings-drawer"
      onToggle={() => {
        if (detailsRef.current?.open) {
          loadSources();
        }
      }}
    >
      <summary
        id="settings-summary"
        title="Language, speech model, and audio devices"
      >
        <span className="summary-label">Settings</span>
        <span>{summaryText}</span>
      </summary>
      <div className="popover-body">
        <label htmlFor="language">Language</label>
        <select
          id="language"
          value={language}
          onChange={(e) => onLanguageChange(e.target.value)}
        >
          <option value="auto">Auto</option>
          <option value="th">ไทย</option>
          <option value="en">English</option>
        </select>

        <label htmlFor="model">Speech model</label>
        <select
          id="model"
          value={model}
          onChange={(e) => onModelChange(e.target.value)}
        >
          {models.map((m) => (
            <option key={m.name} value={m.name}>
              {formatModelOption(m)}
            </option>
          ))}
        </select>

        <label htmlFor="source-mic">Microphone</label>
        <select
          id="source-mic"
          value={micVal}
          onChange={(e) => handleChooseSource("mic", e.target.value)}
        >
          {micOptions.map(([val, text]) => (
            <option key={val} value={val}>
              {text}
            </option>
          ))}
        </select>

        <label htmlFor="source-system">System audio from (online calls)</label>
        <select
          id="source-system"
          value={sysVal}
          onChange={(e) => handleChooseSource("system", e.target.value)}
        >
          {sysOptions.map(([val, text]) => (
            <option key={val} value={val}>
              {text}
            </option>
          ))}
        </select>

        <div id="source-error" className="err" role="alert">
          {sourceError}
        </div>
      </div>
    </details>
  );
}
