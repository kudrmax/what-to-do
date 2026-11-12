import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { ApiError, createApi, type EventCard, type Mention } from "../api/client";
import { ApiContext } from "../api/queries";
import { EventWindow } from "./EventWindow";

const EVENT: EventCard = {
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

function openOriginal(mentions: () => Promise<Mention[]>) {
  const api = createApi("");
  vi.spyOn(api, "event").mockResolvedValue(EVENT);
  vi.spyOn(api, "feed").mockResolvedValue([]);
  const loadMentions = vi.spyOn(api, "mentions").mockImplementation(mentions);
  render(
    <ApiContext.Provider value={api}>
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter initialEntries={["/event/7?day=2026-11-13"]}>
          <Routes>
            <Route path="/event/:id" element={<EventWindow />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    </ApiContext.Provider>,
  );
  return loadMentions;
}

describe("event window original", () => {
  it("says the posts did not load instead of showing an empty tab, and loads them again on request", async () => {
    const loadMentions = openOriginal(() => Promise.reject(new ApiError(404, "Not Found")));
    fireEvent.click(await screen.findByRole("tab", { name: "Оригинал" }));

    expect(await screen.findByText("Не получилось загрузить")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Попробовать ещё раз" }));
    expect(loadMentions).toHaveBeenCalledTimes(2);
  });

  it("says the posts are loading while they are on the way", async () => {
    openOriginal(() => new Promise(() => {}));
    fireEvent.click(await screen.findByRole("tab", { name: "Оригинал" }));

    expect(screen.getByText("Загружаю пост…")).toBeTruthy();
  });
});
