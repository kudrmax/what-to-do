# Codex as a second reader

## Why

The app reads posts, photos and duplicates through Claude only. Max also pays for ChatGPT Plus and wants the app to run
on Codex with that subscription, switched in Settings. No API key either way: both run on the user's own login.

## What Max decided

- Settings get a switch "Claude / Codex". **Claude is the default**; nothing changes for anyone who never touches it.
- The switch lives in Settings only. No first-run screen, no onboarding choice.
- **Approach 1:** each provider keeps its own models for the three steps (photo reading, post and page reading,
  duplicate merging). Switching back and forth loses nothing.
- Codex models are the standard ones of the ChatGPT Plus plan; the defaults are chosen by a comparison on a copy of the
  data, low against medium reasoning, as was done for Haiku against Sonnet.
- When a login or an install is needed, Max is told and does it.

## Goals

- Every call the app makes today (`JsonLlm.complete_json`: system text, prompt, JSON schema, images) works on Codex.
- The switch takes effect from the next call, like a model change today.
- Signing in to ChatGPT from the app, the way signing in to Claude works today: a button, the browser page, done.
- The built app bundles Codex the way it bundles the Claude CLI: the user installs nothing.

## Non-goals

- Mixing providers per step (approach 3, rejected).
- API-key login for either provider.
- Changing prompts per provider. The same prompts go to both.

## Anti-goals

- Codex touching anything on the computer. It is an agent with shell tools; here it must only answer.
- Max's Claude model choices reset by trying Codex.
- A refresh on Codex silently burning the five-hour Plus limit with no way to see why it stopped.

## Facts found (2026-11-27)

- Official Python SDK: PyPI `openai-codex` (Python >= 3.10, the app needs 3.13), import `openai_codex`. It installs
  its matching runtime `openai-codex-cli-bin` itself. https://github.com/openai/codex/tree/main/sdk/python
- Per turn: `output_schema`, `model`, `effort`; images as `LocalImageInput(path)` or `ImageInput(url)` with a base64
  `data:` URL. Threads: `sandbox=Sandbox.read_only`, `ephemeral=True`. No documented switch that removes tools.
- Login: `codex.login_chatgpt()` gives `auth_url` and `wait()`; `codex.account()` tells whether someone is signed in;
  credentials in `~/.codex/auth.json` or the OS keychain.
- Models with ChatGPT sign-in: `gpt-6.2-astra`, `gpt-6.2-sol`, `gpt-6-astra`, `gpt-6.1-sol`, `gpt-6.1-terra`,
  `gpt-6-luna`. Effort: low, medium, high, xhigh (and more above that). https://developers.openai.com/codex/models
- Plus limits per five hours (local messages): Astra 6-50, Sol 17-180, Terra 35-285, Luna 350-3000; weekly limits may
  apply. https://developers.openai.com/codex/pricing

## Design

### Backend

- `LlmProvider` enum: `claude`, `codex`. Setting `llm_provider`, default `claude`.
- Codex settings, one model and one effort per step: `codex_photo_model`, `codex_photo_effort`,
  `codex_extraction_model`, `codex_extraction_effort`, `codex_matching_model`, `codex_matching_effort`. The existing
  `photo_model`, `extraction_model`, `matching_model` stay as the Claude choices (no migration, no rename of stored keys).
- `CodexModel` enum offered in Settings: Luna, Terra, Sol (`gpt-6.1-sol` or `gpt-6.2-sol`, builder checks which the
  plan offers), Astra. `CodexEffort`: low, medium, high.
- `CodexJsonLlm` next to `ClaudeJsonLlm`, same `JsonLlm` protocol: one ephemeral, read-only thread per call in an empty
  temporary working folder, no approvals, system text as the thread's instructions (prepended to the prompt if the SDK
  has no such option), images as local image inputs, `output_schema` from the call. Signed-out answers raise a
  provider-neutral `SignedOutError` (today's `ClaudeSignedOutError` generalised).
- `ProviderJsonLlm`: what the container wires for each step. Reads `llm_provider` on every call and hands the call to
  the Claude or the Codex reader of that step. The three steps keep their own model lambdas.
- Sign-in: `CodexLogin` (signed in / signed out / unknown via `account()`) and `CodexSignInFlow` (starts
  `login_chatgpt()`, opens `auth_url` in the browser, keeps it for "open by hand", waits). API mirrors today's:
  `GET/POST /codex/sign-in`. The refresh error and the sign-in box follow the active provider.

### Interface

Settings, section with models today ("Claude models"):

```
Reads posts with        [ Claude ] [ Codex ]
                        hint: which subscription reads posts; the other one keeps its models

Photo reading           [Luna] [Terra] [Sol] [Astra]
                        Thinking [Low] [Medium] [High]
Post and page reading   same
Duplicate merging       same
```

- With Claude chosen the rows show today's Haiku / Sonnet / Opus chips, no thinking row.
- The subsection title and hints name the chosen provider ("Codex models", "your ChatGPT plan").
- Texts that describe the reader in general ("Claude marks the events...", "Claude prompts", re-tag counts) name the
  chosen provider; the builder lists every such text and changes it.
- The sign-in box near Refresh asks for ChatGPT when Codex is chosen, for Claude otherwise.

### Bundle

`build-dmg.sh` checks for and keeps the Codex runtime from `openai-codex-cli-bin` as it does for the Claude CLI,
including its signature. The disk image grows by the size of that binary.

### Choosing the Codex defaults

On a copy of the real data (never the real data folder), with `scripts/model_compare.py` extended to take a provider,
a model and an effort:

1. Pick about 30 stored posts: digests, posters with text in the photo, a table or collage, and posts that are known
   duplicates of each other.
2. Baseline: today's Claude settings.
3. Variants: photo and post reading on Terra and Sol, each low and medium; merging on Luna and Terra, low and medium.
4. Compare with the baseline: events missed or invented, wrong dates or times, misread photo text, wrong merges, calls
   made, time taken.
5. Show Max the differences on the same posts side by side; the cheapest variant with no worse results becomes the
   default. Plus limits count: a refresh makes tens of calls, so Sol for every post may hit the five-hour limit.

The comparison spends Max's Codex limit (a few hundred messages at most); it runs only after he signs in.

## Calls made while writing this (Max checks them)

- **Codex gets no tools, proven first.** Posts are strangers' text and cards leave the computer through the phone
  page, so a post must not be able to make Codex read a file. A read-only sandbox still lets it read files. The first
  task finds and proves, on the installed SDK, a way to turn the shell and every other tool off (Codex config in the
  app's own home, e.g. feature flags or `approval_policy`), with a test where a prompt asks to read a file and the
  answer does not contain it. No such way: work stops and Max decides before anything else is built.
- **The app has its own Codex home** (`CODEX_HOME` in the app's data folder), like `setting_sources=[]` for Claude:
  Max's own Codex config, MCP servers and AGENTS.md never reach the app's calls, and that home's config is where tools
  are turned off. Cost: signing in to ChatGPT once more, from the app.
- **The release waits for the comparison.** Defaults ship already chosen; no interim defaults, no second release to
  change them.
- **Intel builds keep working:** `openai-codex-cli-bin` 0.172.0 has wheels for macOS arm64 and x86_64.

## Left to the builder

- Exact SDK calls (async API, how the system text is passed, what `account()` returns when signed out), checked
  against the installed SDK.
- How Codex reports a hit usage limit, and turning that into a readable refresh error.
- Which texts name the provider, as listed above.

## Release

A merge ships with a release (CLAUDE.md). Before master: the switch, both sign-ins and a refresh on each provider seen
on screen in the built app, on a copy of the data.
