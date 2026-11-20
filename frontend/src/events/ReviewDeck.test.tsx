import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { createApi, type EventCard, type Mark } from "../api/client";
import { ApiContext, useFeed } from "../api/queries";
import { SHOWN_PLANS } from "../domain/plans";
import { ReviewDeck } from "./ReviewDeck";

function card(id: number, title: string): EventCard {
  return {
    id,
    kind: "single",
    title,
    original_title: title,
    description: "",
    start_date: "2026-11-17",
    end_date: null,
    start_time: "19:00:00",
    rrule: null,
    venue: null,
    address: null,
    price: null,
    currency: null,
    booking: null,
    tags: [],
    interest: null,
    plan: null,
    is_going: false,
    is_cancelled: false,
    is_priority: false,
    collection_ids: [],
    conflicts: [],
    source_ids: [1],
    image_url: null,
    image_urls: [],
    place: null,
    map_url: null,
  };
}

/** The deck over the same feed query as «Upcoming», with a server that keeps marks and leaves planned cards out of that feed. */
function Feed() {
  const feed = useFeed({ start: "2026-11-16", plans: SHOWN_PLANS.feed });
  return feed.data ? <ReviewDeck occurrences={feed.data} updatedAt={feed.dataUpdatedAt} today="2026-11-16" /> : null;
}

function setup(first: Partial<EventCard> = {}) {
  const server = new Map<number, EventCard>([1, 2, 3].map((id) => [id, { ...card(id, ["Quiz", "Lecture", "Concert"][id - 1]), ...(id === 1 ? first : {}) }]));
  const api = createApi("");
  vi.spyOn(api, "feed").mockImplementation(async () => [...server.values()].filter((event) => event.plan === null).map((event) => ({ date: "2026-11-17", event: { ...event } })));
  const mark = vi.spyOn(api, "mark").mockImplementation(async (id: number, value: Mark) => {
    const changed = { ...server.get(id)!, ...value };
    server.set(id, changed);
    return changed;
  });
  vi.spyOn(api, "mentions").mockResolvedValue([]);
  render(
    <ApiContext.Provider value={api}>
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <Feed />
        </MemoryRouter>
      </QueryClientProvider>
    </ApiContext.Provider>,
  );
  return { mark };
}

const topTitle = () => screen.getByRole("article").getAttribute("aria-label");
const press = (key: string, extra: KeyboardEventInit = {}) => act(() => void fireEvent.keyDown(window, { key, ...extra }));

describe("review deck", () => {
  it("shows on the card what a feed card shows, under the day heading the feed would give it", async () => {
    setup({ tags: ["Джаз", "Концерт"], place: "Galerija Polet, Cetinjska 15", description: "Квартет играет джаз" });
    await waitFor(() => expect(topTitle()).toBe("Quiz"));
    const top = screen.getByRole("article");
    expect(top.textContent).toContain("Квартет играет джаз");
    expect(top.textContent).toContain("Джаз");
    expect(top.textContent).not.toContain("Концерт");
    expect(top.textContent).not.toContain("Galerija Polet");
    expect(top.textContent).not.toContain("Interest");
    expect(screen.getByRole("heading", { level: 2 }).textContent).toContain("Tomorrow");
  });

  it("rates the card and keeps it, as the feed does; a plan takes it out of the feed and brings the next", async () => {
    const { mark } = setup();
    await waitFor(() => expect(topTitle()).toBe("Quiz"));
    press("4");
    await waitFor(() => expect(mark).toHaveBeenLastCalledWith(1, { interest: 4, plan: null }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Interesting" }).getAttribute("aria-pressed")).toBe("true"));
    expect(topTitle()).toBe("Quiz");
    press("ArrowLeft");
    await waitFor(() => expect(mark).toHaveBeenLastCalledWith(1, { interest: 4, plan: "no" }));
    expect(topTitle()).toBe("Lecture");
  });

  it("takes the last answer back and the card returns with the feed", async () => {
    const { mark } = setup();
    await waitFor(() => expect(topTitle()).toBe("Quiz"));
    press("ArrowUp");
    await waitFor(() => expect(mark).toHaveBeenLastCalledWith(1, { interest: null, plan: "sure" }));
    press("z", { metaKey: true });
    await waitFor(() => expect(mark).toHaveBeenLastCalledWith(1, { interest: null, plan: null }));
    await waitFor(() => expect(topTitle()).toBe("Quiz"));
  });

  it("works with the mouse too; Later steps on without marking", async () => {
    const { mark } = setup();
    await waitFor(() => expect(topTitle()).toBe("Quiz"));
    fireEvent.click(screen.getByRole("button", { name: "Later" }));
    expect(topTitle()).toBe("Lecture");
    fireEvent.click(screen.getByRole("button", { name: "Maybe" }));
    await waitFor(() => expect(mark).toHaveBeenLastCalledWith(2, { interest: null, plan: "maybe" }));
    expect(topTitle()).toBe("Concert");
    expect(mark).toHaveBeenCalledTimes(1);
  });
});
