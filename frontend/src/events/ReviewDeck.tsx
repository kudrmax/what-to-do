import { useEffect, useMemo, useRef, useState, type CSSProperties, type PointerEvent as ReactPointerEvent } from "react";

import type { EventCard, Mark, Occurrence } from "../api/client";
import { usePrefetchMentions, useSetMark } from "../api/queries";
import { dayHeading, plural } from "../domain/dates";
import { INTEREST, INTEREST_WORDS, nextMark, PLANS } from "../domain/plans";
import { exitOf, keyCommand, reviewQueue, swipeAnswer, SWIPE_DISTANCE, type Exit, type ReviewAnswer, type ReviewCommand, type ReviewItem } from "../domain/review";
import { Icon, type IconName } from "../ui/Icon";
import { EmptyState } from "../ui/Screen";
import { DevNoteButton } from "./DevNoteButton";
import { EventCardSummary } from "./EventCardView";
import { EventPhoto } from "./EventPhoto";
import { useOpenEvent } from "./navigation";
import "./ReviewDeck.css";

/** Cards drawn under the top one, so the deck looks like a deck. */
const DEPTH = 2;
const TAP_DISTANCE = 6;

interface Answered {
  event: EventCard;
  answer: ReviewAnswer;
  before: Mark;
}

interface Leaving {
  item: ReviewItem;
  exit: Exit;
  stamp: Stamp | null;
  from: Drag;
  serial: number;
}

interface Drag {
  dx: number;
  dy: number;
}

type Stamp = "no" | "maybe" | "sure";

const STAMPS: Record<Stamp, string> = { no: "Not going", maybe: "Maybe", sure: "Going" };

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
 * The feed one card at a time: swipe or press ← for not going, → for maybe going, ↑ for going for sure,
 * a digit for interest, ↓ to step to the next card. A card leaves the deck when it leaves the feed, as in the list; ⌘Z takes the last answer back.
 */
export function ReviewDeck({ occurrences, updatedAt, today, shownTags }: { occurrences: Occurrence[]; updatedAt: number; today: string; shownTags?: string[] }) {
  const setMark = useSetMark();
  const open = useOpenEvent();
  const prefetch = usePrefetchMentions();
  const [skipped, setSkipped] = useState<ReadonlySet<number>>(new Set());
  const [waiting, setWaiting] = useState<ReadonlyMap<number, number>>(new Map());
  const [history, setHistory] = useState<Answered[]>([]);
  const [leaving, setLeaving] = useState<Leaving[]>([]);
  const [arriving, setArriving] = useState<{ id: number; from: Exit } | null>(null);
  const [drag, setDrag] = useState<Drag | null>(null);
  const serial = useRef(0);
  const saving = useRef<Promise<unknown>>(Promise.resolve());

  /** A card sent off with a plan stays off only until the feed comes back from the server; then the feed alone says whether it is still there. */
  const passed = useMemo(() => {
    const ids = new Set(skipped);
    waiting.forEach((answeredAt, id) => answeredAt >= updatedAt && ids.add(id));
    return ids;
  }, [skipped, waiting, updatedAt]);
  const queue = useMemo(() => reviewQueue(occurrences, passed), [occurrences, passed]);
  const top = queue[0];
  const done = history.filter((entry) => entry.answer.kind !== "interest").length;

  useEffect(() => {
    if (top) prefetch(top.event.id);
  }, [top, prefetch]);

  const stopWaiting = (id: number) => setWaiting((ids) => new Map([...ids].filter(([other]) => other !== id)));

  /** Marks are saved one after another, so a quick undo never lands before the answer it takes back. */
  const save = (id: number, mark: Mark, onError?: () => void) => {
    saving.current = saving.current.then(() => setMark.mutateAsync({ id, mark })).catch(() => onError?.());
  };

  const sendOff = (item: ReviewItem, exit: Exit, stamp: Stamp | null, from: Drag) => {
    setLeaving((cards) => [...cards, { item, exit, stamp, from, serial: ++serial.current }]);
    setArriving(null);
  };

  const answer = (item: ReviewItem, given: ReviewAnswer, from: Drag = { dx: 0, dy: 0 }) => {
    const { event } = item;
    const before: Mark = { interest: event.interest ?? null, plan: event.plan ?? null };
    setHistory((past) => [...past, { event, answer: given, before }]);
    if (given.kind === "skip") {
      setSkipped((ids) => new Set(ids).add(event.id));
      sendOff(item, exitOf(given), null, from);
      return;
    }
    if (given.kind === "plan") {
      setWaiting((ids) => new Map(ids).set(event.id, updatedAt));
      sendOff(item, exitOf(given), given.plan, from);
    }
    const mark = nextMark(event, given.kind === "plan" ? { plan: given.plan } : { interest: given.value });
    save(event.id, mark, () => {
      stopWaiting(event.id);
      setHistory((past) => past.filter((entry) => entry.event.id !== event.id));
    });
  };

  const undo = () => {
    const last = history.at(-1);
    if (!last) return;
    const { event, answer: given } = last;
    setHistory((past) => past.slice(0, -1));
    if (given.kind === "interest") return save(event.id, last.before);
    setLeaving((cards) => cards.filter((card) => card.item.event.id !== event.id));
    setArriving({ id: event.id, from: exitOf(given) });
    if (given.kind === "skip") {
      setSkipped((ids) => new Set([...ids].filter((id) => id !== event.id)));
      return;
    }
    stopWaiting(event.id);
    save(event.id, last.before);
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
  const heading = top && dayHeading(top.day, today);

  return (
    <div className="review">
      <div className="review__progress" aria-live="polite" hidden={!top}>
        <div className="review__bar" role="progressbar" aria-valuemin={0} aria-valuemax={total} aria-valuenow={done} aria-label="Reviewed">
          <div className="review__bar-fill" style={{ width: total ? `${(done / total) * 100}%` : "0%" }} />
        </div>
        <span className="review__left">
          <strong>{left}</strong> left
        </span>
      </div>

      {heading && (
        <h2 className="day-heading review__day">
          <span className="section-title">{heading.title}</span>
          <span className="day-heading__sub">{heading.subtitle}</span>
        </h2>
      )}

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
                  shownTags={shownTags}
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
              title="All caught up"
              text={done ? `${done} ${plural(done, "card", "cards")} reviewed this time. New ones arrive with Refresh.` : "No unmarked events ahead, or filters are hiding them."}
              action={history.length ? { label: "Undo the last one", onClick: undo } : undefined}
            />
          </div>
        )}
        {leaving.map((card) => (
          <ReviewCard
            key={`leaving-${card.serial}`}
            item={card.item}
            shownTags={shownTags}
            depth={0}
            leaving={card}
            onGone={() => setLeaving((cards) => cards.filter((other) => other.serial !== card.serial))}
          />
        ))}
      </div>

      <div className="review__controls" hidden={!top}>
        <RoundAction icon="undo" label="Undo" hint="⌘Z" size="small" disabled={!history.length} onClick={undo} />
        <RoundAction icon={PLANS.no.icon} label="Not going" hint="←" tone="no" hot={hot("no")} disabled={!top} onClick={() => top && answer(top, { kind: "plan", plan: "no" })} />
        <RoundAction icon={PLANS.sure.icon} label="For sure" hint="↑" tone="sure" size="middle" hot={hot("sure")} disabled={!top} onClick={() => top && answer(top, { kind: "plan", plan: "sure" })} />
        <RoundAction icon={PLANS.maybe.icon} label="Maybe" hint="→" tone="maybe" hot={hot("maybe")} disabled={!top} onClick={() => top && answer(top, { kind: "plan", plan: "maybe" })} />
        <RoundAction icon="arrowDown" label="Later" hint="↓" size="small" disabled={!top} onClick={() => top && answer(top, { kind: "skip" })} />
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
  shownTags?: string[];
  depth: number;
  drag?: Drag | null;
  arrivingFrom?: Exit | null;
  leaving?: Leaving;
  onDrag?: (drag: Drag | null) => void;
  onRelease?: (drag: Drag) => void;
  onInterest?: (value: number) => void;
  onGone?: () => void;
}

function ReviewCard({ item, shownTags, depth, drag, arrivingFrom, leaving, onDrag, onRelease, onInterest, onGone }: CardProps) {
  const { event } = item;
  const active = depth === 0 && !leaving;
  const start = useRef<{ x: number; y: number; id: number } | null>(null);
  const live = leaving ? (leaving.stamp ? { stamp: leaving.stamp, strength: 1 } : null) : drag ? dragStamp(drag) : null;

  const onPointerDown = (e: ReactPointerEvent<HTMLElement>) => {
    if (!onDrag || e.button !== 0 || !e.currentTarget.contains(e.target as Node) || (e.target as HTMLElement).closest("button")) return;
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
      aria-label={active ? event.title : undefined}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerCancel}
      onAnimationEnd={(e) => e.target === e.currentTarget && leaving && onGone?.()}
    >
      <EventPhoto path={event.image_url} className="review-card__photo" />
      <div className="review-card__body">
        <EventCardSummary event={event} shownTags={shownTags} />
        <div className="review-card__interest" role="group" aria-label="Interest">
          {INTEREST.map((n) => (
            <button key={n} type="button" tabIndex={active ? 0 : -1} data-tip={INTEREST_WORDS[n]} aria-label={INTEREST_WORDS[n]} aria-pressed={event.interest === n} onClick={() => onInterest?.(n)}>
              {n}
            </button>
          ))}
          {active && <DevNoteButton event={event} size="large" />}
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
