import { useState } from "react";
import { useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";

import type { EventCard, Mention } from "../api/client";
import { useApi, useEvent, useFeed, useMentions, useMerge, useSplit } from "../api/queries";
import { SECTIONS } from "../app/routes";
import { dayAndMonth, longDate } from "../domain/dates";
import { formatPrice } from "../domain/price";
import { describeRecurrence } from "../domain/recurrence";
import { Icon } from "../ui/Icon";
import { IconButton } from "../ui/IconButton";
import { Modal } from "../ui/Modal";
import { Popover } from "../ui/Popover";
import { EventTime } from "./EventTime";
import { DevNoteButton } from "./DevNoteButton";
import { InterestPicker, PlanPicker } from "./MarkPickers";
import { OpenPostButton } from "./OpenPostButton";
import { PhotoViewer, type ViewedPhoto } from "./PhotoViewer";
import { PostText } from "./PostText";
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

type View = (photos: ViewedPhoto[], start: number) => void;

function EventDetails({ event, day }: { event: EventCard; day: string }) {
  const mentions = useMentions(event.id).data ?? [];
  const [viewing, setViewing] = useState<{ photos: ViewedPhoto[]; start: number } | null>(null);
  return (
    <article className="details">
      <Head event={event} day={day} mentions={mentions} />
      <div className="details__marks">
        <div className="marks-row">
          <InterestPicker event={event} size="large" />
          <DevNoteButton event={event} size="large" />
        </div>
        <PlanPicker event={event} size="large" />
      </div>
      <Description event={event} day={day} mentions={mentions} onView={(photos, start) => setViewing({ photos, start })} />
      {viewing && <PhotoViewer photos={viewing.photos} start={viewing.start} onClose={() => setViewing(null)} />}
    </article>
  );
}

function Head({ event, day, mentions }: { event: EventCard; day: string; mentions: Mention[] }) {
  const api = useApi();
  const price = formatPrice(event.price, event.currency);
  const when = describeRecurrence(event.rrule) ?? (event.kind === "multiday" ? "Можно прийти в любой день" : longDate(day));
  return (
    <header className="details__head">
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
        <div className="fact">
          <Icon name="calendar" className="fact__icon" />
          <EventTime event={event} className="fact__main" />
          <span className="fact__sub">{when}</span>
        </div>
        {event.place && (
          <a className="fact fact--link" href={event.map_url ?? undefined} target="_blank" rel="noreferrer" data-tip="Открыть на карте">
            <Icon name="pin" className="fact__icon" />
            <span className="fact__main">{event.venue ?? event.address}</span>
            {event.venue && event.address && <span className="fact__sub">{event.address}</span>}
          </a>
        )}
        {price && (
          <div className="fact">
            <Icon name="ticket" className="fact__icon" />
            <span className="fact__main">{price}</span>
          </div>
        )}
      </div>

      {event.conflicts.map((conflict) => (
        <p key={conflict.field} className="note" role="note">
          <Icon name="alert" />
          {conflict.field === "start_time"
            ? `Источники расходятся во времени: ${conflict.values.join(" или ")}`
            : `Источники расходятся в дате: ${conflict.values.map(dayAndMonth).join(" или ")}`}
        </p>
      ))}

      <div className="details__actions">
        {event.booking ? (
          <a className="button" href={event.booking.url} target="_blank" rel="noreferrer">
            <Icon name="external" size={16} />
            {event.booking.kind === "tickets" ? "Купить билет" : "Записаться"}
          </a>
        ) : (
          <OpenPostButton mentions={mentions} />
        )}
        <a className="button button--quiet" href={api.calendarFileUrl(event.id)} download>
          <Icon name="calendarAdd" size={16} />В календарь
        </a>
      </div>
    </header>
  );
}

type Tab = "summary" | "original";

function Description({ event, day, mentions, onView }: { event: EventCard; day: string; mentions: Mention[]; onView: View }) {
  const [tab, setTab] = useState<Tab>("summary");
  const tabs: { id: Tab; label: string; count?: number }[] = [
    { id: "summary", label: "Кратко" },
    { id: "original", label: "Оригинал", count: mentions.length > 1 ? mentions.length : undefined },
  ];
  return (
    <section className="description">
      <div className="tabs" role="tablist" aria-label="Описание">
        {tabs.map((item) => (
          <button key={item.id} type="button" role="tab" className="tabs__tab" aria-selected={tab === item.id} onClick={() => setTab(item.id)}>
            {item.label}
            {item.count && <span className="chip__count">{item.count}</span>}
          </button>
        ))}
      </div>
      {tab === "summary" ? <Summary event={event} mentions={mentions} onView={onView} /> : <Originals event={event} day={day} mentions={mentions} onView={onView} />}
    </section>
  );
}

function Summary({ event, mentions, onView }: { event: EventCard; mentions: Mention[]; onView: View }) {
  const poster = event.image_url;
  const text = poster ? (mentions.flatMap((m) => m.photos).find((p) => p.url === poster)?.text ?? null) : null;
  return (
    <>
      {poster && (
        <div className="thumbs">
          <Thumb url={poster} label="Открыть афишу крупно" onClick={() => onView([{ url: poster, text }], 0)} />
        </div>
      )}
      <p className="details__description">{event.description}</p>
    </>
  );
}

function Originals({ event, day, mentions, onView }: { event: EventCard; day: string; mentions: Mention[]; onView: View }) {
  const [chosen, setChosen] = useState<number | null>(null);
  const shown = mentions.find((m) => m.id === chosen) ?? mentions[0];
  if (!shown) return null;
  const several = mentions.length > 1;
  const repeated = new Set(mentions.map((m) => m.source_title).filter((title, index, all) => all.indexOf(title) !== index));
  return (
    <>
      {several && (
        <div className="post-choice" role="tablist" aria-label="Посты об этом событии">
          {mentions.map((mention) => (
            <button key={mention.id} type="button" role="tab" className="chip" aria-pressed={mention.id === shown.id} aria-selected={mention.id === shown.id} onClick={() => setChosen(mention.id)}>
              {mention.source_title}
              {repeated.has(mention.source_title) && <span className="post-choice__date">{POSTED_DAY.format(new Date(mention.published_at))}</span>}
            </button>
          ))}
        </div>
      )}
      <PostLine event={event} day={day} mention={shown} named={!several} canSplit={several} />
      {shown.photos.length > 0 && (
        <div className="thumbs">
          {shown.photos.map((photo, index) => (
            <Thumb key={photo.url} url={photo.url} label={`Фото ${index + 1} из ${shown.photos.length}`} onClick={() => onView(shown.photos, index)} />
          ))}
        </div>
      )}
      <PostText key={shown.id} text={shown.post_text} highlighted={shown.event_lines} />
    </>
  );
}

const POSTED = new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "long", hour: "2-digit", minute: "2-digit" });
const POSTED_DAY = new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "long" });

function PostLine({ event, day, mention, named, canSplit }: { event: EventCard; day: string; mention: Mention; named: boolean; canSplit: boolean }) {
  const split = useSplit();
  const open = useOpenEvent();
  const posted = POSTED.format(new Date(mention.published_at));
  return (
    <div className="post-line">
      {named && <span className="post-line__name">{mention.source_title}</span>}
      {mention.data.from_organizer && <span className="badge badge--accent">организатор</span>}
      <span className="post-line__when">{named ? posted : `Пост от ${posted}`}</span>
      <span className="post-line__actions">
        <a className="icon-button" href={mention.post_url} target="_blank" rel="noreferrer" aria-label="Открыть пост в Telegram" data-tip="Открыть пост в Telegram">
          <Icon name="external" size={17} />
        </a>
        {canSplit &&
          (mention.data.start_date === null ? (
            <IconButton icon="split" label="В посте нет даты, отдельным событием он быть не может" aria-disabled />
          ) : (
            <IconButton icon="split" label="Вынести в отдельное событие" onClick={() => split.mutate({ id: event.id, mentionId: mention.id }, { onSuccess: (created) => open(created.id, day, true) })} />
          ))}
        <MergeMenu event={event} day={day} />
      </span>
    </div>
  );
}

function Thumb({ url, label, onClick }: { url: string; label: string; onClick: () => void }) {
  const api = useApi();
  const [broken, setBroken] = useState(false);
  if (broken) return null;
  return (
    <button type="button" className="thumb" aria-label={label} onClick={onClick}>
      <img src={api.imageUrl(url) ?? undefined} alt="" loading="lazy" onError={() => setBroken(true)} />
    </button>
  );
}

/** «Это то же событие, что и…»: choose a card of the same day, then confirm. */
function MergeMenu({ event, day }: { event: EventCard; day: string }) {
  const sameDay = useFeed({ start: day, end: day });
  const merge = useMerge();
  const [target, setTarget] = useState<number | null>(null);
  const others = (sameDay.data ?? []).filter((item) => item.event.id !== event.id);
  if (others.length === 0) return null;
  return (
    <Popover className="post-line__merge" trigger={(open, toggle) => <IconButton icon="merge" label="Склеить с другим событием этого дня" aria-pressed={open} onClick={toggle} />}>
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
