import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { createApi, type CityStats, type Settings } from "../api/client";
import { ApiContext } from "../api/queries";
import { StatsScreen } from "./StatsScreen";

const STATS: CityStats = {
  posts: { read: 206, with_events: 140 },
  photos: { total: 234, read: 224, with_text: 168 },
  events: { announcements: 328, cards: 258, merged: 75, cancelled: 2, places: 1 },
  marked: 117,
  plans: [
    { plan: "maybe", count: 24 },
    { plan: "sure", count: 2 },
    { plan: "no", count: 91 },
    { plan: "went", count: 0 },
    { plan: null, count: 141 },
  ],
  interests: [
    { interest: 5, count: 23 },
    { interest: 4, count: 22 },
    { interest: 3, count: 5 },
    { interest: 2, count: 11 },
    { interest: 1, count: 7 },
    { interest: null, count: 190 },
  ],
  tags: [{ tag: "Лекция", count: 40 }],
  sources: [{ id: 1, title: "Афиша", posts: 30, events: 41 }],
  weeks: [{ start: "2026-11-09", posts: 12, posts_with_events: 7 }],
};

function setup(stats: CityStats) {
  const api = createApi("");
  vi.spyOn(api, "settings").mockResolvedValue({ active_city_id: 1 } as Settings);
  vi.spyOn(api, "cities").mockResolvedValue([{ id: 1, name: "Белград", timezone: "Europe/Belgrade" }]);
  vi.spyOn(api, "stats").mockResolvedValue(stats);
  render(
    <ApiContext.Provider value={api}>
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <StatsScreen />
        </MemoryRouter>
      </QueryClientProvider>
    </ApiContext.Provider>,
  );
}

describe("statistics", () => {
  it("shows the headline numbers, each with its own label", async () => {
    setup(STATS);
    expect(await screen.findByText("Постов прочитано", { selector: ".stat-tile__label" })).toBeInTheDocument();
    const tiles = document.querySelectorAll(".stat-tile");
    expect([...tiles].map((tile) => tile.querySelector(".stat-tile__value")?.textContent)).toEqual(["206", "224", "258", "117"]);
    expect(screen.getByText("в 140 постах есть события")).toBeInTheDocument();
  });

  it("counts the cards going from posts to plans", async () => {
    setup(STATS);
    const list = await screen.findByRole("list", { name: "От поста до планов" });
    const going = within(list).getByText("Собирались пойти").closest("li")!;
    expect(within(going).getByText("26")).toBeInTheDocument();
  });

  it("gives every status its count and share", async () => {
    setup(STATS);
    const row = (await screen.findByText("Не пойду")).closest("li")!;
    expect(within(row).getByText("91")).toBeInTheDocument();
    expect(within(row).getByText(/35\s%/)).toBeInTheDocument();
  });

  it("asks for a refresh while nothing is read", async () => {
    setup({ ...STATS, posts: { read: 0, with_events: 0 } });
    expect(await screen.findByText("Пока нечего считать")).toBeInTheDocument();
  });
});
