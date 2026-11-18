import { describe, expect, it } from "vitest";

import { ambiguousName, originalPlace } from "./sources";

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

describe("originalPlace", () => {
  it("tells a website page, a Telegram post, an Instagram post and an Instagram highlight apart", () => {
    expect(originalPlace({ source_kind: "web", post_url: "https://site.test/events/a" })).toBe("website");
    expect(originalPlace({ source_kind: "telegram", post_url: "https://t.me/afisha/1" })).toBe("telegram");
    expect(originalPlace({ source_kind: "instagram", post_url: "https://www.instagram.com/p/DfmlSc4DQL_/" })).toBe("instagramPost");
    expect(originalPlace({ source_kind: "instagram", post_url: "https://www.instagram.com/stories/highlights/17901/" })).toBe("instagramHighlight");
  });
});
