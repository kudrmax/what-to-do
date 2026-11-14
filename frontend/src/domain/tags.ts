import type { Tag } from "../api/client";

/** A card's tags in the order set in the settings; tags the settings do not know go last, as they came. */
export function orderTags(names: string[], tags: Tag[] | undefined): string[] {
  const position = new Map((tags ?? []).map((tag, index) => [tag.name, index]));
  const rank = (name: string) => position.get(name) ?? Number.MAX_SAFE_INTEGER;
  return [...names].sort((a, b) => rank(a) - rank(b));
}

/** The list with one item moved to another place. */
export function moved<T>(items: T[], from: number, to: number): T[] {
  const next = [...items];
  const [item] = next.splice(from, 1);
  next.splice(to, 0, item);
  return next;
}
