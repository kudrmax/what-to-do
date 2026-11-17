import { describe, expect, it } from "vitest";

import { ambiguousName } from "./sources";

describe("ambiguousName", () => {
  it("is a bare name valid for both Telegram and Instagram", () => {
    for (const link of ["londonevents", "@londonevents", " @london_events2 ", "abcd"]) expect(ambiguousName(link)).toBe(true);
  });

  it("is not a link, a name with a dot, a short or a long name", () => {
    for (const link of ["@eje.belgrade", "eje.belgrade", "t.me/londonevents", "instagram.com/londonevents", "@abc", "_london", "1london", `a${"b".repeat(32)}`, ""]) {
      expect(ambiguousName(link)).toBe(false);
    }
  });
});
