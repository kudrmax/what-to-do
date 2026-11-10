import type { FeedQuery } from "../api/client";
import { useFeed } from "../api/queries";
import type { Section } from "../app/routes";
import { plural } from "../domain/dates";
import { EmptyState } from "../ui/Screen";

/** Nothing matched the search here; when the same words find cards in the other list, it leads there. */
export function NothingFound({ search, elsewhere }: { search: string; elsewhere: { section: Section; query: FeedQuery } }) {
  const other = useFeed({ ...elsewhere.query, search });
  const count = new Set((other.data ?? []).map((item) => item.event.id)).size;
  const words = `«${search.trim()}»`;
  if (count === 0) {
    return <EmptyState title="Ничего не нашлось" text={`Нет событий со словами ${words}. Проверьте фильтры или поищите иначе.`} />;
  }
  return (
    <EmptyState
      title="Здесь ничего не нашлось"
      text={`В «${elsewhere.section.title}» по запросу ${words} есть ${count} ${plural(count, "событие", "события", "событий")}.`}
      link={{ to: `${elsewhere.section.path}?${new URLSearchParams({ search })}`, label: `Открыть «${elsewhere.section.title}»` }}
    />
  );
}
