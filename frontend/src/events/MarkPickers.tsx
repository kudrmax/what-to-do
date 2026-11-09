import type { EventCard, Plan } from "../api/client";
import { useSetMark } from "../api/queries";
import { PLAN_ORDER, PLANS } from "../domain/plans";
import { Icon } from "../ui/Icon";
import "./MarkPickers.css";

type Size = "small" | "large";

const INTEREST = [1, 2, 3, 4, 5] as const;
const INTEREST_WORDS: Record<(typeof INTEREST)[number], string> = {
  1: "Совсем неинтересно",
  2: "Скорее неинтересно",
  3: "Так себе",
  4: "Интересно",
  5: "Очень интересно",
};

/** Interest and plan are independent; a second click on the chosen value clears it. */
function useMark(event: EventCard) {
  const setMark = useSetMark();
  const interest = event.interest ?? null;
  const plan = event.plan ?? null;
  return {
    interest,
    plan,
    setInterest: (value: number) => setMark.mutate({ id: event.id, mark: { interest: interest === value ? null : value, plan } }),
    setPlan: (value: Plan) => setMark.mutate({ id: event.id, mark: { interest, plan: plan === value ? null : value } }),
  };
}

export function InterestPicker({ event, size }: { event: EventCard; size: Size }) {
  const mark = useMark(event);
  return (
    <div role="group" aria-label="Интерес" className={`marks marks--${size}`}>
      {INTEREST.map((n) => (
        <button key={n} type="button" className="marks__interest" aria-label={INTEREST_WORDS[n]} data-tip={INTEREST_WORDS[n]} aria-pressed={mark.interest === n} onClick={() => mark.setInterest(n)}>
          {n}
        </button>
      ))}
    </div>
  );
}

export function PlanPicker({ event, size }: { event: EventCard; size: Size }) {
  const mark = useMark(event);
  return (
    <div role="group" aria-label="Статус" className={`marks marks--${size}`}>
      {PLAN_ORDER.map((plan) => (
        <button
          key={plan}
          type="button"
          className={`marks__plan marks__plan--${plan}`}
          aria-label={PLANS[plan].label}
          data-tip={PLANS[plan].label}
          aria-pressed={mark.plan === plan}
          onClick={() => mark.setPlan(plan)}
        >
          <Icon name={PLANS[plan].icon} size={size === "small" ? 16 : 18} strokeWidth={2.2} />
        </button>
      ))}
    </div>
  );
}
