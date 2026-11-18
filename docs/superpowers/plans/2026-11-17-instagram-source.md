# Instagram Source Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Public Instagram profiles become a third kind of source: their posts and pinned stories (with video frames) are read anonymously and go through the existing pipeline.

**Architecture:** A new `SourceType` (`InstagramSourceType`) next to Telegram and websites. `instagram.py` parses the logged-out HTML of the profile, post and highlight pages; `InstagramReader` decides what is new and fetches through one shared rate limiter; `VideoFrames` turns a video into a few distinct JPEG frames stored as post images. The refresh, photo transcription, reading and merging stay shared.

**Tech Stack:** Python 3.13, httpx, selectolax-free JSON parsing (`json` + `re`), SQLModel/SQLite, PyAV for frames, FastAPI, React + TypeScript (vitest).

**Spec:** `docs/superpowers/specs/2026-11-17-instagram-source-design.md`

## Global Constraints

- No Instagram login, cookie or session anywhere: requests carry only the browser-like headers listed in the spec; the shared `httpx.AsyncClient` must not keep Instagram cookies between requests (send each Instagram request with a fresh cookie jar, e.g. `cookies=httpx.Cookies()` on a dedicated client with `cookies` disabled).
- Interface, messages, code comments and docs in English (tests/test_english_only.py).
- Stories older than 30 days when first seen are stored as skipped and never reach Claude.
- One shared pause of about 1 s between requests to `www.instagram.com` across all Instagram sources of a refresh; CDN media is not limited.
- At most 6 frames per video, a frame every 2 s plus the first, near-duplicates dropped.
- Do not change `prompts.EXTRACTION`: it changes the reading-rules fingerprint and re-reads every channel.
- PyAV pinned to a version with macOS x86_64 and arm64 wheels (19.x); guard test like `tests/test_intel_mac_wheels.py`.
- UI: no facts joined by dots, slashes or commas in one line; each fact its own element (Max's rule).
- Backend tests: `uv run pytest`; frontend: `cd frontend && npm test && npm run lint && npx tsc -b`; full: `make test`.

## Review Focus

1. A profile page that answers 200 but without the data (login wall) must be a refusal, not "0 new posts" — test in Task 4.
2. A story present in two highlights must be stored once — test in Task 4.
3. `@eje.belgrade` must go to Instagram with no picker, `eje.belgrade` to the website check, `@londonevents` must need a picked kind — tests in Task 2 and Task 8.
4. A video that fails to download or decode leaves the post with its cover and no source error — test in Task 5.
5. Turning **Pinned stories** off must stop both collecting and re-reading stories, keeping their cards — tests in Task 6.

---

### Task 1: Parse Instagram pages

**Files:**
- Create: `src/where_to_go/instagram.py`
- Create: `tests/fixtures/instagram/profile.html`, `post_carousel.html`, `reel.html`, `highlight_timetable.html`, `highlight_food.html`, `stories_active.html`, `login_wall.html` (copy the anonymous pages fetched during scouting from the scratchpad `ig/` folder: `page2.html`, `post.html`, `reel.html`, `hl/timetable.html`, `hl/food.html`, `hl/active.html`; `login_wall.html` = `page.html`, the 537 KB page fetched without `Sec-Fetch-*` headers, which has no profile data)
- Test: `tests/test_instagram.py`

**Interfaces:**
- Produces:
  - `InstagramUrls.profile(name) -> str` = `https://www.instagram.com/<name>/`; `.post(code)` = `https://www.instagram.com/p/<code>/`; `.highlight(id)` = `https://www.instagram.com/stories/highlights/<id>/`; `.is_story(url) -> bool`.
  - `InstagramName.parse(link: str) -> str` (lower-case name; raises `SourceError("This doesn't look like a link to an Instagram profile")`), `InstagramName.is_link(link) -> bool` (`instagram.com/<name>` with or without scheme, `www.`, trailing slash, query; `/p/…`, `/reel/…`, `/stories/…` are not profiles).
  - `ProfileSummary(title: str, posts: list[PostSummary], highlights: list[Highlight])`; `PostSummary(pk: int, code: str, caption: str, image_url: str | None, is_video: bool, day: date | None)`; `Highlight(id: str, title: str)`.
  - `PostDetails(pk, code, published_at: datetime, caption: str, image_urls: list[str], video_urls: list[str], place: str | None)`.
  - `Story(pk: int, published_at: datetime, image_url: str | None, video_url: str | None)`.
  - `InstagramPage(html).profile() -> ProfileSummary | None` (None when the data is missing), `.post() -> PostDetails | None`, `.stories() -> list[Story]`, `.anonymous() -> bool` (`"USER_ID":"0"`).
  - Video URL choice: the smallest `video_versions` rendition with width ≥ 480, else the largest.

- [ ] **Step 1: Copy the fixtures** into `tests/fixtures/instagram/` and check `grep -c '"USER_ID":"0"'` is ≥1 in each and no `ds_user_id` cookie value appears.
- [ ] **Step 2: Write the failing tests**

```python
def test_profile_lists_twelve_posts_with_full_captions(): # profile.html
    p = InstagramPage(read("profile.html")).profile()
    assert p.title == "Esthetic Joys Embassy / EJE"
    assert len(p.posts) == 12
    first = next(x for x in p.posts if x.code == "DfXPH9KN62V")
    assert first.caption.startswith("November schedule is here")
    assert first.day == date(2026, 11, 5)
    assert [h.title for h in p.highlights] == ["timetable", "food", "breakfast", "full menu", "press", "drinks", "NY 2026"]
    assert p.highlights[0].id == "18107063872994570"

def test_page_without_data_is_not_a_profile(): # login_wall.html
    assert InstagramPage(read("login_wall.html")).profile() is None

def test_post_page_gives_time_carousel_and_place(): # post_carousel.html, code DfmlSc4DQL_
    d = InstagramPage(read("post_carousel.html")).post()
    assert d.published_at == datetime.fromtimestamp(1794403493, UTC)
    assert len(d.image_urls) == 2 and d.place == "EJE Belgrade" and d.video_urls == []

def test_reel_page_gives_video(): # reel.html
    assert len(InstagramPage(read("reel.html")).post().video_urls) == 1

def test_highlight_gives_every_story():
    assert len(InstagramPage(read("highlight_food.html")).stories()) == 23
    [story] = InstagramPage(read("highlight_timetable.html")).stories()
    assert story.video_url and story.image_url

def test_active_stories_page_has_none():
    assert InstagramPage(read("stories_active.html")).stories() == []

@pytest.mark.parametrize("link", ["instagram.com/eje.belgrade", "https://www.instagram.com/eje.belgrade/?hl=en", "@eje.belgrade"])
def test_name_from_link(link): assert InstagramName.parse(link) == "eje.belgrade"
```

- [ ] **Step 3: Run** `uv run pytest tests/test_instagram.py -v` → FAIL (module missing).
- [ ] **Step 4: Implement `instagram.py`.** Read every `<script type="application/json">` block, `json.loads` it, walk for the keys named in the spec (`polaris_ordered_timeline_connection`, `lox_highlights_connection`, `items` with `taken_at`, the post node with `taken_at` and `carousel_media`). Day from `accessibility_caption` ("on November 05, 2026"). Times are UTC from epoch.
- [ ] **Step 5: Run** → PASS. **Step 6: Commit** `Parse public Instagram pages`.

### Task 2: Tell Telegram, Instagram and websites apart

**Files:**
- Modify: `src/where_to_go/telegram.py` (`SourceLink`), `src/where_to_go/source_types.py` (`SourceTypes.for_link`), `src/where_to_go/sources.py` (`SourceCatalog.preview/add`)
- Test: `tests/test_telegram.py`, `tests/test_instagram.py`

**Interfaces:**
- Produces: `SourceLink.kind_of(link: str) -> SourceKind | None` — `None` means "a name valid for both, the user must pick"; `class AmbiguousNameError(SourceError)` with message "Pick whether this is a Telegram channel or an Instagram profile"; `SourceTypes.for_link(link, kind: SourceKind | None = None) -> SourceType`; `SourceCatalog.preview(city, link, title=None, kind=None)`, `SourceCatalog.add(city, link, title, kind=None, reading: InstagramReading | None = None)`.
- Rules: t.me/telegram.me link → TELEGRAM; instagram.com link → INSTAGRAM; `@` + name with a dot, no slash → INSTAGRAM; `@name`/`name` matching the Telegram handle regex → `None` unless `kind` given; anything else → WEB.

- [ ] **Step 1: Failing tests** — `kind_of("t.me/x_events") == TELEGRAM`, `kind_of("instagram.com/eje.belgrade") == INSTAGRAM`, `kind_of("@eje.belgrade") == INSTAGRAM`, `kind_of("eje.belgrade") == WEB`, `kind_of("@londonevents") is None`, `kind_of("londonevents") is None`; `SourceTypes.for_link("@londonevents")` raises `AmbiguousNameError`; `for_link("@londonevents", SourceKind.TELEGRAM).kind == TELEGRAM`.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** Update existing tests that added a bare `@name` Telegram channel to pass `kind=SourceKind.TELEGRAM` (search `tests/` for `catalog.add(` and `/sources` posts with bare names). PotentialSources.adopt passes `SourceKind.TELEGRAM`.
- [ ] **Step 4: Run** `uv run pytest` → all PASS. **Step 5: Commit** `Ask which network a bare name is`.

### Task 3: Store Instagram sources and skipped stories

**Files:**
- Modify: `src/where_to_go/models.py`, `src/where_to_go/repositories.py`
- Test: `tests/test_instagram_storage.py`, `tests/test_migration.py` (a database from before gets the new table)

**Interfaces:**
- Produces:
  - `SourceKind.INSTAGRAM = "instagram"`; `SourcePublic.url` for it = `InstagramUrls.profile(handle)`.
  - `class InstagramReading(SQLModel)`: `posts: bool = True`, `stories: bool = True`.
  - `class InstagramProfile(SQLModel, table=True)`, table `instagram_profiles`: `source_id` (PK, FK sources, CASCADE), `posts: bool`, `stories: bool`.
  - `InstagramRepository(db)`: `.add(source_id, reading)`, `.reading(source_id) -> InstagramReading`, `.change(source_id, reading) -> InstagramReading`, `.readings(source_ids) -> dict[int, InstagramReading]`.
  - `CollectedPost` gains `video_urls: list[str] = []` and `read: bool = True` (False = store as skipped).
  - `PostRepository.SKIPPED = "skipped"`; `add_new` stores a `read=False` post with `processed_at=now`, `read_with=SKIPPED`.

- [ ] **Step 1: Failing tests** — add/read/change of `InstagramReading`; deleting the source deletes its row; `add_new(..., CollectedPost(read=False, ...))` → post in `known_ids`, not in `unprocessed`, `read_with == "skipped"`; old database file opens and has `instagram_profiles`.
- [ ] **Step 2–4:** run → FAIL, implement, run → PASS. **Step 5: Commit** `Store Instagram sources`.

### Task 4: Read a profile: what is new, one request at a time

**Files:**
- Create: `src/where_to_go/instagram_reader.py`
- Modify: `src/where_to_go/source_types.py` (add `InstagramSourceType`), `src/where_to_go/web_sources.py` (`SitePreview` gains `highlights: int = 0`), `src/where_to_go/container.py`
- Test: `tests/test_instagram_reader.py` (respx)

**Interfaces:**
- Consumes: Task 1 parsers, Task 3 storage.
- Produces:
  - `InstagramRequests(client, pause: float = 1.0, sleep=asyncio.sleep, clock=time.monotonic)`: `async page(url) -> InstagramPage` — one `asyncio.Lock` shared by all sources, waits so requests start ≥ `pause` apart; sends `HEADERS` (the browser-like headers of the spec) with no cookies; non-200, redirect, network error → `InstagramRefused`; logs status, headers and the first 2 KB of a refused answer at WARNING.
  - `class InstagramRefused(SourceError)`, message "Instagram refused to show the profile; will try again on the next refresh". `profile()` is `None` on a 200 page → `InstagramRefused` too, unless the page says the profile doesn't exist (404 → `SourceError("This Instagram profile doesn't exist")`) or is private (page data `is_private: true` → `SourceError("This Instagram profile is private")`).
  - `InstagramReader(requests).title(name) -> tuple[str, int]` (title, number of highlights); `.collect(name, known: set[int], reading: InstagramReading, now: datetime) -> list[CollectedPost]`.
  - `InstagramSourceType(reader, posts: PostRepository, profiles: InstagramRepository)`; `kind = INSTAGRAM`, `already_added = "This profile is already added"`; `preview` → `SitePreview(kind, title, handle, highlights=n)`; `attach(source, city, link, reading)` stores the reading; `collect` uses `profiles.reading(source.id)`. (`SourceType.attach` gains `reading: InstagramReading | None = None`, ignored by the other types.)
- Collect rules (from the spec): posts on → for each `PostSummary` not in `known`, fetch the post page; `CollectedPost(external_id=pk, url=InstagramUrls.post(code), published_at=details.published_at, text=caption + ("\n\nPlace: " + place if place), image_urls=details.image_urls, video_urls=details.video_urls)`; if the post page is refused or has no data, fall back to the summary (its image, `published_at` = day at 12:00 UTC). Stories on → every highlight page; stories deduped by `pk`, skipping `known`; `text = f"Pinned story from the highlight «{title}»"`, `url = InstagramUrls.highlight(id)`, `read = now - published_at <= timedelta(days=30)`. Result sorted oldest first.

- [ ] **Step 1: Failing tests** (respx routes serving the fixtures):
  - first collect with both on → 12 posts read; stories: only those ≤30 days old have `read=True`, the rest `read=False`; post page requested only for unknown posts (assert route call counts).
  - second collect with all `known` → `[]` and zero post-page requests.
  - a story `pk` served in two highlights → one `CollectedPost`.
  - `stories=False` → no highlight requests; `posts=False` → no post-page requests and no posts.
  - profile answer 429 → `InstagramRefused`; `login_wall.html` with 200 → `InstagramRefused`.
  - two sources collected concurrently with a fake clock: request start times are ≥1 s apart.
  - no request carries a `cookie` header (respx side effect asserts it).
- [ ] **Step 2–4:** run → FAIL, implement, wire `InstagramSourceType` into `SourceTypes` in `container.py`, run → PASS. **Step 5: Commit** `Read Instagram profiles anonymously`.

### Task 5: Video frames

**Files:**
- Create: `src/where_to_go/frames.py`
- Modify: `pyproject.toml` (`av>=19,<20`), `uv.lock`, `src/where_to_go/refresh.py` (`_collect_one`), `src/where_to_go/container.py`
- Test: `tests/test_frames.py`, `tests/test_av_wheels.py`, `tests/test_pipeline.py`

**Interfaces:**
- Produces: `VideoFrames(folder: Path, client: httpx.AsyncClient)`: `async save(url: str) -> list[str]` — names of stored JPEG frames in the image folder (same folder as `ImageStore`, names `sha1(url without query) + "-f<i>.jpg"`); `[]` on any download or decode failure. `MAX_FRAMES = 6`, `STEP_SECONDS = 2.0`, near-duplicate = mean absolute difference of 32×32 grayscale thumbnails below a threshold (builder's call, tested). Download limit 60 MB. Decoding runs in a worker thread (`anyio.to_thread.run_sync`).
- `RefreshService._collect_one`: images first, then frames of each `post.video_urls`, in that order, into `image_paths`.

- [ ] **Step 1: Failing tests** — generate a 10 s test video with PyAV in the test (5 s red, 5 s blue, 2 s… use `av.open(..., "w")`) → `save` returns 2 frames (red, blue); a video of 30 distinct colors → 6 frames; a non-video body → `[]`; a 404 → `[]`. Pipeline test: an Instagram post with one image and one video stores image then frames. Wheels guard: pyproject `av` specifier contains `19.0.2`.
- [ ] **Step 2–4:** `uv add "av>=19,<20"`, run → FAIL, implement, run → PASS. **Step 5: Commit** `Read frames of Instagram videos`.

### Task 6: What Claude reads from an Instagram source

**Files:**
- Modify: `src/where_to_go/repositories.py` (`PostRepository.to_read`), `src/where_to_go/refresh.py` (`run`, `PostReader.read`)
- Test: `tests/test_pipeline.py`, `tests/test_potential_sources.py`

**Interfaces:**
- `PostRepository.to_read(source_ids, rules, recent, today, instagram: dict[int, InstagramReading] = {})`: unprocessed posts as before (skipped ones are processed, so never chosen); for an Instagram source on rules change: the latest `recent` non-story posts if `posts` on, and stories with `published_at >= today - 30 days` and `read_with != SKIPPED` if `stories` on; a kind turned off is never re-read; its unprocessed posts are also left out.
- `PostReader.read`: for a post of an Instagram source keep a channel reference only if `f"t.me/{handle.lower()}"` is in the post text (lower-cased).

- [ ] **Step 1: Failing tests** — rules change re-reads Instagram posts and fresh stories, not skipped or old ones; with `stories=False` no story is chosen and existing story cards stay; an Instagram caption with `@scruscru` and `t.me/belgrade_events` notes only `belgrade_events`; Telegram posts keep `@mentions` as before.
- [ ] **Step 2–4:** run → FAIL, implement, run → PASS. **Step 5: Commit** `Read only what is new from Instagram`.

### Task 7: API

**Files:**
- Modify: `src/where_to_go/api/app.py`, `frontend/openapi.json`, `frontend/src/api/schema.d.ts` (`npm run api:types`), `frontend/src/api/client.ts`, `frontend/src/api/queries.ts`
- Test: `tests/test_api.py`

**Interfaces:**
- `SourceRequest` gains `kind: SourceKind | None = None` ("only for a bare name valid for Telegram and Instagram") and `instagram: InstagramReading | None = None`.
- `POST /sources/preview` and `POST /sources`: 422 with the `AmbiguousNameError` message when the kind is needed and missing.
- `SourcePublic` gains `instagram: InstagramReading | None = None`, filled for Instagram sources by `GET /sources` and every source-returning endpoint.
- `PUT /sources/{source_id}/instagram` body `InstagramReading` → `SourcePublic`; 422 for non-Instagram sources; 422 when both are false.
- Frontend client: `previewSource(link, kind?)`, `addSource({link, title, kind?, instagram?})`, `setInstagramReading(id, reading)`; query `useSetInstagramReading` (stale: sources).

- [ ] **Step 1: Failing API tests** for each line above. **Step 2–4:** implement, regenerate types, run `uv run pytest tests/test_api.py` and `cd frontend && npx tsc -b` → PASS. **Step 5: Commit** `Instagram sources in the API`.

### Task 8: Interface

**Files:**
- Modify: `frontend/src/screens/SourcesScreen.tsx`, `SourcesScreen.css`, `frontend/src/ui/Icon.tsx` (add `instagram` glyph), `frontend/src/screens/SourcesScreen.test.tsx`
- Create (if it keeps the screen file focused): `frontend/src/screens/InstagramPreviewCard.tsx`

**Interfaces:**
- `ambiguousName(link: string): boolean` = `/^@?[A-Za-z][A-Za-z0-9_]{3,31}$/` on the trimmed link (mirror of the backend rule; a link with a dot after `@` is not ambiguous).
- Add form: when `ambiguousName(link)`, a segmented choice **Telegram** / **Instagram** appears right after the Link field, nothing selected, Add disabled until one is chosen; the choice resets when the link changes. Placeholder: "t.me/channel, instagram.com/profile or an event page".
- Preview `kind === "instagram"` → `InstagramPreviewCard`: Instagram icon, title, link to the profile; heading "What to read"; checkbox **Posts** with hint "12 latest, then every new one"; checkbox **Pinned stories** with hint "{n} highlights; stories up to 30 days old, then every new one" (n from `highlights`; with 0 highlights: "No highlights yet; new ones will be read"); both checked; **Cancel** and **Add profile** (disabled when both unchecked). Telegram still adds without a card.
- Source row: Instagram icon with label "Instagram profile"; for Instagram sources two small toggles **Posts** and **Pinned stories** (each its own control, not a joined label) calling `useSetInstagramReading`; the last one on cannot be turned off (disabled).

- [ ] **Step 1: Failing tests** — `@londonevents` shows the choice and Add is disabled until a pick; `@eje.belgrade` shows no choice; Instagram preview shows both checkboxes checked and sends `instagram: {posts: true, stories: false}` after unchecking stories; the row toggles call the API.
- [ ] **Step 2–4:** implement, `npm test && npm run lint && npx tsc -b` → PASS. **Step 5: Commit** `Add Instagram profiles in the interface`.

### Task 9: Verify in the real app, document, release

- [ ] **Step 1:** `make test` → all green (any red is a blocker, fix it).
- [ ] **Step 2:** Run the branch on a copy of the prod data (per `docs/development.md`), add `instagram.com/eje.belgrade` through the interface, refresh, see cards from the November poster and the "timetable" story, open **Original**, toggle **Pinned stories**; check the picker with `@londonevents`; screenshots of each state, light and dark.
- [ ] **Step 3:** README: Instagram in "Sources you control" and the FAQ (what is read, what is not: active stories, sound).
- [ ] **Step 4:** Merge to master by the project's way and cut the release with the `release` skill.
