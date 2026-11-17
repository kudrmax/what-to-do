import type { EventCard } from "../api/client";
import { PLANS } from "../domain/plans";
import { formatPrice } from "../domain/price";
import { orderTags } from "../domain/tags";
import { EventTime } from "../events/EventTime";
import { PriorityBadge } from "../events/PriorityBadge";
import { Icon } from "../ui/Icon";
import { usePoster } from "./posters";

/** The poster whole, on a blurred copy of itself, like the app's cards; nothing until it is decrypted. */
export function PhonePoster({ path, className }: { path: string | null | undefined; className: string }) {
  const url = usePoster(path);
  if (!url) return null;
  return (
    <div className={`photo ${className}`}>
      <div className="photo__backdrop" style={{ backgroundImage: `url("${url}")` }} />
      <img className="photo__image" src={url} alt="" />
    </div>
  );
}

/** The plan mark as the app shows it: its icon in its color; the details also name it. */
export function PlanMark({ event, named = false }: { event: EventCard; named?: boolean }) {
  if (event.plan !== "sure" && event.plan !== "maybe") return null;
  const plan = PLANS[event.plan];
  const mark = (
    <span className={`phone-plan phone-plan--${event.plan}`} role={named ? undefined : "img"} aria-label={named ? undefined : plan.label}>
      <Icon name={plan.icon} size={14} strokeWidth={2.6} />
    </span>
  );
  if (!named) return mark;
  return (
    <span className={`badge phone-plan-badge phone-plan-badge--${event.plan}`}>
      {mark}
      {plan.label}
    </span>
  );
}

/** A card in the list: poster, time and plan, title, tag and price. A tap opens the details. */
export function PhoneCard({ event, tags, onOpen }: { event: EventCard; tags: string[]; onOpen: () => void }) {
  const tag = orderTags(event.tags, tags.map((name) => ({ name })))[0];
  const price = event.is_cancelled ? null : formatPrice(event.price, event.currency);
  return (
    <article
      className={`card phone-card${event.is_cancelled ? " card--cancelled" : ""}${event.is_priority ? " card--priority" : ""}`}
      role="button"
      tabIndex={0}
      aria-label={event.title}
      onClick={onOpen}
      onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && e.target === e.currentTarget && onOpen()}
    >
      <div className="card__layout">
        <PhonePoster path={event.image_url} className="card__photo" />
        <div className="card__body phone-card__body">
          <div className="card__meta">
            <EventTime event={event} className="card__time" />
            <PlanMark event={event} />
            {event.is_priority && <PriorityBadge />}
          </div>
          <h3 className="card__title">{event.title}</h3>
          {(tag || price || event.is_cancelled) && (
            <div className="card__meta">
              {tag && <span className="badge">{tag}</span>}
              {event.is_cancelled ? <span className="badge badge--accent card__end">Cancelled</span> : price && <span className="card__price card__end">{price}</span>}
            </div>
          )}
        </div>
      </div>
    </article>
  );
}
