import { WEEKDAY_CODES } from "./dates";

/** Weekday names in JavaScript's weekday order (Sunday first). */
const DAY_NAMES = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];

/** "FREQ=WEEKLY;BYDAY=TU" → "Every Tuesday"; rules it cannot say simply become "Repeats". */
export function describeRecurrence(rule: string | null | undefined): string | null {
  if (!rule) return null;
  const fields = Object.fromEntries(rule.split(";").map((pair) => pair.split("=")));
  if (fields.FREQ === "DAILY" && !fields.INTERVAL) return "Every day";
  if (fields.FREQ !== "WEEKLY" || (fields.INTERVAL && fields.INTERVAL !== "1")) return "Repeats";
  const days = String(fields.BYDAY ?? "")
    .split(",")
    .map((code) => WEEKDAY_CODES.indexOf(code as (typeof WEEKDAY_CODES)[number]))
    .filter((index) => index >= 0);
  if (days.length === 0) return "Every week";
  const names = days.map((index) => DAY_NAMES[index]);
  const list = names.length === 1 ? names[0] : `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;
  return `Every ${list}`;
}
