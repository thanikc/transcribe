import { useEffect, useRef, useState, type FocusEvent } from "react";

interface InlineEditProps {
  label: string;
  initial: string;
  placeholder?: string;
  /** Throws to keep the editor open with the error shown. */
  onSave: (value: string) => Promise<void>;
  onClose: () => void;
  /** What leaving the editor does: save (title) or cancel (popover). */
  onLeave: "save" | "cancel";
  showSave?: boolean;
  resetLabel?: string;
  className?: string;
}

/** A text field that saves on Enter and cancels on Escape. */
export function InlineEdit({
  label,
  initial,
  placeholder,
  onSave,
  onClose,
  onLeave,
  showSave = false,
  resetLabel,
  className,
}: InlineEditProps) {
  const [value, setValue] = useState(initial);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const busyRef = useRef(false);
  const doneRef = useRef(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
    inputRef.current?.select();
  }, []);

  const close = () => {
    doneRef.current = true;
    onClose();
  };

  const save = async (next: string) => {
    if (busyRef.current || doneRef.current) return;
    if (next === initial) {
      close();
      return;
    }
    busyRef.current = true;
    setSaving(true);
    setError("");
    try {
      await onSave(next);
      close();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      inputRef.current?.focus();
    } finally {
      busyRef.current = false;
      setSaving(false);
    }
  };

  const handleBlur = (e: FocusEvent<HTMLFormElement>) => {
    if (e.currentTarget.contains(e.relatedTarget as Node | null)) return;
    if (onLeave === "save") save(value);
    else if (!busyRef.current) close();
  };

  return (
    <form
      className={["inline-edit", className].filter(Boolean).join(" ")}
      onSubmit={(e) => {
        e.preventDefault();
        save(value);
      }}
      onBlur={handleBlur}
    >
      <input
        ref={inputRef}
        type="text"
        aria-label={label}
        placeholder={placeholder}
        value={value}
        readOnly={saving}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Escape") {
            e.preventDefault();
            close();
          }
        }}
      />
      {(showSave || resetLabel) && (
        <div className="inline-edit-actions">
          {showSave && (
            <button type="submit" className="primary" disabled={saving}>
              Save
            </button>
          )}
          {resetLabel && (
            <button type="button" disabled={saving} onClick={() => save("")}>
              {resetLabel}
            </button>
          )}
        </div>
      )}
      <div className="err" role="alert">
        {error}
      </div>
    </form>
  );
}

export function PencilIcon() {
  return (
    <svg
      className="pencil"
      viewBox="0 0 24 24"
      width="14"
      height="14"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M12 20h9" />
      <path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z" />
    </svg>
  );
}
