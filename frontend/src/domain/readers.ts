import type { LlmProvider } from "../api/client";

export interface Reader {
  name: string;
  program: string;
  account: string;
  plan: string;
  linesTheBoxExplains: readonly string[];
  linesThatStay: readonly string[];
  install: readonly { label: string; command: string }[];
}

export const READERS: Record<LlmProvider, Reader> = {
  claude: {
    name: "Claude",
    program: "Claude Code",
    account: "Claude",
    plan: "your Claude plan",
    linesTheBoxExplains: ["Install Claude Code", "Update Claude Code", "Sign in to Claude Code"],
    linesThatStay: [],
    install: [
      { label: "Installer", command: "curl -fsSL https://claude.ai/install.sh | bash" },
      { label: "Homebrew", command: "brew install --cask claude-code@latest" },
    ],
  },
  codex: {
    name: "Codex",
    program: "Codex",
    account: "ChatGPT",
    plan: "your ChatGPT plan",
    linesTheBoxExplains: [
      "Install Codex",
      "Update Codex",
      "Sign in to ChatGPT",
      "This Codex version offers tools",
      "What To Do could not check that Codex has no tools",
      "Codex would give the model the instructions in",
      "Codex is installed at a path What To Do cannot start safely",
    ],
    linesThatStay: ["ChatGPT plan limit reached", "Codex tried to use a tool"],
    install: [
      { label: "Installer", command: "curl -fsSL https://chatgpt.com/codex/install.sh | sh" },
      { label: "Homebrew", command: "brew install --cask codex" },
    ],
  },
};

const startsWithAny = (line: string, starts: readonly string[]) => starts.some((start) => line.startsWith(start));

export const boxExplains = (reader: Reader, line: string) => startsWithAny(line, reader.linesTheBoxExplains);

export const staysAsLine = (reader: Reader, line: string) => startsWithAny(line, reader.linesThatStay);
