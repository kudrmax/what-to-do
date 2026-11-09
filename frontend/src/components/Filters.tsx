import { useEffect, useRef, useState } from "react";

import { Icon } from "./Icon";
import "./Filters.css";

export function ToggleChip({ label, on, onChange }: { label: string; on: boolean; onChange: (on: boolean) => void }) {
  return (
    <button type="button" className="chip" aria-pressed={on} onClick={() => onChange(!on)}>
      {on && <Icon name="check" size={14} strokeWidth={2.2} />}
      {label}
    </button>
  );
}

interface Option<T> {
  value: T;
  label: string;
}

/** A chip that opens a list of checkboxes; while something is chosen it shows how many. */
export function MultiSelectChip<T extends string | number>({
  label,
  options,
  selected,
  onChange,
}: {
  label: string;
  options: Option<T>[];
  selected: T[];
  onChange: (selected: T[]) => void;
}) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  const toggle = (value: T) => onChange(selected.includes(value) ? selected.filter((v) => v !== value) : [...selected, value]);

  return (
    <div className="multi" ref={root}>
      <button type="button" className="chip" aria-pressed={selected.length > 0} aria-expanded={open} onClick={() => setOpen(!open)}>
        {label}
        {selected.length > 0 && <span className="chip__count">{selected.length}</span>}
        <Icon name="chevronDown" size={14} />
      </button>
      {open && (
        <div className="multi__menu">
          {options.map((option) => (
            <label key={option.value} className="multi__option">
              <input type="checkbox" checked={selected.includes(option.value)} onChange={() => toggle(option.value)} />
              {option.label}
            </label>
          ))}
          {selected.length > 0 && (
            <button type="button" className="multi__clear" onClick={() => onChange([])}>
              Сбросить
            </button>
          )}
        </div>
      )}
    </div>
  );
}
