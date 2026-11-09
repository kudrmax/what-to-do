import { useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";

import type { EventDetail, Mention, Occurrence } from "../api/client";
import { useEvent, useFeed, useMerge, useSplit } from "../api/hooks";
import { EventImage } from "../components/EventImage";
import { EventTime } from "../components/EventTime";
import { Icon } from "../components/Icon";
import { InterestPicker, PlanPicker } from "../components/MarkControls";
import { useActiveCity } from "../api/useActiveCity";
import { ago, clock, dateRange, dayAndMonth, dayHeading, longDate } from "../domain/dates";
import { describeRecurrence } from "../domain/recurrence";
import "./EventScreen.css";

/** An open card next to the other events of its day. */
export function EventScreen() {
  const id = Number(useParams().id);
  const [params] = useSearchParams();
  const { today } = useActiveCity();
  const event = useEvent(id);
  const day = params.get("day") ?? event.data?.start_date ?? null;
  const dayEvents = useFeed({ start: day ?? undefined, end: day ?? undefined, hideMarked: false }, day !== null);

  return (
    <div className="event-screen">
      {day && today && <DayList day={day} today={today} items={dayEvents.data ?? []} currentId={id} />}
      {event.data ? <EventDetails event={event.data} day={day} dayEvents={dayEvents.data ?? []} /> : event.isError ? <p className="event-screen__missing">Этого события больше нет.</p> : null}
    </div>
  );
}

function DayList({ day, today, items, currentId }: { day: string; today: string; items: Occurrence[]; currentId: number }) {
  const heading = dayHeading(day, today);
  return (
    <nav className="day-list" aria-label={`События: ${heading.title}`}>
      <div className="day-list__heading">
        <h2>{heading.title}</h2>
        <span>{heading.title === "Сегодня" || heading.title === "Завтра" ? dayAndMonth(day) : heading.subtitle}</span>
      </div>
      {items.map(({ event }) => (
        <Link key={event.id} to={`/event/${event.id}?day=${day}`} className="day-list__item" aria-current={event.id === currentId ? "page" : undefined}>
          <EventTime event={event} className="day-list__time" iconSize={16} />
          <span className="day-list__title">{event.title}</span>
        </Link>
      ))}
    </nav>
  );
}

function EventDetails({ event, day, dayEvents }: { event: EventDetail; day: string | null; dayEvents: Occurrence[] }) {
  const recurrence = describeRecurrence(event.recurrence);
  const place = event.address ?? event.venue;
  return (
    <article className="details">
      <EventImage path={event.image_url} tag={event.tags[0]} className="details__image" />
      <div className="details__title-block">
        <h1 className={event.is_cancelled ? "details__title details__title--cancelled" : "details__title"}>{event.title}</h1>
        {event.is_cancelled && <span className="details__cancelled">Отменено</span>}
      </div>
      <div className="details__facts">
        <Fact icon="calendar">
          <strong>
            {event.kind === "multiday" && event.end_date ? dateRange(event.start_date, event.end_date) : event.start_time ? clock(event.start_time) : <EventTime event={event} iconSize={18} />}
          </strong>
          <span>{recurrence ?? (event.kind === "multiday" ? "можно прийти в любой день" : longDate(day ?? event.start_date))}</span>
        </Fact>
        {place && (
          <Fact icon="pin">
            <strong>{event.venue && event.address ? `${event.venue}, ${event.address}` : place}</strong>
            {event.map_url && (
              <a href={event.map_url} target="_blank" rel="noreferrer">
                Открыть в Google Картах
              </a>
            )}
          </Fact>
        )}
        {event.price && (
          <Fact icon="ticket">
            <strong>{event.price}</strong>
          </Fact>
        )}
      </div>
      {event.conflicts.map((conflict) => (
        <div key={conflict.field} className="details__conflict" role="note">
          <Icon name="alert" />
          {conflict.field === "start_time"
            ? `Источники расходятся во времени: ${conflict.values.join(" и ")}`
            : `Источники расходятся в дате: ${conflict.values.map((d) => dayAndMonth(d)).join(" и ")}`}
        </div>
      ))}
      <p className="details__description">{event.description}</p>
      <div className="details__marks">
        <div className="details__mark-group">
          <span>Интерес</span>
          <InterestPicker event={event} size="large" />
        </div>
        <div className="details__mark-group">
          <span>Статус</span>
          <PlanPicker event={event} size="large" />
        </div>
      </div>
      <Sources event={event} day={day} dayEvents={dayEvents} />
    </article>
  );
}

function Fact({ icon, children }: { icon: "calendar" | "pin" | "ticket"; children: React.ReactNode }) {
  return (
    <div className="fact">
      <Icon name={icon} className="fact__icon" />
      <div className="fact__text">{children}</div>
    </div>
  );
}

type Mode = "view" | "split" | "merge";

function Sources({ event, day, dayEvents }: { event: EventDetail; day: string | null; dayEvents: Occurrence[] }) {
  const [mode, setModeState] = useState<Mode>("view");
  const [mergeTarget, setMergeTarget] = useState<number | null>(null);
  const setMode = (next: Mode) => {
    setModeState(next);
    setMergeTarget(null);
  };
  const split = useSplit();
  const merge = useMerge();
  const navigate = useNavigate();
  const others = dayEvents.filter((item) => item.event.id !== event.id);

  return (
    <section className="sources">
      <div className="sources__header">
        <div className="sources__title">
          <h2>Источники</h2>
          <span className="sources__count">{event.mentions.length}</span>
        </div>
        <div className="sources__actions">
          {others.length > 0 && (
            <button type="button" className="sources__action" aria-pressed={mode === "merge"} onClick={() => setMode(mode === "merge" ? "view" : "merge")}>
              Склеить с…
            </button>
          )}
          {event.mentions.length > 1 && (
            <button type="button" className="sources__action" aria-pressed={mode === "split"} onClick={() => setMode(mode === "split" ? "view" : "split")}>
              Разделить
            </button>
          )}
        </div>
      </div>
      {mode === "merge" && (
        <div className="merge">
          <p>Это то же событие, что и…</p>
          {others.map(({ event: other }) => (
            <label key={other.id} className="merge__option">
              <input type="radio" name="merge-target" checked={mergeTarget === other.id} onChange={() => setMergeTarget(other.id)} />
              <EventTime event={other} className="merge__time" iconSize={16} />
              {other.title}
            </label>
          ))}
          <div className="merge__buttons">
            <button type="button" className="merge__cancel" onClick={() => setMode("view")}>
              Отмена
            </button>
            <button
              type="button"
              className="merge__confirm"
              disabled={mergeTarget === null || merge.isPending}
              onClick={() => mergeTarget !== null && merge.mutate({ id: event.id, otherId: mergeTarget }, { onSuccess: () => setMode("view") })}
            >
              Склеить
            </button>
          </div>
        </div>
      )}
      <div className="sources__grid">
        {event.mentions.map((mention) => (
          <SourceCard
            key={mention.id}
            mention={mention}
            onSplit={
              mode === "split"
                ? () =>
                    split.mutate(
                      { id: event.id, mentionId: mention.id },
                      {
                        onSuccess: (created) => {
                          setMode("view");
                          navigate(`/event/${created.id}?day=${day ?? created.start_date}`);
                        },
                      },
                    )
                : undefined
            }
          />
        ))}
      </div>
    </section>
  );
}

function SourceCard({ mention, onSplit }: { mention: Mention; onSplit?: () => void }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="source-card">
      <div className="source-card__top">
        <span className="source-card__name">{mention.source_title}</span>
        {mention.from_organizer && <span className="source-card__badge">организатор</span>}
      </div>
      <span className="source-card__original">{mention.original_title}</span>
      <span className="source-card__date">Опубликовано {ago(mention.published_at)}</span>
      {open && <p className="source-card__text">{mention.post_text}</p>}
      <div className="source-card__links">
        <button type="button" className="source-card__link" onClick={() => setOpen(!open)} aria-expanded={open}>
          {open ? "Свернуть пост" : "Текст поста"}
        </button>
        <a href={mention.post_url} target="_blank" rel="noreferrer" className="source-card__link">
          В Telegram
          <Icon name="external" size={13} />
        </a>
      </div>
      {onSplit && (
        <button type="button" className="source-card__split" onClick={onSplit}>
          Вынести в отдельное событие
        </button>
      )}
    </div>
  );
}
