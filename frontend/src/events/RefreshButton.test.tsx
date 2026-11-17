import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { createApi, type ClaudeSignIn, type RefreshStatus } from "../api/client";
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

const SIGNED_OUT: ClaudeSignIn = { state: "signed_out", hint: SIGN_IN, signing_in: false, page_url: null, error: null };
const PAGE = "https://claude.com/cai/oauth/authorize?code=true";

function setup(progress: RefreshStatus, signIn: ClaudeSignIn = SIGNED_OUT) {
  const api = createApi("");
  vi.spyOn(api, "refreshStatus").mockResolvedValue(progress);
  vi.spyOn(api, "claudeSignIn").mockResolvedValue(signIn);
  const start = vi.spyOn(api, "startClaudeSignIn").mockResolvedValue({ ...signIn, signing_in: true, page_url: PAGE });
  const submit = vi.spyOn(api, "submitClaudeSignInCode").mockResolvedValue({ ...signIn, signing_in: true, page_url: PAGE });
  render(
    <ApiContext.Provider value={api}>
      <QueryClientProvider client={new QueryClient()}>
        <RefreshButton />
      </QueryClientProvider>
    </ApiContext.Provider>,
  );
  return { start, submit };
}

describe("refresh errors", () => {
  it("offers to sign in to Claude instead of the raw error", async () => {
    setup(finished({ errors: ["Кафана: couldn't read it", SIGN_IN], claude_signed_out: true }));

    const note = await screen.findByRole("alert");
    expect(note).toHaveTextContent("Sign in to Claude to read the posts");
    expect(note.querySelector("code")).toBeNull();
    expect(screen.getByRole("button", { name: "Sign in to Claude" })).toBeTruthy();
    expect(screen.getByRole("status")).toHaveTextContent("Кафана: couldn't read it");
    expect(screen.queryByText(/Not logged in/)).toBeNull();
    expect(screen.getByRole("status")).not.toHaveTextContent("Sign in to Claude Code");
  });

  it("signs in through the browser and takes the code when the browser didn't open", async () => {
    const { start, submit } = setup(finished({ claude_signed_out: true }));

    fireEvent.click(await screen.findByRole("button", { name: "Sign in to Claude" }));

    expect(await screen.findByText("Finish signing in in your browser")).toBeTruthy();
    expect(start).toHaveBeenCalled();
    fireEvent.click(screen.getByText("The browser didn’t open?"));
    expect(screen.getByRole("link", { name: "Open the sign-in page" })).toHaveAttribute("href", PAGE);
    fireEvent.change(screen.getByLabelText("Code from the sign-in page"), { target: { value: " abc#def " } });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    await waitFor(() => expect(submit).toHaveBeenCalledWith("abc#def"));
  });

  it("says why the pasted code didn't work", async () => {
    setup(finished({ claude_signed_out: true }), { ...SIGNED_OUT, signing_in: true, page_url: PAGE, error: "Invalid code. Please make sure the full code was copied." });

    expect(await screen.findByText("Invalid code. Please make sure the full code was copied.")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Open the sign-in page" })).toBeTruthy();
  });

  it("says when the sign-in is done", async () => {
    setup(finished({ claude_signed_out: true }), { ...SIGNED_OUT, state: "signed_in" });

    expect(await screen.findByText("Signed in to Claude")).toBeTruthy();
    expect(screen.getByText("Press Refresh to read the posts.")).toBeTruthy();
  });

  it("tells why the last sign-in failed", async () => {
    setup(finished({ claude_signed_out: true }), { ...SIGNED_OUT, error: "Login failed: That code wasn't accepted." });

    expect(await screen.findByText("Login failed: That code wasn't accepted.")).toBeTruthy();
  });

  it("shows commands in other errors as code", async () => {
    setup(finished({ errors: ["Run `where-to-go restart` and try again"] }));

    const errors = await screen.findByRole("status");
    expect(errors.querySelector("code")).toHaveTextContent("where-to-go restart");
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
