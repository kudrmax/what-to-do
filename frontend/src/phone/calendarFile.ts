import type { EventCard } from "../api/client";

/** Posts give a start time only; a calendar entry needs an end. The app's own .ics assumes the same. */
const ASSUMED_HOURS = 2;

const compact = (day: string) => day.replaceAll("-", "");

function nextDay(day: string): string {
  const [year, month, date] = day.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, date + 1)).toISOString().slice(0, 10);
}

/** A local wall-clock moment in the iCalendar form, `hours` later. */
function localMoment(day: string, time: string, hours = 0): string {
  const [year, month, date] = day.split("-").map(Number);
  const [hour, minute] = time.split(":").map(Number);
  return new Date(Date.UTC(year, month - 1, date, hour + hours, minute)).toISOString().slice(0, 19).replace(/[-:]/g, "");
}

function text(value: string): string {
  return value.replaceAll("\\", "\\\\").replaceAll(";", "\\;").replaceAll(",", "\\,").replace(/\r?\n/g, "\\n");
}

/** One card as an .ics file, as the app's own "Add to Calendar" gives it: timed events last two hours, the rest are all-day. */
export function calendarFile(event: EventCard, timezone: string, postUrl: string | null, now: Date = new Date()): string {
  const span =
    event.kind === "multiday" || event.start_time === null
      ? [`DTSTART;VALUE=DATE:${compact(event.start_date)}`, `DTEND;VALUE=DATE:${compact(nextDay(event.kind === "multiday" ? (event.end_date ?? event.start_date) : event.start_date))}`]
      : [`DTSTART;TZID=${timezone}:${localMoment(event.start_date, event.start_time)}`, `DTEND;TZID=${timezone}:${localMoment(event.start_date, event.start_time, ASSUMED_HOURS)}`];
  const place = [event.venue, event.address].filter((part, index, all): part is string => !!part && all.indexOf(part) === index);
  const lines = [
    "BEGIN:VCALENDAR",
    "VERSION:2.0",
    "PRODID:-//What To Do//phone page//EN",
    "BEGIN:VEVENT",
    `UID:event-${event.id}@where-to-go`,
    `DTSTAMP:${now.toISOString().slice(0, 19).replace(/[-:]/g, "")}Z`,
    `SUMMARY:${text(event.title)}`,
    ...span,
    ...(event.kind === "recurring" && event.rrule ? [`RRULE:${event.rrule}`] : []),
    ...(place.length ? [`LOCATION:${text(place.join(", "))}`] : []),
    `DESCRIPTION:${text([event.description, postUrl].filter(Boolean).join("\n\n"))}`,
    ...(postUrl ? [`URL:${postUrl}`] : []),
    "END:VEVENT",
    "END:VCALENDAR",
  ];
  return lines.join("\r\n") + "\r\n";
}
