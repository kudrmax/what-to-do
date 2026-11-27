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
    events_touched: 0,
    errors: [],
    reader_unavailable: false, reader: null,
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
    setup(finished({ errors: ["Кафана: couldn't read it", SIGN_IN], reader_unavailable: true, reader: "claude" }));

    const note = await screen.findByRole("alert");
    expect(note).toHaveTextContent("Sign in to Claude to read the posts");
    expect(note.querySelector("code")).toBeNull();
    expect(screen.getByRole("button", { name: "Sign in to Claude" })).toBeTruthy();
    expect(screen.getByRole("status")).toHaveTextContent("Кафана: couldn't read it");
    expect(screen.queryByText(/Not logged in/)).toBeNull();
    expect(screen.getByRole("status")).not.toHaveTextContent("Sign in to Claude Code");
  });

  it("signs in through the browser and takes the code when the browser didn't open", async () => {
    const { start, submit } = setup(finished({ reader_unavailable: true, reader: "claude" }));

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
    setup(finished({ reader_unavailable: true, reader: "claude" }), { ...SIGNED_OUT, signing_in: true, page_url: PAGE, error: "Invalid code. Please make sure the full code was copied." });

    expect(await screen.findByText("Invalid code. Please make sure the full code was copied.")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Open the sign-in page" })).toBeTruthy();
  });

  it("says when the sign-in is done", async () => {
    setup(finished({ reader_unavailable: true, reader: "claude" }), { ...SIGNED_OUT, state: "signed_in" });

    expect(await screen.findByText("Signed in to Claude")).toBeTruthy();
    expect(screen.getByText("Press Refresh to read the posts.")).toBeTruthy();
  });

  it("explains a read that failed before Claude Code got ready during the refresh", async () => {
    setup(finished({ errors: ["Install Claude Code: What To Do needs it to read posts"], reader_unavailable: true, reader: "claude" }), { ...SIGNED_OUT, state: "signed_in" });

    expect(await screen.findByText("Signed in to Claude")).toBeTruthy();
    expect(screen.getByText("Press Refresh to read the posts.")).toBeTruthy();
    expect(screen.queryByText(/needs it to read posts/)).toBeNull();
  });

  it("tells why the last sign-in failed", async () => {
    setup(finished({ reader_unavailable: true, reader: "claude" }), { ...SIGNED_OUT, error: "Login failed: That code wasn't accepted." });

    expect(await screen.findByText("Login failed: That code wasn't accepted.")).toBeTruthy();
  });

  it("says how to install Claude Code instead of the raw error", async () => {
    setup(finished({ errors: ["Кафана: couldn't read it", "Install Claude Code: What To Do needs it to read posts"], reader_unavailable: true, reader: "claude" }), {
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
    setup(finished({ errors: ["Update Claude Code: you have 2.1.200, What To Do needs 2.1.321 or newer"], reader_unavailable: true, reader: "claude" }), {
      ...SIGNED_OUT,
      state: "too_old",
      version: "2.1.200",
    });

    expect(await screen.findByRole("alert")).toHaveTextContent("Update Claude Code to read the posts");
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("keeps the backend's line when it can't tell whether Claude Code is there", async () => {
    setup(finished({ errors: ["Install Claude Code: What To Do needs it to read posts"], reader_unavailable: true, reader: "claude" }), () => Promise.reject(new Error("offline")));

    expect(await screen.findByRole("status")).toHaveTextContent("Install Claude Code: What To Do needs it to read posts");
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("offers to sign in once Claude Code is installed and the next refresh ends, without a restart", async () => {
    let signIn: ClaudeSignIn = { ...SIGNED_OUT, state: "not_installed", version: null, update_command: null };
    const { refresh } = setup(finished({ reader_unavailable: true, reader: "claude" }), async () => signIn);
    expect(await screen.findByText("Install Claude Code to read the posts")).toBeTruthy();

    signIn = SIGNED_OUT;
    refresh.mockResolvedValue(finished({ finished_at: "2026-11-16T11:00:00Z", errors: [SIGN_IN], reader_unavailable: true, reader: "claude" }));
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
    const { claude, codex } = setup(finished({ errors: ["Кафана: couldn't read it", CODEX_SIGN_IN], reader_unavailable: true, reader: "codex" }), SIGNED_OUT, "codex");

    const note = await screen.findByRole("alert");
    expect(note).toHaveTextContent("Sign in to ChatGPT to read the posts");
    expect(screen.getByRole("button", { name: "Sign in to ChatGPT" })).toBeTruthy();
    expect(screen.getByRole("status")).toHaveTextContent("Кафана: couldn't read it");
    expect(screen.getByRole("status")).not.toHaveTextContent(CODEX_SIGN_IN);
    expect(codex).toHaveBeenCalled();
    expect(claude).not.toHaveBeenCalled();
  });

  it("says how to install Codex instead of the raw error", async () => {
    setup(finished({ errors: ["Install Codex: What To Do needs it to read posts"], reader_unavailable: true, reader: "codex" }), SIGNED_OUT, "codex", {
      ...CODEX_SIGNED_OUT,
      state: "not_installed",
      version: null,
      update_command: null,
    });

    expect(await screen.findByRole("alert")).toHaveTextContent("Install Codex to read the posts");
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("says how to update Codex instead of the raw error", async () => {
    setup(finished({ errors: ["Update Codex: you have 0.150.0, What To Do needs 0.172.0 or newer"], reader_unavailable: true, reader: "codex" }), SIGNED_OUT, "codex", {
      ...CODEX_SIGNED_OUT,
      state: "too_old",
      version: "0.150.0",
    });

    expect(await screen.findByRole("alert")).toHaveTextContent("Update Codex to read the posts");
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("says once why Codex is refused", async () => {
    setup(finished({ errors: [OFFERS_TOOLS], reader_unavailable: true, reader: "codex" }), SIGNED_OUT, "codex", { ...CODEX_SIGNED_OUT, state: "refused", message: OFFERS_TOOLS });

    const box = await screen.findByRole("alert");
    expect(box).toHaveTextContent("Codex can’t be used safely");
    expect(screen.getAllByText(OFFERS_TOOLS)).toHaveLength(1);
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

  it("keeps the line about a tool Codex tried to use instead of saying it is signed in", async () => {
    setup(finished({ errors: ["Codex tried to use a tool; nothing was read"], reader_unavailable: true, reader: "codex" }), SIGNED_OUT, "codex", { ...CODEX_SIGNED_OUT, state: "signed_in" });

    expect(await screen.findByRole("status")).toHaveTextContent("Codex tried to use a tool; nothing was read");
    expect(screen.queryByText("Signed in to ChatGPT")).toBeNull();
  });

  it("names the reader from the settings when the refresh doesn't say whose it was", async () => {
    const { claude } = setup(finished({ errors: [CODEX_SIGN_IN], reader_unavailable: true, reader: null }), SIGNED_OUT, "codex");

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
    const { claude, codex } = setup(finished({ errors: [SIGN_IN], reader_unavailable: true, reader: "claude" }), SIGNED_OUT, "codex");

    expect(await screen.findByRole("button", { name: "Sign in to Claude" })).toBeTruthy();
    expect(claude).toHaveBeenCalled();
    expect(codex).not.toHaveBeenCalled();
  });

  it("keeps the backend's line when Codex can't tell whether someone is signed in", async () => {
    setup(finished({ errors: [CODEX_SIGN_IN], reader_unavailable: true, reader: "codex" }), SIGNED_OUT, "codex", { ...CODEX_SIGNED_OUT, state: "unknown" });

    expect(await screen.findByRole("status")).toHaveTextContent(CODEX_SIGN_IN);
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.queryByRole("button", { name: "Sign in to ChatGPT" })).toBeNull();
  });

  it("keeps the backend's line when Claude Code can't tell whether someone is signed in", async () => {
    setup(finished({ errors: [SIGN_IN], reader_unavailable: true, reader: "claude" }), { ...SIGNED_OUT, state: "unknown" });

    expect(await screen.findByRole("status")).toHaveTextContent("Sign in to Claude Code");
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.queryByRole("button", { name: "Sign in to Claude" })).toBeNull();
  });
});
