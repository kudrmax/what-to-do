import { Link, useSearchParams } from "react-router-dom";

import type { Occurrence } from "../api/client";
import { useFeed } from "../api/hooks";
import { EventTime } from "../components/EventTime";
import { Icon } from "../components/Icon";
import { EmptyState, Screen } from "../components/Screen";
import { useActiveCity } from "../api/useActiveCity";
import { addDays, dayNumber, monthTitle, weekStart, weekdayShort } from "../domain/dates";
import "./CalendarScreen.css";

/** A week at a time, for planning ahead; events the user plans to visit stand out. */
export function CalendarScreen() {
  const { city, today } = useActiveCity();
  const [params, setParams] = useSearchParams();
  const monday = params.get("week") ?? (today ? weekStart(today) : null);
  const days = monday ? Array.from({ length: 7 }, (_, i) => addDays(monday, i)) : [];
  const feed = useFeed({ start: days[0], end: days[6], hideMarked: true }, monday !== null);
  const goTo = (week: string) => setParams(week === (today && weekStart(today)) ? {} : { week }, { replace: true });

  if (!city || !today || !monday) {
    return (
      <Screen title="Календарь">
        <EmptyState title="Здесь пока пусто" text="Добавьте город и источники." link={{ to: "/sources", label: "Добавить город и источники" }} />
      </Screen>
    );
  }

  const byDay = new Map<string, Occurrence[]>(days.map((day) => [day, []]));
  feed.data?.forEach((item) => byDay.get(item.date)?.push(item));
  const months = [...new Set([monthTitle(days[0]), monthTitle(days[6])])].join(" – ");

  return (
    <Screen
      title={months}
      action={
        <div className="week-nav">
          <button type="button" aria-label="Предыдущая неделя" onClick={() => goTo(addDays(monday, -7))}>
            <Icon name="chevronLeft" />
          </button>
          <button type="button" className="week-nav__today" onClick={() => goTo(weekStart(today))}>
            Сегодня
          </button>
          <button type="button" aria-label="Следующая неделя" onClick={() => goTo(addDays(monday, 7))}>
            <Icon name="chevronRight" />
          </button>
        </div>
      }
    >
      <div className="week">
        <div className="week__grid">
          {days.map((day) => (
            <div key={day} className="week__day">
              <div className="week__day-head">
                <span className="week__weekday">{weekdayShort(day)}</span>
                <span className={`week__number${day === today ? " week__number--today" : ""}`}>{dayNumber(day)}</span>
              </div>
              {byDay.get(day)?.map(({ event }) => {
                const planned = event.mark.plan === "maybe" || event.mark.plan === "sure";
                return (
                  <Link key={event.id} to={`/event/${event.id}?day=${day}`} className={`week__item${planned ? " week__item--planned" : ""}`}>
                    <EventTime event={event} className="week__time" iconSize={14} />
                    <span className="week__title">{event.title}</span>
                  </Link>
                );
              })}
            </div>
          ))}
        </div>
      </div>
    </Screen>
  );
}
