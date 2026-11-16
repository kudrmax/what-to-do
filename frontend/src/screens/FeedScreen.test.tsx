import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { createApi, type City, type RefreshStatus, type Settings, type Source } from "../api/client";
import { ApiContext } from "../api/queries";
import { FeedScreen } from "./FeedScreen";
import { SourceList } from "./SourcesScreen";

const LONDON: City = { id: 1, name: "London", country: "United Kingdom", timezone: "Europe/London", card_language: "English" };
const IDLE = { stage: "idle", running: false, errors: [] } as unknown as RefreshStatus;

function channel(refreshed: string | null): Source {
  return { id: 1, title: "London Events", status: "new", kind: "telegram", handle: "londonevents", url: "https://t.me/londonevents", last_refreshed_at: refreshed, last_error: null, events_found: 0, paused: false };
}

function setup(sources: Source[], ui = <FeedScreen />) {
  const api = createApi("");
  vi.spyOn(api, "settings").mockResolvedValue({ active_city_id: 1 } as Settings);
  vi.spyOn(api, "cities").mockResolvedValue([LONDON]);
  vi.spyOn(api, "sources").mockResolvedValue(sources);
  vi.spyOn(api, "feed").mockResolvedValue([]);
  vi.spyOn(api, "tags").mockResolvedValue([]);
  vi.spyOn(api, "refreshStatus").mockResolvedValue(IDLE);
  const refresh = vi.spyOn(api, "refresh").mockResolvedValue({ ...IDLE, stage: "collecting", running: true } as RefreshStatus);
  render(
    <ApiContext.Provider value={api}>
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>{ui}</MemoryRouter>
      </QueryClientProvider>
    </ApiContext.Provider>,
  );
  return { refresh };
}

describe("a new city's feed", () => {
  it("before the first refresh says the sources wait to be read, not that all is caught up", async () => {
    const { refresh } = setup([channel(null)]);
    await screen.findByText("Ready for the first refresh");
    expect(screen.queryByText("All caught up")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Refresh now" }));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    await screen.findByText("Reading the sources of London");
  });

  it("after a refresh that found nothing it is caught up", async () => {
    setup([channel("2026-11-16T10:00:00Z")]);
    await screen.findByText("All caught up");
  });

  it("the Refresh button says which city it refreshes", async () => {
    setup([channel(null)]);
    await screen.findByText("Ready for the first refresh");
    expect(screen.getByRole("button", { name: "Refresh" }).getAttribute("data-tip")).toContain("of London");
  });

  it("an empty source list explains how to find channels in the city", async () => {
    setup([], <SourceList />);
    await screen.findByText("How to find sources");
    expect(screen.getAllByText("London events")).toHaveLength(1);
    expect(screen.getByText("t.me/s/name")).toBeTruthy();
  });
});
