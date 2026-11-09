import { useFeed } from "../api/queries";
import { useActiveCity } from "../api/useActiveCity";
import { SECTIONS } from "../app/routes";
import { addDays } from "../domain/dates";
import { SHOWN_PLANS } from "../domain/plans";
import { DayFeed } from "../events/DayFeed";
import { FilterBar } from "../events/FilterBar";
import { useEventFilters } from "../events/useEventFilters";
import { ToggleChip } from "../ui/Chips";
import { EmptyState, Screen } from "../ui/Screen";
import { NoCity } from "./NoCity";

/** Cards the user plans to visit, ahead or behind: the same cards and filters as in the feed. */
export function PlansScreen() {
  const { city, today } = useActiveCity();
  const filters = useEventFilters();
  const past = filters.params.get("past") === "true";
  const onlySure = filters.params.get("sure") === "true";
  const setParam = (name: string, on: boolean) => filters.change((next) => (on ? next.set(name, "true") : next.delete(name)));
  const plans = onlySure ? SHOWN_PLANS.sure : past ? SHOWN_PLANS.past : SHOWN_PLANS.going;
  const range = today ? (past ? { end: addDays(today, -1) } : { start: today }) : {};
  const feed = useFeed({ ...filters.query, ...range, plans }, today !== null);

  const toolbar = city && (
    <FilterBar filters={filters}>
      <div className="segmented" role="group" aria-label="Когда">
        <button type="button" aria-pressed={!past} onClick={() => setParam("past", false)}>
          Впереди
        </button>
        <button type="button" aria-pressed={past} onClick={() => setParam("past", true)}>
          Прошедшие
        </button>
      </div>
      <ToggleChip label="Только «точно пойду»" on={onlySure} onChange={(on) => setParam("sure", on)} />
    </FilterBar>
  );

  return (
    <Screen title={SECTIONS.plans.title} toolbar={toolbar}>
      {!city ? (
        <NoCity />
      ) : feed.data?.length === 0 ? (
        <EmptyState title={past ? "Прошедших планов нет" : "Планов пока нет"} text="Отметьте событие кнопкой «возможно пойду» или «точно пойду» — оно переедет сюда." />
      ) : (
        today && feed.data && <DayFeed occurrences={feed.data} today={today} shownTags={filters.query.tags} newestFirst={past} />
      )}
    </Screen>
  );
}
