import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { createApi, type Source } from "../api/client";
import { ApiContext } from "../api/queries";
import { SourceList } from "./SourcesScreen";

function source(id: number, title: string, status: Source["status"]): Source {
  return {
    id,
    title,
    status,
    kind: "telegram",
    handle: `channel${id}`,
    url: `https://t.me/channel${id}`,
    last_refreshed_at: null,
    last_error: null,
    events_found: 0,
  };
}

function setup(sources: Source[]) {
  const api = createApi("");
  vi.spyOn(api, "sources").mockResolvedValue(sources);
  const mark = vi.spyOn(api, "markSource").mockResolvedValue(sources[0]);
  render(
    <ApiContext.Provider value={api}>
      <QueryClientProvider client={new QueryClient()}>
        <SourceList />
      </QueryClientProvider>
    </ApiContext.Provider>,
  );
  return { mark };
}

describe("source status", () => {
  it("puts favorite sources first and shows which are favorite", async () => {
    setup([source(1, "Афиша", "new"), source(2, "Квизы", "favorite")]);
    const rows = await screen.findAllByRole("row");
    expect(within(rows[0]).getByText("Квизы")).toBeTruthy();
    expect(within(rows[0]).getByRole("button", { name: "Убрать из избранного" }).getAttribute("aria-pressed")).toBe("true");
    expect(within(rows[1]).getByRole("button", { name: "В избранное" }).getAttribute("aria-pressed")).toBe("false");
  });

  it("toggles a source between new and favorite", async () => {
    const { mark } = setup([source(1, "Афиша", "new"), source(2, "Квизы", "favorite")]);
    fireEvent.click(await screen.findByRole("button", { name: "В избранное" }));
    await waitFor(() => expect(mark).toHaveBeenCalledWith(1, "favorite"));
    fireEvent.click(screen.getByRole("button", { name: "Убрать из избранного" }));
    await waitFor(() => expect(mark).toHaveBeenCalledWith(2, "new"));
  });
});
