# Web sources: event websites next to Telegram channels

## Why

Max wants events from event websites to reach the app the same way as from Telegram channels. The first website is polakohedonist.club (events in Belgrade and Novi Sad). Websites must be connected without code for each one: a website is a record in the sources, not a class in the code.

## Goals

- Adding a website is as simple as adding a channel: paste a link to any event of the site, see what was found, confirm.
- A general mechanism that knows nothing about specific websites. Polako is the first, but not a special case.
- Only the clean gist of an event goes to Claude (like a channel post), not HTML.
- From there, events go through the same pipeline: Claude, merging duplicates with the same events from Telegram, tags, description language.

## Non-goals

- Websites without a sitemap and without schema.org `Event` markup. Such a website gets a clear refusal when added; other ways are a separate task.
- Getting around bot protection (Cloudflare challenge, captchas). If a website turns it on, the source gets an error, like a broken channel.
- Internal website APIs (Polako's `/api/*` is closed in robots.txt).

## Anti-goals

- Raw HTML or the whole page sent to Claude.
- Code that mentions polakohedonist.club, its addresses or fields.
- Thousands of Claude calls per refresh: only events within the horizon go to Claude, each once.

## What is known about Polako (scouting on 15.11.2026)

- No captcha; Cloudflare is there, but plain requests are served with code 200.
- robots.txt opens the event pages and the sitemap and closes `/api/*`.
- sitemap.xml: ~3200 addresses, 820 events per language among them (`/ru/events/…`, `/sr/events/…`, `/en/events/…`), plus category pages `/ru/events/category/…` (without an `Event` block). `lastmod` is the same everywhere (the generation date), so it can't be relied on.
- The events page `/ru/events` is rendered in the browser: its HTML has no links to events. The only feed is the sitemap.
- Every event page (9 checked) has a `<script type="application/ld+json">` with `"@type": "Event"`: `name`, `description` (markdown, ~600–1500 characters), `image`, `startDate`, `endDate`, `location` (`name`, `address.streetAddress`, `address.addressLocality`), sometimes `offers` (price), `organizer` (for Polako it is "Event Catalog", an aggregator).
- **The time is labelled UTC but is local time:** `"startDate": "2026-11-18T19:00:00.000Z"` for an event at 19:00 Belgrade time. Eventbrite and Meetup write an honest offset (`+01:00`).
- Other websites: Eventbrite and Meetup have an `Event` block; robots.txt names a sitemap at KudaGo, Timepad, Resident Advisor and Luma, but not at tickets.rs. Eventbrite's `description` in the block is 12 characters.

## Approaches

1. **A general web source: sitemap feed + address template + schema.org `Event` block → a text "post" → the existing pipeline** (chosen). A website is described by data, and one piece of code serves all websites; Claude gets ~1 KB of facts instead of a ~270 KB page.
2. **The `Event` block straight into a card, without Claude.** Cheaper, but tags, description language and merging duplicates would need a second pipeline. Rejected: Claude is needed for descriptions and merging anyway.
3. **A separate parser per website in the code.** Rejected by Max: every new website means new code.

## How it works for Max

1. **Sources** → the add field accepts both `t.me/channel` and a link to an event page of a website.
2. For a website link, the app checks the site in a few seconds and shows a preview: the site name, how many event pages were found, three examples (title and date on separate lines). **Cancel** and **Add** buttons.
3. If the website doesn't fit, a clear error instead of the preview: "The site has no page list (sitemap)", "The page has no event markup", "The site doesn't respond" and so on.
4. An added website stands in the source list next to the channels, with its own icon (a globe instead of the Telegram icon), a link to the site and the same actions: rename, star, delete. **Refresh** takes events from it too.

## Algorithm (general, knows nothing about the site)

### When adding (`WebSiteProbe`)

1. The link gives the site (`https://host`) and the **section prefix**: the link's path without its last segment (`/ru/events/iskusstvo-…` → `/ru/events/`). The prefix automatically cuts off other languages and other sections.
2. The page at the link is downloaded; it must have an `Event` block. If not, the refusal "the page has no event markup".
3. The sitemap is looked up: `Sitemap:` lines in `/robots.txt`, otherwise `/sitemap.xml`. Sitemap indexes (nested sitemaps) and gzip are supported. If none, a refusal.
4. Addresses with the prefix are taken from the sitemap. Zero means a refusal.
5. **Time:** decide whether the offset in `startDate` is honest. Rule: if the time in the block has a `Z`/`+00:00` offset, and the visible text of the page has the same "HH:MM" as written and not the time converted to the city's time zone, the time is considered local (`times_are_local = true`). Checked on the opened page and on 2 examples.
6. The preview shows "Found N event pages" (the number of addresses with the prefix) and three examples from the opened pages. How many of them fall within 30 days is unknown without downloading every page, so the preview doesn't show that number: it appears on the source after the first refresh.

The saved source: `kind = web`, `handle` = site + prefix (`polakohedonist.club/ru/events/`), `title` = `og:site_name` or the host name, plus the web source settings (sitemap, prefix, `times_are_local`, horizon in days = 30).

### When refreshing (`WebSiteReader`)

1. Download the sitemap and pick the addresses with the prefix.
2. **New addresses** (not yet in the source's page table) are downloaded, their `Event` block extracted and remembered in the page table: address, start date, when checked. A page without a block is remembered as "not an event" and never downloaded again.
3. **Recheck:** pages of known events dated within the next 7 days are downloaded again (reschedules and cancellations). If the text of the facts changed, the post is updated and read by Claude again.
4. A page dated within the horizon (today … +30 days) that is not a post yet becomes a post. Pages beyond the horizon wait: when the date enters the horizon, the post appears without downloading the page again.
5. Addresses that disappeared from the sitemap are left alone (the cards already exist; a deleted event just stops being updated).
6. Page downloads: at most 4 at once, with the app's honest User-Agent; an error on one page doesn't fail the source, a sitemap error is a source error (as with a channel).

First run on Polako: ~820 page downloads (no Claude, a few minutes), ~450–500 events to Claude; after that, dozens of new ones a day.

### What becomes a "post"

Text from the block's fields, in one form for all websites:

```
The Art of Being Awkward
Start: 2026-11-18 19:00
End: 2026-11-18 21:00
Place: Restoran Tri, Svetogorska, 46, Belgrade
Price: 0 RSD                      (if there are offers)
Organizer: Event Catalog          (if present)

<description>
```

- The post's `url` is the page address; `published_at` is when the page was first found; the picture is `image` (saved locally, as for channels).
- If `description` is shorter than ~200 characters (as at Eventbrite), the visible text of the page's main part (`<main>`/`<article>`, otherwise `<body>`) is added to it, cleaned the same way as Telegram posts and cut to a reasonable length.
- The time is written already converted to the city's time zone, taking `times_are_local` into account.

## Changes to existing code

- `SourceKind.WEB`; `SourcePublic.url` depends on the kind (channel → t.me, website → section address).
- Today `TelegramChannelReader` is hard-wired into `RefreshService` and `SourceCatalog`. A "source reader" interface is introduced (new posts of a source; title/check when adding) with two implementations, picked by `source.kind`.
- `Post.external_id` is an integer; for web posts it is the row id in the new page table, so the `posts` schema doesn't change.
- New tables: web source settings (sitemap, prefix, `times_are_local`, horizon) and web source pages (address, start date, "not an event" flag, when checked, facts fingerprint, post id). Created by `create_all`, no migration needed.
- `PostRepository.to_read`: for web sources the "last `recent`" rule doesn't apply; unread posts are read.
- The default extraction and matching prompts say "Telegram channel posts"; they need to be generalized to "posts from Telegram channels and event pages of websites" (see the decisions after review). The rule "the channel organizes the event itself" (`is_organizer`) gives false for aggregator websites.
- Claude's photo transcription (`PhotoTranscriber`) isn't needed for web posts: the facts are already text. The picture is only saved for the card.
- **Potential sources** work as is: t.me links in event descriptions get there.
- API: `POST /sources` accepts a website link; a new preview endpoint `POST /sources/preview` (link → kind, title, number of pages found, examples or a clear error), so the frontend can show a preview before adding.
- Frontend: the add field accepts both links; a preview before adding a website; a source kind icon in the list.

## Decisions after the design review (mine, Max may correct them)

- **The time check showed nothing** (the page text has no "HH:MM", or the examples contradict each other): trust the offset as the site writes it (`times_are_local = false`). This is the standard behavior; for Polako the check is unambiguous: the page text says "at 19:00" for `19:00Z`.
- **Prompts.** The defaults in `prompts.py` are updated. Max hasn't changed his prompts in the settings (they aren't in the `settings` table), so the change reaches him by itself. A prompt changed by the user is not touched. `ReadingRules` are not bumped: by their own rule, a prompt change applies to new posts and doesn't reread old ones. The `channel` field in the request to Claude keeps its name (it holds the source name, channel or website), so reading Telegram posts doesn't change.
- **Multi-day events.** An event is within the horizon if its period [`startDate`, `endDate` or `startDate`] overlaps [today, today + 30 days]: a running exhibition makes it. A page without `startDate` is not an event.
- **A changed page and manual merging.** As with Telegram: a post whose events Max merged or split by hand is not reread, since the manual decision matters more. Other changed pages are reread.

## Decisions left to the implementer

- Exact class names and module layout (suggestion: `web.py` for the general web layer: sitemap, `Event` markup, page text; `web_sources.py` for reading a web source and checking it when adding).
- How web source settings are stored (a separate table or columns), provided existing tables change only by adding columns with a default.
- The look of the preview in the UI: in the style of the existing sources screen; no lists separated by "·" (Max's rule).

## Verification

- Tests of the general web layer on saved pages from Polako, Eventbrite and Meetup (fixtures in `tests/`), including sitemap index and gzip, a page without a block, a wrong `Z`.
- A run on a copy of the data (not Max's working data): add Polako, refresh, see the cards in the feed, merging with an event that already came from Telegram, the right time (19:00, not 20:00).
- With your own eyes in the app: adding with a preview, an error for an unsuitable website, the website in the source list, a card with an "original" button leading to the website's page.
