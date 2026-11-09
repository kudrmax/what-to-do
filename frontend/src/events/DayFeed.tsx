import type { Occurrence } from "../api/client";
import { dayHeading } from "../domain/dates";
import { groupByDay } from "../domain/feed";
import { EventCardView } from "./EventCardView";
import "./DayFeed.css";

/** Cards under day headings, in the order the backend gives them. */
export function DayFeed({ occurrences, today, shownTags, newestFirst = false }: { occurrences: Occurrence[]; today: string; shownTags?: string[]; newestFirst?: boolean }) {
  const days = groupByDay(occurrences);
  return (
    <div className="day-feed">
      {(newestFirst ? days.reverse() : days).map(([day, items]) => {
        const heading = dayHeading(day, today);
        return (
          <section key={day} className="day-feed__day" aria-label={heading.title}>
            <h2 className="day-heading">
              <span className="section-title">{heading.title}</span>
              <span className="day-heading__sub">{heading.subtitle}</span>
            </h2>
            <div className="day-feed__grid">
              {items.map((item) => (
                <EventCardView key={`${item.event.id}-${day}`} event={item.event} day={day} shownTags={shownTags} />
              ))}
            </div>
          </section>
        );
      })}
    </div>
  );
}
