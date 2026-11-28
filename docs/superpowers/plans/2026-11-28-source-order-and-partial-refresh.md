# Source Order and Partial Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The user orders sources; the reader reads posts in that order; a "Refresh N" button reads only the next N unread posts.

**Architecture:** `Source.position` per city with a reorder API mirroring tags; `PostRepository.to_read` orders by source position then newest first; refresh takes an optional post limit applied after collecting.

**Tech Stack:** Python 3.13, FastAPI, SQLModel, pytest; React + TypeScript, vitest.

**Spec:** `docs/superpowers/specs/2026-11-28-source-order-and-partial-refresh-design.md`

## Global Constraints

- Never read or copy Max's real data folder (`~/Library/Application Support/where-to-go`); checks use the dev copy's `./data` or test fixtures.
- Collecting is unchanged: every unpaused source is downloaded on every refresh.
- Inside a source: newest post first. New sources go last. Existing sources: favourites first, then by title.
- `partial_refresh_posts` default 30, range 1..500.
- English only; commit messages without AI mention and without the word "Claude".
- UI: no several facts in one line joined by separators; follow the tags drag pattern and styles.

## Review Focus

- A city with sources added before the migration: positions are dense and unique per city -> test in Task 1.
- Reorder request missing an id or with another city's id: 422, nothing changes -> test in Task 1.
- Limit larger than unread posts: reads all, `posts_left` 0 -> test in Task 3.
- Linked posts (fetched from links during the refresh) count toward the limit in order of their own source -> test in Task 3.
- A refresh with a limit while photos fail: the dropped post still counts; next press continues after it -> test in Task 3.

---

## Release 1

### Task 1: Source position, order API, reading order (backend)

**Files:** `src/where_to_go/models.py` (SourceBase.position), `src/where_to_go/db.py`/migrations (column + backfill), `src/where_to_go/repositories.py` (`SourceRepository.in_city` by position, `add` appends last, `reorder(city_id, ids)`, `PostRepository.to_read` ordering), `src/where_to_go/api/app.py` (`PUT /sources/order`), photo order in `refresh.py`; tests `tests/test_source_order.py`.

- `position: int` default 0 on sources; backfill per city: favourites first then title, positions 0..n-1.
- `PUT /sources/order` body `{ids: list[int]}` -> list of SourcePublic in the new order; 422 unless exactly the active city's ids.
- `to_read` result sorted by (source position, published_at desc); `PhotoTranscriber.untranscribed` keeps the given post order; photo batches and post batches built from that order.
- [ ] Tests first (migration backfill, append-last, reorder ok/422, to_read order across two sources and within a source, photo order), implement, `uv run pytest -q`, regenerate API types (`cd frontend && npm run api:types && npx tsc -b`), commit, push.

### Task 2: Drag to reorder on the Sources screen

**Files:** `frontend/src/screens/SourcesScreen.tsx` (SourceList), queries (`useReorderSources`), CSS; tests.

- Rows draggable like tags in Settings (reuse the tags drag logic/component if it can be shared without changing tags' behaviour); order saved on drop; favourite star stays but no longer sorts.
- [ ] Tests (render in API order, drag moves and calls the API with the new ids, favourites not moved), `npm test && npm run lint && npx tsc -b`, commit, push.

### Task 3a: Release 1 check and release

- [ ] Build, run the built app on the dev data, drag sources on screen, run a refresh, confirm read order from the DB (`posts.processed_at` order by source), CI green, merge, release.

## Release 2

### Task 3: Partial refresh (backend)

**Files:** `settings.py` (`partial_refresh_posts`), `refresh.py` (`start(limit: int | None)`, slicing after linked posts, photos only of chosen posts, `RefreshProgress.posts_left: int | None`), `api/app.py` (`POST /refresh` body `{limit?: int}`); tests.

- [ ] Tests (limit slices in order, photos only for chosen posts, posts_left, limit > unread, linked posts in order, failed photos count), implement, types, commit, push.

### Task 4: Refresh N button and setting

**Files:** `frontend/src/events/RefreshButton.tsx` (+css, test), SettingsScreen (number row next to "Recent posts per channel").

- Second button "Refresh 30" beside Refresh (secondary style), tooltip; after a limited refresh a status line "N posts left to read"; both disabled while running.
- [ ] Tests, `npm test && npm run lint && npx tsc -b`, commit, push.

### Task 5: Release 2 check and release

- [ ] Build, dev data on screen: Refresh 30 reads 30 posts, line shows posts left, second press continues; CI green, merge, release.
