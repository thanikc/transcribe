import { useRef, useState } from "react";
import { uploadAudioFile } from "../api";
import { LANG_LABEL } from "../utils";

interface ImportDrawerProps {
  language: string;
  model: string;
  onImported: (meetingId: string) => Promise<void> | void;
}

export function ImportDrawer({
  language,
  model,
  onImported,
}: ImportDrawerProps) {
  const detailsRef = useRef<HTMLDetailsElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [fileName, setFileName] = useState("");
  const [title, setTitle] = useState("");
  const [importing, setImporting] = useState(false);
  const [error, setError] = useState("");

  const handleImport = async () => {
    const file = fileInputRef.current?.files?.[0];
    if (!file || importing) return;
    setImporting(true);
    setError("");
    try {
      const effectiveTitle = title.trim() || baseName(file.name);
      const data = await uploadAudioFile(file, {
        title: effectiveTitle,
        language,
        model,
      });
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
      setFileName("");
      setTitle("");
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
              onChange={(e) => setFileName(e.target.files?.[0]?.name || "")}
            />
          </div>
        </div>
        <label htmlFor="import-title">Title</label>
        <div className="row">
          <div>
            <input
              type="text"
              id="import-title"
              autoComplete="off"
              placeholder={fileName ? baseName(fileName) : "The file's name"}
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
          </div>
          <button
            type="button"
            id="import"
            disabled={!fileName || importing}
            onClick={handleImport}
          >
            {importing ? "Importing…" : "Import"}
          </button>
        </div>
        <p
          className="muted"
          style={{ margin: "8px 0 0", fontSize: "var(--text-xs)" }}
        >
          {`Transcribed as ${LANG_LABEL[language] || language} · ${model || "the default model"}. Change these in Settings.`}
        </p>
        <div id="import-error" className="err" role="alert">
          {error}
        </div>
      </div>
    </details>
  );
}

const baseName = (name: string) => name.replace(/\.[^.]+$/, "");
