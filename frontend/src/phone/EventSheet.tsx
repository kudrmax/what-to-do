import { useEffect, useRef, useState, type TouchEvent } from "react";

import { describeRecurrence } from "../domain/recurrence";
import { longDate } from "../domain/dates";
import { formatPrice } from "../domain/price";
import { orderTags } from "../domain/tags";
import { EventTime } from "../events/EventTime";
import { PriorityBadge } from "../events/PriorityBadge";
import { Icon } from "../ui/Icon";
import { IconButton } from "../ui/IconButton";
import { PhonePoster, PlanMark } from "./PhoneCard";
import type { PhoneOccurrence } from "./snapshot";

/** How far the sheet must be pulled down to close rather than spring back. */
const CLOSE_DISTANCE = 96;

/** An event's details over the list, read-only: a sheet that closes by its button, Escape or a pull down. */
export function EventSheet({ occurrence, tags, onClose }: { occurrence: PhoneOccurrence; tags: string[]; onClose: () => void }) {
  const { event, date, post_url } = occurrence;
  const pull = usePullToClose(onClose);
  const price = formatPrice(event.price, event.currency);
  const when = describeRecurrence(event.rrule) ?? (event.kind === "multiday" ? "Come any day" : longDate(date));

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    document.body.classList.add("phone-body--sheet");
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.classList.remove("phone-body--sheet");
    };
  }, [onClose]);

  return (
    <div className="phone-sheet">
      <div className="phone-sheet__scrim" onClick={onClose} />
      <article
        ref={pull.ref}
        className="phone-sheet__panel"
        role="dialog"
        aria-modal="true"
        aria-label={event.title}
        style={pull.offset ? { transform: `translateY(${pull.offset}px)`, transition: "none" } : undefined}
        onTouchStart={pull.start}
        onTouchMove={pull.move}
        onTouchEnd={pull.end}
        onTouchCancel={pull.end}
      >
        <div className="phone-sheet__grabber" aria-hidden="true" />
        <IconButton icon="close" label="Close" className="phone-sheet__close" onClick={onClose} />
        <PhonePoster path={event.image_url} className="phone-sheet__poster" />
        <div className="phone-sheet__content">
          <div className="details__badges">
            <PlanMark event={event} named />
            {event.is_priority && <PriorityBadge />}
            {orderTags(event.tags, tags.map((name) => ({ name }))).map((tag) => (
              <span key={tag} className="badge">
                {tag}
              </span>
            ))}
            {event.is_cancelled && <span className="badge badge--accent">Cancelled</span>}
          </div>
          <h2 className={`details__title phone-sheet__title${event.is_cancelled ? " details__title--cancelled" : ""}`}>{event.title}</h2>

          <div className="details__facts">
            <div className="fact">
              <Icon name="calendar" className="fact__icon" />
              <EventTime event={event} className="fact__main" />
              <span className="fact__sub">{when}</span>
            </div>
            {event.place && (
              <a className="fact fact--link" href={event.map_url ?? undefined} target="_blank" rel="noreferrer">
                <Icon name="pin" className="fact__icon" />
                <span className="phone-fact__lines">
                  <span className="fact__main">{event.venue ?? event.address}</span>
                  {event.venue && event.address && <span className="fact__sub">{event.address}</span>}
                </span>
              </a>
            )}
            {price && (
              <div className="fact">
                <Icon name="ticket" className="fact__icon" />
                <span className="fact__main">{price}</span>
              </div>
            )}
          </div>

          {(event.booking || post_url) && (
            <div className="phone-sheet__actions">
              {event.booking && (
                <a className="button" href={event.booking.url} target="_blank" rel="noreferrer">
                  <Icon name="external" size={16} />
                  {event.booking.kind === "tickets" ? "Buy ticket" : "Sign up"}
                </a>
              )}
              {post_url && (
                <a className={event.booking ? "button button--quiet" : "button"} href={post_url} target="_blank" rel="noreferrer">
                  <Icon name="forward" size={16} />
                  Open post
                </a>
              )}
            </div>
          )}

          <p className="details__description">{event.description}</p>
        </div>
      </article>
    </div>
  );
}

/** Pulling the sheet down from its top follows the finger; let go far enough and it closes. */
function usePullToClose(onClose: () => void) {
  const ref = useRef<HTMLElement>(null);
  const origin = useRef<number | null>(null);
  const [offset, setOffset] = useState(0);
  return {
    ref,
    offset,
    start: (e: TouchEvent) => {
      origin.current = (ref.current?.scrollTop ?? 0) <= 0 ? e.touches[0].clientY : null;
    },
    move: (e: TouchEvent) => {
      if (origin.current === null) return;
      setOffset(Math.max(0, e.touches[0].clientY - origin.current));
    },
    end: () => {
      const far = offset > CLOSE_DISTANCE;
      origin.current = null;
      setOffset(0);
      if (far) onClose();
    },
  };
}
