import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ApiError, createApi, type PotentialSource, type Source } from "../api/client";
import { ApiContext } from "../api/queries";
import { PotentialSources } from "./PotentialSources";

function potential(id: number, handle: string, processed: boolean, posts = 1): PotentialSource {
  return {
    id,
    handle,
    processed,
    url: `https://t.me/${handle}`,
    found_at: "2026-11-01T10:00:00Z",
    origins: Array.from({ length: posts }, (_, i) => ({
      via: i === 0 ? "forward" : "link",
      source_title: `Канал ${i + 1}`,
      post_url: `https://t.me/source/${i + 1}`,
      published_at: "2026-11-01T10:00:00Z",
    })),
  };
}

function setup(found: PotentialSource[]) {
  const api = createApi("");
  vi.spyOn(api, "potentialSources").mockResolvedValue(found);
  const mark = vi.spyOn(api, "markPotentialSource").mockResolvedValue(undefined as never);
  const adopt = vi.spyOn(api, "adoptPotentialSource").mockResolvedValue({} as Source);
  render(
    <ApiContext.Provider value={api}>
      <QueryClientProvider client={new QueryClient()}>
        <PotentialSources />
      </QueryClientProvider>
    </ApiContext.Provider>,
  );
  return { mark, adopt };
}

describe("potential sources", () => {
  it("shows each channel with the posts that pointed to it and keeps processed ones folded away", async () => {
    setup([potential(1, "lectures_bg", false, 2), potential(2, "old_one", true)]);
    const channel = await screen.findByRole("link", { name: "@lectures_bg" });
    expect(channel.getAttribute("href")).toBe("https://t.me/lectures_bg");
    const row = channel.closest("li") as HTMLElement;
    expect(within(row).getByRole("link", { name: "Канал 1" }).getAttribute("href")).toBe("https://t.me/source/1");
    expect(within(row).getByLabelText("Пост переслан из этого канала")).toBeTruthy();
    expect(within(row).getByLabelText("Пост ссылается на этот канал")).toBeTruthy();
    expect(screen.getByText("Неинтересные").closest("details")?.open).toBe(false);
  });

  it("shows the first posts and the rest on request", async () => {
    setup([potential(1, "busy", false, 5)]);
    await screen.findByRole("link", { name: "@busy" });
    expect(screen.queryByRole("link", { name: "Канал 4" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Ещё 2 поста" }));
    expect(screen.getByRole("link", { name: "Канал 5" })).toBeTruthy();
  });

  it("turns a channel into a source", async () => {
    const { adopt } = setup([potential(1, "lectures_bg", false)]);
    fireEvent.click(await screen.findByRole("button", { name: "В источники" }));
    await waitFor(() => expect(adopt).toHaveBeenCalledWith(1));
  });

  it("keeps a channel that could not be added and says why", async () => {
    const { adopt } = setup([potential(1, "lectures_bg", false)]);
    adopt.mockRejectedValue(new ApiError(422, "Канал закрыт или у него выключен веб-просмотр"));
    fireEvent.click(await screen.findByRole("button", { name: "В источники" }));
    expect(await screen.findByText("Не получилось добавить: Канал закрыт или у него выключен веб-просмотр")).toBeTruthy();
    expect(screen.getByRole("button", { name: "В источники" })).toBeTruthy();
  });

  it("puts an uninteresting channel away and brings it back", async () => {
    const { mark } = setup([potential(1, "lectures_bg", false), potential(2, "old_one", true)]);
    fireEvent.click(await screen.findByRole("button", { name: "Неинтересно" }));
    await waitFor(() => expect(mark).toHaveBeenCalledWith(1, true));
    fireEvent.click(screen.getByRole("button", { name: "Вернуть" }));
    await waitFor(() => expect(mark).toHaveBeenCalledWith(2, false));
  });
});
