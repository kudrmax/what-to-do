import type { Occurrence } from "../api/client";

/** Occurrences under their day: days in the order they come, or exactly the given days (empty ones too). */
export function groupByDay(occurrences: Occurrence[], days?: string[]): [string, Occurrence[]][] {
  const byDay = new Map<string, Occurrence[]>((days ?? []).map((day) => [day, []]));
  for (const item of occurrences) {
    if (days && !byDay.has(item.date)) continue;
    byDay.set(item.date, [...(byDay.get(item.date) ?? []), item]);
  }
  return [...byDay.entries()];
}
