/** Occurrences under their day: days in the order they come, or exactly the given days (empty ones too). */
export function groupByDay<T extends { date: string }>(occurrences: T[], days?: string[]): [string, T[]][] {
  const byDay = new Map<string, T[]>((days ?? []).map((day) => [day, []]));
  for (const item of occurrences) {
    if (days && !byDay.has(item.date)) continue;
    byDay.set(item.date, [...(byDay.get(item.date) ?? []), item]);
  }
  return [...byDay.entries()];
}
