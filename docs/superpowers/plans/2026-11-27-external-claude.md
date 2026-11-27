# Claude Code Installed by the User Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The app stops shipping the Claude CLI and runs the `claude` the user installed, saying how to install or update it when it is missing or too old.

**Architecture:** A new `InstalledCli` finds a program (PATH first, then known install folders), reads and caches its version and knows the update command for its install method. Everything that runs the Claude CLI gets it injected. Missing or too old becomes a `ClaudeUnavailableError` and two new sign-in states that the refresh report, re-tagging, the API and the sign-in box carry. The disk image drops `claude_agent_sdk/_bundled`.

**Tech Stack:** Python 3.13, FastAPI, pydantic, claude-agent-sdk, pytest; React + TypeScript, vitest; bash (`build-dmg.sh`, `smoke-test-bundle.sh`).

**Spec:** `docs/superpowers/specs/2026-11-27-external-claude-design.md`

## Global Constraints

- Minimum Claude Code version: `2.1.321`.
- Search order: PATH first, then `~/.local/bin`, `/opt/homebrew/bin`, `/usr/local/bin`, `~/.claude/local`, npm global bins (Volta, nvm). Windows name `claude.exe`.
- Update command: resolved path inside `Caskroom/<cask>/` -> `brew upgrade --cask <cask>`; otherwise `claude update`.
- Install commands shown: `curl -fsSL https://claude.ai/install.sh | bash` and `brew install --cask claude-code@latest` (re-check on https://code.claude.com/docs/en/setup when writing them).
- The Claude desktop app's private CLI is never used.
- UI, code and docs English only (`tests/test_english_only.py`).
- Never touch Max's installed `claude` or the real data folder; built-app checks run on a copy of the data.
- Commit messages: no AI mentions (a hook rejects them).

## Review Focus

- `claude --version` prints something unexpected or hangs: state is `too_old` with `version None`, the check gives up after 5 s -> test in Task 1.
- `claude` on PATH is a broken symlink or not executable: skipped, search goes on -> test in Task 1.
- Claude Code updated while the app runs: the cached version is dropped because the file changed -> test in Task 1.
- A refresh with Claude missing makes many calls: one message, not one per batch, in refresh and in re-tagging -> tests in Task 3.
- Box state changes after the user installs and presses Refresh, without an app restart -> test in Task 2 (finder asked on every check).

---

### Task 1: InstalledCli finder

**Files:**
- Create: `src/where_to_go/installed_cli.py`
- Modify: `src/where_to_go/launcher/tools.py:31-60` (expose the folders)
- Test: `tests/test_installed_cli.py`

**Interfaces:**
- Produces:
  - `class CliStatus(StrEnum)`: `READY = "ready"`, `MISSING = "missing"`, `TOO_OLD = "too_old"`.
  - `@dataclass(frozen=True) class FoundCli`: `status: CliStatus`, `path: Path | None`, `version: str | None`, `minimum: str`, `update_command: str | None`.
  - `class InstalledCli`: `__init__(self, name: str, minimum: str, extra_dirs: Callable[[], list[Path]], environ: Mapping[str, str] = os.environ, run_version: Callable[[Path], str | None] | None = None)`; `find(self) -> FoundCli`.
  - `def claude_cli(environ: Mapping[str, str] = os.environ, home: Path | None = None) -> InstalledCli` — the Claude instance with the spec's folders and minimum `2.1.321`.
  - `Tools.program_dirs(self) -> list[Path]` in `launcher/tools.py`: common dirs + `~/.volta/bin` + nvm dirs (what `npm()` searches today); `npm()` uses it.

- [ ] **Step 1: Write the failing tests** in `tests/test_installed_cli.py`, with fake executables in `tmp_path` and a fake `run_version`:
  - `test_path_wins_over_fixed_places`: same name on PATH and in an extra dir -> `path` is the PATH one.
  - `test_fixed_places_when_path_lacks_it`: PATH empty -> found in `extra_dirs`.
  - `test_missing`: nowhere -> `status == MISSING`, `path is None`.
  - `test_too_old`: version `2.1.200` -> `TOO_OLD`, `version == "2.1.200"`, `minimum == "2.1.321"`.
  - `test_ready`: `2.1.325 (Claude Code)` -> `READY`, `version == "2.1.325"`.
  - `test_unreadable_version_counts_as_too_old`: `run_version` returns `None` or `"garbage"` -> `TOO_OLD`, `version is None`.
  - `test_version_cached_until_file_changes`: two `find()` calls -> `run_version` called once; touch the file (new mtime) -> called again.
  - `test_broken_symlink_skipped`: a dangling `claude` link on PATH, real one in extra dir -> the real one.
  - `test_homebrew_cask_update_command`: resolved path `.../Caskroom/claude-code@latest/2.1.325/claude` (via symlink) -> `update_command == "brew upgrade --cask claude-code@latest"`.
  - `test_other_install_update_command` -> `"claude update"`.
  - `test_windows_name` (monkeypatch `os.name` or pass name via a `windows: bool` flag on `claude_cli`) -> looks for `claude.exe` in `~/.local/bin`.
  - `test_program_dirs_lists_nvm_and_volta` for `Tools.program_dirs`.
- [ ] **Step 2:** Run `uv run pytest tests/test_installed_cli.py -q` — Expected: FAIL (module missing).
- [ ] **Step 3:** Implement. Default `run_version` runs `[path, "--version"]` with `timeout=5`, `stdin=DEVNULL`, environment cleaned by `ClaudeCliEnvironment.cleaned`, returns stdout or `None` on error. Version parse: first `\d+\.\d+\.\d+`. Cache: dict keyed by `(resolved path, st_mtime_ns)`.
- [ ] **Step 4:** Run `uv run pytest tests/test_installed_cli.py tests/ -q -k "installed_cli or tools"` — Expected: PASS.
- [ ] **Step 5:** Commit `git add src/where_to_go/installed_cli.py src/where_to_go/launcher/tools.py tests/test_installed_cli.py && git commit -m "Find the installed CLI: PATH first, install folders, cached version, update command"`

### Task 2: Run the installed Claude everywhere

**Files:**
- Modify: `src/where_to_go/claude_login.py` (drop `find_cli`/`_found_cli`; `ClaudeSignIn` new states; `ClaudeLogin`, `ClaudeSignInFlow` take `InstalledCli`)
- Modify: `src/where_to_go/llm.py` (`ClaudeUnavailableError`, `cli_path`)
- Modify: `src/where_to_go/container.py:131-133,231` (build one `claude_cli()` and pass it)
- Modify: `src/where_to_go/launcher/cli.py:256-260`
- Modify: `scripts/model_compare.py` (constructor change)
- Test: `tests/test_claude_sign_in.py`, `tests/test_llm.py`

**Interfaces:**
- Consumes: `InstalledCli.find() -> FoundCli`, `claude_cli()` (Task 1).
- Produces:
  - `ClaudeSignIn` gains `NOT_INSTALLED = "not_installed"`, `TOO_OLD = "too_old"`.
  - `class ClaudeUnavailableError(LlmError)`: `__init__(self, found: FoundCli)`, attribute `found`; message `"Install Claude Code to read posts"` or `"Update Claude Code: you have X, What To Do needs 2.1.321 or newer"`.
  - `class ClaudeNotReadyError(LlmError)`: common base of `ClaudeSignedOutError` and `ClaudeUnavailableError`; callers that stop once catch it.
  - `ClaudeJsonLlm(model: Callable[[], str], cli: InstalledCli)`; `ClaudeLogin(cli: InstalledCli)`; `ClaudeSignInFlow(cli: InstalledCli)`.
  - `ClaudeLogin.check()` returns `NOT_INSTALLED` / `TOO_OLD` from `cli.find()` before asking `auth status`.

- [ ] **Step 1: Write the failing tests:**
  - `test_llm_passes_the_found_cli_path`: fake `query` captures `options.cli_path == "/fake/claude"`.
  - `test_llm_raises_unavailable_when_missing` and `..._too_old`: `pytest.raises(ClaudeUnavailableError)`, `query` never called.
  - `test_login_check_not_installed` / `test_login_check_too_old`.
  - `test_sign_in_flow_without_cli_reports_install_hint`: `progress().error` names installing Claude Code (no "Reinstall What To Do").
  - Update existing tests to construct with a fake `InstalledCli` returning `READY`.
- [ ] **Step 2:** Run `uv run pytest tests/test_claude_sign_in.py tests/test_llm.py -q` — Expected: FAIL.
- [ ] **Step 3:** Implement as in Interfaces; the launcher warning prints the unavailable message when `check()` is `NOT_INSTALLED`/`TOO_OLD`.
- [ ] **Step 4:** Run `uv run pytest -q` — Expected: all PASS.
- [ ] **Step 5:** Commit `"Run the Claude Code the user installed; not installed and too old are states of their own"`

### Task 3: Refresh, re-tag and API carry the reason

**Files:**
- Modify: `src/where_to_go/refresh.py:78,95-101`, `src/where_to_go/retagging.py:155`, `src/where_to_go/api/app.py:107-113,644-648`
- Modify: `frontend/src/api/schema.d.ts` (regenerated)
- Test: `tests/test_refresh*.py` / `tests/test_retagging*.py` (where `claude_signed_out` is asserted today; `grep -rn claude_signed_out tests`), `tests/test_api*.py`

**Interfaces:**
- Consumes: `ClaudeNotReadyError`, `ClaudeUnavailableError.found`, new `ClaudeSignIn` states (Task 2).
- Produces:
  - `RefreshProgress.claude_unavailable: bool` (replaces `claude_signed_out`), description "Claude Code is missing, too old or signed out: nothing was read".
  - `ClaudeSignInView` adds `version: str | None`, `minimum: str`, `update_command: str | None`.
- [ ] **Step 1: Write the failing tests:** a refresh whose LLM raises `ClaudeUnavailableError` on every call ends with `claude_unavailable is True` and exactly one error line; same for re-tagging (one line); `GET /api/claude/sign-in` with a fake missing CLI answers `state == "not_installed"`, with too old answers `state == "too_old"`, `version`, `minimum == "2.1.321"`, `update_command`.
- [ ] **Step 2:** Run the touched test files — Expected: FAIL.
- [ ] **Step 3:** Implement; `claude_failed` and re-tag catch `ClaudeNotReadyError` and say it once. Regenerate types: `cd frontend && npm run api:types`.
- [ ] **Step 4:** Run `uv run pytest -q` — Expected: PASS.
- [ ] **Step 5:** Commit `"Refresh, re-tagging and the API say once that Claude Code is missing, too old or signed out"`

### Task 4: The install and update boxes

**Files:**
- Modify: `frontend/src/events/ClaudeSignIn.tsx`, `frontend/src/events/RefreshButton.tsx:10-27`, their CSS if needed
- Test: `frontend/src/events/RefreshButton.test.tsx`, new `frontend/src/events/ClaudeSignIn.test.tsx`

**Interfaces:**
- Consumes: `RefreshProgress.claude_unavailable`, `ClaudeSignInView` fields (Task 3).

- [ ] **Step 1: Write the failing tests:**
  - `not_installed`: heading "Install Claude Code to read the posts", both commands visible as code, each with a Copy button that writes the command to the clipboard; no Sign in button.
  - `too_old`: text contains `"2.1.200"` and `"2.1.321"`, shows `update_command` with Copy.
  - `signed_out`: today's sign-in box unchanged.
  - RefreshButton shows the box when `claude_unavailable` is true and hides the backend's matching error line.
- [ ] **Step 2:** Run `cd frontend && npx vitest run src/events` — Expected: FAIL.
- [ ] **Step 3:** Implement. Each command is its own code element with its own Copy button (no commands joined in one line). Reuse the existing note styles of the box.
- [ ] **Step 4:** Run `cd frontend && npm test && npm run lint && npx tsc -b` — Expected: PASS.
- [ ] **Step 5:** Commit `"Under Refresh: install and update boxes for Claude Code"`

### Task 5: Image without the CLI, CI, docs

**Files:**
- Modify: `macos/scripts/build-dmg.sh:60,107-108`, `macos/scripts/smoke-test-bundle.sh:22`
- Modify: `README.md` (Requirements, FAQ, line 7 "No API key..." keep, drop "needs nothing else" wording), `docs/macos-app.md` if it mentions the bundled CLI

- [ ] **Step 1:** `build-dmg.sh`: replace the `_bundled` check with `trash "$site_packages/claude_agent_sdk/_bundled"` and fail if it still exists; drop the comment on the CLI's own signature.
- [ ] **Step 2:** `smoke-test-bundle.sh`: fail if `_bundled` is inside the app; accept `"state":"(signed_in|signed_out|not_installed|too_old)"`.
- [ ] **Step 3:** Build: `macos/scripts/build-dmg.sh arm64` into a separate scratch output folder (never named like the real app's install place), run the smoke test on it — Expected: "Smoke test passed."; record image size before (256 MB) and after.
- [ ] **Step 4:** README and docs: install commands, FAQ "Refresh says to install Claude Code", Windows/Linux checkouts need Claude Code installed.
- [ ] **Step 5:** `uv run pytest tests/test_english_only.py -q` — PASS. Commit `"The disk image no longer carries the Claude CLI; smoke test and docs follow"`

### Task 6: Seen on screen, then release

- [ ] **Step 1:** Back up the real data folder to `~/Backups` (memory rule), make a copy of the data, run the built app from the scratch folder on that copy.
- [ ] **Step 2:** Refresh reads posts through `/opt/homebrew/bin/claude` — seen on screen in the built-in browser pane at the app's address.
- [ ] **Step 3:** Start the built app with `PATH` holding only a scratch folder and `HOME` pointing at a scratch home (so neither PATH nor `~/.local/bin` finds Max's `claude`; `/opt/homebrew/bin` still would, so for this check run it with a scratch folder containing a fake `claude` that prints `2.1.200 (Claude Code)` first on PATH for the too-old box). For the install box, use the unit-tested finder state via the API in a dev run with the same scratch PATH/HOME and an injected empty places list in a tiny scratch script. See both boxes on screen; Copy puts the command on the clipboard. No override ships in the app.
- [ ] **Step 4:** Remove the scratch build (`trash`). Full checks on the branch after merging fresh master: `uv run pytest -q`, `cd frontend && npm test && npm run lint`.
- [ ] **Step 5:** Merge to master by the project's way and cut the release with the `release` skill; release notes open with "Install Claude Code if you don't have it" and the new download size.
