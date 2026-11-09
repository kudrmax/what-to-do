import { useState } from "react";

/** A value shown as text; a click turns it into a field with the old value selected, Enter or leaving saves. */
export function InlineEdit({ value, label, onSave, className = "" }: { value: string; label: string; onSave: (next: string) => void; className?: string }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  if (!editing) {
    return (
      <button type="button" className={`inline-edit ${className}`} data-tip="Переименовать" onClick={() => (setDraft(value), setEditing(true))}>
        {value}
      </button>
    );
  }
  const save = () => {
    setEditing(false);
    if (draft.trim() && draft.trim() !== value) onSave(draft.trim());
  };
  return (
    <input
      className="input inline-edit__input"
      aria-label={label}
      value={draft}
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
