import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useEffect, useState, type ReactNode } from "react";
import { HashRouter, Route, Routes } from "react-router-dom";

import type { Api } from "../api/client";
import { ApiContext } from "../api/queries";
import { ReadOnlyContext } from "../app/readOnly";
import { EVENT_PATH, SECTIONS } from "../app/routes";
import { EventWindow } from "../events/EventWindow";
import { useScreenLocation } from "../events/navigation";
import { PlansScreen } from "../screens/PlansScreen";

function Screens({ tools }: { tools: ReactNode }) {
  const screen = useScreenLocation(SECTIONS.feed.path);
  return (
    <>
      <Routes location={screen}>
        <Route path="*" element={<PlansScreen tools={tools} />} />
      </Routes>
      <Routes>
        <Route path={EVENT_PATH} element={<EventWindow />} />
        <Route path="*" element={null} />
      </Routes>
    </>
  );
}

/** The app's own Want to go screen and event window over a read-only API; the address lives after the # so any sub-path works. */
export function PhoneScreens({ api, tools }: { api: Api; tools: ReactNode }) {
  const [queries] = useState(() => new QueryClient({ defaultOptions: { queries: { staleTime: Infinity, retry: false, refetchOnWindowFocus: false } } }));
  useEffect(() => void queries.invalidateQueries(), [api, queries]);
  return (
    <ReadOnlyContext.Provider value={true}>
      <ApiContext.Provider value={api}>
        <QueryClientProvider client={queries}>
          <HashRouter>
            <div className="phone">
              <Screens tools={tools} />
            </div>
          </HashRouter>
        </QueryClientProvider>
      </ApiContext.Provider>
    </ReadOnlyContext.Provider>
  );
}
