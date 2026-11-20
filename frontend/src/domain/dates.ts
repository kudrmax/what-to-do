import { dateFormat } from "./formatters";
import { conventions } from "./locale";

/** Calendar days as "YYYY-MM-DD" strings: the backend's format, free of time-zone shifts. */
export type IsoDay = string;

/** RFC 5545 weekday codes in JavaScript's weekday order (Sunday first). */
export const WEEKDAY_CODES = ["SU", "MO", "TU", "WE", "TH", "FR", "SA"] as const;

function parts(day: IsoDay): { year: number; month: number; date: number; weekday: number } {
  const [year, month, date] = day.split("-").map(Number);
  return { year, month: month - 1, date, weekday: new Date(Date.UTC(year, month - 1, date)).getUTCDay() };
}

/** A calendar day as a moment Intl formats back to the same day. */
function utc(day: IsoDay): Date {
  const { year, month, date } = parts(day);
  return new Date(Date.UTC(year, month, date));
}

function dayFormat(options: Intl.DateTimeFormatOptions): Intl.DateTimeFormat {
  return dateFormat(conventions().locale, { ...options, timeZone: "UTC" });
}

export function todayIn(timeZone: string, now: Date = new Date()): IsoDay {
  return dateFormat("en-CA", { timeZone, year: "numeric", month: "2-digit", day: "2-digit" }).format(now);
}

export function addDays(day: IsoDay, count: number): IsoDay {
  const { year, month, date } = parts(day);
  return new Date(Date.UTC(year, month, date + count)).toISOString().slice(0, 10);
}

/** The first day of the week the day belongs to: Monday or Sunday or Saturday, as the person's region counts. */
export function weekStart(day: IsoDay, firstDay: number = conventions().firstDay): IsoDay {
  return addDays(day, -((parts(day).weekday - firstDay + 7) % 7));
}

export function dayNumber(day: IsoDay): number {
  return parts(day).date;
}

export function weekdayShort(day: IsoDay): string {
  return dayFormat({ weekday: "short" }).format(utc(day));
}

function weekday(day: IsoDay): string {
  return dayFormat({ weekday: "long" }).format(utc(day));
}

export function monthTitle(day: IsoDay): string {
  return dayFormat({ month: "long" }).format(utc(day));
}

/** "9 November" or "November 9". */
export function dayAndMonth(day: IsoDay): string {
  return dayFormat({ day: "numeric", month: "long" }).format(utc(day));
}

/** "Monday 9 November" or "Monday, November 9". */
export function longDate(day: IsoDay): string {
  return dayFormat({ weekday: "long", day: "numeric", month: "long" }).format(utc(day));
}

/** Day heading: "Today" / "Monday 9 November", "Tomorrow" / …, "11 November" / "Wednesday". */
export function dayHeading(day: IsoDay, today: IsoDay): { title: string; subtitle: string; relative: boolean } {
  if (day === today) return { title: "Today", subtitle: longDate(day), relative: true };
  if (day === addDays(today, 1)) return { title: "Tomorrow", subtitle: longDate(day), relative: true };
  return { title: dayAndMonth(day), subtitle: weekday(day), relative: false };
}

/** "1–30 November" or "28 October – 5 November", in the order the region writes them; never with years, even across one. */
export function dateRange(start: IsoDay, end: IsoDay): string {
  if (parts(start).year !== parts(end).year) return `${dayAndMonth(start)}\u2009–\u2009${dayAndMonth(end)}`;
  const pieces = dayFormat({ day: "numeric", month: "long" }).formatRangeToParts(utc(start), utc(end));
  return pieces.map((piece, i) => (isRangeDash(piece) ? rangeDash(pieces[i - 1], pieces[i + 1]) : piece.value)).join("");
}

/** ICU versions space the range dash differently; it is set here the same way everywhere. */
function isRangeDash(piece: Intl.DateTimeRangeFormatPart): boolean {
  return piece.type === "literal" && piece.source === "shared" && piece.value.trim() === "–";
}

function rangeDash(before?: Intl.DateTimeRangeFormatPart, after?: Intl.DateTimeRangeFormatPart): string {
  return before?.type === "day" && after?.type === "day" ? "–" : "\u2009–\u2009";
}

function timeFormat(): Intl.DateTimeFormat {
  const { locale, hourCycle } = conventions();
  const twelve = hourCycle === "h12" || hourCycle === "h11";
  return dateFormat(locale, { hour: twelve ? "numeric" : "2-digit", minute: "2-digit", hourCycle, timeZone: "UTC" });
}

/** A wall-clock time as the region writes it: "19:00:00" → "19:00" or "7:00 PM". */
export function clock(time: string): string {
  const [hours, minutes] = time.split(":").map(Number);
  return timeFormat().format(new Date(Date.UTC(2000, 0, 1, hours, minutes)));
}

/** "today at 18:40", "yesterday at 09:05", "3 days ago", "2 November". */
export function ago(moment: string, now: Date = new Date()): string {
  const then = new Date(moment);
  const days = Math.floor((startOfDay(now) - startOfDay(then)) / 86_400_000);
  const hm = clock(`${then.getHours()}:${then.getMinutes()}`);
  if (days <= 0) return `today at ${hm}`;
  if (days === 1) return `yesterday at ${hm}`;
  if (days < 7) return `${days} ${plural(days, "day", "days")} ago`;
  return dayAndMonth(localDay(then));
}

/** A moment in the person's own time: "9 November at 18:40" or "November 9 at 6:40 PM". */
export function momentText(moment: string): string {
  const { locale, hourCycle } = conventions();
  return dateFormat(locale, { day: "numeric", month: "long", hour: "numeric", minute: "2-digit", hourCycle }).format(new Date(moment));
}

/** A moment's day in the person's own time: "9 November". */
export function momentDay(moment: string): string {
  return dayAndMonth(localDay(new Date(moment)));
}

function localDay(moment: Date): IsoDay {
  return `${moment.getFullYear()}-${String(moment.getMonth() + 1).padStart(2, "0")}-${String(moment.getDate()).padStart(2, "0")}`;
}

function startOfDay(moment: Date): number {
  return new Date(moment.getFullYear(), moment.getMonth(), moment.getDate()).getTime();
}

export function plural(count: number, one: string, other: string): string {
  return count === 1 ? one : other;
}
