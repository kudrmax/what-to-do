const DAYS: Record<string, [string, string]> = {
  MO: ["понедельник", "каждый"],
  TU: ["вторник", "каждый"],
  WE: ["среду", "каждую"],
  TH: ["четверг", "каждый"],
  FR: ["пятницу", "каждую"],
  SA: ["субботу", "каждую"],
  SU: ["воскресенье", "каждое"],
};

/** "FREQ=WEEKLY;BYDAY=TU" → "Каждый вторник"; rules it cannot say simply become "Повторяется". */
export function describeRecurrence(rule: string | null): string | null {
  if (!rule) return null;
  const fields = Object.fromEntries(rule.split(";").map((pair) => pair.split("=")));
  if (fields.FREQ === "DAILY" && !fields.INTERVAL) return "Каждый день";
  if (fields.FREQ !== "WEEKLY" || (fields.INTERVAL && fields.INTERVAL !== "1")) return "Повторяется";
  const days: string[] = (fields.BYDAY ?? "").split(",").filter((day: string) => day in DAYS);
  if (days.length === 0) return "Каждую неделю";
  const [firstName, every] = DAYS[days[0]];
  const names = [firstName, ...days.slice(1).map((day) => DAYS[day][0])];
  const list = names.length === 1 ? names[0] : `${names.slice(0, -1).join(", ")} и ${names[names.length - 1]}`;
  return `${every[0].toUpperCase()}${every.slice(1)} ${list}`;
}
