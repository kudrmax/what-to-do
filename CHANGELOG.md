# What's new

What changed in each release of What To Do, newest first.

## 1.15.2 — 2026-11-16

A **Review** card shows what a card in the list shows.

### Fixed
- A **Review** card no longer adds its own details. It shows the time, one tag, the price, the title and the description, just as the list does, and no longer the place or extra tags. The day sits above the card, as a heading in the list does.
- The rating row on a **Review** card lost its **Interest** label and gained the **Note to developer** button the list card has.
![](docs/images/changelog/1.15.2/review-card.png)

## 1.15.1 — 2026-11-16

Digests are read in full.

### Fixed
- A channel that posts long digests of many events no longer loses part of them: several digests read together made Claude skip a third or more of their events, sometimes a whole digest. A long post is now read with short posts only or on its own.
- The latest posts of every channel are read again at the next **Refresh**, so the events they lost appear. Your ratings and plans stay on their cards.
- Quitting the app stops reading. Before, the app could close while **Refresh** kept running in the background and kept calling Claude. Now quitting stops the refresh and Claude's calls with it. The window shows **Stopping…** for a few seconds. Posts already read stay, and the rest are read at the next **Refresh**.

## 1.15.0 — 2026-11-16

Sources can be paused instead of deleted.

### Pause a source
A source you no longer want new events from can be paused with the pause button next to **Delete** in **Sources**. **Refresh** skips a paused source, and its events you have not marked leave **Upcoming**, **Calendar** and **Stats**. Events you have rated or planned stay, and so do events another source also announces. Press the play button to resume it: its hidden events come back.
![](docs/images/changelog/1.15.0/pause.png)

## 1.14.3 — 2026-11-16

Long tooltips fit in the window.

### Fixed
- A long tooltip wraps onto several lines instead of running off the window. This was most visible on **For you**, whose tooltip quotes what you wrote in **Settings**.
![](docs/images/changelog/1.14.3/tooltip.png)
- In **Review**, the tooltip on a card's **For you** badge is no longer cut off at the card's edge.
- In a small window, a **Review** card fits its answers and no longer cuts the description in the middle of a line.

## 1.14.2 — 2026-11-16

Tooltips are shown in full.

### Fixed
- Tooltips on a card's ratings and on the repeat and unknown-time icons are no longer cut off at the card's edge. A rating at the left edge used to show only part of its words, such as "…nteresting at all".
- Tooltips on the **Statuses** bar in **Stats** are no longer cut off by the bar.
![](docs/images/changelog/1.14.2/tooltip.png)

## 1.14.1 — 2026-11-16

Review mode follows the same rules as the list.

### Fixed
- In **Review**, a rating no longer takes the card away. A card leaves the deck only when it leaves **Upcoming**, after **Not going**, **Maybe** or **For sure**. Rated cards that have no plan yet show up in Review too, just as they do in the list.
- Choosing a card's current rating or plan again clears it, as on the cards in the list.
![](docs/images/changelog/1.14.1/review-rating.png)

## 1.14.0 — 2026-11-16

Tell Claude what you look for first, and those events stand out.

### For you
In **Settings → What I look for first**, describe in your own words what matters to you most, for example «I'm looking for friends: events made for meeting people». While reading posts, Claude marks the events that fit with **For you**: their cards get a violet frame and badge in the feed, in **Review** and in the event window, and they are tinted in the **Calendar**. The **For you** filter next to the search shows only them. After you change the wish, the next **Refresh** reads the recent posts again so the cards already in the feed get marked too.
![](docs/images/changelog/1.14.0/wish.png)
![](docs/images/changelog/1.14.0/highlight.png)
![](docs/images/changelog/1.14.0/filter.png)

## 1.13.0 — 2026-11-16

Go through the feed one card at a time, like a dating app.

### Review mode
Switch **Upcoming** from **List** to **Review**: one event fills the screen, and every answer brings the next. Drag the card right or press → for **Maybe**, left or ← for **Not going**, up or ↑ for **For sure**. Keys 1–5 set your interest and move on too, ↓ leaves a card for later, and ⌘Z or the **Undo** button takes the last answer back. A click on the card opens the whole event. The buttons under the card do the same with the mouse, and the app remembers which view you used last.
![](docs/images/changelog/1.13.0/review-switch.png)
![](docs/images/changelog/1.13.0/review-swipe.png)

## 1.12.0 — 2026-11-16

The app now speaks English. Your events, tags and prompts stay as they were.

### English interface
Every screen, button, hint and message is in English: the sidebar, filters, the event window, stats, settings, the **Refresh** progress, errors and the update steps. The macOS app's menus and windows are in English too. Claude still writes event titles and descriptions in the language set in **Settings**, and your tags keep their names.
![](docs/images/changelog/1.12.0/english.png)

### Improvements
- Dates read the English way, such as **Tuesday, 17 November**, and prices as **RSD 1,500**.
- The section of events you plan to attend is called **Want to go**.

## 1.11.1 — 2026-11-16

Merging duplicates shows its progress, and website pages are no longer called posts.

### Improvements
- While duplicates are merged, the **Refresh** button counts announcements and shows roughly how long is left.
![](docs/images/changelog/1.11.1/merge-progress.png)
- Website pages are no longer called posts. The **Collecting sources** and **Reading posts and pages** labels on the button, the event window and the stats speak of sources, posts and pages.

## 1.11.0 — 2026-11-16

While a refresh runs, you can see how much is done and roughly how long is left.

### Refresh progress
The **Refresh** button counts every stage: how many sources are collected, how many website pages are downloaded, how many photos and posts are read. Next to it you see roughly how much time is left, judged by how fast the current stage goes.
![](docs/images/changelog/1.11.0/refresh-progress.png)

## 1.10.2 — 2026-11-16

Event dates and places from websites now match the website exactly.

### Improvements
- The app takes the date, time, place and price of a website event straight from the page rather than from Claude's retelling, so they can no longer get mixed up. Claude writes only the title, description and tags.

## 1.10.1 — 2026-11-15

Event websites use less Claude and are read more reliably.

### Improvements
- Website events in other cities and online events no longer go to Claude. The app asks Claude once which place names belong to your city and remembers the answer.
- The website preview shows how many events the site has and which of them will make it into the app.
![](docs/images/changelog/1.10.1/site-preview.png)
- A website is added right after the preview, without a second check.
- When a website asks to slow down, the app waits and downloads every page instead of skipping them.
- Upcoming events of a website are rechecked once a day, so **Refresh** no longer drags on for extra minutes.
- Website descriptions are shown as plain text, without markup.

### Fixed
- Website links with and without www count as one website.
- An event the website published later than its page still makes it into the app.

## 1.10.0 — 2026-11-15

Events can now come not only from Telegram channels but also from event websites.

### Event websites
In **Sources**, paste a link to any event on an event website. The app finds the site's list of all events by itself and shows how many pages it found and which events are coming up. After **Add website**, the site appears in the list next to the channels, and **Refresh** takes its events for the next 30 days. They merge with the same events from channels. Sites that mark up their events for search engines work, such as Polako Hedonist. If a site can't do that, the app says so right away.
![](docs/images/changelog/1.10.0/site-preview.png)
![](docs/images/changelog/1.10.0/site-source.png)

### Improvements
- Website events have an **Open on website** button that leads to the event's page.
- A channel or website that is already among your sources is not added a second time: the app warns you.

## 1.9.1 — 2026-11-15

Fixed the strip under the window title.

### Fixed
- In the macOS app, scrolled cards and events no longer show through the title bar strip with the close buttons. In **Calendar**, the area above the pinned row of days is now clean.

## 1.9.0 — 2026-11-15

The interface responds to every action: buttons react to presses, windows and menus fade in and out smoothly, and **Calendar** is easier to use.

### Calendar
- The weekdays stay at the top when you scroll a long week.
- When a search finds nothing in this week, the calendar says so and tells you how many such events are in **Upcoming**.
![](docs/images/changelog/1.9.0/calendar-search.png)
- Long Latin names break by syllables ("Shcher-ba-kova") rather than after any letter.
- The week grid no longer runs past the edges of the screen.

### Improvements
- All buttons, chips, ratings and menu items show a press. Ones that are switched on keep their color while pressed.
- Every element responds to hover, including active filters, marked events in **Calendar**, **Upcoming / Past** and **+ Add city**. They all respond at the same speed.
- Windows close as smoothly as they open. Menus appear and disappear with a short animation.
- The **Summary / Original** switch in the event window looks the same as **Upcoming / Past**.
- In **Want to go**, the **Upcoming / Past** switch moved to the header, and the filters fit on one line.
![](docs/images/changelog/1.9.0/plans.png)
- Cards in one row have the same height, and ratings and statuses line up.
![](docs/images/changelog/1.9.0/cards.png)
- Input fields are as tall as the buttons next to them. In **Settings**, the model picker lines up with the fields above it.

## 1.8.1 — 2026-11-15

Fixed visual glitches on the **Sources**, **Calendar** and **Stats** screens and in the filter menu.

### Fixed
- **Sources**: the refresh date and the event count no longer break onto two lines, and the columns line up.
![](docs/images/changelog/1.8.1/sources.png)
- **Calendar**: in a narrow window, long Latin names break with a hyphen instead of splitting mid-word.
- **Stats**: in a narrow window, the four tiles at the top form a 2 × 2 grid, with no lonely tile in the second row.
![](docs/images/changelog/1.8.1/stats-tiles.png)
- **Stats**: short bars in **Tags** and **Sources** no longer look like clipped semicircles.
- The filter menu is wider, and the checkbox sits at the first line of a long channel name.
![](docs/images/changelog/1.8.1/filter-menu.png)

## 1.8.0 — 2026-11-14

Tags can now be hidden from the feed and arranged in your own order.

### Tag blacklist and order
In **Settings**, tags became a list. Click the eye next to a tag to put it on the blacklist, and events with it disappear from the feed. Events you have already marked stay in **Want to go**, even if they have a hidden tag. Drag a tag by the handle on the left to change the order: tags are shown in this order on cards and in the event window, and a card with several tags shows the one that matters most to you.
![](docs/images/changelog/1.8.0/tags.png)

## 1.7.1 — 2026-11-12

Fix: events show their original post again.

### Fixed
- The **Original** tab was empty, and the **Open post** button disappeared from the event window. This happened when another program on the computer used the same port as the app: post requests went to it. Now the app talks only to its own server and checks at startup that it is the one answering.
- If posts still fail to load, the **Original** tab says so and offers a **Try again** button instead of pretending to be empty.
![](docs/images/changelog/1.7.1/posts-error.png)

## 1.7.0 — 2026-11-11

A new **Stats** screen: everything the app has read and found, in numbers and charts.

### Stats
The menu has a new **Stats** section. At the top are the main numbers: how many posts and photos Claude read, how many events were found and how many of them you marked. Below is the path from a post to your plans: how many announcements the posts had and how many cards remained after merging duplicates. There are also the statuses and interest ratings of your cards, posts by week, the most frequent tags and how many events each channel brings. Hover over a bar to see the exact numbers.
![](docs/images/changelog/1.7.0/stats.png)

## 1.6.2 — 2026-11-10

Search finds any card, however it is marked.

### Fixed
- A card marked **Not going** used to be impossible to find anywhere, even with search, and there was nowhere to remove the mark. Now search on any screen finds cards with any mark. In **Calendar**, **Not going** cards are crossed out, and in the feed their mark is visible and can be removed. Without a search, everything shows as before.
![](docs/images/changelog/1.6.2/search-declined.png)

## 1.6.1 — 2026-11-10

Photos on the cards of events from posts with one shared cover, and a more reliable update button.

### Fixed
- If a post has one photo and Claude gave it to none of its events, such as a cover for "Which museums to visit for free on November 11", it is now on the card of every event from that post. Cards you already have get it on the next refresh, without Claude calls.
![](docs/images/changelog/1.6.1/post-cover.png)
- The **Update to…** button sometimes showed that the update had failed even though it was going fine. This fix takes effect from the update after this one.

## 1.6.0 — 2026-11-10

A potential source is added with one button.

### Add or dismiss in one click
Each potential source now has two buttons instead of a checkbox. **Add to sources** adds the channel to your sources right away, and it leaves the list. **Not interesting** moves the channel to the collapsed **Dismissed** block, where you can bring it back from. If a channel could not be added, for example because it is private or has its web preview turned off, it stays in the list with the reason below it.
![](docs/images/changelog/1.6.0/adopt.png)

## 1.5.1 — 2026-11-10

A photo for every lecture of a series, and editing prompts without extra Claude calls.

### Fixed
- If a post announces a lecture series with one shared poster, that poster is now on the card of every lecture, not only the first. Cards you already have get it on the next refresh, without Claude calls.
![](docs/images/changelog/1.5.1/series-poster.png)

### Improvements
- Editing prompts in **Settings** no longer rereads posts that were already parsed: the new text applies to new posts, and a refresh does not spend extra Claude calls.

## 1.5.0 — 2026-11-10

Sources can be starred, so you don't get lost among many channels.

### Favorite sources
Each channel on the **Sources** page has a star. A new channel is added without it, and clicking the star makes it a favorite: favorites stand at the top of the list. Clicking again removes the mark. The star is only for your own organizing and affects neither the refresh nor the feed.
![](docs/images/changelog/1.5.0/favorite-sources.png)

## 1.4.2 — 2026-11-10

The rating buttons on a card are back on one line.

### Fixed
- In a narrow feed column, the 1–5 rating, the note and the status buttons fit on one line instead of wrapping.

## 1.4.1 — 2026-11-10

An internal fix for sign-up links.

### Fixed
- The sign-up or ticket link of an event card is saved during a refresh without warnings in the app log.

## 1.4.0 — 2026-11-10

The app suggests new channels: the ones your sources forward posts from or link to.

### Potential sources
During a refresh, Claude notes the channels a post links to and the channels it was forwarded from. They are collected on the **Sources** page in the **Potential sources** section. Each channel shows which posts it came from, and both the channel and those posts open by link. If you like a channel, add it by hand as usual. Mark it **Done**, and the channel won't appear again. Channels already among your sources and bots don't make the list.
![](docs/images/changelog/1.4.0/potential-sources.png)

### Improvements
- To collect channels from posts already read, the first refresh after installing rereads the recent posts of every channel.

## 1.3.1 — 2026-11-10

The feed and the event window respond instantly, and nothing jumps.

### Fixed
- A card's hover shadow appears and disappears instantly, and the photos on this and neighboring cards no longer jump.
- The event window opens complete right away: no intermediate "Loading…", no jump in size and shadow, buttons and photos in place from the first frame.
- While the event window is open, the section under it stays highlighted in the menu.

## 1.3.0 — 2026-11-10

You can leave a note to the developer on a card: what to improve in this event or in the app.

### Notes to the developer
Next to the 1–5 interest scale there is a new button with a speech bubble. It opens a window where you can write any text, such as "this needs a new tag" or "the time was parsed wrong". Notes are collected in the database for future improvements and are not shown anywhere else in the app.
![](docs/images/changelog/1.3.0/button.png)
![](docs/images/changelog/1.3.0/window.png)

## 1.2.0 — 2026-11-10

The event window shows the original posts, so you can compare what Claude wrote with what the channel wrote.

### New event window
At the top is the gist: title, time, place, price, the sign-up button and the **Add to Calendar** button. Below are two tabs. **Summary** has the poster and the description. **Original** has the post itself: all its photos and its text as is, with the lines about this event highlighted and the post scrolled straight to them. If several channels wrote about the event, the posts are picked with chips at the top.
![](docs/images/changelog/1.2.0/event-window.png)
![](docs/images/changelog/1.2.0/original.png)

### New
- A **Sign up** or **Buy ticket** button when the post has a sign-up or ticket link.
- Any photo opens large, next to the text Claude read on it.
![](docs/images/changelog/1.2.0/photo-text.png)

### Improvements
- An event can now be added to the calendar with a separate button.

## 1.1.0 — 2026-11-10

Post photos are read separately, and the Claude model for each step is chosen in the settings.

### New
- **Settings → Claude models**: pick Haiku, Sonnet or Opus for reading photos, parsing posts and merging duplicates.
- Your own prompt for reading photos in **Claude prompts**.

### Improvements
- Text from posters and images is transcribed in a separate step and saved, so the full description from a poster is no longer lost. While a refresh runs, the button shows "Reading photos: N of M".

### Fixed
- The app is called What To Do.

## 1.0.0 — 2026-11-10

The first release: What To Do got versions, its own macOS app and one-button updates.

### macOS app
What To Do opens in its own window, without a browser. The app starts the server on launch and stops it on quit. The menu has **Settings…** (⌘,), **Check for Updates…**, zoom and page reload.

### One-button updates
Once a day the app checks whether a new version is out. If it is, **New version** appears in the sidebar. It opens the list of changes with an **Update** button. While the update runs, you see its stages. After the update, **What's new** is shown once. The whole change history is in **Settings → App**.
