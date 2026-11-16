import { Link } from "react-router-dom";

import { useFeed, usePrefetchMentions } from "../api/queries";
import { useActiveCity } from "../api/useActiveCity";
import { feedFromHref, SECTIONS } from "../app/routes";
import { addDays, dayAndMonth, dayNumber, monthTitle, weekStart, weekdayShort } from "../domain/dates";
import { groupByDay } from "../domain/feed";
import { plansToShow, SHOWN_PLANS } from "../domain/plans";
import { EventTime } from "../events/EventTime";
import { FilterBar } from "../events/FilterBar";
import { NothingFound } from "../events/NothingFound";
import { useEventFilters } from "../events/useEventFilters";
import { useOpenEvent } from "../events/navigation";
import { Icon } from "../ui/Icon";
import { IconButton } from "../ui/IconButton";
import { LoadError, Screen } from "../ui/Screen";
import { softHyphenate } from "../ui/softHyphens";
import { NoCity } from "./NoCity";
import "./CalendarScreen.css";

/** A week at a time, for planning ahead: what is not marked yet and what the user is going to, the latter highlighted. */
export function CalendarScreen() {
  const { city, today } = useActiveCity();
  const filters = useEventFilters();
  const open = useOpenEvent();
  const prefetch = usePrefetchMentions();
  const monday = filters.params.get("week") ?? (today ? weekStart(today) : null);
  const days = monday ? Array.from({ length: 7 }, (_, i) => addDays(monday, i)) : [];
  const feed = useFeed({ ...filters.query, start: days[0], end: days[6], plans: plansToShow(SHOWN_PLANS.calendar, filters.query.search) }, monday !== null);
  const goTo = (week: string) => filters.change((next) => (today && week === weekStart(today) ? next.delete("week") : next.set("week", week)));

  if (!city || !today || !monday) {
    return (
      <Screen title={SECTIONS.calendar.title}>
        <NoCity />
      </Screen>
    );
  }

  const title = [...new Set([monthTitle(days[0]), monthTitle(days[6])])].join(" – ");
  return (
    <Screen
      title={title}
      action={
        <div className="week-nav">
          <IconButton icon="chevronLeft" label="Previous week" onClick={() => goTo(addDays(monday, -7))} />
          <button type="button" className="button button--quiet button--small" onClick={() => goTo(weekStart(today))}>
            Today
          </button>
          <IconButton icon="chevronRight" label="Next week" onClick={() => goTo(addDays(monday, 7))} />
        </div>
      }
      toolbar={<FilterBar filters={filters} />}
    >
      {feed.isError ? (
        <LoadError error={feed.error} />
      ) : feed.data?.length === 0 && filters.query.search ? (
        <NothingFound search={filters.query.search} elsewhere={{ section: SECTIONS.feed, query: { start: today, plans: SHOWN_PLANS.feed } }} />
      ) : (
        <div className="week">
          {groupByDay(feed.data ?? [], days).map(([day, items]) => (
            <div key={day} className={`week__day${day < today ? " week__day--past" : ""}`}>
              <div className="week__band">
                <Link to={feedFromHref(day)} className="week__head" data-tip={`Upcoming from ${dayAndMonth(day)}`}>
                  <span className="week__weekday">{weekdayShort(day)}</span>
                  <span className={`week__number${day === today ? " week__number--today" : ""}`}>{dayNumber(day)}</span>
                </Link>
              </div>
              {items.map(({ event }) => (
                <button key={event.id} type="button" className={`week__item${event.is_going ? " week__item--going" : ""}${event.plan === "no" ? " week__item--declined" : ""}${event.is_priority ? " week__item--priority" : ""}`} onClick={() => open(event.id, day)} onPointerEnter={() => prefetch(event.id)} onFocus={() => prefetch(event.id)}>
                  <span className="week__top">
                    <EventTime event={event} className="week__time" iconSize={14} />
                    {event.is_priority && (
                      <span className="week__priority" data-tip="Fits what you look for first" aria-label="For you">
                        <Icon name="sparkle" size={13} strokeWidth={2.2} />
                      </span>
                    )}
                  </span>
                  <span className="week__title">{softHyphenate(event.title)}</span>
                </button>
              ))}
            </div>
          ))}
        </div>
      )}
    </Screen>
  );
}
