import type { EventCard, Plan } from "../api/client";
import { useSetMark } from "../api/queries";
import { useReadOnly } from "../app/readOnly";
import { INTEREST, INTEREST_WORDS, nextMark, PLAN_ORDER, PLANS } from "../domain/plans";
import { Icon } from "../ui/Icon";
import "./MarkPickers.css";

type Size = "small" | "large";

/** Read-only, the marks look the same but are not buttons one can press: no click, no hover, no focus. */
function useMark(event: EventCard) {
  const setMark = useSetMark();
  const readOnly = useReadOnly();
  const press = (run: () => void) => (readOnly ? { "aria-disabled": true, tabIndex: -1 } : { onClick: run });
  return {
    interest: event.interest ?? null,
    plan: event.plan ?? null,
    className: readOnly ? " marks--read-only" : "",
    setInterest: (value: number) => press(() => setMark.mutate({ id: event.id, mark: nextMark(event, { interest: value }) })),
    setPlan: (value: Plan) => press(() => setMark.mutate({ id: event.id, mark: nextMark(event, { plan: value }) })),
  };
}

export function InterestPicker({ event, size }: { event: EventCard; size: Size }) {
  const mark = useMark(event);
  return (
    <div role="group" aria-label="Interest" className={`marks marks--${size}${mark.className}`}>
      {INTEREST.map((n) => (
        <button key={n} type="button" className="marks__interest" aria-label={INTEREST_WORDS[n]} data-tip={INTEREST_WORDS[n]} aria-pressed={mark.interest === n} {...mark.setInterest(n)}>
          {n}
        </button>
      ))}
    </div>
  );
}

export function PlanPicker({ event, size }: { event: EventCard; size: Size }) {
  const mark = useMark(event);
  return (
    <div role="group" aria-label="Status" className={`marks marks--${size}${mark.className}`}>
      {PLAN_ORDER.map((plan) => (
        <button
          key={plan}
          type="button"
          className={`marks__plan marks__plan--${plan}`}
          aria-label={PLANS[plan].label}
          data-tip={PLANS[plan].label}
          aria-pressed={mark.plan === plan}
          {...mark.setPlan(plan)}
        >
          <Icon name={PLANS[plan].icon} size={size === "small" ? 14 : 18} strokeWidth={2.2} />
        </button>
      ))}
    </div>
  );
}
