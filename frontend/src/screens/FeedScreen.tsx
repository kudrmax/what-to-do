import { useFeed, useSources } from "../api/queries";
import { useActiveCity } from "../api/useActiveCity";
import { SECTIONS } from "../app/routes";
import { dayAndMonth } from "../domain/dates";
import { SHOWN_PLANS } from "../domain/plans";
import { DayFeed } from "../events/DayFeed";
import { FilterBar } from "../events/FilterBar";
import { useEventFilters } from "../events/useEventFilters";
import { RefreshButton } from "../events/RefreshButton";
import { Icon } from "../ui/Icon";
import { EmptyState, LoadError, Screen } from "../ui/Screen";
import { NoCity } from "./NoCity";

/** Everything ahead that the user has not marked yet; a marked card moves to «Собираюсь пойти» or leaves. */
export function FeedScreen() {
  const { city, today } = useActiveCity();
  const filters = useEventFilters();
  const from = filters.params.get("from");
  const start = from ?? today ?? undefined;
  const sources = useSources(city !== null);
  const feed = useFeed({ ...filters.query, start, plans: SHOWN_PLANS.feed }, start !== undefined);

  const toolbar = city && (
    <FilterBar filters={filters}>
      {from && (
        <button type="button" className="chip" aria-pressed onClick={() => filters.change((next) => next.delete("from"))} data-tip="Показать с сегодняшнего дня">
          С {dayAndMonth(from)}
          <Icon name="close" size={14} />
        </button>
      )}
    </FilterBar>
  );

  return (
    <Screen title={SECTIONS.feed.title} action={city && <RefreshButton />} toolbar={toolbar}>
      {!city ? (
        <NoCity />
      ) : sources.data?.length === 0 ? (
        <EmptyState title="Нет источников" text="Добавьте Telegram-каналы с афишами, потом нажмите «Обновить»." link={{ to: SECTIONS.sources.path, label: "Добавить источники" }} />
      ) : feed.isError ? (
        <LoadError error={feed.error} />
      ) : feed.data?.length === 0 ? (
        <EmptyState title="Всё разобрано" text="Неразмеченных событий впереди нет, или их скрывают фильтры. Размеченные — в «Собираюсь пойти»." />
      ) : (
        today && feed.data && <DayFeed occurrences={feed.data} today={today} shownTags={filters.query.tags} />
      )}
    </Screen>
  );
}
