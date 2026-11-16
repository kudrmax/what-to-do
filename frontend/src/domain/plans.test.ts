import { describe, expect, it } from "vitest";

import { nextMark, plansToShow, SHOWN_PLANS } from "./plans";

describe("plansToShow", () => {
  it("keeps the list's own plans without a search", () => {
    expect(plansToShow(SHOWN_PLANS.feed, "")).toEqual(["none"]);
    expect(plansToShow(SHOWN_PLANS.calendar, "   ")).toEqual(["none", "maybe", "sure"]);
  });

  it("looks through every mark, “not going” included, when searching", () => {
    expect(plansToShow(SHOWN_PLANS.feed, "Музыкальная")).toEqual([]);
    expect(plansToShow(SHOWN_PLANS.going, "Шуман")).toEqual([]);
  });
});

describe("nextMark", () => {
  it("changes one mark and keeps the other", () => {
    expect(nextMark({ interest: 4, plan: null }, { plan: "maybe" })).toEqual({ interest: 4, plan: "maybe" });
    expect(nextMark({ interest: null, plan: "sure" }, { interest: 2 })).toEqual({ interest: 2, plan: "sure" });
  });

  it("clears a mark chosen again", () => {
    expect(nextMark({ interest: 4, plan: "no" }, { interest: 4 })).toEqual({ interest: null, plan: "no" });
    expect(nextMark({ interest: 4, plan: "no" }, { plan: "no" })).toEqual({ interest: 4, plan: null });
  });
});
