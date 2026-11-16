import type { Mark, Plan, PlanFilter } from "../api/client";
import type { IconName } from "../ui/Icon";

/** Each plan's name, as a button tooltip and in sentences, and its icon. */
export const PLANS: Record<Plan, { label: string; icon: IconName }> = {
  maybe: { label: "Maybe going", icon: "maybe" },
  sure: { label: "Going for sure", icon: "check" },
  no: { label: "Not going", icon: "cross" },
  went: { label: "Went", icon: "flag" },
};

/** The interest levels and what each says, as a button tooltip. */
export const INTEREST = [1, 2, 3, 4, 5] as const;
export const INTEREST_WORDS: Record<(typeof INTEREST)[number], string> = {
  1: "Not interesting at all",
  2: "Not very interesting",
  3: "So-so",
  4: "Interesting",
  5: "Very interesting",
};

export const PLAN_ORDER = Object.keys(PLANS) as Plan[];

/** Which cards each list shows: the feed what is not marked yet, the plans what the user is going to. */
export const SHOWN_PLANS = {
  feed: ["none"],
  going: ["maybe", "sure"],
  sure: ["sure"],
  past: ["maybe", "sure", "went"],
  calendar: ["none", "maybe", "sure"],
} satisfies Record<string, PlanFilter[]>;

/** A search looks through every card whatever its mark, so a card marked by mistake can still be found. */
export const plansToShow = (plans: PlanFilter[], search: string | undefined): PlanFilter[] => (search?.trim() ? [] : plans);

/** Interest and plan are independent; choosing the value a card already has clears it. */
export function nextMark(current: { interest?: number | null; plan?: Plan | null }, change: { interest: number } | { plan: Plan }): Mark {
  const interest = current.interest ?? null;
  const plan = current.plan ?? null;
  if ("interest" in change) return { interest: interest === change.interest ? null : change.interest, plan };
  return { interest, plan: plan === change.plan ? null : change.plan };
}
