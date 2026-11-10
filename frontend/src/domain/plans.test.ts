import { describe, expect, it } from "vitest";

import { plansToShow, SHOWN_PLANS } from "./plans";

describe("plansToShow", () => {
  it("keeps the list's own plans without a search", () => {
    expect(plansToShow(SHOWN_PLANS.feed, "")).toEqual(["none"]);
    expect(plansToShow(SHOWN_PLANS.calendar, "   ")).toEqual(["none", "maybe", "sure"]);
  });

  it("looks through every mark, «не пойду» included, when searching", () => {
    expect(plansToShow(SHOWN_PLANS.feed, "Музыкальная")).toEqual([]);
    expect(plansToShow(SHOWN_PLANS.going, "Шуман")).toEqual([]);
  });
});
