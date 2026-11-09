import { useLocation, useNavigate } from "react-router-dom";

import { eventHref } from "../app/routes";

/** Opens an event in a window over the current screen, which stays under it. */
export function useOpenEvent() {
  const navigate = useNavigate();
  const location = useLocation();
  const background = (location.state as { background?: unknown } | null)?.background ?? location;
  return (id: number, day: string, replace = false) => navigate(eventHref(id, day), { state: { background }, replace });
}
