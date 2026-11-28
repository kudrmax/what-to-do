import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { createApi, type ClaudeSignIn, type CodexSignIn, type LlmProvider, type RefreshStatus, type Settings } from "../api/client";
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
    limit: null,
    posts_left: null,
    events_touched: 0,
    errors: [],
    reader_unavailable: false, reader: null, reader_error: null,
    running: false,
    ...overrides,
  };
}

const SIGNED_OUT: ClaudeSignIn = { state: "signed_out", hint: SIGN_IN, signing_in: false, page_url: null, error: null, version: "2.1.325", minimum: "2.1.321", update_command: "claude update" };
const PAGE = "https://claude.com/cai/oauth/authorize?code=true";

const CODEX_SIGN_IN = "Sign in to ChatGPT in What To Do to read posts with Codex";
const CODEX_SIGNED_OUT: CodexSignIn = { ...SIGNED_OUT, hint: CODEX_SIGN_IN, version: "0.172.0", minimum: "0.172.0", update_command: "codex update", message: null };
const OFFERS_TOOLS = "This Codex version offers tools What To Do cannot turn off; update What To Do";

function setup(progress: RefreshStatus, signIn: ClaudeSignIn | (() => Promise<ClaudeSignIn>) = SIGNED_OUT, provider: LlmProvider = "claude", codexSignIn: CodexSignIn = CODEX_SIGNED_OUT) {
  const api = createApi("");
  vi.spyOn(api, "refreshStatus").mockResolvedValue(progress);
  vi.spyOn(api, "settings").mockResolvedValue({ llm_provider: provider } as Settings);
  const codex = vi.spyOn(api, "codexSignIn").mockResolvedValue(codexSignIn);
  const claude = vi.spyOn(api, "claudeSignIn").mockImplementation(typeof signIn === "function" ? signIn : async () => signIn);
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
  return { start, submit, refresh, codex, claude };
}

describe("refresh errors", () => {
  it("offers to sign in to Claude instead of the raw error", async () => {
    setup(finished({ errors: ["Кафана: couldn't read it"], reader_error: SIGN_IN, reader_unavailable: true, reader: "claude" }));

    const note = await screen.findByRole("alert");
    expect(note).toHaveTextContent("Sign in to Claude to read the posts");
    expect(note.querySelector("code")).toBeNull();
    expect(screen.getByRole("button", { name: "Sign in to Claude" })).toBeTruthy();
    expect(screen.getByRole("status")).toHaveTextContent("Кафана: couldn't read it");
    expect(screen.queryByText(/Not logged in/)).toBeNull();
    expect(screen.getByRole("status")).not.toHaveTextContent("Sign in to Claude Code");
  });

  it("signs in through the browser and takes the code when the browser didn't open", async () => {
    const { start, submit } = setup(finished({ reader_error: SIGN_IN, reader_unavailable: true, reader: "claude" }));

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
    setup(finished({ reader_error: SIGN_IN, reader_unavailable: true, reader: "claude" }), { ...SIGNED_OUT, signing_in: true, page_url: PAGE, error: "Invalid code. Please make sure the full code was copied." });

    expect(await screen.findByText("Invalid code. Please make sure the full code was copied.")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Open the sign-in page" })).toBeTruthy();
  });

  it("says when the sign-in is done", async () => {
    setup(finished({ reader_error: SIGN_IN, reader_unavailable: true, reader: "claude" }), { ...SIGNED_OUT, state: "signed_in" });

    expect(await screen.findByText("Signed in to Claude")).toBeTruthy();
    expect(screen.getByText("Press Refresh to read the posts.")).toBeTruthy();
  });

  it("explains a read that failed before Claude Code got ready during the refresh", async () => {
    setup(finished({ reader_error: "Install Claude Code: What To Do needs it to read posts", reader_unavailable: true, reader: "claude" }), { ...SIGNED_OUT, state: "signed_in" });

    expect(await screen.findByText("Signed in to Claude")).toBeTruthy();
    expect(screen.getByText("Press Refresh to read the posts.")).toBeTruthy();
    expect(screen.queryByText(/needs it to read posts/)).toBeNull();
  });

  it("tells why the last sign-in failed", async () => {
    setup(finished({ reader_error: SIGN_IN, reader_unavailable: true, reader: "claude" }), { ...SIGNED_OUT, error: "Login failed: That code wasn't accepted." });

    expect(await screen.findByText("Login failed: That code wasn't accepted.")).toBeTruthy();
  });

  it("says how to install Claude Code instead of the raw error", async () => {
    setup(finished({ errors: ["Кафана: couldn't read it"], reader_error: "Install Claude Code: What To Do needs it to read posts", reader_unavailable: true, reader: "claude" }), {
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
    setup(finished({ reader_error: "Update Claude Code: you have 2.1.200, What To Do needs 2.1.321 or newer", reader_unavailable: true, reader: "claude" }), {
      ...SIGNED_OUT,
      state: "too_old",
      version: "2.1.200",
    });

    expect(await screen.findByRole("alert")).toHaveTextContent("Update Claude Code to read the posts");
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("keeps the backend's line when it can't tell whether Claude Code is there", async () => {
    setup(finished({ reader_error: "Install Claude Code: What To Do needs it to read posts", reader_unavailable: true, reader: "claude" }), () => Promise.reject(new Error("offline")));

    expect(await screen.findByRole("status")).toHaveTextContent("Install Claude Code: What To Do needs it to read posts");
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("offers to sign in once Claude Code is installed and the next refresh ends, without a restart", async () => {
    let signIn: ClaudeSignIn = { ...SIGNED_OUT, state: "not_installed", version: null, update_command: null };
    const { refresh } = setup(finished({ reader_error: SIGN_IN, reader_unavailable: true, reader: "claude" }), async () => signIn);
    expect(await screen.findByText("Install Claude Code to read the posts")).toBeTruthy();

    signIn = SIGNED_OUT;
    refresh.mockResolvedValue(finished({ finished_at: "2026-11-16T11:00:00Z", reader_error: SIGN_IN, reader_unavailable: true, reader: "claude" }));
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

describe("refresh errors with Codex reading", () => {
  it("offers to sign in to ChatGPT instead of the raw error and never asks Claude Code", async () => {
    const { claude, codex } = setup(finished({ errors: ["Кафана: couldn't read it"], reader_error: CODEX_SIGN_IN, reader_unavailable: true, reader: "codex" }), SIGNED_OUT, "codex");

    const note = await screen.findByRole("alert");
    expect(note).toHaveTextContent("Sign in to ChatGPT to read the posts");
    expect(screen.getByRole("button", { name: "Sign in to ChatGPT" })).toBeTruthy();
    expect(screen.getByRole("status")).toHaveTextContent("Кафана: couldn't read it");
    expect(screen.getByRole("status")).not.toHaveTextContent(CODEX_SIGN_IN);
    expect(codex).toHaveBeenCalled();
    expect(claude).not.toHaveBeenCalled();
  });

  it("says how to install Codex instead of the raw error", async () => {
    setup(finished({ reader_error: "Install Codex: What To Do needs it to read posts", reader_unavailable: true, reader: "codex" }), SIGNED_OUT, "codex", {
      ...CODEX_SIGNED_OUT,
      state: "not_installed",
      version: null,
      update_command: null,
    });

    expect(await screen.findByRole("alert")).toHaveTextContent("Install Codex to read the posts");
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("says how to update Codex instead of the raw error", async () => {
    setup(finished({ reader_error: "Update Codex: you have 0.150.0, What To Do needs 0.172.0 or newer", reader_unavailable: true, reader: "codex" }), SIGNED_OUT, "codex", {
      ...CODEX_SIGNED_OUT,
      state: "too_old",
      version: "0.150.0",
    });

    expect(await screen.findByRole("alert")).toHaveTextContent("Update Codex to read the posts");
    expect(screen.queryByRole("status")).toBeNull();
  });

  it.each([
    OFFERS_TOOLS,
    "Codex is installed right in /usr/local; What To Do would have to let the model read that whole folder, so reinstall Codex with its installer or Homebrew",
    "Codex is installed at a path What To Do cannot put into its settings safely; reinstall Codex with its installer or Homebrew",
    "Codex can't limit file access on Windows; use Claude there",
  ])("says once why Codex is refused: %s", async (refusal) => {
    setup(finished({ reader_error: refusal, reader_unavailable: true, reader: "codex" }), SIGNED_OUT, "codex", { ...CODEX_SIGNED_OUT, state: "refused", message: refusal });

    const box = await screen.findByRole("alert");
    expect(box).toHaveTextContent("Codex can’t be used safely");
    expect(screen.getAllByText(refusal)).toHaveLength(1);
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("shows the plan limit as a plain note without asking Codex", async () => {
    const { codex } = setup(finished({ errors: ["ChatGPT plan limit reached, resets at 18:40"], reader_unavailable: true, reader: "codex" }), SIGNED_OUT, "codex", { ...CODEX_SIGNED_OUT, state: "signed_in" });

    expect(await screen.findByRole("status")).toHaveTextContent("ChatGPT plan limit reached, resets at 18:40");
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.queryByRole("button", { name: /Sign in/ })).toBeNull();
    expect(screen.queryByText("Signed in to ChatGPT")).toBeNull();
    expect(codex).not.toHaveBeenCalled();
  });

  it("keeps the line about a tool Codex tried to use without asking Codex", async () => {
    const skipped = "Codex tried to use a tool while reading 3 posts; they were skipped";
    const { codex } = setup(finished({ errors: [skipped] }), SIGNED_OUT, "codex", { ...CODEX_SIGNED_OUT, state: "signed_in" });

    expect(await screen.findByRole("status")).toHaveTextContent(skipped);
    expect(screen.queryByText("Signed in to ChatGPT")).toBeNull();
    expect(codex).not.toHaveBeenCalled();
  });

  it("names the reader from the settings when the refresh doesn't say whose it was", async () => {
    const { claude } = setup(finished({ reader_error: CODEX_SIGN_IN, reader_unavailable: true, reader: null }), SIGNED_OUT, "codex");

    expect(await screen.findByRole("button", { name: "Sign in to ChatGPT" })).toBeTruthy();
    expect(claude).not.toHaveBeenCalled();
  });

  it("asks no reader while every read went fine", async () => {
    const { claude, codex } = setup(finished({ errors: ["Кафана: couldn't read it"] }), SIGNED_OUT, "codex");

    expect(await screen.findByRole("status")).toHaveTextContent("Кафана: couldn't read it");
    expect(codex).not.toHaveBeenCalled();
    expect(claude).not.toHaveBeenCalled();
  });

  it("asks only Claude Code when Claude is the reader that isn't ready", async () => {
    const { claude, codex } = setup(finished({ reader_error: SIGN_IN, reader_unavailable: true, reader: "claude" }), SIGNED_OUT, "codex");

    expect(await screen.findByRole("button", { name: "Sign in to Claude" })).toBeTruthy();
    expect(claude).toHaveBeenCalled();
    expect(codex).not.toHaveBeenCalled();
  });

  it("keeps the backend's line when Codex can't tell whether someone is signed in", async () => {
    setup(finished({ reader_error: CODEX_SIGN_IN, reader_unavailable: true, reader: "codex" }), SIGNED_OUT, "codex", { ...CODEX_SIGNED_OUT, state: "unknown" });

    expect(await screen.findByRole("status")).toHaveTextContent(CODEX_SIGN_IN);
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.queryByRole("button", { name: "Sign in to ChatGPT" })).toBeNull();
  });

  it("still offers to sign in to Claude when Claude Code can't tell whether someone is signed in", async () => {
    setup(finished({ reader_error: SIGN_IN, reader_unavailable: true, reader: "claude" }), { ...SIGNED_OUT, state: "unknown" });

    expect(await screen.findByRole("alert")).toHaveTextContent("Sign in to Claude to read the posts");
    expect(screen.getByRole("button", { name: "Sign in to Claude" })).toBeTruthy();
    expect(screen.queryByRole("status")).toBeNull();
  });
});

function setupShort(progress: RefreshStatus, partial = 30) {
  const api = createApi("");
  const status = vi.spyOn(api, "refreshStatus").mockResolvedValue(progress);
  vi.spyOn(api, "settings").mockResolvedValue({ llm_provider: "claude", partial_refresh_posts: partial } as Settings);
  const refresh = vi.spyOn(api, "refresh");
  render(
    <ApiContext.Provider value={api}>
      <QueryClientProvider client={new QueryClient()}>
        <RefreshButton />
      </QueryClientProvider>
    </ApiContext.Provider>,
  );
  return { refresh, status };
}

const RUNNING = { stage: "reading", finished_at: null, posts_to_read: 30, posts_read: 4, running: true } as const;

describe("short refresh", () => {
  it("names the button with the number of posts from the settings", async () => {
    setupShort(finished({}), 45);

    const button = await screen.findByRole("button", { name: "Refresh 45" });
    expect(button.getAttribute("data-tip")).toBe("Collect what’s new from every source, but read only the next 45 posts, top to bottom in your source order");
  });

  it("asks for only that many posts, while Refresh asks for all", async () => {
    const { refresh } = setupShort(finished({}));
    refresh.mockResolvedValue(finished({ ...RUNNING, limit: 30 }));

    fireEvent.click(await screen.findByRole("button", { name: "Refresh 30" }));
    await waitFor(() => expect(refresh).toHaveBeenCalledWith(30));
  });

  it("sends no limit from the plain Refresh", async () => {
    const { refresh } = setupShort(finished({}));
    refresh.mockResolvedValue(finished(RUNNING));

    fireEvent.click(await screen.findByRole("button", { name: "Refresh" }));
    await waitFor(() => expect(refresh).toHaveBeenCalledWith(undefined));
  });

  it("disables both while a short refresh runs and shows its stage on its own button", async () => {
    setupShort(finished({ ...RUNNING, limit: 30 }));

    const busy = await screen.findByRole("button", { name: /Reading posts and pages: 4 of 30/ });
    expect(busy).toBeDisabled();
    expect(busy).toHaveAttribute("aria-busy", "true");
    expect(busy).toHaveClass("button--quiet");
    const plain = screen.getByRole("button", { name: "Refresh" });
    expect(plain).toBeDisabled();
    expect(plain).toHaveAttribute("aria-busy", "false");
  });

  it("shows the stage on Refresh while a full refresh runs, whichever button was pressed", async () => {
    setupShort(finished({ ...RUNNING, limit: null }));

    const busy = await screen.findByRole("button", { name: /Reading posts and pages: 4 of 30/ });
    expect(busy).not.toHaveClass("button--quiet");
    expect(screen.getByRole("button", { name: "Refresh 30" })).toBeDisabled();
  });

  it.each([
    [12, "12 posts left to read"],
    [1, "1 post left to read"],
    [0, "All posts are read"],
  ])("says how many posts are left after a short refresh: %i", async (left, text) => {
    setupShort(finished({ limit: 30, posts_left: left }));

    expect(await screen.findByText(text)).toHaveClass("refresh__posts-left");
  });

  it("says nothing about posts left after a full refresh", async () => {
    setupShort(finished({}));

    await screen.findByRole("button", { name: "Refresh 30" });
    expect(screen.queryByText(/left to read|All posts are read/)).toBeNull();
  });
});
