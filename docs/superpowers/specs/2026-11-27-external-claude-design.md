# Claude Code installed by the user, not bundled

## Why

The disk image carries its own copy of the Claude CLI (309 MB, about 145 MB compressed, more than half of today's
256 MB image). Max wants the AI programs to be dependencies the user installs, not passengers in every download: the
app does not read posts until the user has installed Claude Code. This is the first of two releases; the second adds
Codex the same way (see `2026-11-27-codex-provider-design.md` on branch `codex-provider`), so the mechanism here is
built to take a second program.

## What Max decided

- The app no longer ships Claude Code. It uses the `claude` the user installed.
- Not installed: refreshing does not work, and the app says how to install it.
- A separate release, before Codex.

## Goals

- The disk image loses the bundled CLI (expected about 110 MB instead of 256).
- The app finds an installed Claude Code even when started from Finder, where the terminal's PATH is not set.
- Missing or too old Claude Code gives a clear message with the install or update command, never a cryptic error.
- Dev runs (`uv run`) behave the same as the built app: they also use the installed `claude`, not the copy inside the
  `claude-agent-sdk` wheel.

## Non-goals

- Installing Claude Code from the app.
- Codex (next release).

## Anti-goals

- A user who has Claude Code installed and signed in notices anything except a smaller download.
- The app silently using a different `claude` from the one the user updates.

## Facts (checked 2026-11-27)

- `claude-agent-sdk` takes `ClaudeAgentOptions(cli_path=...)`; without it, it prefers its `_bundled/claude`, then
  `shutil.which("claude")` (`subprocess_cli.py:237-264`).
- The SDK itself refuses a CLI older than 2.0.0 and needs 2.1.248 for verbatim prompts
  (`MINIMUM_CLAUDE_CODE_VERSION`, `VERBATIM_PROMPTS_MINIMUM_CLAUDE_CODE_VERSION`). The wheel bundles 2.1.321.
- Max's Claude Code: `/opt/homebrew/bin/claude` (Homebrew cask), 2.1.325.
- Today the app finds the CLI in `ClaudeLogin.find_cli` (bundled first, then PATH); `build-dmg.sh:60` fails the build
  when the bundled CLI is missing; the signing step skips it because it keeps Anthropic's signature.

## Design

### Finding the program (built for two programs)

- `InstalledCli`: finds one program by name in a fixed list of install places plus PATH, and reads its version.
  - Places for `claude`: `~/.local/bin` (native installer), `/opt/homebrew/bin` and `/usr/local/bin` (Homebrew),
    `~/.claude/local` (old local install), npm global bin (`~/.npm-global/bin`, `$(npm prefix -g)/bin` if npm exists),
    then PATH. The first executable found wins.
  - Version: `claude --version`, parsed `X.Y.Z`. Minimum for the app: 2.1.248 (the SDK's verbatim-prompts minimum).
  - State: `missing`, `too_old` (with found version and minimum), `ready` (path, version).
  - Looked up on each check (cheap), so installing while the app runs works without a restart.
- `ClaudeJsonLlm` passes `cli_path` from `InstalledCli` on every call. Missing or too old raises
  `ClaudeNotInstalledError` (an `LlmError`), handled like signed-out: nothing is read, the refresh says why.
- `ClaudeLogin` and `ClaudeSignInFlow` use the same found path instead of `find_cli`.

### What the user sees

- The sign-in box under Refresh gains two earlier states. With Claude Code missing:

  ```
  Install Claude Code to read the posts
  What To Do reads posts with your Claude subscription through Claude Code.
  [ curl -fsSL https://claude.ai/install.sh | bash ]  [Copy]
  Or with Homebrew: brew install --cask claude-code
  Then press Refresh.
  ```

  Too old: "Update Claude Code: you have 2.0.10, What To Do needs 2.1.248 or newer", with `claude update`.
  The builder checks both install commands against Anthropic's current docs before writing them.
- Settings: nothing new.
- The launcher's start-up warning (`launcher/cli.py:256-260`) also says "not installed" / "too old".
- README Requirements: Claude Code installed, with the command; the line "the user needs nothing else" goes; FAQ
  gets "Refresh says to install Claude Code".
- Existing users without Claude Code see the install box after updating; the release notes say so first.

### Bundle

- `build-dmg.sh` removes `claude_agent_sdk/_bundled` from the image instead of requiring it, and checks it is gone.
- The signing comment about the Claude CLI's own signature goes.
- Measure both images before and after; the release notes give the new size.

## Verification before master

- Tests: finder (places order, PATH, versions, missing, too old), `ClaudeJsonLlm` passing `cli_path`, refresh and
  sign-in states, the box in each state.
- In the built app on a copy of the data: a refresh reads posts through Max's Homebrew `claude`; with the program
  hidden from the finder (a test override of the places list, never touching Max's install) the install box shows.

## Left to the builder

- Exact npm global path detection.
- Parsing `claude --version` output variants.
