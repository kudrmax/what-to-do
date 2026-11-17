import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { createApi, type Collection, type EventCard, type Settings } from "../api/client";
import { ApiContext } from "../api/queries";
import { AppShell } from "../app/AppShell";
import { UpdatesProvider } from "../updates/UpdatesProvider";
import { EventCardView } from "./EventCardView";

function card(overrides: Partial<EventCard> = {}): EventCard {
  return {
    id: 7,
    kind: "single",
    title: "Квиз",
    original_title: "Quiz",
    description: "Командный квиз",
    start_date: "2026-11-13",
    end_date: null,
    start_time: "20:00:00",
    rrule: null,
    venue: null,
    address: null,
    price: 0,
    currency: null,
    booking: null,
    tags: ["Игры и квизы", "Встреча"],
    interest: null,
    plan: null,
    is_going: false,
    is_cancelled: false,
    is_priority: false,
    collection_ids: [],
    conflicts: [],
    source_ids: [1],
    image_url: null,
    place: null,
    map_url: null,
    ...overrides,
  };
}

const FUNNY: Collection = { id: 1, name: "Смешное", size: 0 };
const ODD: Collection = { id: 2, name: "Необычное", size: 1 };

function setup(enabled: boolean, collections: Collection[], event = card()) {
  const api = createApi("");
  vi.spyOn(api, "settings").mockResolvedValue({ collections_enabled: enabled } as Settings);
  vi.spyOn(api, "collections").mockResolvedValue(collections);
  vi.spyOn(api, "cities").mockResolvedValue([]);
  const setCollections = vi.spyOn(api, "setCollections").mockResolvedValue(event);
  render(
    <ApiContext.Provider value={api}>
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <UpdatesProvider>
            <AppShell screenPath="/">
              <EventCardView event={event} day="2026-11-13" />
            </AppShell>
          </UpdatesProvider>
        </MemoryRouter>
      </QueryClientProvider>
    </ApiContext.Provider>,
  );
  return { setCollections };
}

afterEach(cleanup);

describe("collections", () => {
  it("stay hidden while switched off", async () => {
    setup(false, [FUNNY]);
    await waitFor(() => expect(screen.getByRole("link", { name: "Квиз" })).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: "Add to a collection" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Collections" })).not.toBeInTheDocument();
  });

  it("stay hidden while switched on without a collection", async () => {
    setup(true, []);
    await waitFor(() => expect(screen.getByRole("link", { name: "Квиз" })).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: "Add to a collection" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Collections" })).not.toBeInTheDocument();
  });

  it("add the event from the heart without opening it, and show the menu item", async () => {
    const { setCollections } = setup(true, [FUNNY, ODD], card({ collection_ids: [2] }));
    const heart = await screen.findByRole("button", { name: "In collections" });
    expect(screen.getByRole("link", { name: "Collections" })).toBeInTheDocument();
    fireEvent.click(heart);
    const menu = screen.getByRole("menu", { name: "Collections" });
    expect(within(menu).getByRole("menuitemcheckbox", { name: "Необычное" })).toHaveAttribute("aria-checked", "true");
    fireEvent.click(within(menu).getByRole("menuitemcheckbox", { name: "Смешное" }));
    await waitFor(() => expect(setCollections).toHaveBeenCalledWith(7, [2, 1]));
  });
});
