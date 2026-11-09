import type { EventCard } from "../api/client";
import { clock, dateRange } from "../domain/dates";
import { describeRecurrence } from "../domain/recurrence";
import { Icon, UnknownTimeIcon } from "../ui/Icon";

/** The time slot of an event: a clock time, the dashed clock when unknown, a date range for multiday events; a repeat mark for regular ones. */
export function EventTime({ event, className = "", iconSize = 18 }: { event: EventCard; className?: string; iconSize?: number }) {
  if (event.kind === "multiday" && event.end_date) {
    return <span className={className}>{dateRange(event.start_date, event.end_date)}</span>;
  }
  const time = event.start_time ? clock(event.start_time) : null;
  return (
    <span className={`event-time ${className}`}>
      {time ?? (
        <span className="event-time__unknown" data-tip="Время уточняется">
          <UnknownTimeIcon size={iconSize} />
        </span>
      )}
      {event.kind === "recurring" && (
        <span className="event-time__repeat" data-tip={describeRecurrence(event.rrule) ?? "Повторяется"}>
          <Icon name="repeat" size={14} />
        </span>
      )}
    </span>
  );
}
