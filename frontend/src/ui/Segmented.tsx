export interface SegmentedOption<T extends string> {
  id: T;
  label: string;
  count?: number;
}

type SegmentedRole = "switch" | "tabs" | "radio";

const ARIA: Record<SegmentedRole, { group: string; option?: string; state: "aria-pressed" | "aria-selected" | "aria-checked" }> = {
  switch: { group: "group", state: "aria-pressed" },
  tabs: { group: "tablist", option: "tab", state: "aria-selected" },
  radio: { group: "radiogroup", option: "radio", state: "aria-checked" },
};

/**
 * One choice among a few: views of the same thing (`tabs`), a switch of what a list shows,
 * or an answer in a form (`radio`) that may start with nothing chosen.
 * All look the same everywhere; only what they say to a screen reader differs.
 */
export function Segmented<T extends string>({
  label,
  options,
  value,
  onChange,
  role = "switch",
}: {
  label: string;
  options: SegmentedOption<T>[];
  value: T | null;
  onChange: (id: T) => void;
  role?: SegmentedRole;
}) {
  const aria = ARIA[role];
  return (
    <div className="segmented" role={aria.group} aria-label={label}>
      {options.map((option) => (
        <button key={option.id} type="button" role={aria.option} {...{ [aria.state]: option.id === value }} onClick={() => onChange(option.id)}>
          {option.label}
          {option.count !== undefined && <span className="chip__count">{option.count}</span>}
        </button>
      ))}
    </div>
  );
}
