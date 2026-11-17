import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes } from "react-router-dom";

import type { Api } from "./api/client";
import { ApiContext } from "./api/queries";
import { AppShell } from "./app/AppShell";
import { EVENT_PATH, SECTIONS } from "./app/routes";
import { EventWindow } from "./events/EventWindow";
import { useScreenLocation } from "./events/navigation";
import { CalendarScreen } from "./screens/CalendarScreen";
import { CollectionsScreen } from "./screens/CollectionsScreen";
import { FeedScreen } from "./screens/FeedScreen";
import { PlansScreen } from "./screens/PlansScreen";
import { SettingsScreen } from "./screens/SettingsScreen";
import { SourcesScreen } from "./screens/SourcesScreen";
import { StatsScreen } from "./screens/StatsScreen";
import { onNativeCheckForUpdates } from "./native/nativeHost";
import { UpdatesProvider } from "./updates/UpdatesProvider";

const queries = new QueryClient({ defaultOptions: { queries: { staleTime: 30_000, retry: 1, refetchOnWindowFocus: false } } });

/** The screens; an event opens in a window over the screen it was opened from (the feed when opened by its link). */
function Screens() {
  const screen = useScreenLocation(SECTIONS.feed.path);
  return (
    <>
      <AppShell screenPath={screen.pathname}>
        <Routes location={screen}>
          <Route path={SECTIONS.feed.path} element={<FeedScreen />} />
          <Route path={SECTIONS.calendar.path} element={<CalendarScreen />} />
          <Route path={SECTIONS.plans.path} element={<PlansScreen />} />
          <Route path={SECTIONS.collections.path} element={<CollectionsScreen />} />
          <Route path={SECTIONS.sources.path} element={<SourcesScreen />} />
          <Route path={SECTIONS.stats.path} element={<StatsScreen />} />
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
          <UpdatesProvider onNativeCheck={onNativeCheckForUpdates}>
            <Screens />
          </UpdatesProvider>
        </BrowserRouter>
      </QueryClientProvider>
    </ApiContext.Provider>
  );
}
