import type { EventCard, Plan } from "../api/client";
import { useSetMark } from "../api/hooks";
import { Icon, type IconName } from "./Icon";
import "./MarkControls.css";

const PLANS: { plan: Plan; label: string; icon: IconName; stroke: number }[] = [
  { plan: "maybe", label: "Возможно пойду", icon: "maybe", stroke: 2.2 },
  { plan: "sure", label: "Точно пойду", icon: "check", stroke: 2.4 },
  { plan: "no", label: "Не пойду", icon: "cross", stroke: 2.4 },
  { plan: "went", label: "Сходил", icon: "flag", stroke: 2.2 },
];

type Size = "small" | "large";

/** Interest and plan are independent; a second click on the chosen value clears it. */
function useMarkSaver(event: EventCard) {
  const setMark = useSetMark();
  const { interest, plan } = event.mark;
  return {
    interest: interest ?? null,
    plan: plan ?? null,
    setInterest: (value: number) => setMark.mutate({ id: event.id, mark: { interest: interest === value ? null : value, plan: plan ?? null } }),
    setPlan: (value: Plan) => setMark.mutate({ id: event.id, mark: { interest: interest ?? null, plan: plan === value ? null : value } }),
  };
}

export function InterestPicker({ event, size }: { event: EventCard; size: Size }) {
  const marks = useMarkSaver(event);
  return (
    <div role="group" aria-label="Интерес" className={`marks marks--${size}`}>
      {[1, 2, 3, 4, 5].map((n) => (
        <button key={n} type="button" className="marks__interest" aria-label={`Интерес ${n} из 5`} aria-pressed={marks.interest === n} onClick={() => marks.setInterest(n)}>
          {n}
        </button>
      ))}
    </div>
  );
}

export function PlanPicker({ event, size }: { event: EventCard; size: Size }) {
  const marks = useMarkSaver(event);
  return (
    <div role="group" aria-label="Статус" className={`marks marks--${size}`}>
      {PLANS.map((item) => (
        <button
          key={item.plan}
          type="button"
          className={`marks__plan marks__plan--${item.plan}`}
          aria-label={item.label}
          title={item.label}
          aria-pressed={marks.plan === item.plan}
          onClick={() => marks.setPlan(item.plan)}
        >
          <Icon name={item.icon} size={size === "small" ? 16 : 18} strokeWidth={item.stroke} />
        </button>
      ))}
    </div>
  );
}
