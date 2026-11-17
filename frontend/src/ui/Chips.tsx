import { useEffect } from "react";

import { Icon, type IconName } from "./Icon";
import { Popover } from "./Popover";

export function ToggleChip({ label, on, onChange, icon, tip, className }: { label: string; on: boolean; onChange: (on: boolean) => void; icon?: IconName; tip?: string; className?: string }) {
  return (
    <button type="button" className={className ? `chip ${className}` : "chip"} aria-pressed={on} data-tip={tip} onClick={() => onChange(!on)}>
      {icon ? <Icon name={icon} size={14} strokeWidth={2.2} /> : on && <Icon name="check" size={14} strokeWidth={2.2} />}
      {label}
    </button>
  );
}

interface Option<T> {
  value: T;
  label: string;
}

/**
 * A chip that opens a list of checkboxes. Nothing chosen means every option counts, so then every box is ticked.
 * Any row can be picked alone with "Only"; the last ticked box stays, since an empty list would show nothing.
 * A remembered choice of an option that no longer exists is dropped, so it cannot hide events unseen.
 */
export function MultiSelectChip<T extends string | number>({ label, options, selected, onChange }: { label: string; options: Option<T>[]; selected: T[]; onChange: (selected: T[]) => void }) {
  const all = options.map((option) => option.value);
  const known = selected.filter((value) => all.includes(value));
  const narrowed = known.length > 0 && known.length < all.length;
  const ticked = narrowed ? known : all;
  const choose = (next: T[]) => onChange(next.length === all.length ? [] : next);
  const stale = all.length > 0 && known.length < selected.length;
  useEffect(() => {
    if (stale) choose(known);
  });
  const toggle = (value: T) => choose(ticked.includes(value) ? ticked.filter((v) => v !== value) : all.filter((v) => v === value || ticked.includes(v)));
  return (
    <Popover
      trigger={(open, toggleOpen) => (
        <button type="button" className="chip" aria-pressed={narrowed} aria-expanded={open} onClick={toggleOpen}>
          {label}
          {narrowed && <span className="chip__count">{known.length}</span>}
          <Icon name="chevronDown" size={14} />
        </button>
      )}
    >
      {() => (
        <>
          <div className="popover__header">
            <label className="popover__item">
              <input type="checkbox" checked={!narrowed} onChange={() => narrowed && onChange([])} />
              All {label.toLowerCase()}
            </label>
          </div>
          {options.map((option) => {
            const on = ticked.includes(option.value);
            const alone = on && ticked.length === 1;
            return (
              <div key={option.value} className="popover__row">
                <label className="popover__item">
                  <input type="checkbox" checked={on} onChange={() => !alone && toggle(option.value)} />
                  {option.label}
                </label>
                {!alone && all.length > 1 && (
                  <button type="button" className="popover__only" aria-label={`Only ${option.label}`} onClick={() => choose([option.value])}>
                    Only
                  </button>
                )}
              </div>
            );
          })}
        </>
      )}
    </Popover>
  );
}
