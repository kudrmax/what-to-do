import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { createApi, type EventCard } from "../api/client";
import { ApiContext } from "../api/queries";
import { EventCardView } from "./EventCardView";
import { EventTime } from "./EventTime";
import { SearchField } from "./SearchField";
import { useEventFilters } from "./useEventFilters";

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
    tags: ["Игры и квизы", "Встреча"],
    interest: null,
    plan: null,
    is_going: false,
    is_cancelled: false,
    conflicts: [],
    source_ids: [1],
    image_url: null,
    place: null,
    map_url: null,
    ...overrides,
  };
}

function Where() {
  const location = useLocation();
  return <output data-testid="where">{location.pathname + location.search}</output>;
}

function setup(children: ReactNode, path = "/") {
  const api = createApi("");
  const mark = vi.spyOn(api, "mark").mockResolvedValue(card());
  render(
    <ApiContext.Provider value={api}>
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter initialEntries={[path]}>
          <Routes>
            <Route path="*" element={<>{children}<Where /></>} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    </ApiContext.Provider>,
  );
  return { mark };
}

describe("event card", () => {
  it("opens the event from anywhere on the card", () => {
    setup(<EventCardView event={card()} day="2026-11-13" />);
    fireEvent.click(screen.getByText("Командный квиз"));
    expect(screen.getByTestId("where").textContent).toBe("/event/7?day=2026-11-13");
  });

  it("marks without opening, and a second click on the same mark clears it", async () => {
    const { mark } = setup(<EventCardView event={card({ interest: 4 })} day="2026-11-13" />);
    fireEvent.click(screen.getByRole("button", { name: "Точно пойду" }));
    await waitFor(() => expect(mark).toHaveBeenLastCalledWith(7, { interest: 4, plan: "sure" }));
    fireEvent.click(screen.getByRole("button", { name: "Интересно" }));
    await waitFor(() => expect(mark).toHaveBeenLastCalledWith(7, { interest: null, plan: null }));
    expect(screen.getByTestId("where").textContent).toBe("/");
  });

  it("shows the price as words and the tag the list is filtered by", () => {
    setup(<EventCardView event={card()} day="2026-11-13" shownTags={["Встреча"]} />);
    expect(screen.getByText("Бесплатно")).toBeInTheDocument();
    expect(screen.getByText("Встреча")).toBeInTheDocument();
    expect(screen.queryByText("Игры и квизы")).not.toBeInTheDocument();
  });
});

describe("event time", () => {
  it("shows the time, the dashed clock when unknown, the range for multiday, a repeat mark for regular ones", () => {
    const { rerender } = render(<EventTime event={card()} />);
    expect(screen.getByText("20:00")).toBeInTheDocument();
    rerender(<EventTime event={card({ start_time: null })} />);
    expect(screen.getByRole("img", { name: "Время уточняется" })).toBeInTheDocument();
    rerender(<EventTime event={card({ kind: "multiday", start_date: "2026-11-01", end_date: "2026-11-30" })} />);
    expect(screen.getByText("1–30 ноября")).toBeInTheDocument();
    rerender(<EventTime event={card({ kind: "recurring", rrule: "FREQ=WEEKLY;BYDAY=TU" })} />);
    expect(document.querySelector('[data-tip="Каждый вторник"]')).not.toBeNull();
  });
});

describe("filters", () => {
  function Probe() {
    const filters = useEventFilters();
    return (
      <>
        <button onClick={() => filters.setList("tags", ["Кино", "Театр"])}>tags</button>
        <button onClick={() => filters.setFlag("only_timed", true)}>timed</button>
        <output data-testid="query">{JSON.stringify(filters.query)}</output>
      </>
    );
  }

  it("keeps filters in the address under the API's names", () => {
    setup(<Probe />);
    fireEvent.click(screen.getByText("tags"));
    fireEvent.click(screen.getByText("timed"));
    expect(screen.getByTestId("where").textContent).toBe("/?tags=%D0%9A%D0%B8%D0%BD%D0%BE&tags=%D0%A2%D0%B5%D0%B0%D1%82%D1%80&only_timed=true");
    expect(JSON.parse(screen.getByTestId("query").textContent!)).toEqual({ tags: ["Кино", "Театр"], sources: [], only_timed: true, hide_multiday: false, search: "" });
  });
});

describe("search", () => {
  function Probe() {
    const filters = useEventFilters();
    return (
      <>
        <SearchField value={filters.query.search ?? ""} onChange={filters.setSearch} />
        <output data-testid="search">{filters.query.search}</output>
      </>
    );
  }

  it("puts the words in the address once typing pauses, and clears them", async () => {
    setup(<Probe />);
    const field = screen.getByRole("searchbox", { name: "Поиск по событиям" });
    fireEvent.change(field, { target: { value: "импро иг" } });
    expect(screen.getByTestId("search").textContent).toBe("");
    await waitFor(() => expect(screen.getByTestId("search").textContent).toBe("импро иг"));
    expect(screen.getByTestId("where").textContent).toBe("/?search=%D0%B8%D0%BC%D0%BF%D1%80%D0%BE+%D0%B8%D0%B3");
    fireEvent.click(screen.getByRole("button", { name: "Очистить поиск" }));
    expect(field).toHaveValue("");
    expect(screen.getByTestId("where").textContent).toBe("/");
  });

  it("takes the cursor on «/» and lets go of the words on Esc", async () => {
    setup(<Probe />);
    const field = screen.getByRole("searchbox");
    fireEvent.keyDown(document.body, { key: "/" });
    expect(field).toHaveFocus();
    fireEvent.change(field, { target: { value: "джаз" } });
    fireEvent.keyDown(field, { key: "Escape" });
    expect(field).toHaveValue("");
  });
});
