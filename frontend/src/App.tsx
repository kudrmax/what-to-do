import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes, useLocation, type Location } from "react-router-dom";

import type { Api } from "./api/client";
import { ApiContext } from "./api/queries";
import { AppShell } from "./app/AppShell";
import { EVENT_PATH, SECTIONS } from "./app/routes";
import { EventWindow } from "./events/EventWindow";
import { CalendarScreen } from "./screens/CalendarScreen";
import { FeedScreen } from "./screens/FeedScreen";
import { PlansScreen } from "./screens/PlansScreen";
import { SettingsScreen } from "./screens/SettingsScreen";
import { SourcesScreen } from "./screens/SourcesScreen";

const queries = new QueryClient({ defaultOptions: { queries: { staleTime: 30_000, retry: 1, refetchOnWindowFocus: false } } });

/** The screens; an event opens in a window over the screen it was opened from (the feed when opened by its link). */
function Screens() {
  const location = useLocation();
  const background = (location.state as { background?: Location } | null)?.background;
  const isEvent = location.pathname.startsWith("/event/");
  return (
    <>
      <AppShell>
        <Routes location={background ?? (isEvent ? { ...location, pathname: SECTIONS.feed.path, search: "" } : location)}>
          <Route path={SECTIONS.feed.path} element={<FeedScreen />} />
          <Route path={SECTIONS.calendar.path} element={<CalendarScreen />} />
          <Route path={SECTIONS.plans.path} element={<PlansScreen />} />
          <Route path={SECTIONS.sources.path} element={<SourcesScreen />} />
          <Route path={SECTIONS.settings.path} element={<SettingsScreen />} />
        </Routes>
      </AppShell>
      <Routes>
        <Route path={EVENT_PATH} element={<EventWindow />} />
        <Route path="*" element={null} />
      </Routes>
    </>
  );
}

export function App({ api }: { api: Api }) {
  return (
    <ApiContext.Provider value={api}>
      <QueryClientProvider client={queries}>
        <BrowserRouter>
          <Screens />
        </BrowserRouter>
      </QueryClientProvider>
    </ApiContext.Provider>
  );
}
