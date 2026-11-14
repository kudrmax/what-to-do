import { describe, expect, it } from "vitest";

import type { Tag } from "../api/client";
import { moved, orderTags } from "./tags";

const tag = (id: number, name: string, is_fallback = false): Tag => ({ id, name, is_fallback, hidden: false });
const settings = [tag(1, "Кино"), tag(2, "Концерт"), tag(3, "Лекция"), tag(4, "не распознано", true)];

describe("orderTags", () => {
  it("puts a card's tags in the settings order", () => {
    expect(orderTags(["Лекция", "Кино"], settings)).toEqual(["Кино", "Лекция"]);
  });

  it("keeps unknown tags last and the card's own order while tags are loading", () => {
    expect(orderTags(["Танцы", "Концерт"], settings)).toEqual(["Концерт", "Танцы"]);
    expect(orderTags(["Лекция", "Кино"], undefined)).toEqual(["Лекция", "Кино"]);
  });
});

describe("moved", () => {
  it("moves an item up and down", () => {
    expect(moved(["a", "b", "c"], 2, 0)).toEqual(["c", "a", "b"]);
    expect(moved(["a", "b", "c"], 0, 1)).toEqual(["b", "a", "c"]);
  });
});
