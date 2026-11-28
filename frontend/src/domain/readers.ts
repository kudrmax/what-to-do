import type { LlmProvider } from "../api/client";

export interface Reader {
  name: string;
  program: string;
  account: string;
  plan: string;
  boxWhenSignInUnknown: boolean;
  install: readonly { label: string; command: string }[];
}

export const READERS: Record<LlmProvider, Reader> = {
  claude: {
    name: "Claude",
    program: "Claude Code",
    account: "Claude",
    plan: "your Claude plan",
    boxWhenSignInUnknown: true,
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
    boxWhenSignInUnknown: false,
    install: [
      { label: "Installer", command: "curl -fsSL https://chatgpt.com/codex/install.sh | sh" },
      { label: "Homebrew", command: "brew install --cask codex" },
    ],
  },
};

