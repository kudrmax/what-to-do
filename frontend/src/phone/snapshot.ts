import type { Occurrence } from "../api/client";

export type PhoneOccurrence = Occurrence & { post_url: string | null };

/** What the app publishes: its upcoming plans for one city, as the Plans screen listed them when it was made. */
export interface PhoneSnapshot {
  made_at: string;
  city: string;
  timezone: string;
  today: string;
  tags: string[];
  occurrences: PhoneOccurrence[];
}

const STALE_AFTER_MS = 24 * 60 * 60 * 1000;

export function readSnapshot(bytes: ArrayBuffer): PhoneSnapshot {
  return JSON.parse(new TextDecoder().decode(bytes)) as PhoneSnapshot;
}

/** Older than a day: the laptop may be asleep and the list may be out of date. */
export function isStale(snapshot: PhoneSnapshot, now: Date): boolean {
  return now.getTime() - new Date(snapshot.made_at).getTime() > STALE_AFTER_MS;
}

/** The encrypted files published next to the page. */
export interface PageFiles {
  snapshot(): Promise<ArrayBuffer>;
  file(path: string): Promise<ArrayBuffer>;
}

/** Fetches the files from wherever the page itself is served, so it works under any path. */
export class PublishedFiles implements PageFiles {
  snapshot(): Promise<ArrayBuffer> {
    return this.file(`data.bin?t=${Date.now()}`);
  }

  async file(path: string): Promise<ArrayBuffer> {
    const response = await fetch(path, { cache: "no-store" });
    if (!response.ok) throw new Error(`${path}: ${response.status}`);
    return response.arrayBuffer();
  }
}
