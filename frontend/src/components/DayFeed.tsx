import type { Occurrence } from "../api/client";
import { dayHeading } from "../domain/dates";
import { groupByDay } from "../domain/feed";
import { EventCardView } from "./EventCardView";
import "./DayFeed.css";

/** Cards grouped under day headings, in the order the backend gives them. */
export function DayFeed({ occurrences, today, shownTags }: { occurrences: Occurrence[]; today: string; shownTags?: string[] }) {
  const days = groupByDay(occurrences);
  return (
    <div className="day-feed">
      {days.map(([day, items]) => {
        const heading = dayHeading(day, today);
        return (
          <section key={day} className="day-feed__day" aria-label={heading.title}>
            <div className="day-feed__heading">
              <h2>{heading.title}</h2>
              <span>{heading.subtitle}</span>
            </div>
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
