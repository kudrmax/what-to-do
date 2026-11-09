import type { ReactNode } from "react";

import { useSources, useTags } from "../api/queries";
import { MultiSelectChip, ToggleChip } from "../ui/Chips";
import type { EventFilters } from "./useEventFilters";

export function FilterBar({ filters, children }: { filters: EventFilters; children?: ReactNode }) {
  const tags = useTags();
  const sources = useSources();
  const { query } = filters;
  return (
    <div className="filter-bar">
      {children}
      <MultiSelectChip label="Теги" options={(tags.data ?? []).map((t) => ({ value: t.name, label: t.name }))} selected={query.tags ?? []} onChange={(v) => filters.setList("tags", v)} />
      <MultiSelectChip label="Источники" options={(sources.data ?? []).map((s) => ({ value: s.id, label: s.title }))} selected={query.sources ?? []} onChange={(v) => filters.setList("sources", v)} />
      <ToggleChip label="Только с временем" on={!!query.only_timed} onChange={(on) => filters.setFlag("only_timed", on)} />
      <ToggleChip label="Без многодневных" on={!!query.hide_multiday} onChange={(on) => filters.setFlag("hide_multiday", on)} />
    </div>
  );
}
