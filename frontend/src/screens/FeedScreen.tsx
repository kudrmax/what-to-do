import type { Source } from "../api/client";
import { useFeed, useRefresh, useSources } from "../api/queries";
import { useActiveCity } from "../api/useActiveCity";
import { SECTIONS } from "../app/routes";
import { dayAndMonth, plural } from "../domain/dates";
import { plansToShow, SHOWN_PLANS } from "../domain/plans";
import { DayFeed } from "../events/DayFeed";
import { FilterBar } from "../events/FilterBar";
import { NothingFound } from "../events/NothingFound";
import { useEventFilters } from "../events/useEventFilters";
import { RefreshButton } from "../events/RefreshButton";
import { ReviewDeck } from "../events/ReviewDeck";
import { useFeedView } from "../events/useFeedView";
import { Icon } from "../ui/Icon";
import { Segmented } from "../ui/Segmented";
import { EmptyState, LoadError, Screen } from "../ui/Screen";
import { NoCity } from "./NoCity";

const neverRefreshed = (sources: Source[]) => sources.every((source) => source.last_refreshed_at === null);

/** Sources are added but nothing is read yet: the feed is empty because it waits, not because nothing is ahead. */
function FirstRefresh({ count, city }: { count: number; city: string }) {
  const refresh = useRefresh();
  if (refresh.running) {
    return <EmptyState title={`Reading the sources of ${city}`} text="Cards appear here when the refresh ends. The first one takes a few minutes." />;
  }
  return (
    <EmptyState
      title="Ready for the first refresh"
      text={`${count} ${plural(count, "source is", "sources are")} waiting to be read. Refresh collects ${plural(count, "its", "their")} recent posts, and Claude turns them into event cards.`}
      action={{ label: "Refresh now", onClick: refresh.start }}
    />
  );
}

/** Everything ahead that the user has not marked yet; a marked card moves to "Want to go" or leaves. A search finds marked cards too. */
export function FeedScreen() {
  const { city, today } = useActiveCity();
  const filters = useEventFilters();
  const { view, setView } = useFeedView(filters);
  const from = filters.params.get("from");
  const start = from ?? today ?? undefined;
  const sources = useSources(city !== null);
  const feed = useFeed({ ...filters.query, start, plans: plansToShow(SHOWN_PLANS.feed, filters.query.search) }, start !== undefined);

  const toolbar = city && (
    <FilterBar filters={filters}>
      {from && (
        <button type="button" className="chip" aria-pressed onClick={() => filters.change((next) => next.delete("from"))} data-tip="Show from today">
          From {dayAndMonth(from)}
          <Icon name="close" size={14} />
        </button>
      )}
    </FilterBar>
  );

  const actions = city && (
    <div className="screen__actions">
      <Segmented
        role="tabs"
        label="View"
        options={[
          { id: "list", label: "List" },
          { id: "review", label: "Review" },
        ]}
        value={view}
        onChange={setView}
      />
      <RefreshButton />
    </div>
  );

  return (
    <Screen title={SECTIONS.feed.title} action={actions} toolbar={toolbar}>
      {!city ? (
        <NoCity />
      ) : sources.data?.length === 0 ? (
        <EmptyState title="No sources yet" text={`Add Telegram channels and websites that announce events in ${city.name}, then click Refresh.`} link={{ to: SECTIONS.sources.path, label: "Add sources" }} />
      ) : sources.data && neverRefreshed(sources.data) && feed.data?.length === 0 && !filters.query.search ? (
        <FirstRefresh count={sources.data.length} city={city.name} />
      ) : feed.isError ? (
        <LoadError error={feed.error} />
      ) : view === "review" ? (
        today && feed.data && <ReviewDeck occurrences={feed.data} updatedAt={feed.dataUpdatedAt} today={today} shownTags={filters.query.tags} />
      ) : feed.data?.length === 0 && filters.query.search ? (
        <NothingFound search={filters.query.search} elsewhere={{ section: SECTIONS.plans, query: { start: today ?? undefined, plans: SHOWN_PLANS.going } }} />
      ) : feed.data?.length === 0 ? (
        <EmptyState title="All caught up" text="No unmarked events ahead, or filters are hiding them. Marked events are in Want to go." />
      ) : (
        today && feed.data && <DayFeed occurrences={feed.data} today={today} shownTags={filters.query.tags} />
      )}
    </Screen>
  );
}
