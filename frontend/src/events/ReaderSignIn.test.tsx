import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { createApi, type ClaudeSignIn as SignInView, type CodexSignIn } from "../api/client";
import { ApiContext } from "../api/queries";
import { ReaderSignIn } from "./ReaderSignIn";

const INSTALLER = "curl -fsSL https://claude.ai/install.sh | bash";
const HOMEBREW = "brew install --cask claude-code@latest";

const SIGNED_OUT: SignInView = {
  state: "signed_out",
  hint: "Sign in to Claude Code: run `claude` in a terminal and type /login",
  signing_in: false,
  page_url: null,
  error: null,
  version: "2.1.325",
  minimum: "2.1.321",
  update_command: "claude update",
};

const CODEX_SIGNED_OUT: CodexSignIn = {
  state: "signed_out",
  hint: "Sign in to ChatGPT in What To Do to read posts with Codex",
  signing_in: false,
  page_url: null,
  error: null,
  version: "0.172.0",
  minimum: "0.172.0",
  update_command: "brew upgrade --cask codex",
  message: null,
};
const CODEX_PAGE = "https://auth.openai.com/oauth/authorize?client_id=c&state=s";

function setup(view: SignInView) {
  const api = createApi("");
  vi.spyOn(api, "claudeSignIn").mockResolvedValue(view);
  const codex = vi.spyOn(api, "codexSignIn");
  render(
    <ApiContext.Provider value={api}>
      <QueryClientProvider client={new QueryClient()}>
        <ReaderSignIn provider="claude" />
      </QueryClientProvider>
    </ApiContext.Provider>,
  );
  return { codex };
}

function setupCodex(view: CodexSignIn) {
  const api = createApi("");
  vi.spyOn(api, "codexSignIn").mockResolvedValue(view);
  const claude = vi.spyOn(api, "claudeSignIn");
  const start = vi.spyOn(api, "startCodexSignIn").mockResolvedValue({ ...view, signing_in: true, page_url: CODEX_PAGE });
  render(
    <ApiContext.Provider value={api}>
      <QueryClientProvider client={new QueryClient()}>
        <ReaderSignIn provider="codex" />
      </QueryClientProvider>
    </ApiContext.Provider>,
  );
  return { claude, start };
}

function withClipboard() {
  const writeText = vi.fn().mockResolvedValue(undefined);
  Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
  return writeText;
}

afterEach(() => {
  delete (navigator as { clipboard?: Clipboard }).clipboard;
});

function commandRow(command: string) {
  const code = screen.getByText(command);
  expect(code.tagName).toBe("CODE");
  return code.parentElement as HTMLElement;
}

describe("Claude Code box under Refresh", () => {
  it("says how to install Claude Code when it is missing", async () => {
    const writeText = withClipboard();
    setup({ ...SIGNED_OUT, state: "not_installed", version: null, update_command: null });

    const box = await screen.findByRole("alert");
    expect(box).toHaveTextContent("Install Claude Code to read the posts");
    expect(within(box).getByText("Installer")).toBeTruthy();
    expect(within(box).getByText("Homebrew")).toBeTruthy();
    expect(box.querySelectorAll("code")).toHaveLength(2);
    expect(screen.queryByRole("button", { name: "Sign in to Claude" })).toBeNull();

    fireEvent.click(within(commandRow(HOMEBREW)).getByRole("button", { name: "Copy" }));
    expect(writeText).toHaveBeenCalledWith(HOMEBREW);
    expect(await within(commandRow(HOMEBREW)).findByRole("button", { name: "Copied" })).toBeTruthy();
    expect(within(commandRow(INSTALLER)).getByRole("button", { name: "Copy" })).toBeTruthy();

    fireEvent.click(within(commandRow(INSTALLER)).getByRole("button", { name: "Copy" }));
    expect(writeText).toHaveBeenLastCalledWith(INSTALLER);
  });

  it("says which version is there and how to update it when it is too old", async () => {
    const writeText = withClipboard();
    setup({ ...SIGNED_OUT, state: "too_old", version: "2.1.200", update_command: "brew upgrade --cask claude-code@latest" });

    const box = await screen.findByRole("alert");
    expect(box).toHaveTextContent("Update Claude Code to read the posts");
    expect(box).toHaveTextContent("2.1.200");
    expect(box).toHaveTextContent("2.1.321");
    expect(screen.queryByRole("button", { name: "Sign in to Claude" })).toBeNull();

    fireEvent.click(within(commandRow("brew upgrade --cask claude-code@latest")).getByRole("button", { name: "Copy" }));
    expect(writeText).toHaveBeenCalledWith("brew upgrade --cask claude-code@latest");
  });

  it("offers to sign in when Claude Code is there but signed out", async () => {
    const { codex } = setup(SIGNED_OUT);

    const box = await screen.findByRole("alert");
    expect(box).toHaveTextContent("Sign in to Claude to read the posts");
    expect(screen.getByRole("button", { name: "Sign in to Claude" })).toBeTruthy();
    expect(box.querySelector("code")).toBeNull();
    expect(codex).not.toHaveBeenCalled();
  });
});

describe("Codex box under Refresh", () => {
  it("says how to install Codex when it is missing", async () => {
    const writeText = withClipboard();
    const { claude } = setupCodex({ ...CODEX_SIGNED_OUT, state: "not_installed", version: null, update_command: null });

    const box = await screen.findByRole("alert");
    expect(box).toHaveTextContent("Install Codex to read the posts");
    expect(box).toHaveTextContent("your ChatGPT plan");
    expect(within(box).getByText("Installer")).toBeTruthy();
    expect(within(box).getByText("Homebrew")).toBeTruthy();
    expect(box.querySelectorAll("code")).toHaveLength(2);
    expect(screen.queryByRole("button", { name: "Sign in to ChatGPT" })).toBeNull();

    fireEvent.click(within(commandRow("curl -fsSL https://chatgpt.com/codex/install.sh | sh")).getByRole("button", { name: "Copy" }));
    expect(writeText).toHaveBeenCalledWith("curl -fsSL https://chatgpt.com/codex/install.sh | sh");
    fireEvent.click(within(commandRow("brew install --cask codex")).getByRole("button", { name: "Copy" }));
    expect(writeText).toHaveBeenLastCalledWith("brew install --cask codex");
    expect(claude).not.toHaveBeenCalled();
  });

  it("says which version is there and how to update it when it is too old", async () => {
    const writeText = withClipboard();
    setupCodex({ ...CODEX_SIGNED_OUT, state: "too_old", version: "0.150.0", update_command: "brew upgrade --cask codex" });

    const box = await screen.findByRole("alert");
    expect(box).toHaveTextContent("Update Codex to read the posts");
    expect(box).toHaveTextContent("You have 0.150.0. What To Do needs 0.172.0 or newer.");

    fireEvent.click(within(commandRow("brew upgrade --cask codex")).getByRole("button", { name: "Copy" }));
    expect(writeText).toHaveBeenCalledWith("brew upgrade --cask codex");
  });

  it("offers to sign in to ChatGPT and shows the page to open by hand while it waits", async () => {
    const { start } = setupCodex(CODEX_SIGNED_OUT);

    const box = await screen.findByRole("alert");
    expect(box).toHaveTextContent("Sign in to ChatGPT to read the posts");
    expect(box.querySelector("code")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Sign in to ChatGPT" }));

    expect(await screen.findByText("Finish signing in in your browser")).toBeTruthy();
    expect(start).toHaveBeenCalled();
    fireEvent.click(screen.getByText("The browser didn’t open?"));
    expect(screen.getByRole("link", { name: "Open the sign-in page" })).toHaveAttribute("href", CODEX_PAGE);
    expect(screen.queryByLabelText("Code from the sign-in page")).toBeNull();
  });

  it("says why the last sign-in to ChatGPT failed", async () => {
    setupCodex({ ...CODEX_SIGNED_OUT, error: "Sign-in was declined" });

    expect(await screen.findByText("Sign-in was declined")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Sign in to ChatGPT" })).toBeTruthy();
  });

  it("says why Codex is refused and offers nothing to press", async () => {
    setupCodex({ ...CODEX_SIGNED_OUT, state: "refused", message: "This Codex version offers tools What To Do cannot turn off; update What To Do" });

    const box = await screen.findByRole("alert");
    expect(within(box).getByText("Codex can’t be used safely")).toBeTruthy();
    expect(within(box).getByText("This Codex version offers tools What To Do cannot turn off; update What To Do")).toBeTruthy();
    expect(within(box).queryByRole("button")).toBeNull();
  });

  it("says when the sign-in to ChatGPT is done", async () => {
    setupCodex({ ...CODEX_SIGNED_OUT, state: "signed_in" });

    expect(await screen.findByText("Signed in to ChatGPT")).toBeTruthy();
    expect(screen.getByText("Press Refresh to read the posts.")).toBeTruthy();
  });
});
