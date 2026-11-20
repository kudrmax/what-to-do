import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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
} as Settings;

const IDLE_RETAG = { started_at: null, finished_at: null, upcoming: 386, cards_to_retag: 0, cards_retagged: 0, cards_changed: 0, claude_calls: 13, errors: [], running: false };

function setup(tags: Tag[] = []) {
  const api = createApi("");
  vi.spyOn(api, "settings").mockResolvedValue(SETTINGS);
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
    const api = setup([{ id: 1, name: "Квиз", description: "", is_fallback: false, hidden: true }]);
    const change = vi.spyOn(api, "changeTag").mockResolvedValue({ id: 1, name: "Квиз", description: "вопросы ведущего", is_fallback: false, hidden: true });

    fireEvent.click(await screen.findByRole("button", { name: "Add what it means" }));
    const field = screen.getByLabelText("What “Квиз” means");
    fireEvent.change(field, { target: { value: " вопросы ведущего " } });
    fireEvent.keyDown(field, { key: "Enter" });

    await waitFor(() => expect(change).toHaveBeenCalledWith(1, { description: "вопросы ведущего" }));
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
