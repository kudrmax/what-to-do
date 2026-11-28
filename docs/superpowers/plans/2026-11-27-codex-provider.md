# Codex as a Second Reader Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Settings switch "Claude / Codex"; with Codex chosen, every post, photo and duplicate is read by the Codex the user installed, signed in with ChatGPT, with no tools and no disk access.

**Architecture:** A `codex_login.py` mirrors `claude_login.py` (finder via the generic `InstalledCli`, sign-in flow, the app's own Codex home with a locked-down `config.toml`, a runtime tool guard). `CodexJsonLlm` implements `JsonLlm` on one long-lived `AsyncCodex`. `ProviderJsonLlm` routes each call by the `llm_provider` setting. Refresh, re-tag, API and the box under Refresh talk about "the reader" with its name.

**Tech Stack:** Python 3.13, FastAPI, pydantic, `openai-codex` 0.172.0 SDK, claude-agent-sdk, pytest; React + TypeScript, vitest; bash.

**Spec:** `docs/superpowers/specs/2026-11-27-codex-provider-design.md`

## Global Constraints

- Default provider `claude`; existing settings keys `photo_model`, `extraction_model`, `matching_model` keep their meaning (Claude).
- Codex models: Luna `gpt-6-luna`, Terra `gpt-6.1-terra`, Sol `gpt-6.2-sol`, Astra `gpt-6.2-astra`. Efforts: `low`, `medium`, `high`.
- Codex minimum version `0.172.0`. Install commands: `curl -fsSL https://chatgpt.com/codex/install.sh | sh`, `brew install --cask codex`. Update: cask -> `brew upgrade --cask codex`, else `codex update`.
- Never pass `sandbox=` to the SDK; always `approval_mode=ApprovalMode.deny_all`; `base_instructions` = system text; images as `ImageInput(url="data:<mime>;base64,...")`; threads `ephemeral=True`, cwd an empty temp folder.
- The app's Codex home: `~/Library/Application Support/What To Do/codex` on macOS (platform user-data equivalent elsewhere), never inside the data folder; its `config.toml` holds exactly the spec's "No tools" flags, `features.memories = false`, and the `answer-only` permissions profile.
- Runtime tool guard: before the first call with a given codex (path + mtime), `codex debug prompt-input` with the app's home must show zero tools and no `<skills_instructions>`; otherwise refuse.
- Never touch `~/.codex`, Max's data folder or his installed programs; tests use the wheel's codex (`codex_cli_bin.bundled_codex_path()`) or fakes.
- English only (`tests/test_english_only.py`). Commit messages: no AI mention and no word "Claude" (a hook rejects them).

## Review Focus

- A new installed Codex exposes a tool: calls refused with the readable message, nothing sent -> test in Task 1.
- ChatGPT plan limit hit mid-refresh: one readable line "ChatGPT plan limit reached", not one per call -> test in Task 2/3.
- Switching provider in Settings while a refresh runs: the running calls finish on the provider they started with; the next call uses the new one -> test in Task 3.
- Codex app-server process dies mid-refresh: the next call starts a new one instead of failing forever -> test in Task 2.
- Images larger than a few MB go as data URLs without temp files -> test in Task 2.

---

### Task 1: Codex home, finder and tool guard

**Files:** Create `src/where_to_go/codex_login.py`; modify `pyproject.toml`/`uv.lock` (add `openai-codex==0.172.0`); test `tests/test_codex_home.py`.

**Interfaces — Produces:**
- `CODEX_MINIMUM = "0.172.0"`, `CODEX_INSTALL_COMMANDS: tuple[str, str]`.
- `codex_places(environ, home) -> list[Path]`, `codex_cli(environ=os.environ, home=None) -> InstalledCli` (name `"codex"`).
- `class CodexHome`: `__init__(self, folder: Path)`; `prepare(self) -> Path` writes `config.toml` (idempotent, overwrites drift) and returns the folder; `environ(self, base: Mapping[str,str]) -> dict[str,str]` adds `CODEX_HOME`; `default() -> CodexHome` (classmethod, platform folder).
- `class ToolGuard`: `__init__(self, home: CodexHome, run: Callable[[Path, Mapping[str,str]], str | None] | None = None)`; `check(self, codex: Path) -> str | None` returns `None` when safe, else the refusal message; cached by (resolved path, mtime_ns), thread-safe.

- [ ] Tests (offline, wheel codex): `test_config_turns_every_tool_off` (prompt-input via the wheel codex with the prepared home: zero tools, no `skills_instructions`); `test_sandbox_profile_reads_nothing_and_has_no_network` (`codex sandbox -P answer-only -- cat <tmp file outside cwd>` fails; `curl` absent? use `/usr/bin/python3 -c urllib` to a host -> fails; skip on non-macOS where `codex sandbox` differs); `test_guard_refuses_a_codex_that_offers_a_tool` (fake run output with one tool -> message); `test_guard_caches_by_file`; `test_home_never_inside_data_folder`; `test_codex_cli_places_and_update_command` (fake programs via `tests/helpers.fake_program`).
- [ ] RED, implement, GREEN (`uv run pytest -q tests/test_codex_home.py`), full suite, commit, push.

### Task 2: CodexJsonLlm and reader errors

**Files:** Create `src/where_to_go/codex_llm.py`; modify `src/where_to_go/llm.py`; test `tests/test_codex_llm.py`.

**Interfaces:**
- Consumes Task 1.
- Produces in `llm.py`: rename `ClaudeNotReadyError` -> `ReaderNotReadyError` (keep the Claude subclasses, update every import); `CodexSignedOutError(ReaderNotReadyError)`, `CodexUnavailableError(ReaderNotReadyError)` (with `found`), `CodexRefusedError(ReaderNotReadyError)` (tool guard), `PlanLimitError(ReaderNotReadyError)` ("ChatGPT plan limit reached" + reset time when given).
- `class CodexJsonLlm`: `__init__(self, model: Callable[[], str], effort: Callable[[], str], runtime: CodexRuntime)`; `complete_json(...)` per `JsonLlm`.
- `class CodexRuntime`: owns one lazily started `AsyncCodex(CodexConfig(codex_bin=..., env=home.environ(...)))`, restarts it after the process died, `close()` on app shutdown; checks `codex_cli().find()` and `ToolGuard.check` (both via `asyncio.to_thread`) before each call.
- [ ] Tests with a fake runtime/SDK double recording the arguments: no `sandbox` argument ever; `approval_mode is ApprovalMode.deny_all`; `base_instructions == system`; `output_schema`, `model`, `effort` per turn; images arrive as data URLs in order after their captions; `unauthorized` -> `CodexSignedOutError`; `usageLimitExceeded` -> `PlanLimitError`; guard refusal -> `CodexRefusedError` with no SDK call; missing/too old -> `CodexUnavailableError`; a dead app-server is replaced on the next call.
- [ ] RED, implement against the real SDK API (read `openai_codex` source in `.venv`), GREEN, full suite, commit, push.

### Task 3: Provider setting, routing, refresh and re-tag

**Files:** Modify `src/where_to_go/settings.py`, `container.py`, `refresh.py:78-101`, `retagging.py:155`, `launcher/cli.py` warning, `scripts/model_compare.py` (provider/model/effort args); tests `tests/test_provider.py` + touched tests.

**Interfaces:**
- `LlmProvider(StrEnum)`: `CLAUDE="claude"`, `CODEX="codex"`; `CodexModel`, `CodexEffort` enums with the Global Constraints values.
- `AppSettings`: `llm_provider` (default claude), `codex_photo_model`/`_effort`, `codex_extraction_model`/`_effort`, `codex_matching_model`/`_effort` (defaults chosen by the comparison: photos Terra/low, extraction Terra/medium, matching Luna/low).
- `class ProviderJsonLlm(JsonLlm)`: `__init__(self, provider: Callable[[], LlmProvider], claude: JsonLlm, codex: JsonLlm)` — reads the provider once per call.
- `Container`: `codex: InstalledCli`, `codex_runtime: CodexRuntime`, three `ProviderJsonLlm`; closes the runtime on shutdown.
- `RefreshProgress.reader_unavailable: bool` + `reader: LlmProvider | None` replace `claude_unavailable`; one line per refresh for any `ReaderNotReadyError` (plan limit included).
- [ ] Tests: routing per provider and switching between calls; refresh and re-tag say a Codex sign-out / limit once; settings defaults and validation; launcher warns for the active provider; model_compare accepts `--provider codex --model gpt-6.1-terra --effort low`.
- [ ] RED, implement, GREEN, full suite, `cd frontend && npm run api:types && npx tsc -b` (fix renamed field usages minimally), commit, push.

### Task 4: Codex sign-in and API

**Files:** `codex_login.py` (`CodexLogin`, `CodexSignInFlow`), `api/app.py` (`GET/POST /codex/sign-in`, same view model as Claude's), regenerated types; tests `tests/test_codex_sign_in.py`.

- `CodexLogin(cli, runtime).state() -> view fields` (not_installed / too_old / signed_in / signed_out / unknown); `CodexSignInFlow(runtime)`: `start()` calls `login_chatgpt()`, opens `auth_url` with `webbrowser.open`, keeps it as `page_url`, waits in the background; `progress()`; `stop()` cancels.
- [ ] Tests with a fake runtime: states, start/progress/stop, a second press does not start a second login, API answers.
- [ ] RED, implement, GREEN, types, commit, push.

### Task 5: Settings switch and the reader box

**Files:** `frontend/src/screens/SettingsScreen.tsx` (ModelsSubsection), `frontend/src/events/ClaudeSignIn.tsx` -> `ReaderSignIn.tsx` (+ test), `RefreshButton.tsx`, `api/queries.ts`.

- Switch "Reads posts with" with two chips; with Codex: per step one row of model chips (Luna, Terra, Sol, Astra) and a "Thinking" row (Low, Medium, High); with Claude: today's rows. Title and hints name the provider ("Claude models" / "Codex models", "your Claude plan" / "your ChatGPT plan"). No facts joined in one line by separators.
- Box under Refresh shows the active reader: install commands, update command, sign-in button ("Sign in to ChatGPT" for Codex), plan-limit and tool-refusal messages as their own states.
- General texts naming Claude in Settings name the active provider.
- [ ] Tests for both providers' rows, switching, each box state per reader; `npm test && npm run lint && npx tsc -b`; commit, push.

### Task 6: Image, smoke test, docs

- `build-dmg.sh` trashes `codex_cli_bin`'s binaries and fails if any remain; `smoke-test-bundle.sh` checks absence via the bundle's Python and accepts `/api/codex/sign-in` states; `scripts/smoke_test.py` accepts them too. README: Codex option, install commands, FAQ "Refresh says to install Codex"; docs/development.md.
- [ ] Build arm64 locally, smoke test, image size before/after, commit, push; CI green on all jobs (Windows included).

### Task 7: Live checks with Max's Codex (needs Max)

- [ ] Ask Max to run `brew install --cask codex`, then sign in to ChatGPT from the app box in a scratch run on a copy of the data.
- [ ] Live trap through `CodexJsonLlm`: a post asking to read a planted file in a scratch folder; the answer must not contain it; the turn has no `commandExecution`/`fileChange`.

### Task 8: Model comparison and defaults (needs Max's sign-in)

- [ ] On a copy of the data, ~30 posts per the spec; baseline Claude settings; variants per the spec; record limit share per variant (`account/rateLimits/read`).
- [ ] Publish the side-by-side comparison as a page for Max; set the defaults from the result; commit.

### Task 9: On screen, merge, release

- [ ] Built app on a copy of the data: switch to Codex, refresh reads posts, switch back to Claude; each box state seen on screen.
- [ ] Merge, release with the `release` skill.
