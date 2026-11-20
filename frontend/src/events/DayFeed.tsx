import { useEffect, useRef, useState } from "react";

import type { Occurrence } from "../api/client";
import { dayHeading } from "../domain/dates";
import { groupByDay } from "../domain/feed";
import { EventCardView } from "./EventCardView";
import { useOpenEvent, type OpenEvent } from "./navigation";
import "./DayFeed.css";

/** Cards drawn with the screen; the days after them are drawn as they come near, so a long feed opens at once. */
const FIRST_CARDS = 12;
/** How far ahead of the visible part a day starts to be drawn. */
const AHEAD = "1500px 0px";
/** The height a day waits with before its cards are drawn: about one row of cards for every two of them. */
const CARD_ROW_ESTIMATE = 420;

/** Cards under day headings, in the order the backend gives them. */
export function DayFeed({ occurrences, today, shownTags, newestFirst = false }: { occurrences: Occurrence[]; today: string; shownTags?: readonly string[]; newestFirst?: boolean }) {
  const open = useOpenEvent();
  const days = groupByDay(occurrences);
  let before = 0;
  return (
    <div className="day-feed">
      {(newestFirst ? days.reverse() : days).map(([day, items]) => {
        const eager = before < FIRST_CARDS;
        before += items.length;
        return <Day key={day} day={day} items={items} today={today} shownTags={shownTags} onOpen={open} eager={eager} />;
      })}
    </div>
  );
}

interface DayProps {
  day: string;
  items: Occurrence[];
  today: string;
  shownTags?: readonly string[];
  onOpen: OpenEvent;
  eager: boolean;
}

function Day({ day, items, today, shownTags, onOpen, eager }: DayProps) {
  const heading = dayHeading(day, today);
  const [grid, near] = useNearView<HTMLDivElement>(eager);
  return (
    <section className="day-feed__day" aria-label={heading.title}>
      <h2 className="day-heading">
        <span className="section-title">{heading.title}</span>
        <span className="day-heading__sub">{heading.subtitle}</span>
      </h2>
      <div ref={grid} className="day-feed__grid" style={near ? undefined : { minHeight: Math.ceil(items.length / 2) * CARD_ROW_ESTIMATE }}>
        {near && items.map((item) => <EventCardView key={`${item.event.id}-${day}`} event={item.event} day={day} shownTags={shownTags} onOpen={onOpen} />)}
      </div>
    </section>
  );
}

/** True once the element has come near the visible part of the page; it stays true, so what was drawn is not taken away. */
function useNearView<T extends Element>(initially: boolean) {
  const element = useRef<T>(null);
  const [near, setNear] = useState(initially || typeof IntersectionObserver === "undefined");
  useEffect(() => {
    const node = element.current;
    if (near || !node) return;
    const watcher = new IntersectionObserver((entries) => entries.some((entry) => entry.isIntersecting) && setNear(true), { rootMargin: AHEAD });
    watcher.observe(node);
    return () => watcher.disconnect();
  }, [near]);
  return [element, near] as const;
}
