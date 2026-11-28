# Source order and partial refresh

## Why

Reading with Claude or Codex spends a subscription limit; a big refresh can take a fifth of ChatGPT Plus's five-hour
window. Max wants his favourite sources read first, and a way to read only a slice when the limit is low.

## What Max decided

- Two small releases, in this order.
- **Release 1:** the user orders sources in Settings' Sources screen. A refresh still downloads everything; photos and
  posts go to the reader top to bottom by that order.
- **Release 2:** next to **Refresh**, a second button **Refresh N**. It downloads everything too, but sends only the
  first N unread posts (with their photos) to the reader, in source order. Pressing it again reads the next N.
  Plain **Refresh** reads everything left. N is a setting; default **30** posts.

## Facts (code as of 1.31.0)

- Refresh already has two stages: collect all sources (`refresh.py:296-298`), then read posts that are not read yet
  (`PostRepository.to_read`, `processed_at` marks a read post). Unread posts left over are read next time. No new
  status model is needed.
- Sources are listed by title (`repositories.py:163`) and the Sources screen puts favourites first
  (`SourcesScreen.tsx:170`). Posts are read oldest first (`to_read` sorts by `published_at`).
- Tags already have drag ordering (`Tag.position`, `PUT /tags/order`, `TagRepository.reorder`): the pattern to follow.

## Design

### Release 1: source order

- `Source.position: int` (per city), added to existing tables by the existing column-adding migration. Existing
  sources get positions in today's visible order: favourites first, then by title. A new source goes last.
- `PUT /sources/order` with the active city's source ids in the new order (same rules as `PUT /tags/order`: all ids
  of the city, else 422). `GET /sources` returns sources by position.
- Sources screen: rows can be dragged to reorder, like tags (same interaction and styles). The favourite star stays a
  mark and no longer moves a source to the top.
- Reading order: `to_read` returns posts sorted by source position, then **newest first** inside a source (new posts
  announce upcoming events). Photos are transcribed in the same post order, and batches keep it. Concurrency stays;
  batches start in order, so order is "approximately first" by design.
- Paused sources are skipped as today.

### Release 2: Refresh N

- Setting `partial_refresh_posts: int`, default 30, 1..500, in Settings next to "Recent posts per channel", with a hint
  that says what it is for.
- `POST /refresh` takes an optional `limit` (posts). With a limit: collect everything as today; then take the first
  `limit` posts of the ordered `to_read` list (after linked posts are added); transcribe only those posts' photos;
  read them; merge. Without a limit: unchanged.
- Progress tells how many unread posts are left after a limited refresh (`posts_left`), shown under the button as its
  own line ("12 posts left to read").
- UI: a second button next to **Refresh**, label **Refresh 30** (the number from settings), with a tooltip saying it
  downloads everything and reads only the next 30 posts in source order. Both buttons disabled while a refresh runs.
- A post dropped because its photos could not be read counts toward the limit (it was attempted).

## Non-goals

- Limits by calls, photos or plan percentage. Automatic stopping at a plan limit.
- Per-source limits.

## Verification before each release

Tests for ordering, migration of positions, the reorder API, the limit slicing, photos only of chosen posts,
`posts_left`; on screen in the built app on the dev copy's data (never Max's real data folder): drag sources, refresh reads in the new order (by the
order of read posts in the database), Refresh 30 reads 30 posts and says how many are left.
