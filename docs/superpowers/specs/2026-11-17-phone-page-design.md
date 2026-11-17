# Phone page: the plans list on GitHub Pages, behind a password

## Why

The app lives on the laptop, and so does the list of events Max plans to go to. Away from the laptop, with only the phone, there is no way to check what is on tonight. Max wants a read-only copy of that list on the phone, kept up to date by the app on its own.

## Goals

- On the phone, open a bookmark (or a Home Screen icon) and see the upcoming events marked "Going for sure" and "Maybe going", by day, looking like the app.
- The app republishes the list by itself whenever it changes: no button to remember.
- Nobody but Max can read the list, although the site and its repository are public.
- Works for any user of the app, not only Max: an optional feature switched on in Settings.

## Non-goals

- Editing anything on the phone: no marks, no ratings, no undo. The page is a snapshot.
- A native iOS or Android app, push notifications, offline sync beyond what the browser caches.
- Publishing the feed, the past plans, sources or settings. Only upcoming plans.
- Hosting other than GitHub Pages.

## Anti-goals

- Event data readable by anyone in the repository or on the site, even for a moment (no plaintext commit "to be encrypted later").
- The password or the GitHub token leaving the laptop for anywhere other than GitHub (the token) and nowhere at all (the password).
- A repository whose history grows with every publish until it weighs gigabytes of posters.
- Publishing noise: a commit on every single click, or GitHub Pages builds hitting its rate limit.

## Constraints (checked)

- **A GitHub Pages site is public on any plan except GitHub Enterprise Cloud.** Access control exists only there ([docs](https://docs.github.com/en/enterprise-cloud@latest/pages/getting-started-with-github-pages/about-privately-published-github-pages-sites)). So privacy must come from encryption, not from GitHub.
- The app runs on macOS, Linux and Windows and must not require `git` or `gh` to be installed. Publishing goes through the GitHub REST API over `httpx`, which is already a dependency.
- Frontend and backend are strictly separate: the backend builds, encrypts and publishes the snapshot; the phone page is a separate presentation layer that only reads it.
- English everywhere in the interface and code (tests/test_english_only.py); event data stays in its own language.

## Approaches

1. **GitHub Pages, encrypted snapshot** (chosen by Max). The app pushes a static page plus an encrypted data file to a public repository. The page asks for a password once, decrypts in the browser with WebCrypto and draws the list. Free, no new account, real privacy through encryption.
2. **Apple Calendar through iCloud.** The app writes the plans into a dedicated calendar; iCloud carries it to the iPhone. No server and works offline, but it looks like a calendar, not like the app: no posters, no descriptions, Apple-only. Rejected for now; can come later as a separate feature.
3. **Cloudflare Pages + Cloudflare Access.** True access control with e-mail login, also free, but one more account and a setup too heavy for other users of the app. Rejected.

## How it works for Max

### Setting it up (once)

**Settings** get a new section **Phone page**:

1. A short guide with a link: create an empty public repository on GitHub (any name, e.g. `what-to-do-plans`) and a fine-grained token limited to that one repository with permissions *Contents: read and write* and *Pages: read and write*. Each step on its own line with its own link.
2. Fields: **Repository** (`owner/name`), **Token**, **Password** (with a show/hide eye; this is the password typed on the phone).
3. **Turn on** button. The app checks the token and the repository, turns on GitHub Pages for it (source: the `main` branch, root) if it is off, and makes the first publish. Errors are shown in plain words next to the field they concern ("The token has no access to this repository", "Repository not found", "The token expired").
4. Once on, the section shows: the page link with a **Copy** button and a QR code to open it on the phone; the state of the last publish (time, or the error); a **Publish now** button; a **Turn off** button.

Changing the password republishes with the new one; the phone then asks for it again.

**Turn on refuses a repository that holds anything else.** Every publish replaces the whole `main` branch, so the app only publishes to a repository that is empty, holds nothing but what GitHub's "Add a README / .gitignore / license" boxes create, or carries the app's marker file `.what-to-do-phone-page` from an earlier publish. Anything else gets the error "This repository already has other files. Create a new empty one." (builder's call, settled in review)

**Turn off** stops publishing and replaces the repository contents with a single commit holding only a plain "This page is turned off" `index.html` and the marker file, so no encrypted plans stay on the site. GitHub Pages stays on, the repository is not deleted, and the token and password stay stored so turning it back on is one click; typing new ones replaces them. Forgetting them without replacing is not built (a follow-up if needed). (builder's call, settled in review)

### On the phone

1. Max opens the link. The first time, the page shows one password field and an **Open** button. A wrong password says so and stays on the field.
2. The password is remembered on the phone, so later visits open the list straight away. A small **Lock** action in the header forgets it.
3. The list: the same as **Plans → Upcoming** in the app for the city that was active when publishing. Cards grouped by day with the day header, each card with poster, time, title, tag, price and the plan mark (its icon and color, as in the app). An **Only "Going for sure"** chip, like in the app.
4. Tapping a card opens its details: date and time, place with a map link, price, the ticket or sign-up link, the full description, the link to the original post. Read-only, no mark buttons.
5. In the header, when the snapshot was made ("Updated today at 18:40"), so Max knows how fresh it is. If it is older than a day the time is shown in the warning color: the laptop may be asleep.
6. Empty list: "No plans yet" in the app's empty-state style.

Sketch:

```
┌──────────────────────────────┐
│ Plans          Updated 18:40 🔒│
│ [Only "Going for sure"]       │
├──────────────────────────────┤
│ Today, Mon 17 Nov             │
│ ┌──────┬───────────────────┐ │
│ │poster│ 19:00   ✓          │ │
│ │      │ Jazz at Dorćol     │ │
│ │      │ #music   800 RSD   │ │
│ └──────┴───────────────────┘ │
│ Tomorrow, Tue 18 Nov          │
│ ...                           │
└──────────────────────────────┘
```

## When the app publishes

- Once a minute, while the page is on, the app rebuilds the snapshot (one feed query) and publishes when it differs from the last published one. This catches every change: marks, refreshes, manual merges, reschedules, a new active city and the date rolling over at midnight. (builder's call, replaces the trigger list and the 30-second wait of the first draft)
- The app publishes at most once every 10 minutes. GitHub documents a soft limit of 10 Pages builds an hour for branch-built sites, so 6 publishes an hour leaves room. **Publish now** and **Turn on** ignore the cap.
- "Differs" means a hash of the plaintext data, the page bundle and the salt: a new password or a new app release also republishes.
- If the laptop is asleep or the app is closed, nothing is published; the page keeps showing the last snapshot with its time.
- A failed publish is shown in Settings and retried automatically 10 minutes later; it never interrupts the app.

## What is published

The repository holds exactly these files, replaced as a whole on every publish:

- `index.html`, the page's JavaScript and CSS: the phone page bundle. The same for every user; contains no data.
- `data.bin`: the encrypted snapshot.
- `images/<id>.bin`: each poster, resized and encrypted separately, so the main data stays small.
- `.nojekyll` and the marker file `.what-to-do-phone-page`.

**Snapshot contents** (before encryption, JSON): the time it was made, the city (name, time zone), and the upcoming occurrences with plan "sure" or "maybe" from today on, exactly as the app's feed query returns them for the Plans screen (`start = today`, `plans = [maybe, sure]`), with the fields the card and the details window need. The list is taken from the existing feed logic, not from new rules.

**Posters:** each event's main photo as the app already stores it, encrypted, without resizing. Stored posters average about 60 KB (954 files, 56 MB in Max's data on 17.11.2026), small enough for a phone, so no image library (Pillow) is added. An event without a photo is shown like in the app. (builder's call, settled in review)

**Cost on the laptop:** a publish must stay light, a background task that never blocks the app. A poster's encrypted bytes are cached by image name (the IV is an HMAC of the poster's bytes under the key, so an IV never repeats for different contents and the same poster encrypts to the same bytes), and its blob is uploaded only when it is not already in the current tree; a typical publish then uploads one blob for `data.bin` plus a tree, a commit and a ref update, about five small HTTP requests. The key is derived once per password, not per publish. GitHub then rebuilds the site on its side in about a minute.

**History:** every publish is a single commit without a parent, and `main` is moved to it with a forced ref update. The repository therefore always has one commit; old posters and snapshots become unreachable and are collected by GitHub. This uses the Git Data API: create blobs, a tree, a commit with no parents, then `PATCH refs/heads/main` with `force: true`.

## Encryption

- AES-256-GCM. The key is derived from the password with PBKDF2-SHA256, 600 000 iterations, a random 16-byte salt.
- A new salt is generated when the password changes, not on every publish, so the phone can keep the derived key. Every file gets its own random 12-byte IV.
- `data.bin` and every `images/*.bin`: a small header (format version, salt, IV) followed by the ciphertext.
- In the browser: WebCrypto derives the key once, checks it by decrypting `data.bin`, and keeps the derived key (not the password) in `localStorage` together with the salt. If the published salt differs from the stored one (the password was changed), the page asks for the password again.
- On the laptop the password and the token are stored where the app keeps its other settings, but are never returned by the settings API in plaintext (the API says only whether they are set) and never written to logs.

## Architecture

**Backend** (Python, in `src/where_to_go/`), new classes:

- `PhoneSnapshot`: builds the snapshot from the existing `Feed` for the active city and today, exactly like the Plans screen.
- `SnapshotCipher`: derives the key and encrypts bytes into the file format above.
- `GitHubPagesPublisher`: talks to the GitHub REST API (check access, turn Pages on, replace the repository contents with one parentless commit). Knows nothing about events.
- `PhonePageService`: owns the triggers, the 30-second and 5-minute coalescing, the "nothing changed" check, the last-publish state, and glues the three above together. Registered in the `Container` like other services.
- Settings: `phone_page_repository`, `phone_page_token`, `phone_page_password`, `phone_page_enabled` in `AppSettings`, plus the salt.
- API: endpoints for the Settings section (turn on, turn off, publish now, state).

**Phone page** (frontend): a second Vite entry in `frontend/` producing a separate small bundle. It reuses the domain helpers (`dates`, `price`, `plans`, `tags`) and the card's look (styles and icons), but not the app's screens, routing or API client: its only input is the decrypted snapshot. Mobile-first, light and dark theme like the app. The backend ships this built bundle with the app and uploads it on every publish, so a new app release also updates the page.

## Testing

- Backend unit tests: snapshot contents match the Plans query (sure and maybe, from today, active city only); encryption round-trip and the file format; the coalescing timer (30 s, 10 min, Publish now); Turn on refusing a repository with foreign files; Turn off leaving no data; "nothing changed" skip; publisher against a fake GitHub API (parentless commit, forced ref, Pages turned on, error mapping).
- Frontend tests: decrypting a snapshot made by the backend's cipher (a shared test vector), wrong password, changed salt, empty list, the "Only Going for sure" chip.
- By hand before merge: a test repository and token, the page opened in a phone-sized browser and on Max's iPhone: first open with the password, remembered password, Lock, a new mark on the laptop appearing on the phone after the next publish, a poster, the details window, light and dark theme. Max's real data is used only through a copy.

## Left to the builder

- The exact file header layout and the snapshot JSON field names.
- Where the token and password live (the existing settings storage, or the system keychain if a cross-platform way is already at hand) as long as the API never returns them.
- The exact wording of the guide and the errors, and the QR code library.
- How the phone page bundle is built and packaged next to the main frontend.
