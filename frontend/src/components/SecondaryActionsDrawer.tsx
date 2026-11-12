import { useEffect, useState } from "react";
import { api } from "../api";
import type { Meeting, SpeechModelInfo } from "../types";
import { defaultModelName, formatModelOption } from "../utils";

interface SecondaryActionsDrawerProps {
  meeting: Meeting;
  models: SpeechModelInfo[];
  onRetranscribed: () => Promise<void> | void;
  onDeleted: () => Promise<void> | void;
}

export function SecondaryActionsDrawer({
  meeting,
  models,
  onRetranscribed,
  onDeleted,
}: SecondaryActionsDrawerProps) {
  const [language, setLanguage] = useState(meeting.language || "auto");
  const [model, setModel] = useState(
    meeting.model || defaultModelName(models),
  );
  const [submitting, setSubmitting] = useState(false);
  const [retranscribeError, setRetranscribeError] = useState("");
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState("");

  useEffect(() => {
    setLanguage(meeting.language || "auto");
    setModel(meeting.model || defaultModelName(models));
    setRetranscribeError("");
    setDeleteError("");
  }, [meeting.id, meeting.language, meeting.model, models]);

  const handleRetranscribe = async () => {
    setSubmitting(true);
    setRetranscribeError("");
    try {
      await api(
        "POST",
        `/api/meetings/${encodeURIComponent(meeting.id)}/transcribe`,
        {
          language,
          model: model || null,
        },
      );
      await onRetranscribed();
    } catch (e) {
      setRetranscribeError(e instanceof Error ? e.message : String(e));
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async () => {
    if (
      !window.confirm(
        `Delete "${meeting.title || meeting.id}"? Its audio and transcript are removed for good.`,
      )
    ) {
      return;
    }
    setDeleting(true);
    setDeleteError("");
    try {
      await api("DELETE", `/api/meetings/${encodeURIComponent(meeting.id)}`, {});
      await onDeleted();
    } catch (e) {
      setDeleteError(e instanceof Error ? e.message : String(e));
      setDeleting(false);
    }
  };

  return (
    <details
      className="secondary-drawer"
      open={meeting.status === "failed" ? true : undefined}
    >
      <summary>Re-transcribe &amp; meeting actions</summary>

      <div className="again">
        <h4>Transcribe again</h4>
        <div className="row">
          <div>
            <label htmlFor="again-language">Language</label>
            <select
              id="again-language"
              value={language}
              onChange={(e) => setLanguage(e.target.value)}
            >
              <option value="auto">Auto</option>
              <option value="th">ไทย</option>
              <option value="en">English</option>
            </select>
          </div>
          <div>
            <label htmlFor="again-model">Speech model</label>
            <select
              id="again-model"
              value={model}
              onChange={(e) => setModel(e.target.value)}
            >
              {models.map((m) => (
                <option key={m.name} value={m.name}>
                  {formatModelOption(m)}
                </option>
              ))}
            </select>
          </div>
          <div style={{ flex: "0 0 auto" }}>
            <button
              type="button"
              disabled={meeting.status === "transcribing" || submitting}
              onClick={handleRetranscribe}
            >
              Transcribe again
            </button>
          </div>
        </div>
        <div className="err" role="alert">
          {retranscribeError}
        </div>
      </div>

      {(meeting.status === "transcribed" || meeting.status === "failed") && (
        <div className="again">
          <button
            type="button"
            className="danger"
            disabled={deleting}
            onClick={handleDelete}
          >
            Delete meeting
          </button>
          <div className="err" role="alert">
            {deleteError}
          </div>
        </div>
      )}
    </details>
  );
}
