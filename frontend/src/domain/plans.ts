import type { Plan, PlanFilter } from "../api/client";
import type { IconName } from "../ui/Icon";

/** Each plan's name, as a button tooltip and in sentences, and its icon. */
export const PLANS: Record<Plan, { label: string; icon: IconName }> = {
  maybe: { label: "Возможно пойду", icon: "maybe" },
  sure: { label: "Точно пойду", icon: "check" },
  no: { label: "Не пойду", icon: "cross" },
  went: { label: "Сходил", icon: "flag" },
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
