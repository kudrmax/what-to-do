import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes } from "react-router-dom";

import { ApiClient } from "./api/client";
import { ApiContext } from "./api/hooks";
import { AppShell } from "./components/AppShell";
import { CalendarScreen } from "./screens/CalendarScreen";
import { EventScreen } from "./screens/EventScreen";
import { FeedScreen } from "./screens/FeedScreen";
import { PlansScreen } from "./screens/PlansScreen";
import { SourcesScreen } from "./screens/SourcesScreen";

const queries = new QueryClient({ defaultOptions: { queries: { staleTime: 30_000, retry: 1, refetchOnWindowFocus: false } } });

export function App({ api }: { api: ApiClient }) {
  return (
    <ApiContext.Provider value={api}>
      <QueryClientProvider client={queries}>
        <BrowserRouter>
          <Routes>
            <Route path="/" element={<AppShell><FeedScreen /></AppShell>} />
            <Route path="/calendar" element={<AppShell><CalendarScreen /></AppShell>} />
            <Route path="/plans" element={<AppShell><PlansScreen /></AppShell>} />
            <Route path="/sources" element={<AppShell><SourcesScreen /></AppShell>} />
            <Route path="/event/:id" element={<AppShell activeSection="/"><EventScreen /></AppShell>} />
          </Routes>
        </BrowserRouter>
      </QueryClientProvider>
    </ApiContext.Provider>
  );
}
