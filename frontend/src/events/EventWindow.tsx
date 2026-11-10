import { useState } from "react";
import { useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";

import type { EventCard, Mention } from "../api/client";
import { useApi, useEvent, useFeed, useMentions, useMerge, useSplit } from "../api/queries";
import { SECTIONS } from "../app/routes";
import { ago, dayAndMonth, longDate } from "../domain/dates";
import { formatPrice } from "../domain/price";
import { describeRecurrence } from "../domain/recurrence";
import { Icon } from "../ui/Icon";
import { IconButton } from "../ui/IconButton";
import { Modal } from "../ui/Modal";
import { Popover } from "../ui/Popover";
import { EventPhoto } from "./EventPhoto";
import { EventTime } from "./EventTime";
import { InterestPicker, PlanPicker } from "./MarkPickers";
import { OpenPostButton } from "./OpenPostButton";
import { useOpenEvent } from "./navigation";
import "./EventWindow.css";

/** An event opened in a window over the list it was opened from. */
export function EventWindow() {
  const id = Number(useParams().id);
  const [params] = useSearchParams();
  const location = useLocation();
  const navigate = useNavigate();
  const event = useEvent(id);
  const close = () => ((location.state as { background?: unknown } | null)?.background ? navigate(-1) : navigate(SECTIONS.feed.path));
  const day = params.get("day") ?? event.data?.start_date ?? "";

  return (
    <Modal label={event.data?.title ?? "Событие"} onClose={close}>
      {event.data ? <EventDetails event={event.data} day={day} /> : <p className="details__missing">{event.isError ? "Этого события больше нет." : "Загружаю…"}</p>}
    </Modal>
  );
}

function EventDetails({ event, day }: { event: EventCard; day: string }) {
  const recurrence = describeRecurrence(event.rrule);
  const price = formatPrice(event.price, event.currency);
  const api = useApi();
  const mentions = useMentions(event.id);
  return (
    <article className="details">
      <EventPhoto path={event.image_url} className="details__photo" />
      <div className="details__body">
        <div className="details__badges">
          {event.tags.map((tag) => (
            <span key={tag} className="badge">
              {tag}
            </span>
          ))}
          {event.is_cancelled && <span className="badge badge--accent">Отменено</span>}
        </div>
        <h2 className={`details__title${event.is_cancelled ? " details__title--cancelled" : ""}`}>{event.title}</h2>

        <div className="details__facts">
          <a className="fact fact--link" href={api.calendarFileUrl(event.id)} download aria-label="Добавить в календарь" data-tip="Добавить в календарь">
            <Icon name="calendar" className="fact__icon" />
            <div className="fact__text">
              <EventTime event={event} className="fact__main" />
              <span className="fact__sub">{recurrence ?? (event.kind === "multiday" ? "Можно прийти в любой день" : longDate(day))}</span>
            </div>
            <Icon name="calendarAdd" size={14} className="fact__external" />
          </a>
          {event.place && (
            <a className="fact fact--link" href={event.map_url ?? undefined} target="_blank" rel="noreferrer" data-tip="Открыть на карте">
              <Icon name="pin" className="fact__icon" />
              <span className="fact__main">{event.place}</span>
              <Icon name="external" size={14} className="fact__external" />
            </a>
          )}
          {price && (
            <div className="fact">
              <Icon name="ticket" className="fact__icon" />
              <span className="fact__main">{price}</span>
            </div>
          )}
        </div>

        <OpenPostButton mentions={mentions.data ?? []} />

        {event.conflicts.map((conflict) => (
          <p key={conflict.field} className="note" role="note">
            <Icon name="alert" />
            {conflict.field === "start_time"
              ? `Источники расходятся во времени: ${conflict.values.join(" или ")}`
              : `Источники расходятся в дате: ${conflict.values.map(dayAndMonth).join(" или ")}`}
          </p>
        ))}

        <p className="details__description">{event.description}</p>

        <div className="details__marks">
          <InterestPicker event={event} size="large" />
          <PlanPicker event={event} size="large" />
        </div>

        <Sources event={event} day={day} />
      </div>
    </article>
  );
}

function Sources({ event, day }: { event: EventCard; day: string }) {
  const mentions = useMentions(event.id);
  const split = useSplit();
  const open = useOpenEvent();
  const list = mentions.data ?? [];
  return (
    <section className="sources">
      <div className="sources__head">
        <h3 className="section-title">Источники</h3>
        <span className="badge">{list.length}</span>
        <MergeMenu event={event} day={day} />
      </div>
      <div className="sources__list">
        {list.map((mention) => (
          <SourceRow
            key={mention.id}
            mention={mention}
            onSplit={list.length > 1 ? () => split.mutate({ id: event.id, mentionId: mention.id }, { onSuccess: (created) => open(created.id, day, true) }) : undefined}
          />
        ))}
      </div>
    </section>
  );
}

function SourceRow({ mention, onSplit }: { mention: Mention; onSplit?: () => void }) {
  const [reading, setReading] = useState(false);
  return (
    <div className="source-row">
      <div className="source-row__line">
        <div className="source-row__who">
          <div className="source-row__top">
            <span className="source-row__name">{mention.source_title}</span>
            {mention.data.from_organizer && <span className="badge badge--accent">организатор</span>}
            <span className="source-row__when">{ago(mention.published_at)}</span>
          </div>
          <span className="source-row__original">{mention.data.original_title}</span>
        </div>
        <div className="source-row__actions">
          <IconButton icon="text" label={reading ? "Скрыть текст поста" : "Показать текст поста"} aria-pressed={reading} onClick={() => setReading(!reading)} />
          <a className="icon-button" href={mention.post_url} target="_blank" rel="noreferrer" aria-label="Открыть пост в Telegram" data-tip="Открыть пост в Telegram">
            <Icon name="external" size={17} />
          </a>
          {onSplit && <SplitButton mention={mention} onSplit={onSplit} />}
        </div>
      </div>
      {reading && <p className="source-row__text">{mention.post_text}</p>}
    </div>
  );
}

/** «Это то же событие, что и…»: choose a card of the same day, then confirm. */
/** A post that only follows up on the event has no date of its own, so it cannot become an event. */
function SplitButton({ mention, onSplit }: { mention: Mention; onSplit: () => void }) {
  return mention.data.start_date === null ? (
    <IconButton icon="split" label="В посте нет даты, отдельным событием он быть не может" aria-disabled />
  ) : (
    <IconButton icon="split" label="Вынести в отдельное событие" onClick={onSplit} />
  );
}

function MergeMenu({ event, day }: { event: EventCard; day: string }) {
  const sameDay = useFeed({ start: day, end: day });
  const merge = useMerge();
  const [target, setTarget] = useState<number | null>(null);
  const others = (sameDay.data ?? []).filter((item) => item.event.id !== event.id);
  if (others.length === 0) return null;
  return (
    <Popover
      className="sources__merge"
      trigger={(open, toggle) => <IconButton icon="merge" label="Склеить с другим событием этого дня" aria-pressed={open} onClick={toggle} />}
    >
      {(close) => (
        <div className="merge">
          <p className="label merge__question">Это то же событие, что и…</p>
          {others.map(({ event: other }) => (
            <label key={other.id} className="popover__item">
              <input type="radio" name="merge-target" checked={target === other.id} onChange={() => setTarget(other.id)} />
              <EventTime event={other} className="merge__time" iconSize={15} />
              <span>{other.title}</span>
            </label>
          ))}
          <div className="popover__footer merge__buttons">
            <button type="button" className="button button--small button--quiet" onClick={close}>
              Отмена
            </button>
            <button
              type="button"
              className="button button--small"
              disabled={target === null || merge.isPending}
              onClick={() => target !== null && merge.mutate({ id: event.id, otherId: target }, { onSuccess: close })}
            >
              Склеить
            </button>
          </div>
        </div>
      )}
    </Popover>
  );
}
