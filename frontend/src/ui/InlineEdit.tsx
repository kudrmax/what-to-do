import { useState } from "react";

interface InlineEditProps {
  value: string;
  label: string;
  onSave: (next: string) => void;
  className?: string;
  tip?: string;
  /** Shown instead of an empty value; an empty value can then be saved too. */
  placeholder?: string;
}

/** Text that turns into a field on click; Enter or leaving the field saves, Esc cancels. */
export function InlineEdit({ value, label, onSave, className = "", tip = "Rename", placeholder }: InlineEditProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  if (!editing) {
    const empty = !value && placeholder !== undefined;
    return (
      <button type="button" className={`inline-edit ${empty ? "inline-edit--empty" : ""} ${className}`} data-tip={tip} onClick={() => (setDraft(value), setEditing(true))}>
        {empty ? placeholder : value}
      </button>
    );
  }
  const save = () => {
    setEditing(false);
    const next = draft.trim();
    if (next !== value && (next || placeholder !== undefined)) onSave(next);
  };
  return (
    <input
      className="input inline-edit__input"
      aria-label={label}
      value={draft}
      placeholder={placeholder}
      autoFocus
      onFocus={(e) => e.target.select()}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={save}
      onKeyDown={(e) => {
        if (e.key === "Enter") save();
        if (e.key === "Escape") setEditing(false);
      }}
    />
  );
}
