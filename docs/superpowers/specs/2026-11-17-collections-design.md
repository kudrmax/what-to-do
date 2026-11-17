# Collections

## Intent

Max wants to keep fun, unusual, interesting events "for history". A personal feature, off by default; it is
switched on in Settings → Advanced.

## Goals

- A heart button in the card's top-right corner (on the photo when there is one; otherwise the meta row leaves
  the corner free). Filled when the event is in any collection. The same button in the event window.
- A click opens a menu of collections with check marks; an event may be in several.
- Settings → Advanced: a "Collections" switch; when on, a list of collections to add, rename and delete
  (deleting a non-empty one asks first).
- A "Collections" item in the sidebar while the feature is on and at least one collection exists. It shows the
  usual feed of the chosen collection with the usual filters: every date, past and future, newest first. Plans
  do not affect what is shown.

## Non-goals

- The phone page shows no collections.
- Switching the feature off only hides it; collections and their events stay.

## Decisions

- Collections are shared by all cities; the screen shows the active city's events, like the rest of the app.
- Merging duplicates keeps membership: it reuses the path that carries marks to the surviving event.
- Storage (builder's call): a `collections` table (id, name, position) and a `collection_ids` JSON column on
  events, like `source_ids`; deleting a collection strips its id from events. A collected event counts as marked. Setting `collections_enabled: bool = False`. `EventPublic.collection_ids`. The feed takes a
  `collection` filter.

## Approaches

1. Collections as a new table plus a feed filter (chosen): reuses the feed, its filters and cards.
2. Collections as special tags: would mix them with Claude's tags and the tag order/hiding rules. Rejected.
