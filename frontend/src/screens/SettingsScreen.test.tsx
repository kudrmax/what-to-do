import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { createApi, type Settings } from "../api/client";
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

function setup() {
  const api = createApi("");
  vi.spyOn(api, "settings").mockResolvedValue(SETTINGS);
  vi.spyOn(api, "defaultSettings").mockResolvedValue(SETTINGS);
  vi.spyOn(api, "cities").mockResolvedValue([]);
  vi.spyOn(api, "tags").mockResolvedValue([]);
  render(
    <ApiContext.Provider value={api}>
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <SettingsScreen />
        </MemoryRouter>
      </QueryClientProvider>
    </ApiContext.Provider>,
  );
}

describe("settings", () => {
  it("puts what everyone needs first and the advanced settings last", async () => {
    setup();
    await screen.findByRole("button", { name: /Advanced/ });

    const groups = screen.getAllByRole("heading", { level: 2 }).map((heading) => heading.textContent);
    expect(groups).toEqual(["Cities", "Appearance", "Your feed", "App", "Advanced"]);
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
});
