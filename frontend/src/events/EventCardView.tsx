import type { KeyboardEvent, MouseEvent } from "react";

import type { EventCard } from "../api/client";
import { formatPrice } from "../domain/price";
import { EventPhoto } from "./EventPhoto";
import { EventTime } from "./EventTime";
import { InterestPicker, PlanPicker } from "./MarkPickers";
import { useOpenEvent } from "./navigation";
import "./EventCardView.css";

interface Props {
  event: EventCard;
  day: string;
  /** Tags the list is filtered by: the card shows the one it matched rather than just its first tag. */
  shownTags?: string[];
}

/** A card in a list. A click anywhere opens the event; the marks below work on their own. */
export function EventCardView({ event, day, shownTags = [] }: Props) {
  const open = useOpenEvent();
  const tag = event.tags.find((t) => shownTags.includes(t)) ?? event.tags[0];
  const price = event.is_cancelled ? null : formatPrice(event.price, event.currency);
  const show = () => open(event.id, day);
  const keepToMarks = (e: MouseEvent | KeyboardEvent) => e.stopPropagation();

  return (
    <article
      className={`card${event.is_cancelled ? " card--cancelled" : ""}`}
      role="link"
      tabIndex={0}
      aria-label={event.title}
      onClick={show}
      onKeyDown={(e) => e.key === "Enter" && e.target === e.currentTarget && show()}
    >
      <div className="card__layout">
      <EventPhoto path={event.image_url} className="card__photo" />
      <div className="card__body">
        <div className="card__meta">
          <EventTime event={event} className="card__time" />
          {tag && <span className="badge">{tag}</span>}
          {event.is_cancelled ? <span className="badge badge--accent card__end">Отменено</span> : price && <span className="card__price card__end">{price}</span>}
        </div>
        <h3 className="card__title">{event.title}</h3>
        <p className="card__text">{event.description}</p>
        <div className="card__marks" onClick={keepToMarks} onKeyDown={keepToMarks}>
          <InterestPicker event={event} size="small" />
          <PlanPicker event={event} size="small" />
        </div>
      </div>
      </div>
    </article>
  );
}
