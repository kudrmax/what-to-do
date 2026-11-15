# Web sources: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** an event website is added to the sources with one link to an event; its events go through the same pipeline as Telegram posts.

**Architecture:** the general web layer (`web.py`: sitemap, schema.org `Event` markup, page text, time) knows nothing about websites. The web source (`web_sources.py`) stores a website as data (sitemap, section prefix, whether the time is honest, horizon) and turns event pages into ordinary `Post`s. Telegram and a website are two implementations of one source reading interface.

**Tech Stack:** Python 3.13, SQLModel/SQLite, httpx + respx, selectolax; React + TypeScript (Vite), vitest.

**Spec:** `docs/superpowers/specs/2026-11-15-web-sources-design.md`

## Global Constraints

- Only the text of the facts goes to Claude (format in Task 2), never HTML.
- The code doesn't mention polakohedonist.club, except in test fixtures.
- The default horizon is 30 days; known events are rechecked for the next 7 days.
- Page downloads: at most 4 at once, User-Agent `about.USER_AGENT` (the container's shared `httpx.AsyncClient`).
- Existing tables change only by adding columns with a default; new tables are created by `create_all`.
- `ReadingRules` don't change; the `channel` key in the request to Claude is not renamed.
- UI: no lists separated by "·", "|", "/" or commas on one line (Max's rule).
- Delete files only with `trash`.

## Review Focus

1. The sitemap is served as gzip or as a sitemap index: it is read, rather than failing or giving zero addresses.
2. The `Event` block sits in `@graph`, in a list, or `@type` is a list (`["Event","MusicEvent"]`), or a subtype (`MusicEvent`, `TheaterEvent`): the event is found.
3. One page answers 404 or times out: the source's other pages are read, and the source has no error.
4. `startDate` is a date only, without time (`2026-11-20`): an all-day event, no made-up time.
5. A `t.me/...` link in the add field still adds a channel rather than going to the web check.

---

### Task 1: General web layer: sitemap and event markup

**Files:**
- Create: `src/where_to_go/web.py`
- Create: `tests/test_web.py`
- Create: `tests/fixtures/web/polako_event.html` (a real page from the scouting: `curl -s -A "Mozilla/5.0" https://polakohedonist.club/ru/events/iskusstvo-byt-nelepym-restoran-tri-2026-11-18-19-00-1`)
- Modify: `tests/helpers.py` (generators of small pages and sitemaps)

**Interfaces:**
- Produces:
  - `WebEvent` (frozen dataclass): `name: str`, `start: datetime | date`, `end: datetime | date | None`, `start_raw: str`, `place: str | None`, `address: str | None`, `locality: str | None`, `description: str`, `image: str | None`, `price: str | None`, `organizer: str | None`.
  - `EventMarkup.read(html: str) -> WebEvent | None`: the first object of type `Event` or a subtype (`*Event`) in any `application/ld+json`, including `@graph` and lists; without `name` or `startDate` → `None`. `image` is a string, the first item of a list or the `url` of an object. `price` comes from `offers` (`"0 RSD"`, `"from 1500 RSD"` with `lowPrice`).
  - `PageText.main(html: str) -> str`: the visible text of `<main>`, otherwise `<article>`, otherwise `<body>`, cleaned with `telegram.HtmlText.extract`.
  - `PageMeta.site_name(html: str) -> str | None`: `og:site_name`.
  - `SitemapReader(client: httpx.AsyncClient)`: `async def locate(site: str) -> str` (`Sitemap:` lines in `{site}/robots.txt`, otherwise `{site}/sitemap.xml` if it answers 200; otherwise `SourceError("The site has no page list (sitemap)")`); `async def urls(sitemap_url: str) -> list[str]` (follows sitemap indexes recursively, unpacks gzip by the `\x1f\x8b` signature, keeps the order, removes duplicates).
  - `SiteAddress.parse(link: str) -> tuple[str, str]`: `(site, prefix)`: `https://host` and the path without its last segment, with a trailing slash (`/ru/events/`); not http(s) or without a path → `SourceError("This doesn't look like a link to an event page")`.

- [ ] **Step 1: Tests**

```python
def test_polako_page_gives_its_event():
    event = EventMarkup.read(fixture("polako_event.html"))
    assert event.name == "The Art of Being Awkward"   # the fixture's Russian title
    assert event.start_raw == "2026-11-18T19:00:00.000Z"
    assert (event.place, event.locality) == ("Restoran Tri", "Belgrade")
    assert event.description.startswith("# \"THE ART OF BEING AWKWARD\"")

@pytest.mark.parametrize("wrap", ["graph", "list", "type_list", "subtype"])
def test_event_is_found_however_it_is_wrapped(wrap): ...   # the event name is found in all four forms

def test_date_only_start_stays_a_date():
    assert EventMarkup.read(event_page(startDate="2026-11-20")).start == date(2026, 11, 20)

def test_page_without_event_markup_gives_none(): ...        # only Organization/BreadcrumbList → None

def test_site_address_takes_the_section_of_the_link():
    assert SiteAddress.parse("https://x.club/ru/events/a-2026-11-18-1?utm=1") == ("https://x.club", "/ru/events/")

@respx.mock
async def test_sitemap_index_and_gzip_are_followed(): ...   # robots → index → two sitemaps, one gzipped; all addresses in order

@respx.mock
async def test_site_without_sitemap_is_refused(): ...       # robots without Sitemap:, /sitemap.xml 404 → SourceError with the text above
```

- [ ] **Step 2:** `uv run pytest tests/test_web.py -v`: FAIL (no module).
- [ ] **Step 3:** implement `web.py` by the interfaces above (`selectolax` for HTML, `xml.etree` for sitemaps, `gzip` for compressed ones).
- [ ] **Step 4:** `uv run pytest tests/test_web.py -v`: PASS.
- [ ] **Step 5:** commit `web sources: sitemap and schema.org Event reading`.

### Task 2: Event time and text for Claude

**Files:**
- Modify: `src/where_to_go/web.py`
- Test: `tests/test_web.py`

**Interfaces:**
- Consumes: `WebEvent`, `PageText.main` (Task 1).
- Produces:
  - `EventClock(times_are_local: bool, zone: ZoneInfo)`: `def local(value: datetime | date) -> datetime | date`: a date stays a date; with `times_are_local` the hours are taken as written, without a zone; otherwise an aware value is converted to `zone`, a naive one stays as is; the result is naive.
  - `EventClock.detect(event: WebEvent, page_text: str, zone: ZoneInfo) -> bool | None`: `True` if the offset is zero (`Z`/`+00:00`), the text has "HH:MM" as written and not converted to `zone`; `False` if the other way round; otherwise `None`.
  - `EventClock.decide(votes: list[bool | None]) -> bool`: `True` only if there is at least one `True` and no `False` (otherwise trust the offset, as the spec decided).
  - `in_horizon(start: datetime | date, end: datetime | date | None, today: date, days: int) -> bool`: the period `[start, end or start]` overlaps `[today, today + days]`.
  - `WebEventText.render(event: WebEvent, clock: EventClock, page_text: str) -> str`: the format below; if `len(description) < 200`, `page_text` cut to 3000 characters is added after the description.

Format (lines without a value are left out; time as `%Y-%m-%d %H:%M`, a date as `%Y-%m-%d`):

```
{name}
Start: {start}
End: {end}
Place: {place}, {address}, {locality}
Price: {price}
Organizer: {organizer}

{description}
```

- [ ] **Step 1: Tests**

```python
def test_polako_utc_label_is_local_time():
    event = EventMarkup.read(fixture("polako_event.html"))
    text = PageText.main(fixture("polako_event.html"))
    assert EventClock.detect(event, text, BELGRADE) is True
    assert EventClock(True, BELGRADE).local(event.start) == datetime(2026, 11, 18, 19, 0)

def test_honest_offset_is_converted():
    start = datetime(2026, 11, 26, 18, 0, tzinfo=timezone(timedelta(hours=1)))
    assert EventClock(False, BELGRADE).local(start) == datetime(2026, 11, 26, 18, 0)

def test_unclear_votes_trust_the_offset():
    assert EventClock.decide([None, None]) is False
    assert EventClock.decide([True, False]) is False
    assert EventClock.decide([True, None]) is True

def test_running_exhibition_is_in_horizon():
    assert in_horizon(date(2026, 11, 1), date(2026, 11, 30), date(2026, 11, 15), 30)
    assert not in_horizon(date(2026, 12, 20), None, date(2026, 11, 15), 30)

def test_text_for_claude_has_facts_not_html():
    text = WebEventText.render(EventMarkup.read(fixture("polako_event.html")), EventClock(True, BELGRADE), "")
    assert text.splitlines()[:4] == ["The Art of Being Awkward", "Start: 2026-11-18 19:00", "End: 2026-11-18 21:00", "Place: Restoran Tri, Svetogorska, 46, Belgrade"]
    assert "<" not in text.split("\n\n", 1)[0]

def test_short_description_is_completed_with_page_text(): ...  # a 12-character description → the text has page_text
```

- [ ] **Step 2:** run: FAIL. **Step 3:** implement. **Step 4:** `uv run pytest tests/test_web.py -v`: PASS.
- [ ] **Step 5:** commit `web sources: event time and text for Claude`.

### Task 3: Web source data model

**Files:**
- Modify: `src/where_to_go/models.py`, `src/where_to_go/repositories.py`
- Test: `tests/test_web_sources.py` (create), `tests/test_api.py` (source url)

**Interfaces:**
- Produces:
  - `SourceKind.WEB = "web"`.
  - `SourcePublic.url`: `TELEGRAM` → `TelegramUrls.channel(handle)`, `WEB` → `"https://" + handle`. A web source's `handle` is `host + prefix` (`polakohedonist.club/ru/events/`).
  - Table `WebSite` (`web_sites`): `source_id` (PK, FK `sources.id`, `ondelete="CASCADE"`), `sitemap_url: str`, `prefix: str`, `times_are_local: bool`, `horizon_days: int = 30`.
  - Table `WebPage` (`web_pages`, unique `(source_id, url)`): `id`, `source_id` (FK, cascade, index), `url`, `is_event: bool`, `start_at: datetime | None`, `end_at: datetime | None` (local naive; a date without time is midnight + `all_day: bool`), `facts: str | None` (the text for Claude), `image_url: str | None`, `checked_at: datetime`.
  - `WebRepository(db)`: `add_site(site: WebSite)`, `site(source_id) -> WebSite`, `pages(source_id) -> dict[str, WebPage]` (by url), `save_page(page: WebPage) -> WebPage`.
  - `PostRepository.to_read`: the last `recent` rule applies only to `TELEGRAM` sources; for `WEB`, only unread posts.
  - `PostRepository.replace_text(post_id: int, text: str) -> None`: new text, `processed_at = None`; a post with a locked mention (`Mention.locked`) doesn't change.

- [ ] **Step 1: Tests**: `test_web_source_url_is_its_section`, `test_deleting_web_source_removes_its_pages`, `test_web_posts_are_not_reread_by_recent_rule` (a read web post with a different `read_with` doesn't get into `to_read`), `test_changed_page_is_not_reread_when_user_merged_it` (locked → the text stays).
- [ ] **Step 2:** FAIL. **Step 3:** implement. **Step 4:** `uv run pytest -q`: all green (old tests too).
- [ ] **Step 5:** commit `web sources: tables for sites and their pages`.

### Task 4: Checking a website when adding and reading it on refresh

**Files:**
- Create: `src/where_to_go/web_sources.py`
- Test: `tests/test_web_sources.py`

**Interfaces:**
- Consumes: Tasks 1–3.
- Produces:
  - `SitePreview` (`Public`): `kind: SourceKind`, `title: str`, `handle: str`, `pages_found: int`, `examples: list[SiteExample]`; `SiteExample`: `title: str`, `starts_at: datetime`, `url: str`.
  - `WebSiteProbe(client, sitemaps: SitemapReader)`: `async def probe(link: str, zone: ZoneInfo) -> tuple[SitePreview, WebSite]` (`WebSite.source_id` is 0 for now). Steps: the spec's "When adding"; time votes from the page itself and from 2 examples; the examples are the first 3 addresses with the prefix that have an `Event`. Errors (`SourceError`): "The page has no event markup", "The site has no page list (sitemap)", "The site's page list has no other pages in this section", "The site doesn't respond".
  - `WebSiteReader(client, sitemaps, web: WebRepository, posts: PostRepository, clock: Callable[[], datetime] = now)`: `async def collect(source: Source, zone: ZoneInfo) -> list[CollectedPost]`: the spec's "When refreshing", steps 1–6. `CollectedPost.external_id` = `WebPage.id`, `url` = page address, `published_at` = the first `checked_at`, `text` = `facts`, `image_urls = [image_url]`. Changed `facts` of a known page with a post → `posts.replace_text`. An error on one page means a skip; a sitemap error means `SourceError`. Concurrency: `asyncio.Semaphore(4)`.

- [ ] **Step 1: Tests (respx, site `https://site.test`)**
  - `test_probe_finds_section_and_examples`: 5 addresses with the prefix, 2 foreign ones; `pages_found == 5`, 3 examples, `handle == "site.test/ru/events/"`.
  - `test_probe_detects_local_time_labelled_utc`: pages with `19:00Z` and "19:00" in the text → `times_are_local is True`.
  - `test_probe_refuses_page_without_event` and `test_probe_refuses_site_without_sitemap`.
  - `test_first_collect_reads_every_page_but_posts_only_horizon`: 3 pages: in 5 days, in 60 days, a category without `Event`; 1 post; the second time none of the three is downloaded again.
  - `test_page_entering_horizon_becomes_post_without_download`: `clock` moved by 40 days → a post for the "60 days" page without requesting the page.
  - `test_upcoming_week_is_rechecked_and_change_rereads_post`: a date within 7 days, the facts changed → the post has the new text and `processed_at is None`.
  - `test_broken_page_does_not_fail_source`: one page answers 500 → the other posts are there, no exception.
- [ ] **Step 2:** FAIL. **Step 3:** implement. **Step 4:** PASS.
- [ ] **Step 5:** commit `web sources: probing a site and collecting its events`.

### Task 5: Wiring into the catalog, refresh, prompts and API

**Files:**
- Modify: `src/where_to_go/sources.py`, `src/where_to_go/refresh.py`, `src/where_to_go/container.py`, `src/where_to_go/prompts.py`, `src/where_to_go/photos.py` (or `refresh.py`, wherever photos are picked), `src/where_to_go/api/app.py`
- Test: `tests/test_pipeline.py`, `tests/test_api.py`, `tests/test_potential_sources.py` (if it breaks)

**Interfaces:**
- Consumes: Task 4.
- Produces:
  - `SourceLink.is_telegram(link: str) -> bool` in `telegram.py`: `t.me`/`telegram.me`/`@name`/a bare name → `True`; other http(s) → `False`.
  - `SourceCatalog(sources, events, cards, telegram: TelegramChannelReader, probe: WebSiteProbe, web: WebRepository)`: `async def preview(city, link) -> SitePreview` (for a channel: `kind=TELEGRAM`, `pages_found=0`, no examples); `add(city, link, title)`: for a website, saves `Source(kind=WEB, handle, title=title or preview.title)` and `WebSite`. A duplicate by `(kind, handle)` → `DuplicateSourceError("This site is already added")`.
  - `RefreshService._collect` picks the reader by `source.kind`; for `WEB`: `WebSiteReader.collect(source, ZoneInfo(city.timezone))`.
  - Photos of web posts are not transcribed: `PhotoTranscriber.shown(post)` for `post.source.kind == WEB` → `[]`.
  - Default prompts (`EXTRACTION`, `PHOTOS`, `MATCHING`): "Telegram channel posts" → "posts from Telegram channels and event pages of websites"; in `EXTRACTION`, the line: "A website post is the event page's facts: name, start, end, place, price, organizer, description. Its "channel" is the website; a website is an afisha, never the organizer."
  - API: `POST /sources/preview` (`SourceRequest` → `SitePreview`; 422 on `SourceError`); `POST /sources` accepts a website link; the description of `SourceRequest.link`: "t.me/name, @name, name, or a link to any event page of a website".

- [ ] **Step 1: Tests**
  - `test_pipeline.py::test_web_source_events_reach_the_feed_and_merge_with_telegram`: the channel `kafana` and a website with the same "Kafana" event on the same date → one card with two sources, time 19:00 (the website writes `19:00Z` and "19:00").
  - `test_pipeline.py::test_web_posts_photos_are_not_transcribed`: the photo fake gets zero calls for one web post.
  - `test_api.py::test_preview_of_site_link`, `test_api.py::test_telegram_link_still_adds_channel`, `test_api.py::test_same_site_twice_is_409`.
- [ ] **Step 2:** FAIL. **Step 3:** implement. **Step 4:** `uv run pytest -q`: all green.
- [ ] **Step 5:** `uv run python scripts/export_openapi.py` and `cd frontend && npm run api:types`: the schema and types are updated.
- [ ] **Step 6:** commit `web sources: add sites as sources and read them on refresh`.

### Task 6: Sources screen

**Files:**
- Modify: `frontend/src/screens/SourcesScreen.tsx`, `frontend/src/screens/SourcesScreen.css`, `frontend/src/api/client.ts`, `frontend/src/api/queries.ts`, `frontend/src/ui/Icon.tsx` (the `globe` and `telegram` icons, if missing)
- Test: `frontend/src/screens/SourcesScreen.test.tsx`

**Interfaces:**
- Consumes: `POST /sources/preview` → `SitePreview`.
- Produces: `api.previewSource(link)`, `usePreviewSource()`.

Behavior:
- The field placeholder: "t.me/channel or a link to an event on a website".
- **Add** with a Telegram link works as now. With a website link, a preview comes first (the button says **Checking…**), and under the form a card: the site name in large type, the section address as a link, "Found N event pages", three examples on separate lines (title, with the date and time below it), **Cancel** and **Add** buttons. An error shows as text under the field, as now.
- A source row: a kind icon (globe or Telegram) before the name; under the name, `@handle` for a channel and the section address for a website; the label "Delete channel…" → "Delete the source and its events"; the table's aria label is "Sources"; an empty list says "No sources yet. Add a Telegram channel or an event website and press **Refresh** in **Upcoming**."

- [ ] **Step 1: Tests**: `shows site preview before adding`, `adds site after confirming preview`, `telegram link is added without preview`, `site row shows its section address and globe icon`.
- [ ] **Step 2:** `cd frontend && npx vitest run src/screens/SourcesScreen.test.tsx`: FAIL. **Step 3:** implement. **Step 4:** `npm test`, `npm run lint` and `npm run build`: green.
- [ ] **Step 5:** commit `web sources: add a site from the sources screen`.

### Task 7: Checking on a copy of the data and with your own eyes

- [ ] **Step 1:** all tests: `uv run pytest -q`, `cd frontend && npm test`. Any red one is a blocker.
- [ ] **Step 2:** data copy: `cp -R ~/Library/Application\ Support/where-to-go <scratchpad>/data-copy`; run the branch with `--data` pointing to the copy and a free port (see `Makefile`, `.env.example`).
- [ ] **Step 3:** in the browser pane: add a Polako link → preview with examples → **Add**; add `https://example.com/foo` → a clear error; **Refresh** → Polako events in the feed, "The Art of Being Awkward" on November 18 at 19:00, the original button leads to the website's page; an event that also came from Telegram is merged. Screenshots of every state, dark and light theme.
- [ ] **Step 4:** Claude calls on the copy: about 10 (Max's rule): before **Refresh** on the copy, set the website's `horizon_days = 2` (in the copy's database, not in the working data); that is ~5 reading batches plus merging. Write the number of calls in the report. Name Max's first real run (30 days, ~60 batches) in the report in advance.
- [ ] **Step 5:** merge into master by the CLAUDE.md rules and publish a release with the `release` skill.
