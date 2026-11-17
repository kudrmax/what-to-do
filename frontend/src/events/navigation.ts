import { useLocation, useNavigate, type Location } from "react-router-dom";

import { eventHref } from "../app/routes";

/** Opens an event in a window over the current screen, which stays under it. */
export function useOpenEvent() {
  const navigate = useNavigate();
  const location = useLocation();
  const background = (location.state as { background?: unknown } | null)?.background ?? location;
  return (id: number, day: string, replace = false) => navigate(eventHref(id, day), { state: { background }, replace });
}

/** The screen to show under the current address: the one an event was opened over, or `home` for an event opened by its link. */
export function useScreenLocation(home: string): Location {
  const location = useLocation();
  const background = (location.state as { background?: Location } | null)?.background;
  const isEvent = location.pathname.startsWith("/event/");
  return background ?? (isEvent ? { ...location, pathname: home, search: "" } : location);
}
