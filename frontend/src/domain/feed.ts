import type { Occurrence } from "../api/client";

/** Occurrences under their day, days in the order they come. */
export function groupByDay(occurrences: Occurrence[]): [string, Occurrence[]][] {
  const days = new Map<string, Occurrence[]>();
  for (const item of occurrences) {
    days.set(item.date, [...(days.get(item.date) ?? []), item]);
  }
  return [...days.entries()];
}
