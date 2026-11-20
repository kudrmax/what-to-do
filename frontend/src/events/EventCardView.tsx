import { memo, type KeyboardEvent, type MouseEvent } from "react";

import type { EventCard } from "../api/client";
import { usePrefetchMentions, useTags } from "../api/queries";
import { useCardLanguage } from "../api/useActiveCity";
import { useReadOnly } from "../app/readOnly";
import { formatPrice } from "../domain/price";
import { orderTags } from "../domain/tags";
import { EventPhotoGrid } from "./EventPhotoGrid";
import { EventTime } from "./EventTime";
import { PriorityBadge } from "./PriorityBadge";
import { CollectionButton } from "./CollectionButton";
import { useCollectionsOn } from "./useCollectionsOn";
import { DevNoteButton } from "./DevNoteButton";
import { InterestPicker, PlanPicker } from "./MarkPickers";
import type { OpenEvent } from "./navigation";
import "./EventCardView.css";

interface Props {
  event: EventCard;
  day: string;
  /** Tags the list is filtered by: the card shows the one it matched rather than just its first tag. */
  shownTags?: readonly string[];
  onOpen: OpenEvent;
}

const NO_TAGS: readonly string[] = [];

/** A card in a list. A click anywhere opens the event; the marks below work on their own. It is drawn again only when its own event changes. */
export const EventCardView = memo(function EventCardView({ event, day, shownTags = NO_TAGS, onOpen }: Props) {
  const readOnly = useReadOnly();
  const prefetch = usePrefetchMentions();
  const show = () => onOpen(event.id, day);
  const keepToMarks = (e: MouseEvent | KeyboardEvent) => e.stopPropagation();

  return (
    <article
      className={`card${readOnly ? " card--read-only" : ""}${event.image_url ? " card--with-photo" : ""}${event.is_cancelled ? " card--cancelled" : ""}${event.is_priority ? " card--priority" : ""}`}
      role="link"
      tabIndex={0}
      aria-label={event.title}
      onClick={show}
      onPointerEnter={() => prefetch(event.id)}
      onFocus={() => prefetch(event.id)}
      onKeyDown={(e) => e.key === "Enter" && e.target === e.currentTarget && show()}
    >
      {!readOnly && <CardCollectionButton event={event} keep={keepToMarks} />}
      <div className="card__layout">
      <EventPhotoGrid paths={event.image_urls?.length ? event.image_urls : [event.image_url]} className="card__photo" />
      <div className="card__body">
        <EventCardSummary event={event} shownTags={shownTags} />
        {!readOnly && (
          <div className="card__marks" onClick={keepToMarks} onKeyDown={keepToMarks}>
            <div className="marks-row">
              <InterestPicker event={event} size="small" />
              <DevNoteButton event={event} size="small" />
            </div>
            <PlanPicker event={event} size="small" />
          </div>
        )}
      </div>
      </div>
    </article>
  );
});

/** The heart in the card's corner; the card under it leaves the corner free while it is shown. */
function CardCollectionButton({ event, keep }: { event: EventCard; keep: (e: MouseEvent | KeyboardEvent) => void }) {
  const on = useCollectionsOn();
  if (!on) return null;
  return (
    <div className="card__collect" onClick={keep} onKeyDown={keep}>
      <CollectionButton event={event} place="card" />
    </div>
  );
}

/** What a card says about its event: time, badges, title and description. Every view of the feed shows exactly this. */
export const EventCardSummary = memo(function EventCardSummary({ event, shownTags = NO_TAGS }: { event: EventCard; shownTags?: readonly string[] }) {
  const tags = orderTags(event.tags, useTags().data);
  const tag = tags.find((t) => shownTags.includes(t)) ?? tags[0];
  const price = event.is_cancelled ? null : formatPrice(event.price, event.currency);
  const { lang } = useCardLanguage();
  return (
    <>
      <div className="card__meta">
        <EventTime event={event} className="card__time" />
        {event.is_priority && <PriorityBadge />}
        {tag && <span className="badge">{tag}</span>}
        {event.is_cancelled ? <span className="badge badge--accent card__end">Cancelled</span> : price && <span className="card__price card__end">{price}</span>}
      </div>
      <h3 className="card__title" lang={lang}>
        {event.title}
      </h3>
      <p className="card__text" lang={lang}>
        {event.description}
      </p>
    </>
  );
});
