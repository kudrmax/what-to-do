/** Calendar days as "YYYY-MM-DD" strings: the backend's format, free of time-zone shifts. */
export type IsoDay = string;

const MONTHS_GENITIVE = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"];
const MONTHS_NOMINATIVE = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"];
const WEEKDAYS = ["воскресенье", "понедельник", "вторник", "среда", "четверг", "пятница", "суббота"];
const WEEKDAYS_SHORT = ["вс", "пн", "вт", "ср", "чт", "пт", "сб"];

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
  return MONTHS_NOMINATIVE[parts(day).month];
}

/** "9 ноября". */
export function dayAndMonth(day: IsoDay): string {
  const { date, month } = parts(day);
  return `${date} ${MONTHS_GENITIVE[month]}`;
}

/** "понедельник, 9 ноября". */
export function longDate(day: IsoDay): string {
  return `${WEEKDAYS[parts(day).weekday]}, ${dayAndMonth(day)}`;
}

/** Day heading: "Сегодня" / "9 ноября, понедельник", "Завтра" / …, "11 ноября" / "среда". */
export function dayHeading(day: IsoDay, today: IsoDay): { title: string; subtitle: string } {
  const weekday = WEEKDAYS[parts(day).weekday];
  if (day === today) return { title: "Сегодня", subtitle: `${dayAndMonth(day)}, ${weekday}` };
  if (day === addDays(today, 1)) return { title: "Завтра", subtitle: `${dayAndMonth(day)}, ${weekday}` };
  return { title: dayAndMonth(day), subtitle: weekday };
}

/** "1–30 ноября" or "28 октября – 5 ноября". */
export function dateRange(start: IsoDay, end: IsoDay): string {
  const a = parts(start);
  const b = parts(end);
  if (a.month === b.month && a.year === b.year) return `${a.date}–${b.date} ${MONTHS_GENITIVE[b.month]}`;
  return `${dayAndMonth(start)} – ${dayAndMonth(end)}`;
}

/** "19:00:00" → "19:00". */
export function clock(time: string): string {
  return time.slice(0, 5);
}

/** "сегодня в 18:40", "вчера в 9:05", "3 дня назад", "2 ноября". */
export function ago(moment: string, now: Date = new Date()): string {
  const then = new Date(moment);
  const days = Math.floor((startOfDay(now) - startOfDay(then)) / 86_400_000);
  const hm = then.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
  if (days <= 0) return `сегодня в ${hm}`;
  if (days === 1) return `вчера в ${hm}`;
  if (days < 7) return `${days} ${plural(days, "день", "дня", "дней")} назад`;
  return `${then.getDate()} ${MONTHS_GENITIVE[then.getMonth()]}`;
}

function startOfDay(moment: Date): number {
  return new Date(moment.getFullYear(), moment.getMonth(), moment.getDate()).getTime();
}

export function plural(count: number, one: string, few: string, many: string): string {
  const mod10 = count % 10;
  const mod100 = count % 100;
  if (mod10 === 1 && mod100 !== 11) return one;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return few;
  return many;
}
