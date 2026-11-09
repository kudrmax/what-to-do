import type { EventCard } from "../api/client";
import { clock, dateRange } from "../domain/dates";
import { Icon, UnknownTimeIcon } from "./Icon";

interface Props {
  event: EventCard;
  className?: string;
  iconSize?: number;
}

/** The time slot of a card: a clock time, the dashed clock when unknown, a date range for multiday events. */
export function EventTime({ event, className, iconSize = 20 }: Props) {
  if (event.kind === "multiday" && event.end_date) {
    return <span className={className}>{dateRange(event.start_date, event.end_date)}</span>;
  }
  const time = event.start_time ? <span className={className}>{clock(event.start_time)}</span> : <UnknownTimeIcon size={iconSize} />;
  if (event.kind !== "recurring") return time;
  return (
    <span className="event-time__recurring" title="Повторяется">
      {time}
      <Icon name="repeat" size={14} />
    </span>
  );
}
