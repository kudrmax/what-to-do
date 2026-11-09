import { Link } from "react-router-dom";

import type { EventCard } from "../api/client";
import { EventImage } from "./EventImage";
import { EventTime } from "./EventTime";
import { InterestPicker, PlanPicker } from "./MarkControls";
import "./EventCardView.css";

interface Props {
  event: EventCard;
  day: string;
  /** Tags the feed is filtered by: the card shows the one it matched, not just its first tag. */
  shownTags?: string[];
}

/** A card in a feed: photo with tag, time and price, title, description, then marks. Place and sources open with the card. */
export function EventCardView({ event, day, shownTags = [] }: Props) {
  const href = `/event/${event.id}?day=${day}`;
  const tag = event.tags.find((t) => shownTags.includes(t)) ?? event.tags[0];
  return (
    <article className={`card${event.is_cancelled ? " card--cancelled" : ""}`}>
      <Link to={href} aria-label={event.title} className="card__image-link">
        <EventImage path={event.image_url} tag={tag} className="card__image" />
      </Link>
      <div className="card__body">
        <div className="card__meta">
          <EventTime event={event} className="card__time" />
          {event.is_cancelled ? <span className="card__cancelled">Отменено</span> : <span className="card__price">{event.price}</span>}
        </div>
        <Link to={href} className="card__title">
          {event.title}
        </Link>
        <p className="card__description">{event.description}</p>
        <div className="card__marks">
          <InterestPicker event={event} size="small" />
          <PlanPicker event={event} size="small" />
        </div>
      </div>
    </article>
  );
}
