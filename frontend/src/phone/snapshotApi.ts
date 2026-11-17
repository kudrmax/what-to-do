import { ApiError, createApi, type Api, type EventCard, type FeedQuery, type Occurrence } from "../api/client";
import { todayIn } from "../domain/dates";
import { calendarFile } from "./calendarFile";
import type { PageImages } from "./images";
import type { PhoneSnapshot } from "./snapshot";

export const READ_ONLY = "This page is read-only";

/** The feed filter of the backend (feed.py, FeedFilter.accepts) over the published cards; the search is plain: every word somewhere in the card. */
export class SnapshotFeed {
  private readonly snapshot: PhoneSnapshot;
  private readonly now: () => Date;

  constructor(snapshot: PhoneSnapshot, now: () => Date) {
    this.snapshot = snapshot;
    this.now = now;
  }

  /** Days before today are never shown: the snapshot may be older than today. */
  query(query: FeedQuery): Occurrence[] {
    const today = todayIn(this.snapshot.timezone, this.now());
    const start = query.start && query.start > today ? query.start : today;
    return this.snapshot.occurrences.filter((item) => item.date >= start && (!query.end || item.date <= query.end) && this.accepts(item.event, query));
  }

  private accepts(event: EventCard, query: FeedQuery): boolean {
    const words = (query.search ?? "").toLowerCase().split(/\s+/).filter(Boolean);
    const tags = query.tags ?? [];
    const sources = query.sources ?? [];
    const plans = query.plans ?? [];
    if (words.length && !words.every((word) => searchable(event).includes(word))) return false;
    if (tags.length && !event.tags.some((tag) => tags.includes(tag))) return false;
    if (sources.length && !event.source_ids.some((id) => sources.includes(id))) return false;
    if (query.only_timed && (event.start_time === null || event.kind === "multiday")) return false;
    if (query.hide_multiday && event.kind === "multiday") return false;
    if (query.only_priority && !event.is_priority) return false;
    return !plans.length || plans.includes(event.plan ?? "none");
  }
}

function searchable(event: EventCard): string {
  return [event.title, event.original_title, event.description, event.venue, event.address, ...event.tags].filter(Boolean).join("\n").toLowerCase();
}

const refuse = () => Promise.reject(new ApiError(403, READ_ONLY));

/** Every call of the app's API, answered from the snapshot; anything that would change something is refused. */
function refusingEverything(): Api {
  return Object.fromEntries(Object.keys(createApi("")).map((name) => [name, refuse])) as unknown as Api;
}

export function createSnapshotApi(snapshot: PhoneSnapshot, images: PageImages, now: () => Date = () => new Date()): Api {
  const feed = new SnapshotFeed(snapshot, now);
  const find = (id: number) => snapshot.occurrences.find((item) => item.event.id === id)?.event;
  const answer = <T>(value: T) => Promise.resolve(value);
  return {
    ...refusingEverything(),
    imageUrl: (path) => (path ? images.url(path) : null),
    calendarFileUrl: (id) => {
      const event = find(id);
      const postUrl = snapshot.mentions[String(id)]?.[0]?.post_url ?? null;
      return event ? `data:text/calendar;charset=utf-8,${encodeURIComponent(calendarFile(event, snapshot.timezone, postUrl, now()))}` : "";
    },
    settings: () => answer(snapshot.settings),
    defaultSettings: () => answer(snapshot.settings),
    cities: () => answer(snapshot.cities),
    sources: () => answer(snapshot.sources),
    tags: () => answer(snapshot.tags),
    feed: (query) => answer(feed.query(query)),
    event: (id) => {
      const event = find(id);
      return event ? answer(event) : Promise.reject(new ApiError(404, "Event not found"));
    },
    mentions: (id) => answer(snapshot.mentions[String(id)] ?? []),
  };
}
