import { describe, expect, it } from "vitest";

import type { Occurrence } from "./client";
import { keepUnchangedCards } from "./cardCache";
import { event } from "../phone/fixtures";

const item = (id: number, date = "2026-11-20"): Occurrence => ({ event: event(id, `Event ${id}`, "maybe"), date }) as Occurrence;

describe("keepUnchangedCards", () => {
  it("keeps the cards after one that left the list, though they moved up", () => {
    const before = [item(1), item(2), item(3)];
    const after = keepUnchangedCards(before, [item(1), item(3)]) as Occurrence[];
    expect(after[0]).toBe(before[0]);
    expect(after[1]).toBe(before[2]);
  });

  it("gives a changed card a new object and keeps the rest", () => {
    const before = [item(1), item(2)];
    const changed = { ...item(2), event: { ...item(2).event, interest: 5 } };
    const after = keepUnchangedCards(before, [item(1), changed]) as Occurrence[];
    expect(after[0]).toBe(before[0]);
    expect(after[1]).not.toBe(before[1]);
    expect(after[1].event.interest).toBe(5);
  });

  it("keeps the whole list when nothing changed", () => {
    const before = [item(1), item(2)];
    expect(keepUnchangedCards(before, [item(1), item(2)])).toBe(before);
  });

  it("tells apart the days of a regular event", () => {
    const before = [item(1, "2026-11-20"), item(1, "2026-11-27")];
    const after = keepUnchangedCards(before, [item(1, "2026-11-27")]) as Occurrence[];
    expect(after[0]).toBe(before[1]);
  });
});
