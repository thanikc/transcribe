import { useEffect, useRef, useState } from "react";
import { uploadAudioFile } from "../api";
import { LANG_LABEL } from "../utils";

export interface DroppedFile {
  file: File | null;
  /** Set when the dropped file was not audio or video. */
  error: string;
  nonce: number;
}

interface ImportDrawerProps {
  language: string;
  model: string;
  dropped: DroppedFile | null;
  onImported: (meetingId: string) => Promise<void> | void;
}

export function ImportDrawer({
  language,
  model,
  dropped,
  onImported,
}: ImportDrawerProps) {
  const detailsRef = useRef<HTMLDetailsElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [importing, setImporting] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!dropped || importing) return;
    if (detailsRef.current) detailsRef.current.open = true;
    setError(dropped.error);
    if (dropped.file) {
      setFile(dropped.file);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
    // only a new drop should do this, not a change of `importing`
  }, [dropped]);

  const handleImport = async () => {
    if (!file || importing) return;
    setImporting(true);
    setProgress(0);
    setError("");
    try {
      const data = await uploadAudioFile(
        file,
        { title: title.trim() || baseName(file.name), language, model },
        setProgress,
      );
      if (fileInputRef.current) fileInputRef.current.value = "";
      setFile(null);
      setTitle("");
      if (detailsRef.current) detailsRef.current.open = false;
      await onImported(data.meeting.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setImporting(false);
    }
  };

  return (
    <details
      ref={detailsRef}
      className="popover"
      id="import-drawer"
      data-busy={importing || undefined}
    >
      <summary
        title="Import an existing audio or video file"
        onClick={(e) => {
          // the upload's progress stays in view until it is done
          if (importing) e.preventDefault();
        }}
      >
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
              disabled={importing}
              onChange={(e) => {
                setFile(e.target.files?.[0] || null);
                setError("");
              }}
            />
          </div>
        </div>
        {file && (
          <p className="muted import-file-name">{`Chosen: ${file.name}`}</p>
        )}
        <label htmlFor="import-title">Title</label>
        <div className="row">
          <div>
            <input
              type="text"
              id="import-title"
              autoComplete="off"
              placeholder={file ? baseName(file.name) : "The file's name"}
              value={title}
              disabled={importing}
              onChange={(e) => setTitle(e.target.value)}
            />
          </div>
          <button
            type="button"
            id="import"
            disabled={!file || importing}
            onClick={handleImport}
          >
            {importing ? "Importing…" : "Import"}
          </button>
        </div>
        {importing && (
          <div className="import-progress" role="status">
            <progress
              max={1}
              value={progress < 1 ? progress : undefined}
              aria-label="Import progress"
            />
            <span>
              {progress < 1
                ? `Uploading ${Math.round(progress * 100)}%`
                : "Converting…"}
            </span>
          </div>
        )}
        <p
          className="muted"
          style={{ margin: "8px 0 0", fontSize: "var(--text-xs)" }}
        >
          {`Transcribed as ${LANG_LABEL[language] || language} · ${model || "the default model"}. Change these in Settings. You can also drop a file anywhere on the page.`}
        </p>
        <div id="import-error" className="err" role="alert">
          {error}
        </div>
      </div>
    </details>
  );
}

const baseName = (name: string) => name.replace(/\.[^.]+$/, "");
