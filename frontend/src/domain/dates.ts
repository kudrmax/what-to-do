/** Calendar days as "YYYY-MM-DD" strings: the backend's format, free of time-zone shifts. */
export type IsoDay = string;

const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
const WEEKDAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
const WEEKDAYS_SHORT = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
/** RFC 5545 weekday codes in JavaScript's weekday order (Sunday first). */
export const WEEKDAY_CODES = ["SU", "MO", "TU", "WE", "TH", "FR", "SA"] as const;

function parts(day: IsoDay): { year: number; month: number; date: number; weekday: number } {
  const [year, month, date] = day.split("-").map(Number);
  return { year, month: month - 1, date, weekday: new Date(Date.UTC(year, month - 1, date)).getUTCDay() };
}

export function todayIn(timeZone: string, now: Date = new Date()): IsoDay {
  return new Intl.DateTimeFormat("en-CA", { timeZone, year: "numeric", month: "2-digit", day: "2-digit" }).format(now);
}

export function addDays(day: IsoDay, count: number): IsoDay {
  const { year, month, date } = parts(day);
  return new Date(Date.UTC(year, month, date + count)).toISOString().slice(0, 10);
}

/** Monday of the week the day belongs to. */
export function weekStart(day: IsoDay): IsoDay {
  return addDays(day, -((parts(day).weekday + 6) % 7));
}

export function dayNumber(day: IsoDay): number {
  return parts(day).date;
}

export function weekdayShort(day: IsoDay): string {
  return WEEKDAYS_SHORT[parts(day).weekday];
}

export function monthTitle(day: IsoDay): string {
  return MONTHS[parts(day).month];
}

/** "9 November". */
export function dayAndMonth(day: IsoDay): string {
  const { date, month } = parts(day);
  return `${date} ${MONTHS[month]}`;
}

/** "Monday, 9 November". */
export function longDate(day: IsoDay): string {
  return `${WEEKDAYS[parts(day).weekday]}, ${dayAndMonth(day)}`;
}

/** Day heading: "Today" / "Monday, 9 November", "Tomorrow" / …, "11 November" / "Wednesday". */
export function dayHeading(day: IsoDay, today: IsoDay): { title: string; subtitle: string; relative: boolean } {
  const weekday = WEEKDAYS[parts(day).weekday];
  if (day === today) return { title: "Today", subtitle: `${weekday}, ${dayAndMonth(day)}`, relative: true };
  if (day === addDays(today, 1)) return { title: "Tomorrow", subtitle: `${weekday}, ${dayAndMonth(day)}`, relative: true };
  return { title: dayAndMonth(day), subtitle: weekday, relative: false };
}

/** "1–30 November" or "28 October – 5 November". */
export function dateRange(start: IsoDay, end: IsoDay): string {
  const a = parts(start);
  const b = parts(end);
  if (a.month === b.month && a.year === b.year) return `${a.date}–${b.date} ${MONTHS[b.month]}`;
  return `${dayAndMonth(start)} – ${dayAndMonth(end)}`;
}

/** "19:00:00" → "19:00". */
export function clock(time: string): string {
  return time.slice(0, 5);
}

/** "today at 18:40", "yesterday at 09:05", "3 days ago", "2 November". */
export function ago(moment: string, now: Date = new Date()): string {
  const then = new Date(moment);
  const days = Math.floor((startOfDay(now) - startOfDay(then)) / 86_400_000);
  const hm = then.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
  if (days <= 0) return `today at ${hm}`;
  if (days === 1) return `yesterday at ${hm}`;
  if (days < 7) return `${days} ${plural(days, "day", "days")} ago`;
  return `${then.getDate()} ${MONTHS[then.getMonth()]}`;
}

function startOfDay(moment: Date): number {
  return new Date(moment.getFullYear(), moment.getMonth(), moment.getDate()).getTime();
}

export function plural(count: number, one: string, other: string): string {
  return count === 1 ? one : other;
}
