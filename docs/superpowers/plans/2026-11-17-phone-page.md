# Phone Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The app publishes the upcoming "Going for sure" and "Maybe going" events, encrypted with a password, to a GitHub Pages site that a phone can read.

**Architecture:** A backend package `where_to_go.phone_page` builds a snapshot from the existing `Feed`, encrypts it (AES-256-GCM, PBKDF2 key), and replaces a GitHub repository's contents through the REST API with one parentless commit. A background loop checks once a minute whether the snapshot changed and publishes at most every 10 minutes. A separate small Vite bundle (`frontend/dist/phone/`) is the phone page: it decrypts in the browser with WebCrypto and draws the list. The Settings screen gets a **Phone page** section.

**Tech Stack:** Python 3, FastAPI, httpx, `cryptography` (already in uv.lock, promote to a direct dependency), respx for tests; React 19, Vite 6, vitest, WebCrypto.

**Spec:** `docs/superpowers/specs/2026-11-17-phone-page-design.md`

## Global Constraints

- English only in code, UI and docs; `tests/test_english_only.py` must pass. Event data stays in its language.
- No `git` or `gh` at runtime: GitHub only through its REST API over the app's `httpx.AsyncClient`.
- No new image library: posters are uploaded as stored, encrypted.
- The token and password never appear in `GET /settings`, in any API response, or in logs.
- Ciphertext only: no plaintext event data is ever committed.
- File format of every encrypted file: `b"WTD1"` (4 bytes) + salt (16) + IV (12) + AES-GCM ciphertext with tag.
- PBKDF2-HMAC-SHA256, 600 000 iterations, 32-byte key. New salt only when the password changes.
- Publishing cadence: at most one publish per 10 minutes; **Publish now** and Turn on ignore the cap.
- Marker file at the repository root: `.what-to-do-phone-page`.
- UI rule: no facts glued into one line with "·", "|", "/" or commas; each fact gets its own element, icon or color.
- Frontend and backend separate: the phone page reads only the decrypted snapshot, never the app API.

## Deviation from the spec (builder's call)

Instead of wiring triggers into `set_mark`, refresh and city change plus a 30-second debounce, `PhonePageService` runs a loop that rebuilds the snapshot every 60 seconds and publishes when its hash changed. The snapshot is one feed query, so this is cheap, and it also catches changes the spec's trigger list misses (manual merges, reschedules from a refresh, the date rolling over at midnight). Update the spec's "When the app publishes" section in Task 9.

## Review Focus

1. **A repository created with "Add a README"** is not empty: the Git Data API works, the tree holds only `README.md`; Turn on must accept it and the publish must replace it. (Task 4 test `test_readme_only_repository_is_accepted`.)
2. **A truly empty repository** (no commits): the Git Data API answers 409 "Git Repository is empty"; the publisher must bootstrap it by creating the marker file through the Contents API first. (Task 4 test `test_empty_repository_is_bootstrapped`.)
3. **The password is changed on the laptop** while the phone remembers the old key: the phone must ask again instead of showing a decryption error. (Task 7 test `asks_again_when_salt_changed`.)
4. **An expired or revoked token** during a background publish: the state shows "The token expired or was revoked", the loop keeps running, and nothing crashes the app. (Task 5 test `test_failed_publish_is_kept_in_state_and_retried`.)
5. **An event whose poster file is missing on disk** (deleted or never downloaded): the snapshot leaves its image out and the publish goes on. (Task 3 test `test_missing_poster_is_left_out`.)

---

### Task 1: Phone page settings storage

**Files:**
- Create: `src/where_to_go/phone_page/__init__.py`, `src/where_to_go/phone_page/config.py`
- Test: `tests/test_phone_page_config.py`

**Interfaces:**
- Produces:
  - `class PhonePageConfig(BaseModel)`: `enabled: bool = False`, `repository: str = ""` (`owner/name`), `token: str = ""`, `password: str = ""`, `salt: str = ""` (base64), `published_hash: str = ""`, `published_at: datetime | None = None`, `last_error: str | None = None`.
  - `class PhonePageConfigRepository(db: Database)`: `load() -> PhonePageConfig`, `update(**change) -> PhonePageConfig`. Stored in the existing `settings` table under keys `phone_page.<field>`; `AppSettings` ignores extra keys (`extra="ignore"`), so nothing leaks into `GET /settings`.

- [ ] **Step 1: Write the failing tests**

```python
def test_config_round_trip(tmp_path):
    repo = PhonePageConfigRepository(Database(tmp_path / "db.sqlite3"))
    repo.update(repository="max/plans", token="t0k", password="pw")
    assert repo.load().repository == "max/plans" and repo.load().token == "t0k"

def test_secrets_do_not_reach_app_settings(client):  # API client fixture as in tests/test_api.py
    container = client.app.state.container
    container.phone_config.update(token="t0k", password="pw")
    body = client.get("/settings").text
    assert "t0k" not in body and "pw" not in body
```

- [ ] **Step 2: Run** `.venv/bin/pytest tests/test_phone_page_config.py -q` — expected FAIL (module missing).
- [ ] **Step 3: Implement** the model and repository; add `phone_config: PhonePageConfigRepository` to `Container` (field and `build`).
- [ ] **Step 4: Run** the same command — expected PASS.
- [ ] **Step 5: Commit** `feat: phone page settings storage`.

### Task 2: Snapshot cipher and a shared test vector

**Files:**
- Create: `src/where_to_go/phone_page/cipher.py`, `tests/fixtures/phone_page_vector.json`
- Modify: `pyproject.toml` (add `cryptography` to `dependencies`, `uv lock`)
- Test: `tests/test_phone_page_cipher.py`

**Interfaces:**
- Produces:
  - `SnapshotCipher.new_salt() -> bytes` (16 random bytes, static).
  - `SnapshotCipher(password: str, salt: bytes)`; derives the key once in `__init__`.
  - `encrypt(data: bytes) -> bytes` with a random IV.
  - `encrypt_stable(data: bytes) -> bytes` with `IV = HMAC-SHA256(key, data)[:12]`: same input gives the same bytes (used for posters).
  - `decrypt(blob: bytes) -> bytes`; raises `WrongPassword` on a tag failure or a salt mismatch. Used by tests and by the vector check.
- The vector file: `{"password": "correct horse", "plaintext": "{\"hello\":\"мир\"}", "blob_base64": "..."}` produced once by `encrypt` and committed; Task 7 decrypts the same file in the browser code.

- [ ] **Step 1: Write the failing tests**

```python
def test_round_trip_and_header():
    c = SnapshotCipher("pw", SnapshotCipher.new_salt())
    blob = c.encrypt(b"data")
    assert blob[:4] == b"WTD1" and len(blob) == 4 + 16 + 12 + len(b"data") + 16
    assert c.decrypt(blob) == b"data"

def test_random_iv_differs_stable_iv_repeats():
    c = SnapshotCipher("pw", SnapshotCipher.new_salt())
    assert c.encrypt(b"x") != c.encrypt(b"x")
    assert c.encrypt_stable(b"x") == c.encrypt_stable(b"x")
    assert c.encrypt_stable(b"x")[20:32] != c.encrypt_stable(b"y")[20:32]

def test_wrong_password():
    salt = SnapshotCipher.new_salt()
    with pytest.raises(WrongPassword):
        SnapshotCipher("other", salt).decrypt(SnapshotCipher("pw", salt).encrypt(b"x"))

def test_shared_vector_decrypts():
    v = json.loads((FIXTURES / "phone_page_vector.json").read_text())
    blob = base64.b64decode(v["blob_base64"])
    assert SnapshotCipher(v["password"], blob[4:20]).decrypt(blob).decode() == v["plaintext"]
```

- [ ] **Step 2: Run** `.venv/bin/pytest tests/test_phone_page_cipher.py -q` — expected FAIL.
- [ ] **Step 3: Implement** with `cryptography.hazmat.primitives.ciphers.aead.AESGCM` and `PBKDF2HMAC(SHA256, length=32, iterations=600_000)`; generate and commit the vector.
- [ ] **Step 4: Run** — expected PASS.
- [ ] **Step 5: Commit** `feat: snapshot cipher`.

### Task 3: Snapshot of the upcoming plans

**Files:**
- Create: `src/where_to_go/phone_page/snapshot.py`
- Test: `tests/test_phone_page_snapshot.py`

**Interfaces:**
- Consumes: `Feed.occurrences(city, FeedFilter)`, `TagRepository.hidden()`, the tag list in order (same source as `GET /tags`), `MentionRepository.of_event(id)` (last mention's `post_url`, as `calendar_file` does), `ImageStore.path(name)`.
- Produces:
  - `class PhoneSnapshot(BaseModel)`: `made_at: datetime`, `city: str` (city label), `timezone: str`, `today: date`, `tags: list[str]` (display order), `occurrences: list[PhoneOccurrence]`.
  - `class PhoneOccurrence(BaseModel)`: `date: date`, `event: dict` (the `EventPublic` JSON as the app's feed returns it, with `image_url` replaced by `images/<stem>.bin` or `None`), `post_url: str | None`.
  - `class SnapshotBuilder(feed, cities, tags, mentions, images)`: `build(now: datetime) -> tuple[PhoneSnapshot, dict[str, Path]] | None` — `None` without an active city; the dict maps `images/<stem>.bin` to the poster file.
  - `PhoneSnapshot.content_hash() -> str`: SHA-256 of the JSON without `made_at`.
- The filter is exactly the Plans screen's: `FeedFilter(start=today in the city's zone, plans={maybe, sure}, hidden_tags=tags.hidden())`.

- [ ] **Step 1: Write the failing tests** (seed with the helpers in `tests/helpers.py` and `EventRepository.set_mark`):
  - `test_only_upcoming_sure_and_maybe`: events marked sure (tomorrow), maybe (today), no (tomorrow), went (yesterday), unmarked → snapshot titles are exactly the maybe one then the sure one.
  - `test_image_url_points_to_encrypted_file`: an event with `image_path="abc.jpg"` → `event["image_url"] == "images/abc.bin"` and the dict maps that key to the stored file.
  - `test_missing_poster_is_left_out`: `image_path` set, file absent → `image_url is None`, not in the dict.
  - `test_hash_ignores_made_at`: two builds at different `now`, same data → same `content_hash()`; marking another event changes it.
  - `test_no_active_city_gives_none`.
- [ ] **Step 2: Run** `.venv/bin/pytest tests/test_phone_page_snapshot.py -q` — expected FAIL.
- [ ] **Step 3: Implement** `SnapshotBuilder`.
- [ ] **Step 4: Run** — expected PASS.
- [ ] **Step 5: Commit** `feat: phone page snapshot`.

### Task 4: GitHub Pages publisher

**Files:**
- Create: `src/where_to_go/phone_page/github.py`
- Test: `tests/test_phone_page_github.py` (respx mocks of `https://api.github.com`)

**Interfaces:**
- Produces:
  - `class PublishError(Exception)`: a message fit to show the user.
  - `class GitHubPagesPublisher(http: httpx.AsyncClient)`, every method takes `repository: str, token: str`:
    - `async check(...) -> None`: repository exists and the token can write (`GET /repos/{r}` → `permissions.push`); raises `PublishError("Repository not found")`, `"The token has no access to this repository"`, `"The token expired or was revoked"` (401).
    - `async ensure_empty_or_ours(...) -> None`: allowed when there are no commits, or the root tree holds only `README.md`, `LICENSE`, `.gitignore`, or contains `.what-to-do-phone-page`; otherwise `PublishError("This repository already has other files. Create a new empty one.")`.
    - `async ensure_pages(...) -> str`: `GET /repos/{r}/pages`; on 404 `POST` with `{"source": {"branch": "main", "path": "/"}}`; returns the site URL (`html_url`).
    - `async current_blobs(...) -> dict[str, str]`: path → blob SHA of the current `main` tree (empty for an empty repository).
    - `async replace(repository, token, files: dict[str, bytes], reuse: dict[str, str]) -> None`: uploads blobs for `files`, builds a tree from them plus `reuse` (path → existing blob SHA), creates a commit with `parents: []`, then `PATCH /git/refs/heads/main` with `force: true` (`POST /git/refs` when `main` does not exist yet).
- Empty-repository bootstrap: if `POST /git/blobs` answers 409, `PUT /repos/{r}/contents/.what-to-do-phone-page` once, then retry.
- Headers: `Authorization: Bearer <token>`, `Accept: application/vnd.github+json`, `X-GitHub-Api-Version: 2022-11-28`.

- [ ] **Step 1: Write the failing tests:** `test_check_maps_errors` (404, 403 without push, 401), `test_readme_only_repository_is_accepted`, `test_foreign_files_are_refused`, `test_marker_makes_repository_ours`, `test_pages_turned_on_when_off`, `test_replace_makes_parentless_commit_and_forces_ref` (assert the commit request body has `parents == []`, the ref PATCH has `force is True`, reused paths are in the tree without a blob upload), `test_empty_repository_is_bootstrapped`.
- [ ] **Step 2: Run** `.venv/bin/pytest tests/test_phone_page_github.py -q` — expected FAIL.
- [ ] **Step 3: Implement** the publisher.
- [ ] **Step 4: Run** — expected PASS.
- [ ] **Step 5: Commit** `feat: GitHub Pages publisher`.

### Task 5: Phone page service

**Files:**
- Create: `src/where_to_go/phone_page/service.py`
- Modify: `src/where_to_go/container.py` (field `phone_page: PhonePageService`; `close()` stops its loop), `src/where_to_go/api/app.py` lifespan (start the loop after the container is built)
- Test: `tests/test_phone_page_service.py`

**Interfaces:**
- Consumes: Tasks 1–4; `ProjectPaths.dist / "phone"` for the page bundle (all files under it, `phone.html` published as `index.html`).
- Produces:
  - `class PhonePageState(Public)`: `enabled: bool`, `repository: str`, `has_token: bool`, `has_password: bool`, `page_url: str | None`, `published_at: datetime | None`, `last_error: str | None`, `publishing: bool`.
  - `class PhonePageService(config, builder, publisher, cipher_factory, bundle_dir: Path, clock: Callable[[], datetime])`:
    - `state() -> PhonePageState`
    - `async turn_on(repository: str, token: str | None, password: str | None) -> PhonePageState` — `None` keeps the stored value; a new password makes a new salt; runs check, ensure_empty_or_ours, ensure_pages, then a forced publish; on `PublishError` stays off and re-raises.
    - `async turn_off() -> PhonePageState` — publishes only `index.html` ("This page is turned off.") and the marker, sets `enabled=False`, keeps token and password.
    - `async publish_now() -> PhonePageState` — forced publish.
    - `async tick() -> None` — when enabled: build; skip if `content_hash + salt` equals `published_hash`; skip if `published_at` is less than 10 minutes ago; else publish. Errors go to `last_error`, never raise.
    - `start()` / `async stop()` — the loop calls `tick()` every 60 s.
  - Publish content: bundle files, `data.bin` = `encrypt(snapshot json)`, each poster `encrypt_stable(bytes)` uploaded only if its path is not already in `current_blobs` (otherwise put in `reuse`), `.nojekyll`, `.what-to-do-phone-page`.

- [ ] **Step 1: Write the failing tests** with a fake publisher recording calls and a controllable clock: `test_tick_publishes_on_change_only`, `test_tick_waits_ten_minutes_between_publishes` (change at +3 min → no publish; at +10 min → publish), `test_publish_now_ignores_the_cap`, `test_known_posters_are_reused_not_uploaded`, `test_turn_on_refused_stays_off`, `test_turn_off_leaves_no_data` (published files are exactly `index.html` and the marker), `test_failed_publish_is_kept_in_state_and_retried`, `test_new_password_makes_new_salt`.
- [ ] **Step 2: Run** `.venv/bin/pytest tests/test_phone_page_service.py -q` — expected FAIL.
- [ ] **Step 3: Implement** the service and wire it into `Container.build` and the lifespan.
- [ ] **Step 4: Run** `.venv/bin/pytest -q` — expected PASS for the whole suite.
- [ ] **Step 5: Commit** `feat: phone page service`.

### Task 6: Phone page API

**Files:**
- Modify: `src/where_to_go/api/app.py` (new `ApiTag.PHONE_PAGE` with help text), `frontend/openapi.json`, `frontend/src/api/schema.d.ts` (`npm run api:types`)
- Test: `tests/test_api.py`

**Interfaces:**
- Produces:
  - `GET /phone-page` → `PhonePageState`
  - `PUT /phone-page` body `PhonePageRequest{repository: str, token: str | None, password: str | None}` → `PhonePageState`; `PublishError` → 422 with its message.
  - `DELETE /phone-page` → `PhonePageState` (turn off)
  - `POST /phone-page/publish` → `PhonePageState`; 409 when off.

- [ ] **Step 1: Write the failing tests:** `test_phone_page_turn_on_error_is_422` (fake publisher raising), `test_phone_page_state_hides_secrets` (`token`/`password` values absent from every response body).
- [ ] **Step 2: Run** `.venv/bin/pytest tests/test_api.py -q -k phone` — expected FAIL.
- [ ] **Step 3: Implement** the routes; regenerate API types.
- [ ] **Step 4: Run** `.venv/bin/pytest -q` — expected PASS.
- [ ] **Step 5: Commit** `feat: phone page API`.

### Task 7: The phone page bundle

**Files:**
- Create: `frontend/phone.html`, `frontend/vite.phone.config.ts` (input `phone.html`, `base: "./"`, `outDir: "dist/phone"`, `emptyOutDir: true`), `frontend/src/phone/main.tsx`, `PhoneApp.tsx`, `PasswordScreen.tsx`, `PlanList.tsx`, `PhoneCard.tsx`, `EventSheet.tsx`, `crypto.ts`, `snapshot.ts`, `phone.css`, tests `crypto.test.ts`, `PhoneApp.test.tsx`
- Modify: `frontend/package.json` (`build`: `tsc -b && vite build && vite build --config vite.phone.config.ts`), `frontend/tsconfig.app.json` if the new folder needs it

**Interfaces:**
- Consumes: the snapshot JSON of Task 3, the file format of Task 2, `tests/fixtures/phone_page_vector.json`.
- Produces (`crypto.ts`):
  - `deriveKey(password: string, salt: Uint8Array): Promise<CryptoKey>` (PBKDF2-SHA256, 600 000, AES-GCM 256, extractable so it can be stored)
  - `decrypt(blob: ArrayBuffer, key: CryptoKey): Promise<ArrayBuffer>`; `saltOf(blob): Uint8Array`
  - `rememberKey(key, salt)`, `rememberedKey(salt): Promise<CryptoKey | null>` (returns null when the stored salt differs), `forgetKey()`; every `localStorage` access in try/catch.
- Reuses from the app: `domain/dates` (`dayHeading`), `domain/feed` (`groupByDay`), `domain/price`, `domain/plans` (`PLANS` icons and labels), `domain/tags` (`orderTags` with `snapshot.tags`), `ui/Icon`, the card CSS variables and theme tokens. Not the API client, router, react-query or mark pickers.
- Screens:
  - Password: one field, **Open** button, "Wrong password" under the field.
  - List: header with title "Plans", the "Updated" time (warning color when older than 24 h), a **Lock** icon button; chip **Only "Going for sure"**; days with headings; cards with poster, time, title, tag, price, plan icon in its color; "No plans yet" empty state.
  - Event sheet on tap: date and time, place with map link, price, ticket or sign-up link, full description, **Open post** link; close by a button or a swipe down.
  - `phone.html` has the viewport meta, `apple-touch-icon` (the app icon) and `apple-mobile-web-app-title` "Plans", so it can sit on the Home Screen.
  - Fetches `data.bin?t=<now>` to bypass caches; posters fetched and decrypted lazily into object URLs.

- [ ] **Step 1: Write the failing tests:**

```ts
test("decrypts the backend's vector", async () => {
  const v = vector; // imported from tests/fixtures/phone_page_vector.json
  const blob = base64ToBytes(v.blob_base64).buffer;
  const key = await deriveKey(v.password, saltOf(blob));
  expect(new TextDecoder().decode(await decrypt(blob, key))).toBe(v.plaintext);
});
```

  Plus `PhoneApp.test.tsx`: `wrong_password_shows_error`, `asks_again_when_salt_changed`, `only_sure_chip_filters`, `empty_snapshot_shows_no_plans_yet`, `lock_forgets_key`.
- [ ] **Step 2: Run** `cd frontend && npm test` — expected FAIL.
- [ ] **Step 3: Implement** the bundle.
- [ ] **Step 4: Run** `cd frontend && npm test && npm run build && npm run lint` — expected PASS, and `frontend/dist/phone/phone.html` exists.
- [ ] **Step 5: Commit** `feat: phone page bundle`.

### Task 8: Phone page section in Settings

**Files:**
- Create: `frontend/src/screens/PhonePageSection.tsx`, `PhonePageSection.css`, `PhonePageSection.test.tsx`
- Modify: `frontend/src/screens/SettingsScreen.tsx` (place after "Your feed"), `frontend/src/api/queries.ts` (hooks for the four endpoints), `frontend/package.json` (a QR code library, exact version)

**Interfaces:**
- Consumes: Task 6 endpoints.
- Off state: the guide as numbered steps, each its own line with its link (create a repository: `https://github.com/new`; create a token: `https://github.com/settings/personal-access-tokens/new` with *Contents* and *Pages* read and write, only that repository); fields **Repository**, **Token**, **Password** (eye toggle); **Turn on** button; a 422 message shown under the field it concerns.
- On state: the page link with **Copy**, a QR code of it, last publish as its own line ("Published today at 18:40") or the error in the error color, **Publish now**, **Turn off**; the fields stay editable, saving them republishes. Token and password fields show "Saved" placeholders when set, never the values.

- [ ] **Step 1: Write the failing tests:** `shows_guide_when_off`, `turn_on_error_appears_under_field`, `on_state_shows_link_qr_and_last_publish`, `secret_fields_never_show_values`.
- [ ] **Step 2: Run** `cd frontend && npm test` — expected FAIL.
- [ ] **Step 3: Implement** the section.
- [ ] **Step 4: Run** `cd frontend && npm test && npm run lint` — expected PASS.
- [ ] **Step 5: Commit** `feat: phone page settings section`.

### Task 9: Docs and end-to-end check on screen

**Files:**
- Modify: `README.md` (feature section "Your plans on the phone" with a screenshot), `docs/superpowers/specs/2026-11-17-phone-page-design.md` ("When the app publishes": the 60-second check loop)

- [ ] **Step 1:** Ask Max in chat before creating anything on GitHub: a public test repository `what-to-do-phone-test` and a token for it (Max creates the token himself). Run the branch's app on a copy of the data (never the prod copy).
- [ ] **Step 2:** Turn on in Settings; check on screen: the guide, errors for a wrong repository and a repository with foreign files, the on state with link and QR.
- [ ] **Step 3:** Open the site in the built-in browser at mobile size (375×812), light and dark: password screen, wrong password, the list, the chip, the event sheet, a poster, Lock. Screenshot each and send them to Max.
- [ ] **Step 4:** Mark an event on the laptop; within 10 minutes plus the Pages build it appears on the site; "Updated" time moves.
- [ ] **Step 5:** Turn off; the site shows "This page is turned off"; the repository holds only `index.html` and the marker.
- [ ] **Step 6:** `make test` and `cd frontend && npm run lint` green; commit `docs: phone page`.
- [ ] **Step 7:** Merge to master and release with the `release` skill, as CLAUDE.md requires; delete the test repository only with Max's OK.
