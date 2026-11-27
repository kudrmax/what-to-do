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
    claude_unavailable: false,
    running: false,
    ...overrides,
  };
}

const SIGNED_OUT: ClaudeSignIn = { state: "signed_out", hint: SIGN_IN, signing_in: false, page_url: null, error: null, version: "2.1.325", minimum: "2.1.321", update_command: "claude update" };
const PAGE = "https://claude.com/cai/oauth/authorize?code=true";

function setup(progress: RefreshStatus, signIn: ClaudeSignIn | (() => Promise<ClaudeSignIn>) = SIGNED_OUT) {
  const api = createApi("");
  vi.spyOn(api, "refreshStatus").mockResolvedValue(progress);
  vi.spyOn(api, "claudeSignIn").mockImplementation(typeof signIn === "function" ? signIn : async () => signIn);
  const view = typeof signIn === "function" ? SIGNED_OUT : signIn;
  const start = vi.spyOn(api, "startClaudeSignIn").mockResolvedValue({ ...view, signing_in: true, page_url: PAGE });
  const submit = vi.spyOn(api, "submitClaudeSignInCode").mockResolvedValue({ ...view, signing_in: true, page_url: PAGE });
  const refresh = vi.spyOn(api, "refresh");
  render(
    <ApiContext.Provider value={api}>
      <QueryClientProvider client={new QueryClient()}>
        <RefreshButton />
      </QueryClientProvider>
    </ApiContext.Provider>,
  );
  return { start, submit, refresh };
}

describe("refresh errors", () => {
  it("offers to sign in to Claude instead of the raw error", async () => {
    setup(finished({ errors: ["Кафана: couldn't read it", SIGN_IN], claude_unavailable: true }));

    const note = await screen.findByRole("alert");
    expect(note).toHaveTextContent("Sign in to Claude to read the posts");
    expect(note.querySelector("code")).toBeNull();
    expect(screen.getByRole("button", { name: "Sign in to Claude" })).toBeTruthy();
    expect(screen.getByRole("status")).toHaveTextContent("Кафана: couldn't read it");
    expect(screen.queryByText(/Not logged in/)).toBeNull();
    expect(screen.getByRole("status")).not.toHaveTextContent("Sign in to Claude Code");
  });

  it("signs in through the browser and takes the code when the browser didn't open", async () => {
    const { start, submit } = setup(finished({ claude_unavailable: true }));

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
    setup(finished({ claude_unavailable: true }), { ...SIGNED_OUT, signing_in: true, page_url: PAGE, error: "Invalid code. Please make sure the full code was copied." });

    expect(await screen.findByText("Invalid code. Please make sure the full code was copied.")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Open the sign-in page" })).toBeTruthy();
  });

  it("says when the sign-in is done", async () => {
    setup(finished({ claude_unavailable: true }), { ...SIGNED_OUT, state: "signed_in" });

    expect(await screen.findByText("Signed in to Claude")).toBeTruthy();
    expect(screen.getByText("Press Refresh to read the posts.")).toBeTruthy();
  });

  it("explains a read that failed before Claude Code got ready during the refresh", async () => {
    setup(finished({ errors: ["Install Claude Code: What To Do needs it to read posts"], claude_unavailable: true }), { ...SIGNED_OUT, state: "signed_in" });

    expect(await screen.findByText("Signed in to Claude")).toBeTruthy();
    expect(screen.getByText("Press Refresh to read the posts.")).toBeTruthy();
    expect(screen.queryByText(/needs it to read posts/)).toBeNull();
  });

  it("tells why the last sign-in failed", async () => {
    setup(finished({ claude_unavailable: true }), { ...SIGNED_OUT, error: "Login failed: That code wasn't accepted." });

    expect(await screen.findByText("Login failed: That code wasn't accepted.")).toBeTruthy();
  });

  it("says how to install Claude Code instead of the raw error", async () => {
    setup(finished({ errors: ["Кафана: couldn't read it", "Install Claude Code: What To Do needs it to read posts"], claude_unavailable: true }), {
      ...SIGNED_OUT,
      state: "not_installed",
      version: null,
      update_command: null,
    });

    expect(await screen.findByRole("alert")).toHaveTextContent("Install Claude Code to read the posts");
    expect(screen.getByRole("status")).toHaveTextContent("Кафана: couldn't read it");
    expect(screen.getByRole("status")).not.toHaveTextContent("needs it to read posts");
  });

  it("says how to update Claude Code instead of the raw error", async () => {
    setup(finished({ errors: ["Update Claude Code: you have 2.1.200, What To Do needs 2.1.321 or newer"], claude_unavailable: true }), {
      ...SIGNED_OUT,
      state: "too_old",
      version: "2.1.200",
    });

    expect(await screen.findByRole("alert")).toHaveTextContent("Update Claude Code to read the posts");
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("keeps the backend's line when it can't tell whether Claude Code is there", async () => {
    setup(finished({ errors: ["Install Claude Code: What To Do needs it to read posts"], claude_unavailable: true }), () => Promise.reject(new Error("offline")));

    expect(await screen.findByRole("status")).toHaveTextContent("Install Claude Code: What To Do needs it to read posts");
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("offers to sign in once Claude Code is installed and the next refresh ends, without a restart", async () => {
    let signIn: ClaudeSignIn = { ...SIGNED_OUT, state: "not_installed", version: null, update_command: null };
    const { refresh } = setup(finished({ claude_unavailable: true }), async () => signIn);
    expect(await screen.findByText("Install Claude Code to read the posts")).toBeTruthy();

    signIn = SIGNED_OUT;
    refresh.mockResolvedValue(finished({ finished_at: "2026-11-16T11:00:00Z", errors: [SIGN_IN], claude_unavailable: true }));
    fireEvent.click(screen.getByRole("button", { name: /Refresh/ }));

    expect(await screen.findByText("Sign in to Claude to read the posts")).toBeTruthy();
    expect(screen.queryByText("Install Claude Code to read the posts")).toBeNull();
  });

  it("shows commands in other errors as code", async () => {
    setup(finished({ errors: ["Run `where-to-go restart` and try again"] }));

    const errors = await screen.findByRole("status");
    expect(errors.querySelector("code")).toHaveTextContent("where-to-go restart");
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
