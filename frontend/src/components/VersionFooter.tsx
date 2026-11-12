import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { VersionState } from "../types";

const RELEASES = "https://github.com/thanikc/transcribe/releases/latest";

interface VersionFooterProps {
  recording: boolean;
  refreshTick: number;
}

export function VersionFooter({ recording, refreshTick }: VersionFooterProps) {
  const [versionState, setVersionState] = useState<VersionState | null>(null);
  const [installing, setInstalling] = useState(false);
  const [installedMsg, setInstalledMsg] = useState("");
  const [updateError, setUpdateError] = useState("");
  const waitedRef = useRef(false);

  const loadVersion = useCallback(async () => {
    if (installing) return;
    try {
      const v = await api<VersionState>("GET", "/api/version");
      setVersionState(v);
      if (!v.checked && !v.error && v.version !== "dev" && !waitedRef.current) {
        waitedRef.current = true;
        setTimeout(() => {
          loadVersion();
        }, 10000);
      }
    } catch {
      /* ignore */
    }
  }, [installing]);

  useEffect(() => {
    loadVersion();
  }, [loadVersion, refreshTick]);

  const handleInstall = async (targetVersion: string) => {
    setInstalling(true);
    setUpdateError("");
    try {
      await api("POST", "/api/update/install");
      setInstalledMsg(
        `The installer for ${targetVersion} is opening. Transcribe closes while it updates.`,
      );
    } catch (e) {
      setInstalling(false);
      setUpdateError(e instanceof Error ? e.message : String(e));
      loadVersion();
    }
  };

  return (
    <footer>
      <p id="version" aria-live="polite" style={{ margin: 0 }}>
        {installedMsg ? (
          installedMsg
        ) : versionState ? (
          <>
            {`Transcribe ${versionState.version}`}
            {versionState.update && versionState.can_install ? (
              <>
                {" · "}
                <button
                  type="button"
                  id="update"
                  className="primary"
                  disabled={recording || installing}
                  title={recording ? "Stop the recording to update" : ""}
                  onClick={() =>
                    versionState.update && handleInstall(versionState.update)
                  }
                >
                  {installing
                    ? `Downloading ${versionState.update}…`
                    : `Update to ${versionState.update}`}
                </button>
              </>
            ) : versionState.update ? (
              <>
                {" · "}
                <a href={RELEASES} target="_blank" rel="noopener">
                  {`${versionState.update} is available`}
                </a>
              </>
            ) : versionState.error ? (
              ` · ${versionState.error[0].toUpperCase()}${versionState.error.slice(1)}`
            ) : versionState.checked ? (
              " · Up to date"
            ) : null}
          </>
        ) : null}
      </p>
      <div id="update-error" className="err" role="alert">
        {updateError}
      </div>
    </footer>
  );
}
