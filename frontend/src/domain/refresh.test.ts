import { describe, expect, it } from "vitest";

import type { RefreshStatus } from "../api/client";
import { refreshLabel, timeLeft } from "./refresh";

const START = "2026-11-16T10:00:00Z";

function status(fields: Partial<RefreshStatus>): RefreshStatus {
  return {
    stage: "collecting",
    started_at: START,
    stage_started_at: START,
    finished_at: null,
    sources_to_collect: 0,
    sources_collected: 0,
    pages_to_fetch: 0,
    pages_fetched: 0,
    announcements_to_merge: 0,
    announcements_merged: 0,
    new_posts: 0,
    photos_to_read: 0,
    photos_read: 0,
    posts_to_read: 0,
    posts_read: 0,
    limit: null,
    posts_left: null,
    events_touched: 0,
    errors: [],
    reader_unavailable: false, reader: null, reader_error: null,
    running: true,
    ...fields,
  };
}

const at = (seconds: number) => new Date(Date.parse(START) + seconds * 1000);

describe("refresh label", () => {
  it("counts sources while collecting", () => {
    expect(refreshLabel(status({ sources_to_collect: 11, sources_collected: 4 }))).toBe("Collecting sources: 4 of 11");
  });

  it("counts site pages once a site is being downloaded", () => {
    expect(refreshLabel(status({ sources_to_collect: 11, sources_collected: 10, pages_to_fetch: 820, pages_fetched: 120 }))).toBe(
      "Downloading site pages: 120 of 820",
    );
  });

  it("counts photos and posts as before", () => {
    expect(refreshLabel(status({ stage: "reading", posts_to_read: 40, posts_read: 8 }))).toBe("Reading posts and pages: 8 of 40");
  });
});

describe("time left", () => {
  it("follows the pace of the current stage", () => {
    expect(timeLeft(status({ pages_to_fetch: 820, pages_fetched: 120 }), at(60))).toBe("~6 min left");
  });

  it("says less than a minute near the end", () => {
    expect(timeLeft(status({ pages_to_fetch: 100, pages_fetched: 90 }), at(60))).toBe("less than a minute");
  });

  it("does not guess before the pace is known", () => {
    expect(timeLeft(status({ pages_to_fetch: 820, pages_fetched: 2 }), at(2))).toBeNull();
    expect(timeLeft(status({ stage: "done" }), at(600))).toBeNull();
  });
});

describe("merging", () => {
  it("counts announcements while merging them", () => {
    expect(refreshLabel(status({ stage: "merging", announcements_to_merge: 60, announcements_merged: 15 }))).toBe("Merging duplicates: 15 of 60");
  });
});
