import { useEffect, useMemo, useRef, useState, type CSSProperties, type PointerEvent as ReactPointerEvent } from "react";

import type { Mark, Occurrence } from "../api/client";
import { usePrefetchMentions, useSetMark, useTags } from "../api/queries";
import { dayHeading, plural } from "../domain/dates";
import { PLANS } from "../domain/plans";
import { formatPrice } from "../domain/price";
import { exitOf, keyCommand, reviewQueue, swipeAnswer, SWIPE_DISTANCE, type Exit, type ReviewAnswer, type ReviewCommand, type ReviewItem } from "../domain/review";
import { orderTags } from "../domain/tags";
import { Icon, type IconName } from "../ui/Icon";
import { EmptyState } from "../ui/Screen";
import { EventPhoto } from "./EventPhoto";
import { EventTime } from "./EventTime";
import { useOpenEvent } from "./navigation";
import "./ReviewDeck.css";

const INTEREST = [1, 2, 3, 4, 5] as const;
const INTEREST_WORDS = ["Совсем неинтересно", "Скорее неинтересно", "Так себе", "Интересно", "Очень интересно"];
/** Cards drawn under the top one, so the deck looks like a deck. */
const DEPTH = 2;
const TAP_DISTANCE = 6;

interface Answered {
  item: ReviewItem;
  answer: ReviewAnswer;
  before: Mark;
}

interface Leaving {
  item: ReviewItem;
  exit: Exit;
  stamp: Stamp | null;
  interest: number | null;
  from: Drag;
  serial: number;
}

interface Drag {
  dx: number;
  dy: number;
}

type Stamp = "no" | "maybe" | "sure";

const STAMPS: Record<Stamp, string> = { no: "Не пойду", maybe: "Возможно", sure: "Точно пойду" };

const stampOf = (answer: ReviewAnswer): Stamp | null => (answer.kind === "plan" ? answer.plan : null);

function dragStamp({ dx, dy }: Drag): { stamp: Stamp; strength: number } | null {
  if (-dy > Math.abs(dx) && dy < 0) return { stamp: "sure", strength: Math.min(1, -dy / SWIPE_DISTANCE) };
  if (dx === 0) return null;
  return { stamp: dx > 0 ? "maybe" : "no", strength: Math.min(1, Math.abs(dx) / SWIPE_DISTANCE) };
}

/** An event, a photo or a dialog opened over the deck takes the keys; the deck lives under the event's address, so it asks the window. */
const somethingOver = () => window.location.pathname.startsWith("/event/") || !!document.querySelector("[aria-modal='true']");

const isTyping = (target: EventTarget | null) => {
  const element = target as HTMLElement | null;
  return !!element && (element.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(element.tagName));
};

/**
 * The feed one card at a time: swipe or press ← for «не пойду», → for «возможно пойду», ↑ for «точно пойду»,
 * a digit for interest, ↓ to leave it for later. Each answer brings the next card; ⌘Z takes the last one back.
 */
export function ReviewDeck({ occurrences, today }: { occurrences: Occurrence[]; today: string }) {
  const setMark = useSetMark();
  const open = useOpenEvent();
  const prefetch = usePrefetchMentions();
  const [answeredIds, setAnsweredIds] = useState<ReadonlySet<number>>(new Set());
  const [returnedIds, setReturnedIds] = useState<ReadonlySet<number>>(new Set());
  const [history, setHistory] = useState<Answered[]>([]);
  const [leaving, setLeaving] = useState<Leaving[]>([]);
  const [arriving, setArriving] = useState<{ id: number; from: Exit } | null>(null);
  const [drag, setDrag] = useState<Drag | null>(null);
  const serial = useRef(0);

  const queue = useMemo(() => reviewQueue(occurrences, answeredIds, returnedIds), [occurrences, answeredIds, returnedIds]);
  const top = queue[0];
  const done = history.length;

  useEffect(() => {
    if (top) prefetch(top.event.id);
  }, [top, prefetch]);

  const without = (id: number) => (ids: ReadonlySet<number>) => new Set([...ids].filter((other) => other !== id));

  const answer = (item: ReviewItem, given: ReviewAnswer, from: Drag = { dx: 0, dy: 0 }) => {
    const { event } = item;
    const before: Mark = { interest: event.interest ?? null, plan: event.plan ?? null };
    setAnsweredIds((ids) => new Set(ids).add(event.id));
    setReturnedIds(without(event.id));
    setHistory((past) => [...past, { item, answer: given, before }]);
    setLeaving((cards) => [...cards, { item, exit: exitOf(given), stamp: stampOf(given), interest: given.kind === "interest" ? given.value : null, from, serial: ++serial.current }]);
    setArriving(null);
    const mark = given.kind === "plan" ? { ...before, plan: given.plan } : given.kind === "interest" ? { ...before, interest: given.value } : null;
    if (mark) {
      setMark.mutate(
        { id: event.id, mark },
        {
          onError: () => {
            setAnsweredIds(without(event.id));
            setHistory((past) => past.filter((entry) => entry.item.event.id !== event.id));
          },
        },
      );
    }
  };

  const undo = () => {
    const last = history.at(-1);
    if (!last) return;
    const { event } = last.item;
    setHistory((past) => past.slice(0, -1));
    setAnsweredIds(without(event.id));
    setReturnedIds((ids) => new Set(ids).add(event.id));
    setLeaving((cards) => cards.filter((card) => card.item.event.id !== event.id));
    setArriving({ id: event.id, from: exitOf(last.answer) });
    if (last.answer.kind !== "skip") setMark.mutate({ id: event.id, mark: last.before });
  };

  const run = (command: ReviewCommand) => {
    if (command.kind === "undo") return undo();
    if (!top) return;
    if (command.kind === "open") return open(top.event.id, top.day);
    answer(top, command);
  };

  const runRef = useRef(run);
  useEffect(() => {
    runRef.current = run;
  });

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.repeat || e.defaultPrevented || isTyping(e.target) || somethingOver()) return;
      const command = keyCommand(e.key, { meta: e.metaKey, ctrl: e.ctrlKey, alt: e.altKey, shift: e.shiftKey });
      if (!command) return;
      const onButton = (e.target as HTMLElement | null)?.closest?.("button, a, [role=link]");
      if (command.kind === "open" && onButton) return;
      e.preventDefault();
      runRef.current(command);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const pulled = drag ? dragStamp(drag) : null;
  const hot = (stamp: Stamp) => pulled?.stamp === stamp && pulled.strength >= 1;
  const left = queue.length;
  const total = done + left;

  return (
    <div className="review">
      <div className="review__progress" aria-live="polite" hidden={!top}>
        <div className="review__bar" role="progressbar" aria-valuemin={0} aria-valuemax={total} aria-valuenow={done} aria-label="Разобрано">
          <div className="review__bar-fill" style={{ width: total ? `${(done / total) * 100}%` : "0%" }} />
        </div>
        <span className="review__left">
          <strong>{left}</strong> {plural(left, "осталась", "осталось", "осталось")}
        </span>
      </div>

      <div className="review__deck">
        {top ? (
          queue
            .slice(0, DEPTH + 1)
            .reverse()
            .map((item) => {
              const depth = queue.indexOf(item);
              const isTop = depth === 0;
              return (
                <ReviewCard
                  key={item.event.id}
                  item={item}
                  today={today}
                  depth={depth}
                  drag={isTop ? drag : null}
                  arrivingFrom={isTop && arriving?.id === item.event.id ? arriving.from : null}
                  onDrag={isTop ? setDrag : undefined}
                  onRelease={
                    isTop
                      ? (released) => {
                          setDrag(null);
                          const swiped = swipeAnswer(released.dx, released.dy);
                          if (swiped) answer(item, swiped, released);
                          else if (Math.hypot(released.dx, released.dy) < TAP_DISTANCE) open(item.event.id, item.day);
                        }
                      : undefined
                  }
                  onInterest={isTop ? (value) => answer(item, { kind: "interest", value }) : undefined}
                />
              );
            })
        ) : (
          <div className="review__done">
            <EmptyState
              title="Всё разобрано"
              text={done ? `За этот разбор — ${done} ${plural(done, "карточка", "карточки", "карточек")}. Новые появятся после «Обновить».` : "Неразмеченных событий впереди нет, или их скрывают фильтры."}
              action={history.length ? { label: "Вернуть последнюю", onClick: undo } : undefined}
            />
          </div>
        )}
        {leaving.map((card) => (
          <ReviewCard
            key={`leaving-${card.serial}`}
            item={card.item}
            today={today}
            depth={0}
            leaving={card}
            onGone={() => setLeaving((cards) => cards.filter((other) => other.serial !== card.serial))}
          />
        ))}
      </div>

      <div className="review__controls" hidden={!top}>
        <RoundAction icon="undo" label="Вернуть" hint="⌘Z" size="small" disabled={!history.length} onClick={undo} />
        <RoundAction icon={PLANS.no.icon} label="Не пойду" hint="←" tone="no" hot={hot("no")} disabled={!top} onClick={() => top && answer(top, { kind: "plan", plan: "no" })} />
        <RoundAction icon={PLANS.sure.icon} label="Точно пойду" hint="↑" tone="sure" size="middle" hot={hot("sure")} disabled={!top} onClick={() => top && answer(top, { kind: "plan", plan: "sure" })} />
        <RoundAction icon={PLANS.maybe.icon} label="Возможно" hint="→" tone="maybe" hot={hot("maybe")} disabled={!top} onClick={() => top && answer(top, { kind: "plan", plan: "maybe" })} />
        <RoundAction icon="arrowDown" label="Позже" hint="↓" size="small" disabled={!top} onClick={() => top && answer(top, { kind: "skip" })} />
      </div>
    </div>
  );
}

function RoundAction({
  icon,
  label,
  hint,
  tone = "plain",
  size = "large",
  hot = false,
  disabled,
  onClick,
}: {
  icon: IconName;
  label: string;
  hint: string;
  tone?: "plain" | "no" | "maybe" | "sure";
  size?: "small" | "middle" | "large";
  hot?: boolean;
  disabled: boolean;
  onClick: () => void;
}) {
  const iconSize = size === "large" ? 28 : size === "middle" ? 22 : 18;
  return (
    <div className={`review-action review-action--${size}`}>
      <div className="review-action__slot">
        <button type="button" className={`review-action__button review-action__button--${tone}${hot ? " review-action__button--hot" : ""}`} aria-label={label} disabled={disabled} onClick={onClick}>
          <Icon name={icon} size={iconSize} strokeWidth={2.4} />
        </button>
      </div>
      <div className="review-action__caption">
        <span className="review-action__label">{label}</span>
        <kbd className="review-action__key">{hint}</kbd>
      </div>
    </div>
  );
}

interface CardProps {
  item: ReviewItem;
  today: string;
  depth: number;
  drag?: Drag | null;
  arrivingFrom?: Exit | null;
  leaving?: Leaving;
  onDrag?: (drag: Drag | null) => void;
  onRelease?: (drag: Drag) => void;
  onInterest?: (value: number) => void;
  onGone?: () => void;
}

function ReviewCard({ item, today, depth, drag, arrivingFrom, leaving, onDrag, onRelease, onInterest, onGone }: CardProps) {
  const { event, day } = item;
  const tags = orderTags(event.tags, useTags().data);
  const price = event.is_cancelled ? null : formatPrice(event.price, event.currency);
  const heading = dayHeading(day, today);
  const start = useRef<{ x: number; y: number; id: number } | null>(null);
  const live = leaving ? (leaving.stamp ? { stamp: leaving.stamp, strength: 1 } : null) : drag ? dragStamp(drag) : null;

  const onPointerDown = (e: ReactPointerEvent<HTMLElement>) => {
    if (!onDrag || e.button !== 0 || (e.target as HTMLElement).closest("button")) return;
    start.current = { x: e.clientX, y: e.clientY, id: e.pointerId };
    e.currentTarget.setPointerCapture(e.pointerId);
    onDrag({ dx: 0, dy: 0 });
  };
  const offset = (e: ReactPointerEvent<HTMLElement>): Drag | null => (start.current ? { dx: e.clientX - start.current.x, dy: e.clientY - start.current.y } : null);
  const onPointerMove = (e: ReactPointerEvent<HTMLElement>) => {
    const moved = offset(e);
    if (moved) onDrag?.(moved);
  };
  const onPointerUp = (e: ReactPointerEvent<HTMLElement>) => {
    const moved = offset(e);
    start.current = null;
    if (moved) onRelease?.(moved);
  };
  const onPointerCancel = () => {
    start.current = null;
    onDrag?.(null);
  };

  const from = leaving?.from ?? drag ?? { dx: 0, dy: 0 };
  const style = {
    "--x": `${from.dx}px`,
    "--y": `${from.dy}px`,
    "--r": `${from.dx / 18}deg`,
    "--depth": depth,
  } as CSSProperties;

  const classes = [
    "review-card",
    depth > 0 && "review-card--under",
    drag && "review-card--dragging",
    leaving && `review-card--leaving review-card--to-${leaving.exit}`,
    arrivingFrom && `review-card--from-${arrivingFrom}`,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <article
      className={classes}
      style={style}
      aria-hidden={depth > 0 || !!leaving}
      aria-label={depth === 0 && !leaving ? event.title : undefined}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerCancel}
      onAnimationEnd={(e) => e.target === e.currentTarget && leaving && onGone?.()}
    >
      <EventPhoto path={event.image_url} className="review-card__photo" />
      <div className="review-card__body">
        <div className="review-card__when">
          {event.kind !== "multiday" && <span className={`review-card__day${heading.relative ? " review-card__day--soon" : ""}`}>{heading.title}</span>}
          {event.kind !== "multiday" && <span className="review-card__weekday">{heading.subtitle}</span>}
          <EventTime event={event} className="review-card__time" />
          {event.is_cancelled ? <span className="badge badge--accent review-card__end">Отменено</span> : price && <span className="review-card__price review-card__end">{price}</span>}
        </div>
        <h2 className="review-card__title">{event.title}</h2>
        {tags.length > 0 && (
          <div className="review-card__tags">
            {tags.slice(0, 4).map((tag) => (
              <span key={tag} className="badge">
                {tag}
              </span>
            ))}
          </div>
        )}
        <p className="review-card__text">{event.description}</p>
        {event.place && (
          <p className="review-card__place">
            <Icon name="pin" size={16} />
            <span>{event.place}</span>
          </p>
        )}
        <div className="review-card__interest" role="group" aria-label="Интерес">
          <span className="review-card__interest-label" aria-hidden>
            Интерес
          </span>
          {INTEREST.map((n) => (
            <button key={n} type="button" tabIndex={depth === 0 && !leaving ? 0 : -1} data-tip={INTEREST_WORDS[n - 1]} aria-label={INTEREST_WORDS[n - 1]} aria-pressed={leaving?.interest === n} onClick={() => onInterest?.(n)}>
              {n}
            </button>
          ))}
        </div>
      </div>
      {live && (
        <span className={`review-stamp review-stamp--${live.stamp}`} style={{ opacity: live.strength }} aria-hidden>
          {STAMPS[live.stamp]}
        </span>
      )}
    </article>
  );
}
