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
- The app finds an installed Claude Code even when started from Finder, where PATH holds only system folders
  (`ServerHome.swift:35-40`, `AppDelegate.swift:25`).
- Missing or too old Claude Code gives a clear message with the right install or update command, never a cryptic error.
- Dev runs (`uv run`, git checkouts on macOS, Linux, Windows) also use the installed `claude`, never the copy inside the
  `claude-agent-sdk` wheel.

## Non-goals

- Installing Claude Code from the app.
- Using the CLI that the Claude desktop app keeps for itself (`~/Library/Application Support/Claude/claude-code/<ver>/`):
  a private part of another app, replaced on its own schedule. A Desktop-only user sees the install box (builder's
  call, Max may overrule).
- Codex (next release).

## Anti-goals

- A user who has Claude Code installed and signed in notices anything except a smaller download.
- The app using a different `claude` from the one `which claude` shows in the user's terminal.

## Facts (checked 2026-11-27)

- `claude-agent-sdk` takes `ClaudeAgentOptions(cli_path=...)` and then skips its own search (`subprocess_cli.py:803-804`);
  without it, it prefers `_bundled/claude`, then PATH.
- The SDK's own version check only logs a warning, never refuses (`subprocess_cli.py:1164-1226`); it runs `claude -v`
  on every call, even with `cli_path`.
- The wheel bundles CLI 2.1.321 (`_cli_version.py`). Max's Claude Code: `/opt/homebrew/bin/claude` ->
  `Caskroom/claude-code@latest/2.1.325`, a native binary that runs with an empty environment.
- Homebrew installs do not update themselves; `claude update` on them answers "up to date"
  (https://code.claude.com/docs/en/setup). The npm package installs the native binary too.
- The login lives in Claude Code's keychain entry, so it carries over to the user's installed CLI (README:251).

## Design

### Finding the program (built for two programs)

- `InstalledCli`, injected into everything that runs the CLI (`ClaudeJsonLlm`, `ClaudeLogin`, `ClaudeSignInFlow`, the
  launcher warning), so tests pass a fake and never need a real `claude`:
  - Search order: **PATH first** (matches the terminal for `uv run`), then fixed places: `~/.local/bin` (native
    installer; `claude.exe` there on Windows), `/opt/homebrew/bin`, `/usr/local/bin`, `~/.claude/local/claude`, and the
    npm global bins found by reusing `launcher/tools.py` (`_common_dirs`, `_nvm_dirs`), not by running npm.
  - Version from `claude --version` (`X.Y.Z`), cached by path and file modification time, so a call costs no extra
    process once known and an update is noticed.
  - **Minimum 2.1.321**, the version the app is built and tested with (the bundled one so far); the app relies on
    `--json-schema`, `--tools ""`, `--no-session-persistence`, `--setting-sources`, JSON `auth status`,
    `auth login --claudeai`.
  - State: `missing`, `too_old` (found version, minimum, update command), `ready` (path, version).
  - Install method from the resolved path: inside `Caskroom/<cask>/` -> `brew upgrade --cask <cask>`; anything else ->
    `claude update`.
  - Looked up on each check, so installing while the app runs works without a restart.
- `ClaudeJsonLlm` passes `cli_path` on every call. Missing or too old raises `ClaudeUnavailableError` (an `LlmError`).

### States the app carries

- `ClaudeSignIn` gains `not_installed` and `too_old`; `ClaudeLogin.check` returns them instead of `unknown`.
- `ClaudeSignInView` (`api/app.py:107`) carries the state plus version, minimum and the install or update command;
  frontend types regenerated.
- The refresh report: `claude_signed_out` (`refresh.py:78`) becomes `claude_unavailable` with the reason
  (signed out, not installed, too old); `RefreshButton.tsx:15` shows the box for any of them. Same rename in tests.
- Re-tagging (`retagging.py:155`) stops on the new error as it does on signed-out: one message, not one per batch.
- The old "Reinstall What To Do" text (`claude_login.py:135`) goes.

### What the user sees

Under Refresh, the existing sign-in box gains two earlier states.

Missing:
```
Install Claude Code to read the posts
What To Do reads posts with your Claude subscription through Claude Code.
  curl -fsSL https://claude.ai/install.sh | bash        [Copy]
  or with Homebrew: brew install --cask claude-code@latest   [Copy]
Then press Refresh.
```
Too old: "Update Claude Code: you have 2.1.200, What To Do needs 2.1.321 or newer" with the command for that install
(`brew upgrade --cask claude-code@latest` or `claude update`) and Copy.
Commands are checked against Anthropic's setup page when written.

Also:
- The launcher's start-up warning (`launcher/cli.py:256-260`) covers not installed and too old.
- README: Requirements get "Claude Code installed" with the commands (Windows and Linux git checkouts included); the
  line that nothing else is needed goes; FAQ gets "Refresh says to install Claude Code".
- Release notes open with: install Claude Code if you don't have it; the download is smaller.

### Bundle and CI

- `build-dmg.sh` deletes `claude_agent_sdk/_bundled` from the image instead of requiring it (`:60`), and fails if it is
  still there. The comment about keeping the CLI's own signature goes.
- `smoke-test-bundle.sh:22` (run in `ci.yml:83`, `release-dmg.yml:54`) checks instead that `_bundled` is absent and
  that `/api/claude/sign-in` answers a valid state, `not_installed` included (GitHub runners have no Claude Code).
- Image sizes measured before and after; the release notes give the new size.

## Verification before master

- Tests: finder (order, PATH first, fixed places, npm dirs, Windows name, version parse and cache, missing, too old,
  update command per install method), `ClaudeJsonLlm` passing `cli_path`, refresh and re-tag stopping once, sign-in
  view states, the box in each state.
- In the built app, on a copy of the data: a refresh reads posts through Max's Homebrew `claude`; with a test override
  of the search list (never touching Max's install) the install box and the too-old box show, each seen on screen.

## Left to the builder

- Parsing `claude --version` output variants.
- Wording of the boxes within the layout above.
