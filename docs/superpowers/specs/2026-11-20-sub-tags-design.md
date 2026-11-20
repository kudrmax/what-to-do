# Sub-tags

## Why

One tag often covers events Max wants and events he does not. "Concert" holds a jazz evening he would go to and a gig
by a band nobody has heard of. Hiding the whole tag loses the first; keeping it floods the feed with the second.
What separates them is a finer kind inside the tag, not another tag beside it.

Today the only tool is a flat list of tags. A second tag next to "Concert" either duplicates it ("jazz" without
"concert") or fights it (a hidden "Concert" plus a visible "Jazz"). A tag needs a way to split into kinds, with
Claude choosing the kind and the user choosing which kinds stay in the feed.

Sub-tags are a general mechanism for any tag. Concerts are the first use.

## What Max decided

- A tag can have sub-tags: kinds of it that exclude each other.
- Claude puts the sub-tag, never the parent tag, on an event. The event stores only the sub-tag. Which parent it
  belongs to is known from the tag list and is never stored on the event.
- One level only: a sub-tag has no sub-tags of its own.
- A sub-tag works like any tag: it has a name, a meaning Claude reads and a visibility (shown, hidden, always hidden).
- The general hiding rule stays: an event leaves the feed when every tag it has is hidden, or when one of its tags is
  always hidden. Marked events and events that fit the priority wish always stay.
- The mechanism is general. Nothing in the code knows about concerts.

## Model

`Tag` gets `parent_id: int | None`, a foreign key to `tags.id`.

Constraints, checked by the repository and answered with 400 from the API:

1. The parent of a tag is a top-level tag. A sub-tag cannot be a parent.
2. The fallback tag ("not recognised") is never a parent and never a sub-tag.
3. Names stay unique across the whole list, sub-tags included, as today. Event tags are stored by name.
4. A tag that has sub-tags is a **parent**. A parent has no visibility of its own: its sub-tags decide. The API
   refuses to set a parent's visibility; `TagPublic.visibility` of a parent is `shown` and means nothing.

`TagPublic` gets `parent_id`. The list `GET /tags` stays flat and ordered: every parent is followed by its sub-tags,
in their own order.

## How Claude tags

The tag list Claude reads (`TagList.lines()`) shows sub-tags under their parent:

```
  "Concert" — live music: musicians play or sing live. Choose exactly one of its kinds:
    "Music evening" — …
    "Special format" — …
    "Artist gig" — …
  "Party" — …
```

One general line in the Tags block of the extraction and the re-tagging prompts says: for a tag with kinds, put
exactly one of its kinds and never the tag itself. The meaning of the parent tells Claude when the parent applies at
all; the meanings of the kinds tell which kind.

Validation of Claude's answer (`resolution.py`, `retagging.py`):

1. A parent name in the answer is dropped. If nothing else is left, the event gets the fallback tag, as with any
   unknown tag today.
2. Two sub-tags of one parent: the first one stays.
3. A sub-tag counts as one tag towards the limit of four.

## Building a card from several posts

`EventResolver._tags` unions the tags of a card's mentions. Two posts may put different kinds of one parent. The card
keeps one sub-tag per parent: the one from the mention that ranks first in the order the resolver already uses.

## Hiding

`HiddenTags.block` does not change. It already works on the tags an event has, and an event now has sub-tags
instead of parents.

Examples, with "Artist gig" hidden and "Jazz" shown:

| Event tags | In the feed |
|---|---|
| Artist gig | no: every tag is hidden |
| Artist gig, Jazz | yes: "Jazz" is shown |
| Music evening | yes |

An event that still carries a parent name directly (tagged before the parent got sub-tags) counts that tag as shown
until it is re-tagged. Re-tagging after adding sub-tags is the expected step; the settings say so.

## Settings → Tags

- Sub-tags sit under their parent, indented.
- Every row keeps what it has today: name, meaning, visibility. A parent's row has no visibility control.
- A parent and a top-level tag have an "Add a kind" control that adds a sub-tag under it. Adding the first sub-tag
  turns a tag into a parent.
- Dragging reorders tags at their own level: parents among top-level tags, sub-tags within their parent. A tag is not
  dragged from one parent to another.
- After a change to sub-tags, the Re-tag block is the next step and says how many upcoming events it reads.

## Feed and other places

- **Card and event window**: the chip shows the sub-tag's name. Nothing else changes.
- **Tag filter in the feed**: lists parents with their sub-tags under them. Choosing a parent selects all its sub-tags.
  The API `tags` filter accepts a parent name and expands it to its sub-tags.
- **Search**: an event matches its sub-tags and the names of their parents, so searching "concert" finds every kind.
- **Statistics**: counts sub-tags, each shown under its parent, plus a total for the parent.
- **Phone page**: renders the same card and the same feed rule, nothing of its own.

## Migration

`parent_id` is added as null for every tag. Existing tags and events are unchanged.

## First use: concerts (data, not code)

Done in Max's settings after the release, on a copy first:

| Tag | Meaning for Claude | Visibility |
|---|---|---|
| Concert (parent) | live music: musicians play or sing live for an audience; a DJ set or listening to a recording is not a concert | — |
| Music evening | people come for the music and the atmosphere, not for a name: jazz in a café or a chamber hall, acoustic or live music in a bar, any classical concert | shown |
| Special format | live music inside an unusual format people come for: a house concert, a music salon with a talk, a concert-lecture, a jam, a concert by candlelight, a festival or a night with many artists | shown |
| Artist gig | people come for a particular artist or band, known or not, any genre: a solo concert, a tour, a club gig of one to three bands | hidden |

"Jazz" stays a top-level tag and shown, so a jazz artist's concert stays in the feed. A DJ set gets "Party", a
listening session gets "Talk": both exist already.

Tag names here are translated; in Max's settings the names and meanings are in Russian, like all his tags.

## Second use: games (data, not code)

Max's marks: improv games, LEGO Battle, D&D and board game nights got "maybe" with 4–5; every quiz, bingo and
KinoLoto got "won't go" with 1–2. Of the 9 upcoming events with "Games and quizzes", 7 are quizzes and bingo.

"Games and quizzes" is renamed to "Games" and gets three kinds:

| Tag | Meaning for Claude | Visibility |
|---|---|---|
| Games (parent) | events where the guests play themselves | — |
| Quiz | teams answer the host's questions; bingo and lotto too | hidden |
| Board and role-playing | board games, D&D and other tabletop role-playing, mafia | shown |
| Live games | games played with the body or on a stage: improv games, LEGO Battle, table football, a detective game | shown |

Improv games belong to "Live games", not to "Theatre"; the meaning says so.

## Non-goals

- Moving an existing tag under a parent. A kind is created as a new tag.
- More than one level.
- Several kinds of one parent on one event.
- Tags not covered by a "use" section above keep their place until it is written.

## Tests

- Repository: the constraints above; a parent's visibility is refused.
- Extraction and re-tagging: the tag list renders kinds under the parent; a parent name in an answer is dropped;
  two kinds of one parent keep the first.
- Resolver: two mentions with different kinds of one parent give one kind.
- Feed: the examples in the Hiding table; a legacy parent tag counts as shown; the `tags` filter expands a parent.
- Settings: adding a kind, reordering within a parent, no visibility control on a parent.
