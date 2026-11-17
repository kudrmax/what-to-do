import { describe, expect, test } from "vitest";

import { ApiError, type Occurrence } from "../api/client";
import { event, mention, snapshot } from "./fixtures";
import { PageImages } from "./images";
import { createSnapshotApi, READ_ONLY } from "./snapshotApi";

const NOW = () => new Date("2026-11-17T12:00:00Z");

const CARDS = snapshot(
  [
    { date: "2026-11-16", event: event(1, "Yesterday's talk", "sure") },
    { date: "2026-11-17", event: event(2, "Jazz", "sure", { tags: ["music"], source_ids: [1], description: "Trio; then a jam\nBring friends" }) },
    { date: "2026-11-17", event: event(3, "Puppets", "maybe", { tags: ["theatre"], source_ids: [2], start_time: null, venue: "Pinokio" }) },
    { date: "2026-11-18", event: event(4, "Fair", "maybe", { kind: "multiday", start_date: "2026-11-18", end_date: "2026-11-19", tags: ["market"], source_ids: [3], is_priority: true, description: "Crafts and food" }) },
  ],
  "2026-11-16T10:00:00Z",
  { "2": [mention(21, "jazz", "https://t.me/jazz/21")] },
);

const api = createSnapshotApi(CARDS, PageImages.none, NOW);
const titles = (found: Occurrence[]) => found.map((item) => item.event.title);

describe("feed", () => {
  test("hides days before today even when the snapshot is older", async () => {
    expect(titles(await api.feed({}))).toEqual(["Jazz", "Puppets", "Fair"]);
    expect(titles(await api.feed({ start: "2026-11-01" }))).toEqual(["Jazz", "Puppets", "Fair"]);
  });

  test("takes the range, the plans and every filter of the backend", async () => {
    expect(titles(await api.feed({ start: "2026-11-18" }))).toEqual(["Fair"]);
    expect(titles(await api.feed({ end: "2026-11-17" }))).toEqual(["Jazz", "Puppets"]);
    expect(titles(await api.feed({ plans: ["sure"] }))).toEqual(["Jazz"]);
    expect(titles(await api.feed({ plans: ["maybe", "sure"] }))).toEqual(["Jazz", "Puppets", "Fair"]);
    expect(titles(await api.feed({ plans: ["none"] }))).toEqual([]);
    expect(titles(await api.feed({ tags: ["theatre", "market"] }))).toEqual(["Puppets", "Fair"]);
    expect(titles(await api.feed({ sources: [1, 3] }))).toEqual(["Jazz", "Fair"]);
    expect(titles(await api.feed({ only_timed: true }))).toEqual(["Jazz"]);
    expect(titles(await api.feed({ hide_multiday: true }))).toEqual(["Jazz", "Puppets"]);
    expect(titles(await api.feed({ only_priority: true }))).toEqual(["Fair"]);
  });

  test("searches the title, description, venue and tags, case aside, every word", async () => {
    expect(titles(await api.feed({ search: "pinOKIO" }))).toEqual(["Puppets"]);
    expect(titles(await api.feed({ search: "crafts FOOD" }))).toEqual(["Fair"]);
    expect(titles(await api.feed({ search: "theatre" }))).toEqual(["Puppets"]);
    expect(titles(await api.feed({ search: "crafts jazz" }))).toEqual([]);
  });
});

describe("multi-day events", () => {
  const running = snapshot(
    [
      { date: "2026-11-15", event: event(5, "Fair", "maybe", { kind: "multiday", start_date: "2026-11-14", end_date: "2026-11-20" }) },
      { date: "2026-11-15", event: event(6, "Over", "maybe", { kind: "multiday", start_date: "2026-11-14", end_date: "2026-11-16" }) },
      { date: "2026-11-17", event: event(7, "Show", "sure") },
      { date: "2026-11-25", event: event(8, "Later fair", "maybe", { kind: "multiday", start_date: "2026-11-25", end_date: "2026-11-28" }) },
    ],
    "2026-11-15T10:00:00Z",
  );
  const feed = createSnapshotApi(running, PageImages.none, NOW);
  const days = (found: Occurrence[]) => found.map((item) => `${item.date} ${item.event.title}`);

  test("one still running is shown on today, after the timed cards, as the backend lays it out", async () => {
    expect(days(await feed.feed({}))).toEqual(["2026-11-17 Show", "2026-11-17 Fair", "2026-11-25 Later fair"]);
  });

  test("a later start moves it to that day while it still runs", async () => {
    expect(days(await feed.feed({ start: "2026-11-19" }))).toEqual(["2026-11-19 Fair", "2026-11-25 Later fair"]);
    expect(days(await feed.feed({ start: "2026-11-21", end: "2026-11-24" }))).toEqual([]);
    expect(days(await feed.feed({ end: "2026-11-26", start: "2026-11-26" }))).toEqual(["2026-11-26 Later fair"]);
  });
});

test("answers the read calls from the snapshot", async () => {
  expect(await api.settings()).toEqual(CARDS.settings);
  expect(await api.cities()).toEqual(CARDS.cities);
  expect(await api.sources()).toEqual(CARDS.sources);
  expect(await api.tags()).toEqual(CARDS.tags);
  expect((await api.event(3)).title).toBe("Puppets");
  expect(await api.mentions(2)).toEqual(CARDS.mentions["2"]);
  expect(await api.mentions(3)).toEqual([]);
  await expect(api.event(99)).rejects.toMatchObject({ status: 404 });
});

test("refuses every change", async () => {
  for (const change of [() => api.mark(2, { interest: 5, plan: "sure" }), () => api.addDevNote(2, "idea"), () => api.merge(2, 3), () => api.split(2, 21), () => api.refresh(), () => api.changeSettings({})]) {
    const refused = change();
    await expect(refused).rejects.toBeInstanceOf(ApiError);
    await expect(refused).rejects.toThrow(READ_ONLY);
  }
});

test("gives the calendar file of a card with its first post", () => {
  const file = decodeURIComponent(api.calendarFileUrl(2).replace("data:text/calendar;charset=utf-8,", ""));
  expect(file).toContain("SUMMARY:Jazz\r\n");
  expect(file).toContain("DTSTART;TZID=Europe/Belgrade:20261117T190000\r\n");
  expect(file).toContain("DTEND;TZID=Europe/Belgrade:20261117T210000\r\n");
  expect(file).toContain("LOCATION:Dorćol Platz\\, Dobračina 59\r\n");
  expect(file).toContain("URL:https://t.me/jazz/21\r\n");
  expect(file).toContain("DESCRIPTION:Trio\\; then a jam\\nBring friends\\n\\nhttps://t.me/jazz/21\r\n");
  const allDay = decodeURIComponent(api.calendarFileUrl(4));
  expect(allDay).toContain("DTSTART;VALUE=DATE:20261118");
  expect(allDay).toContain("DTEND;VALUE=DATE:20261120");
});
