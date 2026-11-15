import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { createApi, type SitePreview, type Source } from "../api/client";
import { ApiContext } from "../api/queries";
import { AddSourceForm, SourceList } from "./SourcesScreen";

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

const SITE_PREVIEW: SitePreview = {
  kind: "web",
  title: "Polako Hedonist",
  handle: "polakohedonist.club/ru/events/",
  pages_found: 820,
  examples: [
    { title: "Искусство быть нелепым", day: "2026-11-18", time: "19:00", url: "https://polakohedonist.club/ru/events/a" },
    { title: "Выставка-ярмарка антиквариата", day: "2026-11-18", time: null, url: "https://polakohedonist.club/ru/events/b" },
  ],
};

function setupForm(preview: SitePreview) {
  const api = createApi("");
  const previewSource = vi.spyOn(api, "previewSource").mockResolvedValue(preview);
  const addSource = vi.spyOn(api, "addSource").mockResolvedValue(source(9, preview.title, "new"));
  render(
    <ApiContext.Provider value={api}>
      <QueryClientProvider client={new QueryClient()}>
        <AddSourceForm />
      </QueryClientProvider>
    </ApiContext.Provider>,
  );
  const submit = (link: string) => {
    fireEvent.change(screen.getByLabelText("Ссылка"), { target: { value: link } });
    fireEvent.click(screen.getByRole("button", { name: "Добавить" }));
  };
  return { previewSource, addSource, submit };
}

describe("adding a source", () => {
  it("shows site preview before adding", async () => {
    const { addSource, submit } = setupForm(SITE_PREVIEW);
    submit("https://polakohedonist.club/ru/events/a");
    const card = await screen.findByRole("region", { name: "Polako Hedonist" });
    expect(within(card).getByText("На сайте 820 событий")).toBeTruthy();
    expect(within(card).getByText("В приложение попадут события вашего города на ближайшие 30 дней")).toBeTruthy();
    expect(within(card).getByText("Искусство быть нелепым")).toBeTruthy();
    expect(within(card).getAllByText("среда, 18 ноября")).toHaveLength(2);
    expect(within(card).getByText("19:00")).toBeTruthy();
    expect(within(card).getByRole("link", { name: "polakohedonist.club/ru/events/" }).getAttribute("href")).toBe("https://polakohedonist.club/ru/events/");
    expect(addSource).not.toHaveBeenCalled();
    expect(screen.getAllByRole("button", { name: /Добавить/ }).map((b) => b.textContent)).toEqual(["Добавить сайт"]);
  });

  it("adds site after confirming preview", async () => {
    const { addSource, submit } = setupForm(SITE_PREVIEW);
    submit("https://polakohedonist.club/ru/events/a");
    const card = await screen.findByRole("region", { name: "Polako Hedonist" });
    fireEvent.click(within(card).getByRole("button", { name: "Добавить сайт" }));
    await waitFor(() => expect(addSource).toHaveBeenCalledWith({ link: "https://polakohedonist.club/ru/events/a", title: null }));
    await waitFor(() => expect(screen.queryByRole("region", { name: "Polako Hedonist" })).toBeNull());
  });

  it("cancel hides the preview without adding", async () => {
    const { addSource, submit } = setupForm(SITE_PREVIEW);
    submit("https://polakohedonist.club/ru/events/a");
    fireEvent.click(within(await screen.findByRole("region", { name: "Polako Hedonist" })).getByRole("button", { name: "Отмена" }));
    expect(screen.queryByRole("region", { name: "Polako Hedonist" })).toBeNull();
    expect(addSource).not.toHaveBeenCalled();
  });

  it("telegram link is added without preview card", async () => {
    const { addSource, submit } = setupForm({ kind: "telegram", title: "Квизы", handle: "quizbg", pages_found: 0, examples: [] });
    submit("t.me/quizbg");
    await waitFor(() => expect(addSource).toHaveBeenCalledWith({ link: "t.me/quizbg", title: null }));
    expect(screen.queryByRole("region")).toBeNull();
  });
});

describe("source kinds", () => {
  it("site row shows its section address and a globe instead of a handle", async () => {
    setup([{ ...source(1, "Polako Hedonist", "new"), kind: "web", handle: "polakohedonist.club/ru/events/", url: "https://polakohedonist.club/ru/events/" }, source(2, "Квизы", "new")]);
    const rows = await screen.findAllByRole("row");
    const site = rows.find((row) => within(row).queryByText("Polako Hedonist"))!;
    expect(within(site).getByRole("link", { name: "polakohedonist.club/ru/events/" })).toBeTruthy();
    expect(within(site).getByRole("img", { name: "Сайт" })).toBeTruthy();
    const channel = rows.find((row) => within(row).queryByText("Квизы"))!;
    expect(within(channel).getByRole("link", { name: "@channel2" })).toBeTruthy();
    expect(within(channel).getByRole("img", { name: "Telegram-канал" })).toBeTruthy();
  });
});
