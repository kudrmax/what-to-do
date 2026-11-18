import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
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
  collection_ids: [],
  conflicts: [],
  source_ids: [1],
  image_url: null,
  place: null,
  map_url: null,
};

async function postLine(): Promise<HTMLElement> {
  await screen.findAllByRole("link", { name: /^Open / });
  const line = document.querySelector<HTMLElement>(".post-line");
  if (!line) throw new Error("no post line");
  return line;
}

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
    expect(screen.getByRole("group", { name: "Interest" })).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Status" })).toBeInTheDocument();
  });

  it("read-only keeps the tabs and the posts but leaves out every editing control", async () => {
    openOriginal(posts, true);
    fireEvent.click(await screen.findByRole("tab", { name: /Original/ }));
    expect(within(await postLine()).getByRole("link", { name: "Open post in Telegram" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "club" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Split into a separate event" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Merge with another event on this day" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Note to developer" })).not.toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "Interest" })).not.toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "Status" })).not.toBeInTheDocument();
    expect(document.querySelector(".details__marks")).toBeNull();
  });
});

describe("event window original", () => {
  it("names the link to each original by where it leads", async () => {
    const instagram = (id: number, url: string) => ({ ...mention(id, "eje"), source_kind: "instagram", post_url: url }) as Mention;
    openOriginal(() => Promise.resolve([instagram(1, "https://www.instagram.com/p/DfmlSc4DQL_/"), { ...instagram(2, "https://www.instagram.com/stories/highlights/17901/"), source_title: "club" }]));
    fireEvent.click(await screen.findByRole("tab", { name: /Original/ }));
    expect(within(await postLine()).getByRole("link", { name: "Open post on Instagram" })).toHaveAttribute("href", "https://www.instagram.com/p/DfmlSc4DQL_/");
    fireEvent.click(screen.getByRole("tab", { name: "club" }));
    expect(within(await postLine()).getByRole("link", { name: "Open highlight on Instagram" })).toBeInTheDocument();
  });

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
