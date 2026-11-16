import { describe, expect, it } from "vitest";

import { addDays, ago, clock, dateRange, dayHeading, longDate, plural, todayIn, weekStart } from "./dates";
import { LocaleConventions, setConventions } from "./locale";

describe("dates", () => {
  it("names today and tomorrow, other days by date", () => {
    expect(dayHeading("2026-11-09", "2026-11-09")).toEqual({ title: "Today", subtitle: "Monday 9 November", relative: true });
    expect(dayHeading("2026-11-10", "2026-11-09")).toEqual({ title: "Tomorrow", subtitle: "Tuesday 10 November", relative: true });
    expect(dayHeading("2026-11-11", "2026-11-09")).toEqual({ title: "11 November", subtitle: "Wednesday", relative: false });
  });

  it("formats ranges inside and across months", () => {
    expect(dateRange("2026-11-01", "2026-11-30")).toBe("1–30 November");
    expect(dateRange("2026-10-28", "2026-11-05")).toBe("28 October\u2009–\u20095 November");
    expect(dateRange("2026-11-18", "2027-01-03")).toBe("18 November\u2009–\u20093 January");
  });

  it("walks days across month and year ends", () => {
    expect(addDays("2026-12-31", 1)).toBe("2027-01-01");
    expect(weekStart("2026-11-15")).toBe("2026-11-09");
    expect(weekStart("2026-11-09")).toBe("2026-11-09");
    expect(longDate("2026-11-09")).toBe("Monday 9 November");
  });

  it("takes today in the city's zone, not the computer's", () => {
    const lateEveningUtc = new Date("2026-11-09T23:30:00Z");
    expect(todayIn("Europe/Belgrade", lateEveningUtc)).toBe("2026-11-10");
    expect(todayIn("America/New_York", lateEveningUtc)).toBe("2026-11-09");
  });

  it("says how long ago in words", () => {
    const now = new Date(2026, 10, 9, 20, 0);
    expect(ago(new Date(2026, 10, 9, 18, 40).toISOString(), now)).toBe("today at 18:40");
    expect(ago(new Date(2026, 10, 6, 10, 0).toISOString(), now)).toBe("3 days ago");
    expect(ago(new Date(2026, 9, 20, 10, 0).toISOString(), now)).toBe("20 October");
  });

  it("picks the singular for one and the plural otherwise", () => {
    expect([0, 1, 2, 11, 21].map((n) => plural(n, "day", "days"))).toEqual(["days", "day", "days", "days", "days"]);
  });
});

describe("dates in the person's region", () => {
  it("an American browser gets month first, a 12-hour clock and weeks from Sunday", () => {
    setConventions(new LocaleConventions("en-US"));
    expect(longDate("2026-11-09")).toBe("Monday, November 9");
    expect(dateRange("2026-11-01", "2026-11-30")).toBe("November 1–30");
    expect(clock("19:05:00")).toBe("7:05 PM");
    expect(clock("09:00")).toBe("9:00 AM");
    expect(weekStart("2026-11-11")).toBe("2026-11-08");
    expect(weekStart("2026-11-08")).toBe("2026-11-08");
  });

  it("a Russian browser keeps English words, the day first, a 24-hour clock and weeks from Monday", () => {
    setConventions(new LocaleConventions("ru-RU"));
    expect(longDate("2026-11-09")).toBe("Monday 9 November");
    expect(clock("19:05:00")).toBe("19:05");
    expect(weekStart("2026-11-15")).toBe("2026-11-09");
  });

  it("weeks start where the region starts them, Saturday included", () => {
    expect(weekStart("2026-11-11", 6)).toBe("2026-11-07");
    expect(new LocaleConventions("ar-EG").firstDay).toBe(6);
    expect(new LocaleConventions("pt-BR").firstDay).toBe(0);
  });

  it("an unreadable browser locale falls back to British English", () => {
    const fallback = new LocaleConventions("not a locale!");
    expect([fallback.locale, fallback.hourCycle, fallback.firstDay]).toEqual(["en-GB", "h23", 1]);
  });
});
