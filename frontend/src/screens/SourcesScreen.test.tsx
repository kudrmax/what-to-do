import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ApiError, createApi, type SitePreview, type Source } from "../api/client";
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
    position: id,
    instagram: null,
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
  highlights: 0,
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
    expect(within(card).getAllByText("Wednesday 18 November")).toHaveLength(2);
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
    const { addSource, submit } = setupForm({ kind: "telegram", title: "Квизы", handle: "quizbg", pages_found: 0, highlights: 0, examples: [] });
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

const INSTAGRAM_PREVIEW: SitePreview = { kind: "instagram", title: "EJE Belgrade", handle: "eje.belgrade", pages_found: 0, highlights: 4, examples: [] };

describe("choosing the network for a bare name", () => {
  it("asks Telegram or Instagram for a name valid for both and keeps Add disabled until a pick", async () => {
    const { previewSource } = setupForm(INSTAGRAM_PREVIEW);
    fireEvent.change(screen.getByLabelText("Link"), { target: { value: "@londonevents" } });
    const network = screen.getByRole("radiogroup", { name: "Network" });
    const radios = within(network).getAllByRole("radio");
    expect(radios.map((radio) => radio.textContent)).toEqual(["Telegram", "Instagram"]);
    expect(radios.map((radio) => radio.getAttribute("aria-checked"))).toEqual(["false", "false"]);
    const add = screen.getByRole("button", { name: "Add" });
    expect(add).toHaveProperty("disabled", true);
    expect(add.getAttribute("title")).toBe("Choose Telegram or Instagram first");
    fireEvent.click(within(network).getByRole("radio", { name: "Instagram" }));
    expect(within(network).getByRole("radio", { name: "Instagram" }).getAttribute("aria-checked")).toBe("true");
    expect(add).toHaveProperty("disabled", false);
    fireEvent.click(add);
    await waitFor(() => expect(previewSource).toHaveBeenCalledWith("@londonevents", "instagram"));
  });

  it("forgets the pick when the link changes", () => {
    setupForm(INSTAGRAM_PREVIEW);
    fireEvent.change(screen.getByLabelText("Link"), { target: { value: "londonevents" } });
    fireEvent.click(screen.getByRole("radio", { name: "Telegram" }));
    fireEvent.change(screen.getByLabelText("Link"), { target: { value: "londonevent" } });
    expect(screen.getByRole("radio", { name: "Telegram" }).getAttribute("aria-checked")).toBe("false");
    expect(screen.getByRole("button", { name: "Add" })).toHaveProperty("disabled", true);
  });

  it("does not ask for a name that only Instagram allows or for a link", () => {
    setupForm(INSTAGRAM_PREVIEW);
    for (const link of ["@eje.belgrade", "eje.belgrade", "t.me/londonevents", "instagram.com/londonevents", "@abc"]) {
      fireEvent.change(screen.getByLabelText("Link"), { target: { value: link } });
      expect(screen.queryByRole("radiogroup")).toBeNull();
      expect(screen.getByRole("button", { name: "Add" })).toHaveProperty("disabled", false);
    }
  });

  it("adds a Telegram channel picked for a bare name with its kind", async () => {
    const { addSource } = setupForm({ kind: "telegram", title: "London", handle: "londonevents", pages_found: 0, highlights: 0, examples: [] });
    fireEvent.change(screen.getByLabelText("Link"), { target: { value: "@londonevents" } });
    fireEvent.click(screen.getByRole("radio", { name: "Telegram" }));
    fireEvent.click(screen.getByRole("button", { name: "Add" }));
    await waitFor(() => expect(addSource).toHaveBeenCalledWith({ link: "@londonevents", title: null, kind: "telegram" }));
  });
});

describe("adding an Instagram profile", () => {
  it("shows the profile with what to read, both on", async () => {
    const { addSource, submit } = setupForm(INSTAGRAM_PREVIEW);
    submit("@eje.belgrade");
    const card = await screen.findByRole("region", { name: "EJE Belgrade" });
    expect(within(card).getByRole("link", { name: "@eje.belgrade" }).getAttribute("href")).toBe("https://www.instagram.com/eje.belgrade/");
    expect(within(card).getByRole("img", { name: "Instagram profile" })).toBeTruthy();
    const reading = within(card).getByRole("group", { name: "What to read" });
    expect(within(reading).getByRole("checkbox", { name: "Posts" })).toHaveProperty("checked", true);
    expect(within(reading).getByRole("checkbox", { name: "Pinned stories" })).toHaveProperty("checked", true);
    expect(within(reading).getByText("12 latest, then every new one")).toBeTruthy();
    expect(within(reading).getByText("4 highlights")).toBeTruthy();
    expect(within(reading).getByText("Stories up to 30 days old, then every new one")).toBeTruthy();
    expect(addSource).not.toHaveBeenCalled();
  });

  it("adds the profile with what was left on", async () => {
    const { addSource, submit } = setupForm(INSTAGRAM_PREVIEW);
    submit("@eje.belgrade");
    const card = await screen.findByRole("region", { name: "EJE Belgrade" });
    fireEvent.click(within(card).getByRole("checkbox", { name: "Pinned stories" }));
    fireEvent.click(within(card).getByRole("button", { name: "Add profile" }));
    await waitFor(() => expect(addSource).toHaveBeenCalledWith({ link: "@eje.belgrade", title: null, instagram: { posts: true, stories: false } }));
  });

  it("cannot add a profile with nothing to read", async () => {
    const { submit } = setupForm(INSTAGRAM_PREVIEW);
    submit("@eje.belgrade");
    const card = await screen.findByRole("region", { name: "EJE Belgrade" });
    fireEvent.click(within(card).getByRole("checkbox", { name: "Posts" }));
    fireEvent.click(within(card).getByRole("checkbox", { name: "Pinned stories" }));
    const add = within(card).getByRole("button", { name: "Add profile" });
    expect(add).toHaveProperty("disabled", true);
    expect(add.getAttribute("title")).toBe("Choose posts, pinned stories or both");
  });

  it("says when a profile has no highlights yet", async () => {
    const { submit } = setupForm({ ...INSTAGRAM_PREVIEW, highlights: 0 });
    submit("@eje.belgrade");
    const card = await screen.findByRole("region", { name: "EJE Belgrade" });
    expect(within(card).getByText("No highlights yet")).toBeTruthy();
    expect(within(card).getByText("New ones will be read")).toBeTruthy();
  });

  it("names one highlight in the singular", async () => {
    const { submit } = setupForm({ ...INSTAGRAM_PREVIEW, highlights: 1 });
    submit("@eje.belgrade");
    const card = await screen.findByRole("region", { name: "EJE Belgrade" });
    expect(within(card).getByText("1 highlight")).toBeTruthy();
  });
});

describe("Instagram source row", () => {
  function instagramSource(reading: { posts: boolean; stories: boolean }): Source {
    return { ...source(1, "EJE Belgrade", "new"), kind: "instagram", handle: "eje.belgrade", url: "https://www.instagram.com/eje.belgrade/", instagram: reading };
  }

  function setupInstagram(reading: { posts: boolean; stories: boolean }, failure?: Error) {
    const api = createApi("");
    vi.spyOn(api, "sources").mockResolvedValue([instagramSource(reading)]);
    const setReading = vi.spyOn(api, "setInstagramReading");
    if (failure) setReading.mockRejectedValue(failure);
    else setReading.mockResolvedValue(instagramSource(reading));
    render(
      <ApiContext.Provider value={api}>
        <QueryClientProvider client={new QueryClient()}>
          <SourceList />
        </QueryClientProvider>
      </ApiContext.Provider>,
    );
    return { setReading };
  }

  it("shows the Instagram icon and a link to the profile", async () => {
    setupInstagram({ posts: true, stories: true });
    const [row] = await screen.findAllByRole("row");
    expect(within(row).getByRole("img", { name: "Instagram profile" })).toBeTruthy();
    expect(within(row).getByRole("link", { name: "@eje.belgrade" }).getAttribute("href")).toBe("https://www.instagram.com/eje.belgrade/");
  });

  it("turns what is read on and off", async () => {
    const { setReading } = setupInstagram({ posts: true, stories: true });
    const [row] = await screen.findAllByRole("row");
    const reading = within(row).getByRole("group", { name: "What to read" });
    fireEvent.click(within(reading).getByRole("checkbox", { name: "Pinned stories" }));
    await waitFor(() => expect(setReading).toHaveBeenCalledWith(1, { posts: true, stories: false }));
  });

  it("keeps the last kind on", async () => {
    const { setReading } = setupInstagram({ posts: false, stories: true });
    const [row] = await screen.findAllByRole("row");
    const stories = within(row).getByRole("checkbox", { name: "Pinned stories" });
    expect(stories).toHaveProperty("disabled", true);
    expect(stories.closest("label")!.getAttribute("title")).toBe("A profile reads at least one of them");
    fireEvent.click(within(row).getByRole("checkbox", { name: "Posts" }));
    await waitFor(() => expect(setReading).toHaveBeenCalledWith(1, { posts: true, stories: true }));
  });

  it("says why a change of what is read failed and shows what is still read", async () => {
    setupInstagram({ posts: true, stories: true }, new ApiError(422, "Choose posts, pinned stories or both"));
    const [row] = await screen.findAllByRole("row");
    fireEvent.click(within(row).getByRole("checkbox", { name: "Pinned stories" }));
    expect(await within(row).findByText("Choose posts, pinned stories or both")).toBeTruthy();
    expect(within(row).getByRole("checkbox", { name: "Pinned stories" })).toHaveProperty("checked", true);
  });

  it("telegram rows have no reading toggles", async () => {
    setup([source(1, "Квизы", "new")]);
    const [row] = await screen.findAllByRole("row");
    expect(within(row).queryByRole("group", { name: "What to read" })).toBeNull();
  });
});
