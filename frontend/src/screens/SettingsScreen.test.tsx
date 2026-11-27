import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { createApi, type Settings, type Tag } from "../api/client";
import { ApiContext } from "../api/queries";
import { SettingsScreen } from "./SettingsScreen";

vi.mock("../updates/UpdatesSection", () => ({ UpdatesSection: () => <h2>App</h2> }));

const SETTINGS = {
  active_city_id: null,
  recent_posts: 25,
  priority_wish: "",
  photo_model: "claude-haiku-5-5",
  extraction_model: "claude-sonnet-5-5",
  matching_model: "claude-sonnet-5-5",
  extraction_prompt: "Read the post",
  photo_prompt: "Copy the text",
  matching_prompt: "Compare the events",
  llm_provider: "claude",
  codex_photo_model: "gpt-6.1-terra",
  codex_photo_effort: "medium",
  codex_extraction_model: "gpt-6.1-terra",
  codex_extraction_effort: "medium",
  codex_matching_model: "gpt-6-luna",
  codex_matching_effort: "low",
} as Settings;

const CODEX = { ...SETTINGS, llm_provider: "codex" } as Settings;

const IDLE_RETAG = { started_at: null, finished_at: null, upcoming: 386, cards_to_retag: 0, cards_retagged: 0, cards_changed: 0, claude_calls: 13, errors: [], running: false };

function setup(tags: Tag[] = [], settings: Settings = SETTINGS) {
  const api = createApi("");
  vi.spyOn(api, "settings").mockResolvedValue(settings);
  vi.spyOn(api, "defaultSettings").mockResolvedValue(SETTINGS);
  vi.spyOn(api, "cities").mockResolvedValue([]);
  vi.spyOn(api, "tags").mockResolvedValue(tags);
  vi.spyOn(api, "retagStatus").mockResolvedValue(IDLE_RETAG);
  vi.spyOn(api, "phonePage").mockResolvedValue({ enabled: false, repository: "", has_token: false, has_password: false, page_url: null, published_at: null, last_error: null, publishing: false });
  render(
    <ApiContext.Provider value={api}>
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <SettingsScreen />
        </MemoryRouter>
      </QueryClientProvider>
    </ApiContext.Provider>,
  );
  return api;
}

describe("settings", () => {
  it("puts what everyone needs first and the advanced settings last", async () => {
    setup();
    await screen.findByRole("button", { name: /Advanced/ });

    const groups = screen.getAllByRole("heading", { level: 2 }).map((heading) => heading.textContent);
    expect(groups).toEqual(["Cities", "Appearance", "Your feed", "Phone page", "App", "Advanced"]);
  });

  it("keeps the advanced settings closed until asked for", async () => {
    setup();
    const advanced = await screen.findByRole("button", { name: /Advanced/ });

    expect(screen.getByLabelText("Recent posts per channel")).not.toBeVisible();
    expect(advanced.getAttribute("aria-expanded")).toBe("false");

    fireEvent.click(advanced);

    expect(screen.getByLabelText("Recent posts per channel")).toBeVisible();
    expect(screen.getByRole("heading", { name: "Claude prompts" })).toBeVisible();
  });

  it("saves what a tag means for Claude", async () => {
    const api = setup([{ id: 1, name: "Квиз", description: "", is_fallback: false, visibility: "hidden" }]);
    const change = vi.spyOn(api, "changeTag").mockResolvedValue({ id: 1, name: "Квиз", description: "вопросы ведущего", is_fallback: false, visibility: "hidden" });

    fireEvent.click(await screen.findByRole("button", { name: "Add what it means" }));
    const field = screen.getByLabelText("What “Квиз” means");
    fireEvent.change(field, { target: { value: " вопросы ведущего " } });
    fireEvent.keyDown(field, { key: "Enter" });

    await waitFor(() => expect(change).toHaveBeenCalledWith(1, { description: "вопросы ведущего" }));
  });

  it("hides a tag always from the eye's menu", async () => {
    const kids = { id: 1, name: "Детям", description: "", is_fallback: false, visibility: "hidden" } as const;
    const api = setup([kids]);
    const change = vi.spyOn(api, "setTagVisibility").mockResolvedValue({ ...kids, visibility: "always_hidden" });

    fireEvent.click(await screen.findByRole("button", { name: "“Детям”: Hidden. Change" }));
    const menu = screen.getByRole("menu", { name: "Show events tagged “Детям”" });
    const choices = within(menu).getAllByRole("menuitemradio");
    expect(choices.map((c) => [c.querySelector(".tag-visibility__title")?.textContent, c.getAttribute("aria-checked")])).toEqual([
      ["Shown", "false"],
      ["Hidden", "true"],
      ["Always hidden", "false"],
    ]);
    fireEvent.click(within(menu).getByRole("menuitemradio", { name: /Always hidden/ }));

    await waitFor(() => expect(change).toHaveBeenCalledWith(1, "always_hidden"));
  });

  it("says what a re-tagging costs and starts it", async () => {
    const api = setup();
    const start = vi.spyOn(api, "retag").mockResolvedValue({ ...IDLE_RETAG, running: true, cards_to_retag: 386, started_at: "2026-11-20T15:00:00Z" });

    expect(await screen.findByText(/386 upcoming events again .* 13 Claude calls/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Re-tag" }));

    expect(await screen.findByRole("button", { name: /0 of 386/ })).toBeDisabled();
    expect(start).toHaveBeenCalled();
  });
});

function chips(group: string) {
  return within(screen.getByRole("group", { name: group }))
    .getAllByRole("button")
    .map((chip) => ({ name: chip.textContent, pressed: chip.getAttribute("aria-pressed") === "true" }));
}

async function openAdvanced() {
  fireEvent.click(await screen.findByRole("button", { name: /Advanced/ }));
}

describe("which subscription reads posts", () => {
  it("shows Claude's models for each step with Claude chosen", async () => {
    setup();
    await openAdvanced();

    expect(chips("Reads posts with")).toEqual([
      { name: "Claude", pressed: true },
      { name: "Codex", pressed: false },
    ]);
    expect(screen.getByRole("heading", { name: "Claude models" })).toBeVisible();
    expect(screen.getByText(/use more of your Claude plan/)).toBeVisible();
    expect(chips("Photo reading")).toEqual([
      { name: "Haiku", pressed: true },
      { name: "Sonnet", pressed: false },
      { name: "Opus", pressed: false },
    ]);
    expect(chips("Post and page reading").map((chip) => chip.name)).toEqual(["Haiku", "Sonnet", "Opus"]);
    expect(chips("Duplicate merging").map((chip) => chip.name)).toEqual(["Haiku", "Sonnet", "Opus"]);
    expect(screen.queryByText("Thinking")).toBeNull();
    expect(screen.queryByRole("group", { name: "Photo reading thinking" })).toBeNull();
  });

  it("shows Codex's models and thinking for each step with Codex chosen", async () => {
    setup([], CODEX);
    await openAdvanced();

    expect(chips("Reads posts with")).toEqual([
      { name: "Claude", pressed: false },
      { name: "Codex", pressed: true },
    ]);
    expect(screen.getByRole("heading", { name: "Codex models" })).toBeVisible();
    expect(screen.getByText(/use more of your ChatGPT plan/)).toBeVisible();
    expect(chips("Photo reading")).toEqual([
      { name: "Luna", pressed: false },
      { name: "Terra", pressed: true },
      { name: "Sol", pressed: false },
      { name: "Astra", pressed: false },
    ]);
    expect(chips("Photo reading thinking")).toEqual([
      { name: "Low", pressed: false },
      { name: "Medium", pressed: true },
      { name: "High", pressed: false },
    ]);
    expect(chips("Duplicate merging").find((chip) => chip.pressed)?.name).toBe("Luna");
    expect(chips("Duplicate merging thinking").find((chip) => chip.pressed)?.name).toBe("Low");
    expect(chips("Post and page reading").find((chip) => chip.pressed)?.name).toBe("Terra");
    expect(screen.getAllByText("Thinking")).toHaveLength(3);
    expect(screen.queryByRole("button", { name: "Haiku" })).toBeNull();
    expect(screen.queryByText(/Haiku mixes up/)).toBeNull();
  });

  it("switches the reader and saves each Codex choice on its own", async () => {
    const api = setup([], CODEX);
    const change = vi.spyOn(api, "changeSettings").mockResolvedValue(CODEX);
    await openAdvanced();

    fireEvent.click(within(screen.getByRole("group", { name: "Photo reading" })).getByRole("button", { name: "Sol" }));
    await waitFor(() => expect(change).toHaveBeenLastCalledWith({ codex_photo_model: "gpt-6.2-sol" }));

    fireEvent.click(within(screen.getByRole("group", { name: "Duplicate merging thinking" })).getByRole("button", { name: "High" }));
    await waitFor(() => expect(change).toHaveBeenLastCalledWith({ codex_matching_effort: "high" }));

    fireEvent.click(within(screen.getByRole("group", { name: "Reads posts with" })).getByRole("button", { name: "Claude" }));
    await waitFor(() => expect(change).toHaveBeenLastCalledWith({ llm_provider: "claude" }));

    fireEvent.click(within(screen.getByRole("group", { name: "Reads posts with" })).getByRole("button", { name: "Codex" }));
    expect(change).toHaveBeenCalledTimes(3);
  });

  it("shows the other reader's rows once the switch is saved", async () => {
    const api = setup();
    vi.spyOn(api, "changeSettings").mockImplementation(async () => {
      vi.spyOn(api, "settings").mockResolvedValue(CODEX);
      return CODEX;
    });
    await openAdvanced();

    fireEvent.click(within(screen.getByRole("group", { name: "Reads posts with" })).getByRole("button", { name: "Codex" }));

    expect(await screen.findByRole("heading", { name: "Codex models" })).toBeVisible();
    expect(screen.getByRole("group", { name: "Photo reading thinking" })).toBeVisible();
    expect(screen.queryByRole("heading", { name: "Claude models" })).toBeNull();
  });

  it("names the chosen reader in every text about reading", async () => {
    setup([{ id: 1, name: "Квиз", description: "", is_fallback: false, visibility: "shown" }], CODEX);
    await openAdvanced();

    expect(await screen.findByText(/386 upcoming events again .* 13 Codex calls/)).toBeInTheDocument();
    expect(screen.getByText("What Codex looks for in posts and how it sorts events. Shared by all cities.")).toBeInTheDocument();
    expect(screen.getByText(/Codex marks the events that fit/)).toBeInTheDocument();
    expect(screen.getByText(/Codex tags events only with these/)).toBeInTheDocument();
    expect(screen.getByText(/uses too much of your ChatGPT plan/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Codex prompts" })).toBeVisible();
    expect(screen.getByText(/The instructions Codex follows/)).toBeVisible();
    expect(screen.getByRole("button", { name: "Add what it means" })).toHaveAttribute("data-tip", "What this tag means for Codex");
    const readerGroup = screen.getByRole("group", { name: "Reads posts with" }).textContent ?? "";
    expect((document.body.textContent ?? "").replace(readerGroup, "")).not.toContain("Claude");
  });
});
