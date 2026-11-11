import type { IconName } from "../ui/Icon";

export interface Section {
  path: string;
  title: string;
  icon: IconName;
}

/** Every screen of the app: its address, its name in the menu and as a heading, its icon. */
export const SECTIONS = {
  feed: { path: "/", title: "Ближайшие", icon: "sun" },
  calendar: { path: "/calendar", title: "Календарь", icon: "calendar" },
  plans: { path: "/plans", title: "Собираюсь пойти", icon: "bookmark" },
  sources: { path: "/sources", title: "Источники", icon: "feed" },
  stats: { path: "/stats", title: "Статистика", icon: "chart" },
  settings: { path: "/settings", title: "Настройки", icon: "settings" },
} satisfies Record<string, Section>;

export const EVENT_PATH = "/event/:id";

export function eventHref(id: number, day: string): string {
  return `/event/${id}?day=${day}`;
}

export function feedFromHref(day: string): string {
  return `${SECTIONS.feed.path}?from=${day}`;
}
