# Instagram sources: public profiles next to Telegram channels and websites

## Why

Max found a venue he cares about, Esthetic Joys Embassy in Belgrade (instagram.com/eje.belgrade), that announces its program only on Instagram: no website, no Telegram channel. Its monthly program is a poster in a pinned post, and its weekly program with times is a story in the pinned highlight "timetable". The app has to read such a profile the same way it reads a channel, without anyone logging in to Instagram.

## Goals

- Adding an Instagram profile is as simple as adding a channel: paste the link (or `@name` and pick Instagram), see what will be read, confirm.
- Posts and pinned stories (highlights) of a public profile reach the existing pipeline: photo transcription, Claude reading, merging duplicates.
- Everything Instagram gives without a login is collected, including the frames of videos, not only their covers; what to send to Claude is decided after.
- Per source the user picks what is read: posts, pinned stories, or both. Both by default.

## Non-goals

- Active 24-hour stories: Instagram serves their page empty to a logged-out visitor.
- The sound of videos and anything said in them.
- Instagram accounts as potential sources (mentions like `@scruscru`): a separate task.
- Private profiles.

## Anti-goals

- Any Instagram login, cookie, session or account of the user, in the app or in tests.
- Old content flooding Claude: a profile with 100+ pinned stories must not send them all on the first refresh.
- A broken Instagram source stopping the refresh or retrying in a loop.

## What is known (scouting on 17.11.2026, all with curl, no cookies)

- `GET https://www.instagram.com/<name>/` with browser-like headers (`User-Agent` of desktop Chrome, `Accept`, `Accept-Language`, `Sec-Fetch-*`, `sec-ch-ua*`, `Upgrade-Insecure-Requests`) returns 200 and ~170 KB of HTML. Without the `Sec-Fetch-*`/`sec-ch-ua*` headers the page comes without the data below.
- The page config says `"USER_ID":"0"`: the visitor is anonymous.
- Data lives in `<script type="application/json">` blocks (Relay preloader `PolarisLoggedOutDesktopWWWProfilePostsTabContentQuery`):
  - `xig_user_by_username.polaris_ordered_timeline_connection.edges[].node`: the 12 latest posts. Per post: `pk` (int), `code` (shortcode), `__typename` (`XIGPolarisImageMedia`, `XIGPolarisCarouselMedia`, `XIGPolarisVideoMedia`), `caption.text` (full, up to ~1000 chars seen), `display_uri` (640 px image), `accessibility_caption` ("Photo by … on November 05, 2026. …"), `carousel_media_count`. No exact time. `page_info.has_next_page` is true, but a logged-out visitor cannot page further.
  - `lox_highlights_connection.edges[].node`: highlights with `id` and `title` (EJE: timetable, food, breakfast, full menu, press, drinks, NY 2026).
  - `latest_reel_media`: time of the latest active story (not readable logged out).
  - The full name of the profile (for the source title) and the biography.
- `GET https://www.instagram.com/<name>/p/<code>/` (and `/reel/<code>/`): `taken_at` (exact time), `carousel_media` (every image of a carousel), `location` (name, lat, lng), `video_versions` (mp4 URL) for videos, the caption.
- `GET https://www.instagram.com/stories/highlights/<id>/`: every story of the highlight in `items[]` (EJE: 1, 23, 6, 9, 24, 9, 35 stories). Per story: `pk`, `taken_at`, `image_versions2.candidates[].url` (for a video it is its cover frame), `video_versions` for videos. A story can sit in several highlights; `pk` is the same.
- `GET https://www.instagram.com/stories/<name>/`: no stories in the HTML for a logged-out visitor.
- Images and videos on `scontent.cdninstagram.com` download without cookies; their URLs are signed and expire.
- The old JSON endpoint `/api/v1/users/web_profile_info/` returns 404 on both hosts.
- Limits: 30 requests (30 s and 5 s apart) and then 390 requests with growing rate (every 2 s, 1 s, 0.5 s, back to back at ~1/s): all 200, all with 12 posts, no refusal. How a refusal looks and how long it lasts is unknown.

## Approaches

1. **A new source type that reads the public profile HTML anonymously** (chosen). Same interface as Telegram and websites (`SourceType`); the refresh, photos, reading and merging stay shared. Works for every user of the app with no setup.
2. **Instagram Graph API (Business Discovery).** Official and stable, but every user would need an Instagram professional account, a Facebook page and a Meta app with a token; only business profiles are readable. Rejected: too heavy for a desktop app; kept as a fallback if the anonymous page closes.
3. **A logged-in session (instaloader-style).** Reads active stories too, but puts the user's account at risk. Rejected by Max.

A browser inside the app was never an option: the app has none.

## How it works for Max

1. **Sources** → the add field accepts `instagram.com/<name>` (with or without `https://`, `www.`, a trailing slash or query), next to `t.me/…` and website links. The placeholder mentions Instagram.
2. **A bare name or `@name`** (no link) is ambiguous. A selector appears right after the field: **Telegram** and **Instagram**, nothing chosen. The add button stays disabled until one is picked. A link never shows the selector. Telegram names never have dots and Instagram names may, so:
   - `@eje.belgrade` (an `@`, a dot, no slash) can only be Instagram: no selector, it goes to Instagram.
   - `eje.belgrade` without `@` still looks like a website address and goes to the website check, as today.
   - `@name` or `name` that is valid for both (letters, digits, underscores, 5–30 characters, starts with a letter) shows the selector.
3. For an Instagram profile the app shows a preview card (in the style of the website preview): the profile name and link, then **What to read** with two checkboxes, both on:
   - **Posts**: "12 latest, then every new one"
   - **Pinned stories**: "N highlights; stories up to 30 days old, then every new one"
   Buttons **Cancel** and **Add**. With both checkboxes off the add button is disabled.
4. Errors instead of the preview: "This Instagram profile doesn't exist", "This Instagram profile is private", "Instagram didn't respond", "Instagram refused to show the profile; try again later".
5. An added profile stands in the source list with its own icon (Instagram's), a link to the profile and the same actions: rename, star, pause, delete. Its row also lets the user change **Posts** / **Pinned stories** later.
   - Turning one off works like pause for that kind: it is no longer collected; what was already stored and its cards stay, and it is not re-read when the reading rules change.
   - Turning it on again collects it from the next refresh by the same rules as at adding: the 12 latest posts, stories up to 30 days old.
6. A card built from a post has **Open post** leading to the post; from a story, to its highlight (a pinned story has no lasting link of its own).

## Reading

### What a refresh fetches for one profile

1. The profile page. Gives the 12 latest posts and the list of highlights.
2. If **Posts** is on: for every post not stored yet, its own page (exact time, all carousel images, location, video URL). Usually 0–2 pages per refresh.
3. If **Pinned stories** is on: every highlight page. Stories already stored are skipped by `pk`, whichever highlight they are in.
4. Media of new posts and stories only: images, and videos for frames (below).

Requests to instagram.com go one after another with a short pause (about 1 s) between them, **across all Instagram sources of a refresh** (one shared limiter), even though the refresh collects up to 4 sources at once. Media downloads from the CDN are not limited this way. EJE costs ~10 requests per refresh.

### Mentions in captions

Instagram captions are full of `@instagram_accounts`. Claude reads them as Telegram channels today (`channels` in the reading result), which would put wrong leads into **Potential sources**. For posts of Instagram sources only real `t.me/…` links are kept as potential sources; `@mentions` are dropped. Instagram accounts as leads stay a separate task.

### What becomes a post in the app

- **An Instagram post** → one `CollectedPost`: `external_id` = `pk`, `url` = `https://www.instagram.com/p/<code>/`, `published_at` = `taken_at`, `text` = the caption plus the place name (e.g. "Place: EJE Belgrade") when the post has a location, images = every carousel image (or the single image), plus video frames.
- **A story** → one `CollectedPost`: `external_id` = `pk`, `url` = the highlight's link, `published_at` = `taken_at`, `text` = "Pinned story from the highlight «<title>»" (a story has no caption), images = its image, plus video frames.
- Post and story `pk`s are unique across Instagram, so both live in one source without clashes.

### Which ones go to Claude

- **Posts**: like a Telegram channel. Every post not stored yet among the 12 is stored and read. When the reading rules change, the latest `recent_posts` posts are read again, as for Telegram.
- **Stories**: a story not stored yet is stored and read only if it is **younger than 30 days at the moment it is first seen**. Older stories are remembered (stored as skipped, never read), so they never come back on later refreshes. In practice: the first refresh after adding takes the fresh stories of every highlight; later, every new story is younger than 30 days anyway and is read. EJE today: ~10 stories instead of 107.
- Changing the reading rules re-reads only stories whose events may still be ahead: the ones younger than 30 days.

### Videos: everything that can be read

For a video (reel, video post, video story) the app downloads the mp4 (the smallest rendition Instagram offers that is at least 480 px wide) and takes frames from it:

- a frame every 2 seconds, plus the first one;
- frames that look the same as the one kept before them are dropped (compare small grayscale thumbnails);
- at most 6 frames per video, spread over its length.

The kept frames are stored as JPEG images of the post, after its cover. They go through the same photo transcription as any photo, so Claude reads the text that appears later in the video. A video that cannot be downloaded or decoded leaves just its cover; it is not an error of the source. Frames are decoded with PyAV (a Python package that bundles ffmpeg; no system ffmpeg needed). PyAV 19 has wheels for macOS x86_64 (11+) and arm64 (14+); the app needs macOS 14, so both disk images get it. A guard test, like the one for Intel `cryptography` wheels, keeps the dependency on a version with both wheels.

## When Instagram refuses

- A refusal is any answer to the profile page that is not 200 with the profile data: 429, a redirect to the login page, a page without the data, a network error.
- The source gets the error text next to it ("Instagram refused to show the profile; will try again on the next refresh"), as a broken Telegram channel does. The rest of the refresh goes on.
- No retries within a refresh, no backoff state: the next refresh tries again.
- The answer of the refusal (status, headers, first 2 KB of the body) goes to the app log, so the first real refusal can be studied.
- A refused highlight or post page after a good profile page is the same: error on the source, whatever was collected before it is kept.

## Data

- `SourceKind.INSTAGRAM = "instagram"`. `handle` = the profile name in lower case, `title` = the profile's full name (or the name).
- Per Instagram source, what to read: `posts` and `stories` flags (both true by default), in a table `instagram_profiles` keyed by `source_id`, like `web_sites`. A migration adds it.
- Skipped old stories: stored as posts marked processed without reading, so `known_ids` covers them. (Exact marking is the builder's call, as long as they never reach Claude, never show in **Original** and never count as the source's events.)
- `SourcePublic.url` for Instagram: `https://www.instagram.com/<handle>/`.
- The API: `POST /sources/preview` returns the Instagram preview (name, link, number of highlights); `POST /sources` takes the two flags and the picked kind for a bare name; a new endpoint (or the existing `PATCH /sources/{id}`) changes the flags.

## Testing

- Parsers are tested on saved HTML fixtures of EJE (profile, a post, a reel, a highlight, the empty active-stories page). Fixtures must not hold anything of the user; they are anonymous pages, so the `USER_ID` is 0.
- The refresh with an Instagram source is tested with respx, like Telegram and websites: new posts, already known posts, the 30-day rule for stories, a story in two highlights, a refusal.
- Frame extraction is tested on a tiny generated video (a few seconds with changing and repeating frames).
- In the real app on a copy of the data: add eje.belgrade, refresh, see the cards from the November poster and the "timetable" story, check **Original**.

## Left to the builder

- How the add form shows the Telegram/Instagram selector exactly, within the app's design system and Max's UI rules (no lists joined with dots or slashes; each fact its own element).
- The exact Instagram icon (a simple glyph, like the globe for websites).
- How skipped stories are stored, within the rule above.
- The pause between requests (about 1 s) and the 2-second frame step: tune if tests show a better value.
