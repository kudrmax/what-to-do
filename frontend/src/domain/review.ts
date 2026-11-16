import type { EventCard, Occurrence, Plan } from "../api/client";

export type ReviewPlan = Extract<Plan, "no" | "maybe" | "sure">;

/** What a review does with the card on top: a plan or an interest (the same marks as on a card in the list), or a skip to the next card. */
export type ReviewAnswer = { kind: "plan"; plan: ReviewPlan } | { kind: "interest"; value: number } | { kind: "skip" };
export type ReviewCommand = ReviewAnswer | { kind: "undo" } | { kind: "open" };

/** Where a card leaves to: the side it was swiped to. */
export type Exit = "left" | "right" | "up" | "down";

export interface ReviewItem {
  event: EventCard;
  day: string;
}

/**
 * The cards of the feed in its order, one by one: each event once, at its nearest day.
 * Which cards the feed holds is the feed's business; the review only steps past the ones it was told to.
 */
export function reviewQueue(occurrences: Occurrence[], passed: ReadonlySet<number>): ReviewItem[] {
  const seen = new Set<number>();
  const queue: ReviewItem[] = [];
  for (const { event, date } of occurrences) {
    if (seen.has(event.id)) continue;
    seen.add(event.id);
    if (!passed.has(event.id)) queue.push({ event, day: date });
  }
  return queue;
}

export function exitOf(answer: { kind: "plan"; plan: ReviewPlan } | { kind: "skip" }): Exit {
  if (answer.kind === "skip") return "down";
  return answer.plan === "no" ? "left" : answer.plan === "maybe" ? "right" : "up";
}

/** A swipe far enough in one direction answers the card; a short one puts it back. */
export const SWIPE_DISTANCE = 120;

export function swipeAnswer(dx: number, dy: number): { kind: "plan"; plan: ReviewPlan } | null {
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
