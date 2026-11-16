import { Icon } from "../ui/Icon";

/** Claude found that the event fits what the user looks for first (the wish in settings). */
export function PriorityBadge() {
  return (
    <span className="badge badge--priority" data-tip="Fits what you look for first">
      <Icon name="sparkle" size={14} strokeWidth={2.2} />
      For you
    </span>
  );
}
