import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, expect, test, vi } from "vitest";

import { createApi } from "../api/client";
import { ApiContext } from "../api/queries";
import { ReadOnlyContext } from "../app/readOnly";
import { event, PLANS } from "../phone/fixtures";
import { PlansScreen } from "./PlansScreen";

beforeEach(() => localStorage.clear());

function show(path: string, readOnly = false) {
  const api = createApi("");
  vi.spyOn(api, "settings").mockResolvedValue(PLANS.settings);
  vi.spyOn(api, "cities").mockResolvedValue(PLANS.cities);
  vi.spyOn(api, "tags").mockResolvedValue(PLANS.tags);
  vi.spyOn(api, "sources").mockResolvedValue(PLANS.sources);
  const unmarked = [{ date: "2026-11-20", event: event(9, "Unmarked", "maybe", { plan: null }) }];
  vi.spyOn(api, "feed").mockImplementation(async (query) => ("only_timed" in query ? [] : unmarked));
  render(
    <ReadOnlyContext.Provider value={readOnly}>
      <ApiContext.Provider value={api}>
        <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
          <MemoryRouter initialEntries={[path]}>
            <PlansScreen />
          </MemoryRouter>
        </QueryClientProvider>
      </ApiContext.Provider>
    </ReadOnlyContext.Provider>,
  );
}

test("in the app, a search that finds nothing here leads to the feed", async () => {
  show("/plans?search=jazz");
  expect(await screen.findByRole("link", { name: "Open Upcoming" })).toBeInTheDocument();
});

test("in the app, an empty list says how to fill it", async () => {
  show("/plans");
  expect(await screen.findByText(/Mark an event as/)).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Want to go" })).toBeInTheDocument();
});

test("read-only, a search that finds nothing only says so", async () => {
  show("/plans?search=jazz", true);
  expect(await screen.findByText("Nothing found")).toBeInTheDocument();
  expect(screen.queryByRole("link")).not.toBeInTheDocument();
});

test("read-only, an empty list gives no instructions", async () => {
  show("/plans", true);
  expect(await screen.findByText("No plans yet")).toBeInTheDocument();
  expect(screen.queryByText(/Mark an event as/)).not.toBeInTheDocument();
});
