import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import { ApiClient, feedParams, type EventCard } from "../api/client";
import { ApiContext } from "../api/hooks";
import { EventTime } from "./EventTime";
import { InterestPicker, PlanPicker } from "./MarkControls";

function card(overrides: Partial<EventCard> = {}): EventCard {
  return {
    id: 7,
    kind: "single",
    title: "Квиз",
    original_title: "Quiz",
    description: "",
    start_date: "2026-11-13",
    end_date: null,
    start_time: "20:00:00",
    recurrence: null,
    venue: null,
    address: null,
    map_url: null,
    price: null,
    tags: ["Игры и квизы"],
    image_url: null,
    is_cancelled: false,
    conflicts: [],
    source_ids: [1],
    mark: { interest: null, plan: null },
    ...overrides,
  };
}

function withApi(api: ApiClient, children: ReactNode) {
  return (
    <ApiContext.Provider value={api}>
      <QueryClientProvider client={new QueryClient()}>{children}</QueryClientProvider>
    </ApiContext.Provider>
  );
}

describe("EventTime", () => {
  it("shows the time, the dashed clock when unknown, the range for multiday", () => {
    const { rerender } = render(<EventTime event={card()} />);
    expect(screen.getByText("20:00")).toBeInTheDocument();
    rerender(<EventTime event={card({ start_time: null })} />);
    expect(screen.getByRole("img", { name: "Время уточняется" })).toBeInTheDocument();
    rerender(<EventTime event={card({ kind: "multiday", start_date: "2026-11-01", end_date: "2026-11-30" })} />);
    expect(screen.getByText("1–30 ноября")).toBeInTheDocument();
    rerender(<EventTime event={card({ kind: "recurring", recurrence: "FREQ=WEEKLY;BYDAY=TU" })} />);
    expect(screen.getByTitle("Повторяется")).toBeInTheDocument();
  });
});

describe("marks", () => {
  it("sets a value in one click and clears it with a second click on the same value", async () => {
    const api = new ApiClient("");
    const mark = vi.spyOn(api, "mark").mockResolvedValue(card());
    const { rerender } = render(withApi(api, <InterestPicker event={card({ mark: { interest: null, plan: "sure" } })} size="small" />));

    fireEvent.click(screen.getByRole("button", { name: "Интерес 4 из 5" }));
    await waitFor(() => expect(mark).toHaveBeenLastCalledWith(7, { interest: 4, plan: "sure" }));

    rerender(withApi(api, <InterestPicker event={card({ mark: { interest: 4, plan: "sure" } })} size="small" />));
    expect(screen.getByRole("button", { name: "Интерес 4 из 5" })).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(screen.getByRole("button", { name: "Интерес 4 из 5" }));
    await waitFor(() => expect(mark).toHaveBeenLastCalledWith(7, { interest: null, plan: "sure" }));
  });

  it("keeps interest when the plan changes", async () => {
    const api = new ApiClient("");
    const mark = vi.spyOn(api, "mark").mockResolvedValue(card());
    render(withApi(api, <PlanPicker event={card({ mark: { interest: 2, plan: null } })} size="large" />));
    fireEvent.click(screen.getByRole("button", { name: "Не пойду" }));
    await waitFor(() => expect(mark).toHaveBeenLastCalledWith(7, { interest: 2, plan: "no" }));
  });
});

describe("feedParams", () => {
  it("repeats list parameters and sends only the flags that are set", () => {
    const params = new URLSearchParams(feedParams({ start: "2026-11-09", tags: ["Кино", "Театр"], sources: [3], plans: ["maybe", "sure"], onlyTimed: true, hideMarked: false }));
    expect(params.getAll("tags")).toEqual(["Кино", "Театр"]);
    expect(params.getAll("plans")).toEqual(["maybe", "sure"]);
    expect(params.get("sources")).toBe("3");
    expect(params.get("only_timed")).toBe("true");
    expect(params.get("hide_multiday")).toBeNull();
    expect(params.get("hide_marked")).toBe("false");
  });
});
