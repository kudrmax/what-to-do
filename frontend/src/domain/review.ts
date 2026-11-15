import type { EventCard, Occurrence, Plan } from "../api/client";

/** What a review does with the card on top: a plan, an interest, a skip until the next review, or taking the last answer back. */
export type ReviewAnswer = { kind: "plan"; plan: Extract<Plan, "no" | "maybe" | "sure"> } | { kind: "interest"; value: number } | { kind: "skip" };
export type ReviewCommand = ReviewAnswer | { kind: "undo" } | { kind: "open" };

/** Where a card leaves to: the side it was swiped to. */
export type Exit = "left" | "right" | "up" | "down";

export interface ReviewItem {
  event: EventCard;
  day: string;
}

/**
 * The cards still to review, in the feed's order: each event once (a repeating one at its nearest day),
 * without the ones already answered in this review and without the ones the user has already rated or planned.
 * A card taken back by undo returns even though the feed may still show its old rating.
 */
export function reviewQueue(occurrences: Occurrence[], answered: ReadonlySet<number>, returned: ReadonlySet<number> = new Set()): ReviewItem[] {
  const seen = new Set<number>();
  const queue: ReviewItem[] = [];
  for (const { event, date } of occurrences) {
    if (seen.has(event.id)) continue;
    seen.add(event.id);
    if (answered.has(event.id)) continue;
    if ((event.interest != null || event.plan != null) && !returned.has(event.id)) continue;
    queue.push({ event, day: date });
  }
  return queue;
}

export function exitOf(answer: ReviewAnswer): Exit {
  if (answer.kind === "skip" || answer.kind === "interest") return "down";
  return answer.plan === "no" ? "left" : answer.plan === "maybe" ? "right" : "up";
}

/** A swipe far enough in one direction answers the card; a short one puts it back. */
export const SWIPE_DISTANCE = 120;

export function swipeAnswer(dx: number, dy: number): ReviewAnswer | null {
  if (-dy > SWIPE_DISTANCE && -dy > Math.abs(dx)) return { kind: "plan", plan: "sure" };
  if (dx > SWIPE_DISTANCE) return { kind: "plan", plan: "maybe" };
  if (dx < -SWIPE_DISTANCE) return { kind: "plan", plan: "no" };
  return null;
}

/** The keys of a review: arrows for plans, digits for interest, ↓ to skip, Enter or Space for the whole event, ⌘Z / Backspace to take back. */
export function keyCommand(key: string, modifiers: { meta: boolean; ctrl: boolean; alt: boolean; shift: boolean }): ReviewCommand | null {
  const command = modifiers.meta || modifiers.ctrl;
  if (command && !modifiers.alt && !modifiers.shift && key.toLowerCase() === "z") return { kind: "undo" };
  if (command || modifiers.alt) return null;
  if (key === "Backspace") return { kind: "undo" };
  if (key === "ArrowLeft") return { kind: "plan", plan: "no" };
  if (key === "ArrowRight") return { kind: "plan", plan: "maybe" };
  if (key === "ArrowUp") return { kind: "plan", plan: "sure" };
  if (key === "ArrowDown") return { kind: "skip" };
  if (key === "Enter" || key === " ") return { kind: "open" };
  if (/^[1-5]$/.test(key)) return { kind: "interest", value: Number(key) };
  return null;
}
