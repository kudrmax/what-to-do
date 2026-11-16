import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { createApi, type RefreshStatus } from "../api/client";
import { ApiContext } from "../api/queries";
import { RefreshButton } from "./RefreshButton";

const SIGN_IN = "Sign in to Claude Code: run `claude` in a terminal and type /login";

function finished(overrides: Partial<RefreshStatus>): RefreshStatus {
  return {
    stage: "done",
    started_at: null,
    stage_started_at: null,
    finished_at: "2026-11-16T10:00:00Z",
    sources_to_collect: 0,
    sources_collected: 0,
    pages_to_fetch: 0,
    pages_fetched: 0,
    announcements_to_merge: 0,
    announcements_merged: 0,
    new_posts: 0,
    photos_to_read: 0,
    photos_read: 0,
    posts_to_read: 0,
    posts_read: 0,
    events_touched: 0,
    errors: [],
    claude_signed_out: false,
    running: false,
    ...overrides,
  };
}

function setup(progress: RefreshStatus) {
  const api = createApi("");
  vi.spyOn(api, "refreshStatus").mockResolvedValue(progress);
  render(
    <ApiContext.Provider value={api}>
      <QueryClientProvider client={new QueryClient()}>
        <RefreshButton />
      </QueryClientProvider>
    </ApiContext.Provider>,
  );
}

describe("refresh errors", () => {
  it("says how to sign in to Claude Code instead of the raw error", async () => {
    setup(finished({ errors: ["Кафана: couldn't read it", SIGN_IN], claude_signed_out: true }));

    const note = await screen.findByRole("alert");
    expect(note).toHaveTextContent("Claude Code isn’t signed in, so nothing was read.");
    expect(note.querySelectorAll("code")[0]).toHaveTextContent("claude");
    expect(note.querySelectorAll("code")[1]).toHaveTextContent("/login");
    expect(screen.getByRole("status")).toHaveTextContent("Кафана: couldn't read it");
    expect(screen.queryByText(/Not logged in/)).toBeNull();
    expect(screen.getByRole("status")).not.toHaveTextContent("Sign in to Claude Code");
  });

  it("shows commands in other errors as code", async () => {
    setup(finished({ errors: ["Run `where-to-go restart` and try again"] }));

    const errors = await screen.findByRole("status");
    expect(errors.querySelector("code")).toHaveTextContent("where-to-go restart");
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
