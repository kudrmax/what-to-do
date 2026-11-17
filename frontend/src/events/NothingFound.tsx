import type { FeedQuery } from "../api/client";
import { useFeed } from "../api/queries";
import type { Section } from "../app/routes";
import { plural } from "../domain/dates";
import { plansToShow } from "../domain/plans";
import { EmptyState } from "../ui/Screen";

/** Nothing matched the search here; when the same words find cards in the other list, it leads there. Without another list it only says so. */
export function NothingFound({ search, elsewhere }: { search: string; elsewhere?: { section: Section; query: FeedQuery } }) {
  const other = useFeed({ ...elsewhere?.query, plans: plansToShow(elsewhere?.query.plans ?? [], search), search }, elsewhere !== undefined);
  const count = new Set((other.data ?? []).map((item) => item.event.id)).size;
  const words = `“${search.trim()}”`;
  if (!elsewhere || count === 0) {
    return <EmptyState title="Nothing found" text={`No events match ${words}. Check the filters or try other words.`} />;
  }
  return (
    <EmptyState
      title="Nothing found here"
      text={`${elsewhere.section.title} has ${count} ${plural(count, "event", "events")} matching ${words}.`}
      link={{ to: `${elsewhere.section.path}?${new URLSearchParams({ search })}`, label: `Open ${elsewhere.section.title}` }}
    />
  );
}
