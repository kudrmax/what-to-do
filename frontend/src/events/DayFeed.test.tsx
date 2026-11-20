import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { createApi, type EventCard, type Occurrence } from "../api/client";
import { ApiContext, useFeed } from "../api/queries";
import { event } from "../phone/fixtures";
import { DayFeed } from "./DayFeed";

const drawn = new Map<number, number>();

vi.mock("./EventTime", () => ({
  EventTime: ({ event: card }: { event: EventCard }) => {
    drawn.set(card.id, (drawn.get(card.id) ?? 0) + 1);
    return <span>time</span>;
  },
}));

const DAY = "2026-11-20";
const unmarked = (id: number, title: string) => event(id, title, "maybe", { plan: null, is_going: false });
const occurrences: Occurrence[] = [unmarked(1, "Quiz"), unmarked(2, "Concert")].map((card) => ({ event: card, date: DAY }) as Occurrence);

function Feed() {
  const feed = useFeed({ start: DAY });
  return feed.data ? <DayFeed occurrences={feed.data} today={DAY} /> : null;
}

function setup() {
  const api = createApi("");
  vi.spyOn(api, "feed").mockResolvedValue(occurrences);
  vi.spyOn(api, "settings").mockResolvedValue({ collections_enabled: false } as never);
  vi.spyOn(api, "cities").mockResolvedValue([]);
  vi.spyOn(api, "tags").mockResolvedValue([]);
  vi.spyOn(api, "stats").mockResolvedValue({} as never);
  let answer: (card: EventCard) => void = () => {};
  const mark = vi.spyOn(api, "mark").mockImplementation(() => new Promise((resolve) => (answer = resolve)));
  render(
    <ApiContext.Provider value={api}>
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <Feed />
        </MemoryRouter>
      </QueryClientProvider>
    </ApiContext.Provider>,
  );
  return { mark, answer: (card: EventCard) => answer(card) };
}

const cardOf = (title: string) => screen.getByRole("link", { name: title });

/** Lets the tags, settings and cities the cards read finish loading, so later draws come only from the mark. */
async function loaded() {
  await screen.findByText("Quiz");
  await act(() => new Promise((resolve) => setTimeout(resolve, 50)));
}

afterEach(() => {
  cleanup();
  drawn.clear();
});

describe("day feed", () => {
  it("shows a mark at once, before the server answers", async () => {
    const { mark } = setup();
    await loaded();
    fireEvent.click(within(cardOf("Quiz")).getByRole("button", { name: "Interesting" }));
    await vi.waitFor(() => expect(within(cardOf("Quiz")).getByRole("button", { name: "Interesting" })).toHaveAttribute("aria-pressed", "true"));
    expect(mark).toHaveBeenCalledWith(1, { interest: 4, plan: null });
  });

  it("draws again only the card that was marked", async () => {
    const { answer } = setup();
    await loaded();
    const concertBefore = drawn.get(2);
    fireEvent.click(within(cardOf("Quiz")).getByRole("button", { name: "Interesting" }));
    await act(async () => answer({ ...occurrences[0].event, interest: 4 }));
    await vi.waitFor(() => expect(within(cardOf("Quiz")).getByRole("button", { name: "Interesting" })).toHaveAttribute("aria-pressed", "true"));
    expect(drawn.get(2)).toBe(concertBefore);
    expect(drawn.get(1)).toBeGreaterThan(1);
  });

  it("takes the mark back when the server refuses it", async () => {
    const { mark } = setup();
    mark.mockRejectedValueOnce(new Error("offline"));
    await loaded();
    fireEvent.click(within(cardOf("Quiz")).getByRole("button", { name: "Interesting" }));
    await vi.waitFor(() => expect(mark).toHaveBeenCalled());
    await vi.waitFor(() => expect(within(cardOf("Quiz")).getByRole("button", { name: "Interesting" })).toHaveAttribute("aria-pressed", "false"));
  });
});
