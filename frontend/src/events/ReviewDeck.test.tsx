import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { createApi, type EventCard, type Occurrence } from "../api/client";
import { ApiContext } from "../api/queries";
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
    conflicts: [],
    source_ids: [1],
    image_url: null,
    place: null,
    map_url: null,
  };
}

const feed: Occurrence[] = [
  { date: "2026-11-17", event: card(1, "Квиз") },
  { date: "2026-11-18", event: card(2, "Лекция") },
  { date: "2026-11-19", event: card(3, "Концерт") },
];

function setup() {
  const api = createApi("");
  const mark = vi.spyOn(api, "mark").mockResolvedValue(card(0, ""));
  vi.spyOn(api, "mentions").mockResolvedValue([]);
  render(
    <ApiContext.Provider value={api}>
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <ReviewDeck occurrences={feed} today="2026-11-16" />
        </MemoryRouter>
      </QueryClientProvider>
    </ApiContext.Provider>,
  );
  return { mark };
}

const topTitle = () => screen.getByRole("article").getAttribute("aria-label");
const press = (key: string, extra: KeyboardEventInit = {}) => fireEvent.keyDown(window, { key, ...extra });

describe("review deck", () => {
  it("answers the top card from the keyboard and moves to the next one", async () => {
    const { mark } = setup();
    expect(topTitle()).toBe("Квиз");
    press("ArrowLeft");
    await waitFor(() => expect(mark).toHaveBeenLastCalledWith(1, { interest: null, plan: "no" }));
    expect(topTitle()).toBe("Лекция");
    press("4");
    await waitFor(() => expect(mark).toHaveBeenLastCalledWith(2, { interest: 4, plan: null }));
    press("ArrowRight");
    await waitFor(() => expect(mark).toHaveBeenLastCalledWith(3, { interest: null, plan: "maybe" }));
    expect(screen.getByText("All caught up")).toBeTruthy();
  });

  it("takes the last answer back and returns its card", async () => {
    const { mark } = setup();
    press("ArrowUp");
    await waitFor(() => expect(mark).toHaveBeenLastCalledWith(1, { interest: null, plan: "sure" }));
    press("z", { metaKey: true });
    await waitFor(() => expect(mark).toHaveBeenLastCalledWith(1, { interest: null, plan: null }));
    expect(topTitle()).toBe("Квиз");
  });

  it("works with the mouse too, and leaves a skipped card unmarked", async () => {
    const { mark } = setup();
    fireEvent.click(screen.getByRole("button", { name: "Not going" }));
    await waitFor(() => expect(mark).toHaveBeenLastCalledWith(1, { interest: null, plan: "no" }));
    fireEvent.click(screen.getByRole("button", { name: "Later" }));
    expect(topTitle()).toBe("Концерт");
    expect(mark).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "Very interesting" }));
    await waitFor(() => expect(mark).toHaveBeenLastCalledWith(3, { interest: 5, plan: null }));
  });
});
