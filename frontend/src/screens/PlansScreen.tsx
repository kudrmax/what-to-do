import type { ReactNode } from "react";

import { useFeed } from "../api/queries";
import { useActiveCity } from "../api/useActiveCity";
import { useReadOnly } from "../app/readOnly";
import { SECTIONS } from "../app/routes";
import { addDays } from "../domain/dates";
import { plansToShow, SHOWN_PLANS } from "../domain/plans";
import { DayFeed } from "../events/DayFeed";
import { FilterBar } from "../events/FilterBar";
import { NothingFound } from "../events/NothingFound";
import { useEventFilters } from "../events/useEventFilters";
import { ToggleChip } from "../ui/Chips";
import { Segmented } from "../ui/Segmented";
import { EmptyState, LoadError, Screen } from "../ui/Screen";
import { NoCity } from "./NoCity";

/**
 * Cards the user plans to visit, ahead or behind: the same cards and filters as in the feed.
 * Read-only (the phone page) it has no title and no past, only what lies ahead; `tools` join the filters.
 */
export function PlansScreen({ tools }: { tools?: ReactNode }) {
  const readOnly = useReadOnly();
  const { city, today } = useActiveCity();
  const filters = useEventFilters();
  const past = !readOnly && filters.params.get("past") === "true";
  const onlySure = filters.params.get("sure") === "true";
  const setParam = (name: string, on: boolean) => filters.change((next) => (on ? next.set(name, "true") : next.delete(name)));
  const plans = plansToShow(onlySure ? SHOWN_PLANS.sure : past ? SHOWN_PLANS.past : SHOWN_PLANS.going, filters.query.search);
  const range = today ? (past ? { end: addDays(today, -1) } : { start: today }) : {};
  const feed = useFeed({ ...filters.query, ...range, plans }, today !== null);

  const when = city && !readOnly && (
    <Segmented
      label="When"
      options={[
        { id: "ahead", label: "Upcoming" },
        { id: "past", label: "Past" },
      ]}
      value={past ? "past" : "ahead"}
      onChange={(id) => setParam("past", id === "past")}
    />
  );

  const toolbar = city && (
    <FilterBar filters={filters}>
      {tools}
      <ToggleChip label="Only “Going for sure”" on={onlySure} onChange={(on) => setParam("sure", on)} />
    </FilterBar>
  );

  return (
    <Screen title={readOnly ? undefined : SECTIONS.plans.title} action={when} toolbar={toolbar}>
      {!city ? (
        <NoCity />
      ) : feed.isError ? (
        <LoadError error={feed.error} />
      ) : feed.data?.length === 0 && filters.query.search ? (
        <NothingFound search={filters.query.search} elsewhere={readOnly ? undefined : { section: SECTIONS.feed, query: { start: today ?? undefined, plans: SHOWN_PLANS.feed } }} />
      ) : feed.data?.length === 0 ? (
        <EmptyState title={past ? "No past plans" : "No plans yet"} text={readOnly ? undefined : "Mark an event as “Maybe going” or “Going for sure” and it will move here."} />
      ) : (
        today && feed.data && <DayFeed occurrences={feed.data} today={today} shownTags={filters.query.tags} newestFirst={past} />
      )}
    </Screen>
  );
}
