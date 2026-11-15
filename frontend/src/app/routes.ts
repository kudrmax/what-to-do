import type { IconName } from "../ui/Icon";

export interface Section {
  path: string;
  title: string;
  icon: IconName;
}

/** Every screen of the app: its address, its name in the menu and as a heading, its icon. */
export const SECTIONS = {
  feed: { path: "/", title: "Upcoming", icon: "sun" },
  calendar: { path: "/calendar", title: "Calendar", icon: "calendar" },
  plans: { path: "/plans", title: "Going", icon: "bookmark" },
  sources: { path: "/sources", title: "Sources", icon: "feed" },
  stats: { path: "/stats", title: "Stats", icon: "chart" },
  settings: { path: "/settings", title: "Settings", icon: "settings" },
} satisfies Record<string, Section>;

export const EVENT_PATH = "/event/:id";

export function eventHref(id: number, day: string): string {
  return `/event/${id}?day=${day}`;
}

export function feedFromHref(day: string): string {
  return `${SECTIONS.feed.path}?from=${day}`;
}
