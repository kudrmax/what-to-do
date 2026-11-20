# Photo Grid Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A card with several photos of its event shows them as a grid: the main photo large, up to four small.

**Architecture:** One pure class picks an event's photos from its posts; the resolver stores the list on the card
(`events.image_paths`), a migration fills it for existing cards; the API exposes `image_urls`; the card renders a grid.

**Tech Stack:** Python 3 / SQLModel / FastAPI, React + TypeScript (vitest).

**Spec:** `docs/superpowers/specs/2026-11-20-photo-grid-design.md`

## Global Constraints

- English only in code, UI, comments (tests/test_english_only.py).
- No "+N" on the grid; at most five photos on the card.
- A card with one photo looks exactly as today.

## Review Focus

- A post shared by several events (digest) gives only its mention's picture.
- Six frames of one video give one tile.
- The card's main photo is first even when its post is not the first mention.
- A database of 1.28 gets the list for every existing card on first start.
- A photo file that fails to load hides its tile, not the whole grid.

---

### Task 1: Photo list on the card

**Files:**
- Create: `src/where_to_go/card_photos.py`
- Modify: `src/where_to_go/models.py` (`EventCard.image_paths`, `EventPublic.image_urls`)
- Modify: `src/where_to_go/resolution.py`, `src/where_to_go/linking.py`, `src/where_to_go/repositories.py`
- Modify: `src/where_to_go/migrations.py` (`"events.image_paths"`)
- Modify: `src/where_to_go/phone_page/snapshot.py` (publish the grid's images)
- Test: `tests/test_card_photos.py`, `tests/test_resolution.py`, `tests/test_photo_list_migration.py`

**Interfaces:**
- Produces: `PostPictures(image_paths: list[str], image_index: int | None, shared: bool)`;
  `CardPhotos.pick(main: str | None, posts: list[PostPictures]) -> list[str]`;
  `EventResolver.resolve(card, mentions, shared_posts: frozenset[int] = frozenset())`;
  `MentionRepository.shared_posts(post_ids: Iterable[int]) -> frozenset[int]` (posts with 2+ mentions);
  API field `image_urls: list[str]` on events (main first; empty when there is no photo).

- [ ] Tests for `CardPhotos.pick`: single post gives all pictures; shared post gives only `image_paths[image_index]`
  (none when index is None); frames `x-f0..x-f5` give one (the main if among them, else `x-f0`); main first, no repeats;
  no main and no pictures gives `[]`.
- [ ] Implement `card_photos.py`; resolver sets `card.image_paths`; `LinkingService.refresh` passes shared posts.
- [ ] Migration test: a 1.28 database (column dropped) with a card over a single post of 3 pictures and a digest post
  gets `image_paths` filled on open.
- [ ] Migration builds `PostPictures` from raw rows (mentions joined to posts, ordered by `posts.published_at`) and
  writes JSON per event.
- [ ] `.venv/bin/pytest -q` green; regenerate `frontend/openapi.json` and `frontend/src/api/schema.d.ts` the way the
  project does; commit.

### Task 2: Grid on the card

**Files:**
- Create: `frontend/src/events/EventPhotoGrid.tsx`, `frontend/src/events/EventPhotoGrid.css`
- Modify: `frontend/src/events/EventCardView.tsx`, `frontend/src/phone/fixtures.ts` if fixtures need the field
- Test: `frontend/src/events/EventPhotoGrid.test.tsx`

**Interfaces:**
- Consumes: `event.image_urls`.
- Produces: `<EventPhotoGrid paths={string[]} className="card__photo" />`; one path renders `EventPhoto` as today.

- [ ] Tests: 1 path renders one photo as today; 5 and 7 paths render exactly 5 tiles with `data-count="5"`;
  no "+" text anywhere.
- [ ] Implement layouts per spec table with CSS grid keyed on `data-count`; large tile = `EventPhoto`, small tiles
  `object-fit: cover`; a broken small tile hides itself.
- [ ] `cd frontend && npm test` and build green; check on screen in the app on a copy of the data, light and dark,
  narrow and wide card, and on the phone page; commit.
