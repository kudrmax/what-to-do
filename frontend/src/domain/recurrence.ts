import { WEEKDAY_CODES } from "./dates";

/** The day in the accusative and the matching «каждый», in JavaScript's weekday order (Sunday first). */
const EVERY_DAY: [string, string][] = [
  ["воскресенье", "каждое"],
  ["понедельник", "каждый"],
  ["вторник", "каждый"],
  ["среду", "каждую"],
  ["четверг", "каждый"],
  ["пятницу", "каждую"],
  ["субботу", "каждую"],
];

/** "FREQ=WEEKLY;BYDAY=TU" → "Каждый вторник"; rules it cannot say simply become "Повторяется". */
export function describeRecurrence(rule: string | null | undefined): string | null {
  if (!rule) return null;
  const fields = Object.fromEntries(rule.split(";").map((pair) => pair.split("=")));
  if (fields.FREQ === "DAILY" && !fields.INTERVAL) return "Каждый день";
  if (fields.FREQ !== "WEEKLY" || (fields.INTERVAL && fields.INTERVAL !== "1")) return "Повторяется";
  const days = String(fields.BYDAY ?? "")
    .split(",")
    .map((code) => WEEKDAY_CODES.indexOf(code as (typeof WEEKDAY_CODES)[number]))
    .filter((index) => index >= 0);
  if (days.length === 0) return "Каждую неделю";
  const names = days.map((index) => EVERY_DAY[index][0]);
  const every = EVERY_DAY[days[0]][1];
  const list = names.length === 1 ? names[0] : `${names.slice(0, -1).join(", ")} и ${names[names.length - 1]}`;
  return `${every[0].toUpperCase()}${every.slice(1)} ${list}`;
}
