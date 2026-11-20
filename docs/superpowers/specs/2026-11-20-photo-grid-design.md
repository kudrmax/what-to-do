# Photo grid on event cards

## Why

Many events are announced by several posts with many photos between them, yet the card shows one. One photo hides
what the event looks like; a grid shows it at a glance.

## What Max decided

- Every card with more than one photo of its event shows a grid instead of the single photo.
- Layout "main photo + four": the card's current photo is large, up to four more are small beside it. Photos beyond
  five are not shown on the card and nothing marks them (no "+N"); the event window shows all of them.
- The large photo is the one the card shows today (`Event.image_path`), so a card with one photo is unchanged.

## Which photos belong to an event (builder's call, agreed in the conversation)

Photos from every post behind the card, in the order of the card's mentions, the card's current photo first, no
repeats, with two filters:

1. **A video counts once.** The frames saved from one video (`<stem>-f<N>.jpg`) give one photo: the frame the card
   uses if it is from this video, else the first frame.
2. **A digest gives only this event's picture.** A post that is behind several events (several mentions) gives only
   the picture its mention points to (`Mention.image_index`); a post behind this event alone gives all its pictures.

## Layout by count

| Photos | Layout |
|---|---|
| 1 | as today |
| 2 | two halves |
| 3 | large left (2/3), two stacked right |
| 4 | large left half, right half: one wide on top, two below |
| 5 | large left half, 2×2 small on the right |
| 6+ | as 5, the first five photos |

The grid keeps today's photo height (16:10). Small tiles fill their cell (cropped); the large tile keeps today's look
(whole photo on its own blurred copy). A wide card (photo beside the text) uses the same layout in its photo column.
Clicking the grid opens the event window, as clicking the photo does today. The phone page renders the same card.

## Approaches

1. **Store the list on the card** (picked): the resolver that builds a card from its mentions also stores its photo
   list; a data migration fills it for existing cards. The feed reads it with no extra queries.
2. Compute the list when the feed is read: joins every card's mentions and posts on every feed load.
3. Let the frontend fetch each card's originals: one request per card in the feed.

## Non-goals

- Changing which photo is the main one.
- A photo viewer on the card itself; the event window already has one.
