import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { createApi, type SitePreview, type Source } from "../api/client";
import { ApiContext } from "../api/queries";
import { AddSourceForm, SourceList } from "./SourcesScreen";

function source(id: number, title: string, status: Source["status"], paused = false): Source {
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
    paused,
  };
}

function setup(sources: Source[]) {
  const api = createApi("");
  vi.spyOn(api, "sources").mockResolvedValue(sources);
  const mark = vi.spyOn(api, "markSource").mockResolvedValue(sources[0]);
  const pause = vi.spyOn(api, "pauseSource").mockResolvedValue(sources[0]);
  render(
    <ApiContext.Provider value={api}>
      <QueryClientProvider client={new QueryClient()}>
        <SourceList />
      </QueryClientProvider>
    </ApiContext.Provider>,
  );
  return { mark, pause };
}

describe("source status", () => {
  it("puts favorite sources first and shows which are favorite", async () => {
    setup([source(1, "Афиша", "new"), source(2, "Квизы", "favorite")]);
    const rows = await screen.findAllByRole("row");
    expect(within(rows[0]).getByText("Квизы")).toBeTruthy();
    expect(within(rows[0]).getByRole("button", { name: "Remove from favorites" }).getAttribute("aria-pressed")).toBe("true");
    expect(within(rows[1]).getByRole("button", { name: "Add to favorites" }).getAttribute("aria-pressed")).toBe("false");
  });

  it("toggles a source between new and favorite", async () => {
    const { mark } = setup([source(1, "Афиша", "new"), source(2, "Квизы", "favorite")]);
    fireEvent.click(await screen.findByRole("button", { name: "Add to favorites" }));
    await waitFor(() => expect(mark).toHaveBeenCalledWith(1, "favorite"));
    fireEvent.click(screen.getByRole("button", { name: "Remove from favorites" }));
    await waitFor(() => expect(mark).toHaveBeenCalledWith(2, "new"));
  });
});

describe("source pause", () => {
  it("shows a paused source and resumes it", async () => {
    const { pause } = setup([source(1, "Афиша", "new", true), source(2, "Квизы", "new")]);
    const [paused, working] = await screen.findAllByRole("row");
    expect(within(paused).getByText("Paused")).toBeTruthy();
    expect(within(working).queryByText("Paused")).toBeNull();
    fireEvent.click(within(paused).getByRole("button", { name: /^Resume/ }));
    await waitFor(() => expect(pause).toHaveBeenCalledWith(1, false));
    fireEvent.click(within(working).getByRole("button", { name: /^Pause/ }));
    await waitFor(() => expect(pause).toHaveBeenCalledWith(2, true));
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
    fireEvent.change(screen.getByLabelText("Link"), { target: { value: link } });
    fireEvent.click(screen.getByRole("button", { name: "Add" }));
  };
  return { previewSource, addSource, submit };
}

describe("adding a source", () => {
  it("shows site preview before adding", async () => {
    const { addSource, submit } = setupForm(SITE_PREVIEW);
    submit("https://polakohedonist.club/ru/events/a");
    const card = await screen.findByRole("region", { name: "Polako Hedonist" });
    expect(within(card).getByText("820 events on the website")).toBeTruthy();
    expect(within(card).getByText("The app will get events in your city for the next 30 days")).toBeTruthy();
    expect(within(card).getByText("Искусство быть нелепым")).toBeTruthy();
    expect(within(card).getAllByText("Wednesday, 18 November")).toHaveLength(2);
    expect(within(card).getByText("19:00")).toBeTruthy();
    expect(within(card).getByRole("link", { name: "polakohedonist.club/ru/events/" }).getAttribute("href")).toBe("https://polakohedonist.club/ru/events/");
    expect(addSource).not.toHaveBeenCalled();
    expect(screen.getAllByRole("button", { name: /Add/ }).map((b) => b.textContent)).toEqual(["Add website"]);
  });

  it("adds site after confirming preview", async () => {
    const { addSource, submit } = setupForm(SITE_PREVIEW);
    submit("https://polakohedonist.club/ru/events/a");
    const card = await screen.findByRole("region", { name: "Polako Hedonist" });
    fireEvent.click(within(card).getByRole("button", { name: "Add website" }));
    await waitFor(() => expect(addSource).toHaveBeenCalledWith({ link: "https://polakohedonist.club/ru/events/a", title: null }));
    await waitFor(() => expect(screen.queryByRole("region", { name: "Polako Hedonist" })).toBeNull());
  });

  it("cancel hides the preview without adding", async () => {
    const { addSource, submit } = setupForm(SITE_PREVIEW);
    submit("https://polakohedonist.club/ru/events/a");
    fireEvent.click(within(await screen.findByRole("region", { name: "Polako Hedonist" })).getByRole("button", { name: "Cancel" }));
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
    expect(within(site).getByRole("img", { name: "Website" })).toBeTruthy();
    const channel = rows.find((row) => within(row).queryByText("Квизы"))!;
    expect(within(channel).getByRole("link", { name: "@channel2" })).toBeTruthy();
    expect(within(channel).getByRole("img", { name: "Telegram channel" })).toBeTruthy();
  });
});
