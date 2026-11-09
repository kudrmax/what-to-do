import { Icon } from "./Icon";
import { Popover } from "./Popover";

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
export function MultiSelectChip<T extends string | number>({ label, options, selected, onChange }: { label: string; options: Option<T>[]; selected: T[]; onChange: (selected: T[]) => void }) {
  const toggle = (value: T) => onChange(selected.includes(value) ? selected.filter((v) => v !== value) : [...selected, value]);
  return (
    <Popover
      trigger={(open, toggleOpen) => (
        <button type="button" className="chip" aria-pressed={selected.length > 0} aria-expanded={open} onClick={toggleOpen}>
          {label}
          {selected.length > 0 && <span className="chip__count">{selected.length}</span>}
          <Icon name="chevronDown" size={14} />
        </button>
      )}
    >
      {() => (
        <>
          {options.map((option) => (
            <label key={option.value} className="popover__item">
              <input type="checkbox" checked={selected.includes(option.value)} onChange={() => toggle(option.value)} />
              {option.label}
            </label>
          ))}
          {selected.length > 0 && (
            <div className="popover__footer">
              <button type="button" className="popover__item" onClick={() => onChange([])}>
                Сбросить
              </button>
            </div>
          )}
        </>
      )}
    </Popover>
  );
}
