import { useRef, useState } from "react";
import { uploadAudioFile } from "../api";

interface ImportDrawerProps {
  title: string;
  language: string;
  model: string;
  onImported: (meetingId: string) => Promise<void> | void;
}

export function ImportDrawer({
  title,
  language,
  model,
  onImported,
}: ImportDrawerProps) {
  const detailsRef = useRef<HTMLDetailsElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [hasFile, setHasFile] = useState(false);
  const [importing, setImporting] = useState(false);
  const [error, setError] = useState("");

  const handleImport = async () => {
    const file = fileInputRef.current?.files?.[0];
    if (!file || importing) return;
    setImporting(true);
    setError("");
    try {
      const effectiveTitle =
        title.trim() || file.name.replace(/\.[^.]+$/, "");
      const data = await uploadAudioFile(file, {
        title: effectiveTitle,
        language,
        model,
      });
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
      setHasFile(false);
      if (detailsRef.current) {
        detailsRef.current.open = false;
      }
      await onImported(data.meeting.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setImporting(false);
    }
  };

  return (
    <details ref={detailsRef} className="popover" id="import-drawer">
      <summary title="Import an existing audio or video file">
        Import audio
      </summary>
      <div className="popover-body">
        <label htmlFor="import-file">Import audio file</label>
        <div className="row" style={{ marginTop: 4 }}>
          <div>
            <input
              ref={fileInputRef}
              type="file"
              id="import-file"
              accept="audio/*,video/*"
              onChange={(e) => setHasFile(!!e.target.files?.length)}
            />
          </div>
          <button
            type="button"
            id="import"
            disabled={!hasFile || importing}
            onClick={handleImport}
          >
            {importing ? "Importing…" : "Import"}
          </button>
        </div>
        <p
          className="muted"
          style={{ margin: "8px 0 0", fontSize: "var(--text-xs)" }}
        >
          Uses the title, language and speech model selected. Without a title,
          the file name is used.
        </p>
        <div id="import-error" className="err" role="alert">
          {error}
        </div>
      </div>
    </details>
  );
}
