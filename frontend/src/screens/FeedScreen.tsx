import { useSearchParams } from "react-router-dom";

import { useFeed, useSources, useTags } from "../api/hooks";
import { DayFeed } from "../components/DayFeed";
import { MultiSelectChip, ToggleChip } from "../components/Filters";
import { RefreshButton } from "../components/RefreshButton";
import { EmptyState, Screen } from "../components/Screen";
import { useActiveCity } from "../api/useActiveCity";
import { addDays } from "../domain/dates";

const HORIZON_DAYS = 14;

/** Filter state lives in the address, so back and forward keep it. */
function useFeedFilters() {
  const [params, setParams] = useSearchParams();
  const update = (change: (next: URLSearchParams) => void) => {
    const next = new URLSearchParams(params);
    change(next);
    setParams(next, { replace: true });
  };
  const flag = (name: string) => params.get(name) === "1";
  const setFlag = (name: string, on: boolean) => update((next) => (on ? next.set(name, "1") : next.delete(name)));
  const setList = (name: string, values: (string | number)[]) =>
    update((next) => {
      next.delete(name);
      values.forEach((value) => next.append(name, String(value)));
    });
  return {
    hideMarked: !flag("all"),
    setHideMarked: (on: boolean) => setFlag("all", !on),
    onlyTimed: flag("timed"),
    setOnlyTimed: (on: boolean) => setFlag("timed", on),
    hideMultiday: flag("nomulti"),
    setHideMultiday: (on: boolean) => setFlag("nomulti", on),
    tags: params.getAll("tag"),
    setTags: (values: string[]) => setList("tag", values),
    sources: params.getAll("source").map(Number),
    setSources: (values: number[]) => setList("source", values),
  };
}

export function FeedScreen() {
  const { city, today } = useActiveCity();
  const filters = useFeedFilters();
  const tags = useTags();
  const sources = useSources(city !== null);
  const feed = useFeed(
    {
      start: today ?? undefined,
      end: today ? addDays(today, HORIZON_DAYS) : undefined,
      hideMarked: filters.hideMarked,
      onlyTimed: filters.onlyTimed,
      hideMultiday: filters.hideMultiday,
      tags: filters.tags,
      sources: filters.sources,
    },
    today !== null,
  );

  const filterBar = (
    <div className="filters">
      <ToggleChip label="Скрыть «не пойду»" on={filters.hideMarked} onChange={filters.setHideMarked} />
      <MultiSelectChip label="Теги" options={(tags.data ?? []).map((t) => ({ value: t.name, label: t.name }))} selected={filters.tags} onChange={filters.setTags} />
      <MultiSelectChip label="Источники" options={(sources.data ?? []).map((s) => ({ value: s.id, label: s.title }))} selected={filters.sources} onChange={filters.setSources} />
      <ToggleChip label="Только точное время" on={filters.onlyTimed} onChange={filters.setOnlyTimed} />
      <ToggleChip label="Без многодневных" on={filters.hideMultiday} onChange={filters.setHideMultiday} />
    </div>
  );

  return (
    <Screen title="Ближайшие" action={city && <RefreshButton />} filters={city && filterBar}>
      {city === null ? (
        <EmptyState title="Здесь пока пусто" text="Добавьте город и Telegram-каналы с афишами — события появятся после обновления." link={{ to: "/sources", label: "Добавить город и источники" }} />
      ) : sources.data?.length === 0 ? (
        <EmptyState title="Нет источников" text="Добавьте Telegram-каналы с афишами, потом нажмите «Обновить»." link={{ to: "/sources", label: "Добавить источники" }} />
      ) : feed.data?.length === 0 ? (
        <EmptyState title="Ничего не нашлось" text="В ближайшие две недели событий нет, или их скрывают фильтры." />
      ) : (
        today && feed.data && <DayFeed occurrences={feed.data} today={today} shownTags={filters.tags} />
      )}
    </Screen>
  );
}
