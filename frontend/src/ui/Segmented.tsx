export interface SegmentedOption<T extends string> {
  id: T;
  label: string;
  count?: number;
}

/**
 * One choice among a few: views of the same thing (`tabs`) or a switch of what a list shows.
 * Both look the same everywhere; only what they say to a screen reader differs.
 */
export function Segmented<T extends string>({ label, options, value, onChange, tabs = false }: { label: string; options: SegmentedOption<T>[]; value: T; onChange: (id: T) => void; tabs?: boolean }) {
  return (
    <div className="segmented" role={tabs ? "tablist" : "group"} aria-label={label}>
      {options.map((option) => {
        const on = option.id === value;
        return (
          <button key={option.id} type="button" role={tabs ? "tab" : undefined} aria-selected={tabs ? on : undefined} aria-pressed={tabs ? undefined : on} onClick={() => onChange(option.id)}>
            {option.label}
            {option.count !== undefined && <span className="chip__count">{option.count}</span>}
          </button>
        );
      })}
    </div>
  );
}
