import { useCollections, useFeed } from "../api/queries";
import { useActiveCity } from "../api/useActiveCity";
import { SECTIONS } from "../app/routes";
import { DayFeed } from "../events/DayFeed";
import { FilterBar } from "../events/FilterBar";
import { NothingFound } from "../events/NothingFound";
import { useEventFilters } from "../events/useEventFilters";
import { Segmented } from "../ui/Segmented";
import { EmptyState, LoadError, Screen } from "../ui/Screen";
import { NoCity } from "./NoCity";

/** One of the user's collections as the usual feed: every date it has, newest first, whatever the marks say. */
export function CollectionsScreen() {
  const { city, today } = useActiveCity();
  const filters = useEventFilters();
  const collections = useCollections().data ?? [];
  const asked = Number(filters.params.get("collection"));
  const chosen = collections.find((c) => c.id === asked) ?? collections[0];
  const feed = useFeed({ ...filters.query, collection: chosen?.id }, today !== null && chosen !== undefined);
  const choose = (id: string) => filters.change((next) => next.set("collection", id));

  const picker = collections.length > 1 && chosen && (
    <Segmented label="Collection" options={collections.map((c) => ({ id: String(c.id), label: c.name }))} value={String(chosen.id)} onChange={choose} />
  );

  return (
    <Screen title={SECTIONS.collections.title} action={picker} toolbar={city && chosen && <FilterBar filters={filters} />}>
      {!city ? (
        <NoCity />
      ) : !chosen ? (
        <EmptyState title="No collections yet" text="Add one in Settings, under Advanced." link={{ to: `${SECTIONS.settings.path}#collections`, label: "Open settings" }} />
      ) : feed.isError ? (
        <LoadError error={feed.error} />
      ) : feed.data?.length === 0 && filters.query.search ? (
        <NothingFound search={filters.query.search} />
      ) : feed.data?.length === 0 ? (
        <EmptyState title={`Nothing in “${chosen.name}” yet`} text="Click the heart on a card to add its event here." />
      ) : (
        today && feed.data && <DayFeed occurrences={feed.data} today={today} shownTags={filters.query.tags} newestFirst />
      )}
    </Screen>
  );
}
