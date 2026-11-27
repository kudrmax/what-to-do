import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { createApi, type ClaudeSignIn as SignInView } from "../api/client";
import { ApiContext } from "../api/queries";
import { ClaudeSignIn } from "./ClaudeSignIn";

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

function setup(view: SignInView) {
  const api = createApi("");
  vi.spyOn(api, "claudeSignIn").mockResolvedValue(view);
  render(
    <ApiContext.Provider value={api}>
      <QueryClientProvider client={new QueryClient()}>
        <ClaudeSignIn />
      </QueryClientProvider>
    </ApiContext.Provider>,
  );
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
    setup(SIGNED_OUT);

    const box = await screen.findByRole("alert");
    expect(box).toHaveTextContent("Sign in to Claude to read the posts");
    expect(screen.getByRole("button", { name: "Sign in to Claude" })).toBeTruthy();
    expect(box.querySelector("code")).toBeNull();
  });
});
