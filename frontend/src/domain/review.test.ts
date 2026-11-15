import { describe, expect, it } from "vitest";

import type { EventCard, Occurrence } from "../api/client";
import { exitOf, keyCommand, reviewQueue, swipeAnswer } from "./review";

const card = (id: number, interest: number | null = null, plan: string | null = null) => ({ id, interest, plan }) as unknown as EventCard;
const at = (event: EventCard, date: string): Occurrence => ({ event, date }) as Occurrence;
const none = { meta: false, ctrl: false, alt: false, shift: false };

describe("reviewQueue", () => {
  it("keeps the feed's order and shows a repeating event once, at its nearest day", () => {
    const weekly = card(1);
    const queue = reviewQueue([at(weekly, "2026-11-17"), at(card(2), "2026-11-18"), at(weekly, "2026-11-24")], new Set());
    expect(queue.map((item) => [item.event.id, item.day])).toEqual([
      [1, "2026-11-17"],
      [2, "2026-11-18"],
    ]);
  });

  it("leaves out cards already planned, which a search brings into the feed", () => {
    expect(reviewQueue([at(card(1, null, "no"), "2026-11-17"), at(card(2), "2026-11-17")], new Set()).map((item) => item.event.id)).toEqual([2]);
  });

  it("leaves out answered and already rated cards, but brings back one taken back by undo", () => {
    const feed = [at(card(1), "2026-11-17"), at(card(2, 4), "2026-11-17"), at(card(3, 3), "2026-11-18")];
    expect(reviewQueue(feed, new Set([1])).map((item) => item.event.id)).toEqual([]);
    expect(reviewQueue(feed, new Set([1]), new Set([3])).map((item) => item.event.id)).toEqual([3]);
  });
});

describe("swipeAnswer", () => {
  it("answers by direction once the card is pulled far enough", () => {
    expect(swipeAnswer(-200, 10)).toEqual({ kind: "plan", plan: "no" });
    expect(swipeAnswer(200, -10)).toEqual({ kind: "plan", plan: "maybe" });
    expect(swipeAnswer(30, -200)).toEqual({ kind: "plan", plan: "sure" });
    expect(swipeAnswer(60, -40)).toBeNull();
  });
});

describe("keyCommand", () => {
  it("maps arrows to plans and digits to interest", () => {
    expect(keyCommand("ArrowLeft", none)).toEqual({ kind: "plan", plan: "no" });
    expect(keyCommand("ArrowRight", none)).toEqual({ kind: "plan", plan: "maybe" });
    expect(keyCommand("ArrowUp", none)).toEqual({ kind: "plan", plan: "sure" });
    expect(keyCommand("ArrowDown", none)).toEqual({ kind: "skip" });
    expect(keyCommand("4", none)).toEqual({ kind: "interest", value: 4 });
    expect(keyCommand("6", none)).toBeNull();
  });

  it("takes back with ⌘Z or Backspace and leaves other shortcuts to the system", () => {
    expect(keyCommand("z", { ...none, meta: true })).toEqual({ kind: "undo" });
    expect(keyCommand("Backspace", none)).toEqual({ kind: "undo" });
    expect(keyCommand("3", { ...none, meta: true })).toBeNull();
    expect(keyCommand("ArrowLeft", { ...none, alt: true })).toBeNull();
  });
});

describe("exitOf", () => {
  it("sends a card off the way it was swiped", () => {
    expect(exitOf({ kind: "plan", plan: "no" })).toBe("left");
    expect(exitOf({ kind: "plan", plan: "maybe" })).toBe("right");
    expect(exitOf({ kind: "plan", plan: "sure" })).toBe("up");
    expect(exitOf({ kind: "interest", value: 5 })).toBe("down");
  });
});
