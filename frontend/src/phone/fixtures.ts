import type { EventCard, Mention, Occurrence, Source } from "../api/client";
import type { PhoneSnapshot } from "./snapshot";

/** Snapshots for the phone page tests, shaped as the app publishes them. */
export const PASSWORD = "correct horse";
export const MADE_AT = "2026-11-17T18:40:00Z";

export function event(id: number, title: string, plan: "sure" | "maybe", extra: Partial<EventCard> = {}): EventCard {
  return {
    id,
    title,
    original_title: title,
    description: `About ${title}`,
    kind: "single",
    start_date: "2026-11-17",
    end_date: null,
    start_time: "19:00:00",
    rrule: null,
    venue: "Dorćol Platz",
    address: "Dobračina 59",
    price: 800,
    currency: "RSD",
    tags: ["music"],
    is_priority: false,
    collection_ids: [],
    booking: null,
    is_cancelled: false,
    conflicts: [],
    source_ids: [1],
    interest: null,
    plan,
    is_going: true,
    image_url: null,
    place: "Dorćol Platz",
    map_url: "https://maps.example/dorcol",
    ...extra,
  } as EventCard;
}

export function mention(id: number, sourceTitle: string, postUrl: string): Mention {
  return {
    id,
    data: { start_date: "2026-11-17", from_organizer: false },
    locked: false,
    source_id: 1,
    source_title: sourceTitle,
    source_kind: "telegram",
    post_url: postUrl,
    post_text: "Jazz tonight",
    published_at: "2026-11-10T10:00:00Z",
    photos: [],
    event_photo: null,
    event_lines: [],
  } as unknown as Mention;
}

function source(id: number, title: string): Source {
  return { id, kind: "telegram", handle: title, title, last_refreshed_at: null, last_error: null, events_found: 1, status: "new", paused: false } as Source;
}

export function snapshot(occurrences: Occurrence[], madeAt = MADE_AT, mentions: PhoneSnapshot["mentions"] = {}): PhoneSnapshot {
  return {
    made_at: madeAt,
    timezone: "Europe/Belgrade",
    settings: {
      active_city_id: 1,
      recent_posts: 20,
      priority_wish: "",
      collections_enabled: false,
      extraction_prompt: "",
      matching_prompt: "",
      photo_prompt: "",
      photo_model: "claude-sonnet-5-5",
      extraction_model: "claude-sonnet-5-5",
      matching_model: "claude-haiku-5-5",
    },
    cities: [{ id: 1, name: "Belgrade", country: "Serbia", timezone: "Europe/Belgrade", card_language: "English" }],
    sources: [source(1, "jazz"), source(2, "puppets")],
    tags: [
      { id: 1, name: "music", is_fallback: false, hidden: false },
      { id: 2, name: "theatre", is_fallback: false, hidden: false },
    ],
    occurrences,
    mentions,
    images: {},
  };
}

export const PLANS = snapshot(
  [
    { date: "2026-11-17", event: event(1, "Jazz at Dorćol", "sure", { interest: 4 }) },
    { date: "2026-11-18", event: event(2, "Puppet theatre", "maybe", { tags: ["theatre"], source_ids: [2], venue: "Pinokio", address: null }) },
  ],
  MADE_AT,
  { "1": [mention(11, "jazz", "https://t.me/jazz/1")] },
);

export async function seal(content: PhoneSnapshot | string, salt: Uint8Array, password = PASSWORD): Promise<ArrayBuffer> {
  return sealBytes(new TextEncoder().encode(typeof content === "string" ? content : JSON.stringify(content)), salt, password);
}

export async function sealBytes(bytes: Uint8Array, salt: Uint8Array, password = PASSWORD): Promise<ArrayBuffer> {
  const base = await crypto.subtle.importKey("raw", new TextEncoder().encode(password), "PBKDF2", false, ["deriveKey"]);
  const key = await crypto.subtle.deriveKey({ name: "PBKDF2", hash: "SHA-256", salt, iterations: 600_000 }, base, { name: "AES-GCM", length: 256 }, false, ["encrypt"]);
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const sealed = new Uint8Array(await crypto.subtle.encrypt({ name: "AES-GCM", iv }, key, bytes));
  const blob = new Uint8Array(32 + sealed.length);
  blob.set(new TextEncoder().encode("WTD1"), 0);
  blob.set(salt, 4);
  blob.set(iv, 20);
  blob.set(sealed, 32);
  return blob.buffer;
}
