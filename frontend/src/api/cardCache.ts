import { replaceEqualDeep, type Query, type QueryClient, type QueryKey } from "@tanstack/react-query";

import type { EventCard, Occurrence } from "./client";

type Saved = [QueryKey, unknown, number][];

/**
 * The cards the interface already holds: every loaded feed and every opened event.
 * A change to one card is written into each place it is shown, so only that card is drawn again.
 */
export class CardCache {
  private readonly client: QueryClient;
  private readonly feedKey: QueryKey;
  private readonly eventKey: QueryKey;

  constructor(client: QueryClient, feedKey: QueryKey, eventKey: QueryKey) {
    this.client = client;
    this.feedKey = feedKey;
    this.eventKey = eventKey;
  }

  /** Stops the loads under way, so a late answer does not overwrite the change, and keeps what was there to restore. */
  async hold(): Promise<Saved> {
    await Promise.all([this.client.cancelQueries({ queryKey: this.feedKey }), this.client.cancelQueries({ queryKey: this.eventKey })]);
    return this.queries().map((query) => [query.queryKey, query.state.data, query.state.dataUpdatedAt]);
  }

  /** Changes one card everywhere. The feeds keep their load time: views that wait for the next load from the server still wait for it. */
  change(id: number, edit: (card: EventCard) => EventCard): void {
    for (const query of this.queries()) {
      const next = this.edited(query, id, edit);
      if (next !== query.state.data) this.client.setQueryData(query.queryKey, next, { updatedAt: query.state.dataUpdatedAt });
    }
  }

  restore(saved: Saved): void {
    for (const [key, data, updatedAt] of saved) this.client.setQueryData(key, data, { updatedAt });
  }

  private queries(): Query[] {
    const cache = this.client.getQueryCache();
    return [...cache.findAll({ queryKey: this.feedKey }), ...cache.findAll({ queryKey: this.eventKey }).filter((query) => this.isCard(query))];
  }

  private isCard(query: Query): boolean {
    return query.queryKey.length === this.eventKey.length + 1;
  }

  private edited(query: Query, id: number, edit: (card: EventCard) => EventCard): unknown {
    const data = query.state.data;
    if (data === undefined) return data;
    if (this.isFeed(query)) {
      const feed = data as Occurrence[];
      return feed.some((item) => item.event.id === id) ? feed.map((item) => (item.event.id === id ? { ...item, event: edit(item.event) } : item)) : feed;
    }
    const card = data as EventCard;
    return card.id === id ? edit(card) : card;
  }

  private isFeed(query: Query): boolean {
    return query.queryKey[0] === this.feedKey[0];
  }
}

const placeOf = (item: Occurrence) => `${item.event.id}-${item.date}`;

/**
 * A reloaded feed that keeps the objects of the cards that did not change, matched by event and day rather than by position:
 * a card leaving or joining the list does not make every card after it look new, so only changed cards are drawn again.
 */
export function keepUnchangedCards(previous: unknown, next: unknown): unknown {
  if (!Array.isArray(previous) || !Array.isArray(next)) return replaceEqualDeep(previous, next);
  const before = new Map((previous as Occurrence[]).map((item) => [placeOf(item), item]));
  const merged = (next as Occurrence[]).map((item) => {
    const old = before.get(placeOf(item));
    return old ? replaceEqualDeep(old, item) : item;
  });
  const same = merged.length === previous.length && merged.every((item, index) => item === previous[index]);
  return same ? previous : merged;
}
