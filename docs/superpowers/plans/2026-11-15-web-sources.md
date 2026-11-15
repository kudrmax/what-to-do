# Веб-источники — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** сайт с афишей добавляется в источники одной ссылкой на событие; его события идут тем же конвейером, что посты Telegram.

**Architecture:** общий веб-слой (`web.py`: sitemap, разметка schema.org `Event`, текст страницы, время) ничего не знает о сайтах. Веб-источник (`web_sources.py`) хранит сайт как данные (sitemap, префикс раздела, честность времени, горизонт) и превращает страницы событий в обычные `Post`. Telegram и сайт — две реализации одного интерфейса чтения источника.

**Tech Stack:** Python 3.13, SQLModel/SQLite, httpx + respx, selectolax; React + TypeScript (Vite), vitest.

**Spec:** `docs/superpowers/specs/2026-11-15-web-sources-design.md`

## Global Constraints

- В Claude уходит только текст фактов (формат — в задаче 2), никогда HTML.
- В коде нет упоминаний polakohedonist.club, кроме тестовых фикстур.
- Горизонт по умолчанию 30 дней; перепроверка известных событий — ближайшие 7 дней.
- Загрузка страниц — не больше 4 одновременно, User-Agent — `about.USER_AGENT` (общий `httpx.AsyncClient` контейнера).
- Существующие таблицы меняются только добавлением колонок с default; новые таблицы создаёт `create_all`.
- `ReadingRules` не меняются; ключ `channel` в запросе к Claude не переименовывается.
- UI: никаких перечислений через «·», «|», «/», запятую в одной строке (правило Макса).
- Удаление файлов только через `trash`.

## Review Focus

1. Sitemap отдаёт gzip или sitemap index: читается, а не падает и не даёт ноль адресов.
2. Блок `Event` лежит в `@graph`, в списке, или `@type` — список (`["Event","MusicEvent"]`), или подтип (`MusicEvent`, `TheaterEvent`): событие находится.
3. Одна страница отвечает 404/таймаутом: остальные страницы источника читаются, ошибки источника нет.
4. `startDate` — только дата без времени (`2026-11-20`): событие весь день, время не выдумывается.
5. Ссылка `t.me/...` в поле добавления по-прежнему добавляет канал, а не уходит в веб-проверку.

---

### Task 1: Общий веб-слой — sitemap и разметка события

**Files:**
- Create: `src/where_to_go/web.py`
- Create: `tests/test_web.py`
- Create: `tests/fixtures/web/polako_event.html` (реальная страница из разведки: `curl -s -A "Mozilla/5.0" https://polakohedonist.club/ru/events/iskusstvo-byt-nelepym-restoran-tri-2026-11-18-19-00-1`)
- Modify: `tests/helpers.py` (генераторы маленьких страниц и sitemap)

**Interfaces:**
- Produces:
  - `WebEvent` (frozen dataclass): `name: str`, `start: datetime | date`, `end: datetime | date | None`, `start_raw: str`, `place: str | None`, `address: str | None`, `locality: str | None`, `description: str`, `image: str | None`, `price: str | None`, `organizer: str | None`.
  - `EventMarkup.read(html: str) -> WebEvent | None` — первый объект с типом `Event` или подтипом (`*Event`) в любом `application/ld+json`, включая `@graph` и списки; без `name` или `startDate` → `None`. `image` — строка, первый элемент списка или `url` объекта. `price` — из `offers` (`"0 RSD"`, `"от 1500 RSD"` при `lowPrice`).
  - `PageText.main(html: str) -> str` — видимый текст `<main>`, иначе `<article>`, иначе `<body>`, очищенный `telegram.HtmlText.extract`.
  - `PageMeta.site_name(html: str) -> str | None` — `og:site_name`.
  - `SitemapReader(client: httpx.AsyncClient)`: `async def locate(site: str) -> str` (строки `Sitemap:` в `{site}/robots.txt`, иначе `{site}/sitemap.xml`, если он отвечает 200; иначе `SourceError("На сайте нет списка страниц (sitemap)")`); `async def urls(sitemap_url: str) -> list[str]` (обходит sitemap index рекурсивно, распаковывает gzip по сигнатуре `\x1f\x8b`, порядок сохраняется, дубли убираются).
  - `SiteAddress.parse(link: str) -> tuple[str, str]` — `(site, prefix)`: `https://host` и путь без последнего сегмента со слешем на конце (`/ru/events/`); не http(s) или без пути → `SourceError("Это не похоже на ссылку на страницу события")`.

- [ ] **Step 1: Тесты**

```python
def test_polako_page_gives_its_event():
    event = EventMarkup.read(fixture("polako_event.html"))
    assert event.name == "Искусство быть нелепым"
    assert event.start_raw == "2026-11-18T19:00:00.000Z"
    assert (event.place, event.locality) == ("Restoran Tri", "Belgrade")
    assert event.description.startswith("# «ИСКУССТВО БЫТЬ НЕЛЕПЫМ»")

@pytest.mark.parametrize("wrap", ["graph", "list", "type_list", "subtype"])
def test_event_is_found_however_it_is_wrapped(wrap): ...   # имя события находится во всех четырёх видах

def test_date_only_start_stays_a_date():
    assert EventMarkup.read(event_page(startDate="2026-11-20")).start == date(2026, 11, 20)

def test_page_without_event_markup_gives_none(): ...        # только Organization/BreadcrumbList → None

def test_site_address_takes_the_section_of_the_link():
    assert SiteAddress.parse("https://x.club/ru/events/a-2026-11-18-1?utm=1") == ("https://x.club", "/ru/events/")

@respx.mock
async def test_sitemap_index_and_gzip_are_followed(): ...   # robots → index → два sitemap, один в gzip; все адреса по порядку

@respx.mock
async def test_site_without_sitemap_is_refused(): ...       # robots без Sitemap:, /sitemap.xml 404 → SourceError с текстом выше
```

- [ ] **Step 2:** `uv run pytest tests/test_web.py -v` — FAIL (нет модуля).
- [ ] **Step 3:** реализовать `web.py` по интерфейсам выше (`selectolax` для HTML, `xml.etree` для sitemap, `gzip` для сжатых).
- [ ] **Step 4:** `uv run pytest tests/test_web.py -v` — PASS.
- [ ] **Step 5:** commit `web sources: sitemap and schema.org Event reading`.

### Task 2: Время и текст события для Claude

**Files:**
- Modify: `src/where_to_go/web.py`
- Test: `tests/test_web.py`

**Interfaces:**
- Consumes: `WebEvent`, `PageText.main` (Task 1).
- Produces:
  - `EventClock(times_are_local: bool, zone: ZoneInfo)`: `def local(value: datetime | date) -> datetime | date` — дата остаётся датой; `times_are_local` → часы как написаны, без пояса; иначе aware переводится в `zone`, naive остаётся как есть; результат naive.
  - `EventClock.detect(event: WebEvent, page_text: str, zone: ZoneInfo) -> bool | None` — `True`, если смещение нулевое (`Z`/`+00:00`), в тексте есть «ЧЧ:ММ» как написано и нет пересчитанного в `zone`; `False`, если наоборот; иначе `None`.
  - `EventClock.decide(votes: list[bool | None]) -> bool` — `True` только если есть хотя бы один `True` и нет `False` (иначе верим смещению — решение из спеки).
  - `in_horizon(start: datetime | date, end: datetime | date | None, today: date, days: int) -> bool` — период `[start, end or start]` пересекается с `[today, today + days]`.
  - `WebEventText.render(event: WebEvent, clock: EventClock, page_text: str) -> str` — формат ниже; если `len(description) < 200`, после описания добавляется `page_text`, обрезанный до 3000 символов.

Формат (строки без значения не пишутся; время `%Y-%m-%d %H:%M`, для даты `%Y-%m-%d`):

```
{name}
Начало: {start}
Конец: {end}
Место: {place}, {address}, {locality}
Цена: {price}
Организатор: {organizer}

{description}
```

- [ ] **Step 1: Тесты**

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
    assert text.splitlines()[:4] == ["Искусство быть нелепым", "Начало: 2026-11-18 19:00", "Конец: 2026-11-18 21:00", "Место: Restoran Tri, Светогорска, 46, Belgrade"]
    assert "<" not in text.split("\n\n", 1)[0]

def test_short_description_is_completed_with_page_text(): ...  # description 12 символов → в тексте есть page_text
```

- [ ] **Step 2:** запустить — FAIL. **Step 3:** реализовать. **Step 4:** `uv run pytest tests/test_web.py -v` — PASS.
- [ ] **Step 5:** commit `web sources: event time and text for Claude`.

### Task 3: Модель данных веб-источника

**Files:**
- Modify: `src/where_to_go/models.py`, `src/where_to_go/repositories.py`
- Test: `tests/test_web_sources.py` (create), `tests/test_api.py` (url источника)

**Interfaces:**
- Produces:
  - `SourceKind.WEB = "web"`.
  - `SourcePublic.url`: `TELEGRAM` → `TelegramUrls.channel(handle)`, `WEB` → `"https://" + handle`. У веб-источника `handle` = `host + prefix` (`polakohedonist.club/ru/events/`).
  - Таблица `WebSite` (`web_sites`): `source_id` (PK, FK `sources.id`, `ondelete="CASCADE"`), `sitemap_url: str`, `prefix: str`, `times_are_local: bool`, `horizon_days: int = 30`.
  - Таблица `WebPage` (`web_pages`, unique `(source_id, url)`): `id`, `source_id` (FK, cascade, index), `url`, `is_event: bool`, `start_at: datetime | None`, `end_at: datetime | None` (локальные naive; дата без времени — полночь + `all_day: bool`), `facts: str | None` (текст для Claude), `image_url: str | None`, `checked_at: datetime`.
  - `WebRepository(db)`: `add_site(site: WebSite)`, `site(source_id) -> WebSite`, `pages(source_id) -> dict[str, WebPage]` (по url), `save_page(page: WebPage) -> WebPage`.
  - `PostRepository.to_read`: последние `recent` применяются только к источникам `TELEGRAM`; для `WEB` — только непрочитанные.
  - `PostRepository.replace_text(post_id: int, text: str) -> None`: новый текст, `processed_at = None`; пост с закреплённым упоминанием (`Mention.locked`) не меняется.

- [ ] **Step 1: Тесты** — `test_web_source_url_is_its_section`, `test_deleting_web_source_removes_its_pages`, `test_web_posts_are_not_reread_by_recent_rule` (прочитанный веб-пост с другим `read_with` не попадает в `to_read`), `test_changed_page_is_not_reread_when_user_merged_it` (locked → текст прежний).
- [ ] **Step 2:** FAIL. **Step 3:** реализовать. **Step 4:** `uv run pytest -q` — всё зелёное (и старые тесты).
- [ ] **Step 5:** commit `web sources: tables for sites and their pages`.

### Task 4: Проверка сайта при добавлении и чтение при обновлении

**Files:**
- Create: `src/where_to_go/web_sources.py`
- Test: `tests/test_web_sources.py`

**Interfaces:**
- Consumes: Task 1–3.
- Produces:
  - `SitePreview` (`Public`): `kind: SourceKind`, `title: str`, `handle: str`, `pages_found: int`, `examples: list[SiteExample]`; `SiteExample`: `title: str`, `starts_at: datetime`, `url: str`.
  - `WebSiteProbe(client, sitemaps: SitemapReader)`: `async def probe(link: str, zone: ZoneInfo) -> tuple[SitePreview, WebSite]` (`WebSite.source_id` пока 0). Шаги — спека «При добавлении»; голоса времени со своей страницы и с 2 примеров; примеры — 3 первых адреса с префиксом, у которых есть `Event`. Ошибки (`SourceError`): «На странице нет разметки события», «На сайте нет списка страниц (sitemap)», «В списке страниц сайта нет других страниц этого раздела», «Сайт не отвечает».
  - `WebSiteReader(client, sitemaps, web: WebRepository, posts: PostRepository, clock: Callable[[], datetime] = now)`: `async def collect(source: Source, zone: ZoneInfo) -> list[CollectedPost]` — спека «При обновлении», шаги 1–6. `CollectedPost.external_id` = `WebPage.id`, `url` = адрес страницы, `published_at` = первое `checked_at`, `text` = `facts`, `image_urls = [image_url]`. Изменившиеся `facts` известной страницы с постом → `posts.replace_text`. Ошибка одной страницы — пропуск; ошибка sitemap — `SourceError`. Параллельность — `asyncio.Semaphore(4)`.

- [ ] **Step 1: Тесты (respx, сайт `https://site.test`)**
  - `test_probe_finds_section_and_examples` — 5 адресов с префиксом, 2 чужих; `pages_found == 5`, 3 примера, `handle == "site.test/ru/events/"`.
  - `test_probe_detects_local_time_labelled_utc` — страницы с `19:00Z` и «19:00» в тексте → `times_are_local is True`.
  - `test_probe_refuses_page_without_event` и `test_probe_refuses_site_without_sitemap`.
  - `test_first_collect_reads_every_page_but_posts_only_horizon` — 3 страницы: через 5 дней, через 60 дней, категория без `Event`; постов 1; во второй раз ни одна из трёх не скачивается заново.
  - `test_page_entering_horizon_becomes_post_without_download` — `clock` сдвинут на 40 дней → пост для «60 дней» без запроса страницы.
  - `test_upcoming_week_is_rechecked_and_change_rereads_post` — дата в течение 7 дней, факты изменились → у поста новый текст и `processed_at is None`.
  - `test_broken_page_does_not_fail_source` — одна страница 500 → остальные посты есть, исключения нет.
- [ ] **Step 2:** FAIL. **Step 3:** реализовать. **Step 4:** PASS.
- [ ] **Step 5:** commit `web sources: probing a site and collecting its events`.

### Task 5: Подключение к каталогу, обновлению, промптам и API

**Files:**
- Modify: `src/where_to_go/sources.py`, `src/where_to_go/refresh.py`, `src/where_to_go/container.py`, `src/where_to_go/prompts.py`, `src/where_to_go/photos.py` (или `refresh.py` — где отбираются фото), `src/where_to_go/api/app.py`
- Test: `tests/test_pipeline.py`, `tests/test_api.py`, `tests/test_potential_sources.py` (если сломается)

**Interfaces:**
- Consumes: Task 4.
- Produces:
  - `SourceLink.is_telegram(link: str) -> bool` в `telegram.py`: `t.me`/`telegram.me`/`@name`/голое имя → `True`; другие http(s) → `False`.
  - `SourceCatalog(sources, events, cards, telegram: TelegramChannelReader, probe: WebSiteProbe, web: WebRepository)`: `async def preview(city, link) -> SitePreview` (для канала — `kind=TELEGRAM`, `pages_found=0`, без примеров); `add(city, link, title)` — для сайта сохраняет `Source(kind=WEB, handle, title=title or preview.title)` и `WebSite`. Дубль по `(kind, handle)` → `DuplicateSourceError("Этот сайт уже добавлен")`.
  - `RefreshService._collect` выбирает читателя по `source.kind`; для `WEB` — `WebSiteReader.collect(source, ZoneInfo(city.timezone))`.
  - Фото веб-постов не расшифровываются: `PhotoTranscriber.shown(post)` для `post.source.kind == WEB` → `[]`.
  - Промпты по умолчанию (`EXTRACTION`, `PHOTOS`, `MATCHING`): «Telegram channel posts» → «posts from Telegram channels and event pages of websites»; в `EXTRACTION` строка: «A website post is the event page's facts: name, start, end, place, price, organizer, description. Its "channel" is the website; a website is an afisha, never the organizer.»
  - API: `POST /sources/preview` (`SourceRequest` → `SitePreview`; 422 `SourceError`); `POST /sources` принимает ссылку сайта; описание `SourceRequest.link` — «t.me/name, @name, name, or a link to any event page of a website».

- [ ] **Step 1: Тесты**
  - `test_pipeline.py::test_web_source_events_reach_the_feed_and_merge_with_telegram` — канал `kafana` и сайт с событием «Кафаны» той же даты → одна карточка с двумя источниками, время 19:00 (сайт пишет `19:00Z` и «19:00»).
  - `test_pipeline.py::test_web_posts_photos_are_not_transcribed` — у photo-fake ноль вызовов при одном веб-посте.
  - `test_api.py::test_preview_of_site_link`, `test_api.py::test_telegram_link_still_adds_channel`, `test_api.py::test_same_site_twice_is_409`.
- [ ] **Step 2:** FAIL. **Step 3:** реализовать. **Step 4:** `uv run pytest -q` — всё зелёное.
- [ ] **Step 5:** `uv run python scripts/export_openapi.py` и `cd frontend && npm run api:types` — схема и типы обновлены.
- [ ] **Step 6:** commit `web sources: add sites as sources and read them on refresh`.

### Task 6: Экран источников

**Files:**
- Modify: `frontend/src/screens/SourcesScreen.tsx`, `frontend/src/screens/SourcesScreen.css`, `frontend/src/api/client.ts`, `frontend/src/api/queries.ts`, `frontend/src/ui/Icon.tsx` (иконки `globe`, `telegram`, если их нет)
- Test: `frontend/src/screens/SourcesScreen.test.tsx`

**Interfaces:**
- Consumes: `POST /sources/preview` → `SitePreview`.
- Produces: `api.previewSource(link)`, `usePreviewSource()`.

Поведение:
- Плейсхолдер поля — «t.me/канал или ссылка на событие сайта».
- «Добавить» по ссылке Telegram — как сейчас. По ссылке сайта — сначала предпросмотр (кнопка «Проверяю…»), под формой карточка: название сайта крупно, адрес раздела ссылкой, «Найдено N страниц событий», три примера отдельными строками (название, под ним дата и время), кнопки «Отмена» и «Добавить». Ошибка — текстом под полем, как сейчас.
- Строка источника: иконка вида (глобус / Telegram) перед названием; под названием `@handle` для канала и адрес раздела для сайта; подписи «Удалить канал…» → «Удалить источник и его события»; aria-метка таблицы «Источники»; пустой список — «Источников пока нет. Добавьте Telegram-канал или сайт с афишей и нажмите «Обновить» в «Ближайших».»

- [ ] **Step 1: Тесты** — `shows site preview before adding`, `adds site after confirming preview`, `telegram link is added without preview`, `site row shows its section address and globe icon`.
- [ ] **Step 2:** `cd frontend && npx vitest run src/screens/SourcesScreen.test.tsx` — FAIL. **Step 3:** реализовать. **Step 4:** `npm test` и `npm run lint` и `npm run build` — зелёные.
- [ ] **Step 5:** commit `web sources: add a site from the sources screen`.

### Task 7: Проверка на копии данных и глазами

- [ ] **Step 1:** все тесты: `uv run pytest -q`, `cd frontend && npm test`. Любой красный — блокер.
- [ ] **Step 2:** копия данных: `cp -R ~/Library/Application\ Support/where-to-go <scratchpad>/data-copy`; запустить ветку с `--data` на копию и свободным портом (см. `Makefile`, `.env.example`).
- [ ] **Step 3:** в браузерной панели: добавить ссылку Polako → предпросмотр с примерами → «Добавить»; добавить `https://example.com/foo` → понятная ошибка; «Обновить» → события Polako в ленте, у «Искусство быть нелепым» 18 ноября 19:00, кнопка оригинала ведёт на страницу сайта; событие, бывшее и в Telegram, склеено. Снимки экрана каждого состояния, тёмная и светлая тема.
- [ ] **Step 4:** вызовы Claude на копии — около 10 (правило Макса): перед «Обновить» на копии поставить сайту `horizon_days = 2` (в копии БД, не в рабочих данных) — это ~5 пачек чтения плюс склейка. Число вызовов записать в отчёт. Первый настоящий прогон у Макса (30 дней, ~60 пачек) — назвать в отчёте заранее.
- [ ] **Step 5:** влить в master по правилам CLAUDE.md и выпустить релиз скиллом `release`.
