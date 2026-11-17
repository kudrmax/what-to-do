# Collections Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Personal collections of events: a heart on each card adds it to collections set up in Advanced settings; a Collections screen shows one collection as the usual feed.

**Architecture:** A `collections` table and a `collection_ids` JSON column on events (like `source_ids`). The feed gets a `collection` filter; merge unions the ids next to the marks. The frontend adds a heart popover, a settings block and a screen built from `DayFeed` + `FilterBar`.

**Tech Stack:** FastAPI + SQLModel (SQLite), React + TanStack Query, openapi-typescript.

**Spec:** `docs/superpowers/specs/2026-11-17-collections-design.md`

## Global Constraints

- English UI, code and docs (tests/test_english_only.py).
- `collections_enabled` defaults to `false`; off hides every collections control, data stays.
- The phone page (read-only) shows no heart and no screen.

## Review Focus

- An existing database gets `events.collection_ids` with `'[]'` for old rows (server default).
- Deleting a collection removes its id from every event.
- A collected event whose only sources are paused stays shown; a collected card keeps its digest line (it counts as marked).
- A collected event with a hidden tag still shows in its collection.
- Merging two cards keeps the union of their collections.

---

### Task 1: Backend

**Files:** `src/where_to_go/models.py`, `settings.py`, `repositories.py`, `container.py`, `feed.py`, `linking.py`, `api/app.py`; tests in `tests/test_collections.py`, `tests/test_feed.py`.

**Produces:**
- `Collection(id, name unique, position)`, `CollectionBase{name}`, `CollectionPublic{id, name, size}`, `EventCollections{collection_ids: list[int]}`.
- `EventCard.collection_ids: list[int]` (server default `'[]'`), `EventCard.is_kept` = interest, plan or a collection.
- `AppSettings.collections_enabled: bool = False`.
- `CollectionRepository.listed() / add(name) / rename(id, name) / delete(id)`; `EventRepository.set_collections(id, ids)`.
- `FeedFilter.collection: int | None`; `GET /events?collection=` starts at the earliest event when no start is given.
- `GET/POST /collections`, `PATCH/DELETE /collections/{id}`, `PUT /events/{id}/collections` (unknown id → 422).

- [ ] Tests: feed filter by collection (+ hidden tag still shown), merge union, delete strips ids, API round trip, paused-only collected event shown.
- [ ] Implement, `pytest -q` green, commit.

### Task 2: Frontend

**Files:** `frontend/src/api/queries.ts`, `schema.d.ts` (`npm run api:types`), `ui/Icon.tsx` (heart), `events/CollectionButton.tsx/.css`, `EventCardView.tsx/.css`, `EventWindow.tsx`, `screens/SettingsScreen.tsx` (CollectionsSubsection), `screens/CollectionsScreen.tsx`, `app/routes.ts`, `app/AppShell.tsx`, `App.tsx`.

- [ ] Heart: top-right corner of the card; on the photo in a translucent circle, otherwise the meta row leaves room. Filled when in any collection. Popover of collections with check marks.
- [ ] Settings → Advanced: switch + list (add, rename, delete with confirm for non-empty).
- [ ] Sidebar item + screen: collection picker (segmented when >1), FilterBar, DayFeed newest first, all dates.
- [ ] Tests (vitest): heart hidden when off; toggling calls PUT; menu item appears only when on with a collection.
- [ ] `npm test`, `npm run lint`, `npm run build`, commit.

### Task 3: Check on screen with a data copy, merge, release.
