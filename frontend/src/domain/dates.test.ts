import { describe, expect, it } from "vitest";

import { addDays, ago, dateRange, dayHeading, longDate, plural, todayIn, weekStart } from "./dates";

describe("dates", () => {
  it("names today and tomorrow, other days by date", () => {
    expect(dayHeading("2026-11-09", "2026-11-09")).toEqual({ title: "Сегодня", subtitle: "9 ноября, понедельник" });
    expect(dayHeading("2026-11-10", "2026-11-09")).toEqual({ title: "Завтра", subtitle: "10 ноября, вторник" });
    expect(dayHeading("2026-11-11", "2026-11-09")).toEqual({ title: "11 ноября", subtitle: "среда" });
  });

  it("formats ranges inside and across months", () => {
    expect(dateRange("2026-11-01", "2026-11-30")).toBe("1–30 ноября");
    expect(dateRange("2026-10-28", "2026-11-05")).toBe("28 октября – 5 ноября");
  });

  it("walks days across month and year ends", () => {
    expect(addDays("2026-12-31", 1)).toBe("2027-01-01");
    expect(weekStart("2026-11-15")).toBe("2026-11-09");
    expect(weekStart("2026-11-09")).toBe("2026-11-09");
    expect(longDate("2026-11-09")).toBe("понедельник, 9 ноября");
  });

  it("takes today in the city's zone, not the computer's", () => {
    const lateEveningUtc = new Date("2026-11-09T23:30:00Z");
    expect(todayIn("Europe/Belgrade", lateEveningUtc)).toBe("2026-11-10");
    expect(todayIn("America/New_York", lateEveningUtc)).toBe("2026-11-09");
  });

  it("says how long ago in words", () => {
    const now = new Date(2026, 10, 9, 20, 0);
    expect(ago(new Date(2026, 10, 9, 18, 40).toISOString(), now)).toBe("сегодня в 18:40");
    expect(ago(new Date(2026, 10, 6, 10, 0).toISOString(), now)).toBe("3 дня назад");
    expect(ago(new Date(2026, 9, 20, 10, 0).toISOString(), now)).toBe("20 октября");
  });

  it("declines Russian nouns", () => {
    expect([1, 2, 5, 11, 21, 22, 25].map((n) => plural(n, "день", "дня", "дней"))).toEqual(["день", "дня", "дней", "дней", "день", "дня", "дней"]);
  });
});
