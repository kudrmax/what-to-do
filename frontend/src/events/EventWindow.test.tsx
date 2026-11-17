import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { ApiError, createApi, type EventCard, type Mention } from "../api/client";
import { ApiContext } from "../api/queries";
import { ReadOnlyContext } from "../app/readOnly";
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
  is_priority: false,
  conflicts: [],
  source_ids: [1],
  image_url: null,
  place: null,
  map_url: null,
};

function openOriginal(mentions: () => Promise<Mention[]>, readOnly = false) {
  const api = createApi("");
  vi.spyOn(api, "event").mockResolvedValue(EVENT);
  vi.spyOn(api, "feed").mockResolvedValue([{ date: "2026-11-13", event: { ...EVENT, id: 8, title: "Другое" } }]);
  const loadMentions = vi.spyOn(api, "mentions").mockImplementation(mentions);
  render(
    <ReadOnlyContext.Provider value={readOnly}>
      <ApiContext.Provider value={api}>
        <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
          <MemoryRouter initialEntries={["/event/7?day=2026-11-13"]}>
            <Routes>
              <Route path="/event/:id" element={<EventWindow />} />
            </Routes>
          </MemoryRouter>
        </QueryClientProvider>
      </ApiContext.Provider>
    </ReadOnlyContext.Provider>,
  );
  return loadMentions;
}

function mention(id: number, sourceTitle: string): Mention {
  return {
    id,
    data: { start_date: "2026-11-13", from_organizer: false },
    locked: false,
    source_id: id,
    source_title: sourceTitle,
    source_kind: "telegram",
    post_url: `https://t.me/${sourceTitle}/${id}`,
    post_text: "Квиз в пятницу",
    published_at: "2026-11-10T10:00:00Z",
    photos: [],
    event_photo: null,
    event_lines: [],
  } as unknown as Mention;
}

describe("event window editing", () => {
  const posts = () => Promise.resolve([mention(1, "afisha"), mention(2, "club")]);

  it("offers to split, merge and note in the app", async () => {
    openOriginal(posts);
    fireEvent.click(await screen.findByRole("tab", { name: /Original/ }));
    expect(await screen.findByRole("button", { name: "Split into a separate event" })).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Merge with another event on this day" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Note to developer" })).toBeInTheDocument();
  });

  it("read-only keeps the tabs and the posts but leaves out every editing control", async () => {
    openOriginal(posts, true);
    fireEvent.click(await screen.findByRole("tab", { name: /Original/ }));
    expect(await screen.findByRole("link", { name: "Open post in Telegram" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "club" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Split into a separate event" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Merge with another event on this day" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Note to developer" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Going for sure" })).toHaveAttribute("aria-disabled", "true");
  });
});

describe("event window original", () => {
  it("says the posts did not load instead of showing an empty tab, and loads them again on request", async () => {
    const loadMentions = openOriginal(() => Promise.reject(new ApiError(404, "Not Found")));
    fireEvent.click(await screen.findByRole("tab", { name: "Original" }));

    expect(await screen.findByText("Couldn’t load")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(loadMentions).toHaveBeenCalledTimes(2);
  });

  it("says the posts are loading while they are on the way", async () => {
    openOriginal(() => new Promise(() => {}));
    fireEvent.click(await screen.findByRole("tab", { name: "Original" }));

    expect(screen.getByText("Loading original…")).toBeTruthy();
  });
});
