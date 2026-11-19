# What To Do

**Every event in your city from the Telegram channels, Instagram profiles and websites you follow, in one calm feed.**

Event announcements are scattered across dozens of channels: long digests, posters with the date only in the picture, the same concert posted five times. What To Do reads them for you. Claude turns each post into a clean event card, merges duplicates and lays everything out by day, so you can pick tonight's plan in a minute.

It runs on your own computer and uses your existing Claude subscription through Claude Code. No API key, no account, no server.

![The Upcoming feed: event cards by day with photo, time, tag, price and description](docs/images/readme/feed.png)

## Contents

- [Features](#features)
- [Requirements](#requirements)
- [Install and run](#install-and-run)
- [First steps](#first-steps)
- [FAQ](#faq)
- [For developers](#for-developers)
- [License](#license)

## Features

### A feed of what's ahead

**Upcoming** shows every event you haven't decided on yet, grouped by day. Each card has the poster, time, tag, price and a short description written by Claude. Search, filter by tag or source, or hide multi-day events. Rate your interest from 1 to 5 and mark a plan right on the card:

| Button | Meaning |
| --- | --- |
| ✓ | Going for sure |
| ? | Maybe |
| ✕ | Not going |
| ⚑ | Went |

Once you pick a plan, the card leaves the feed, so the feed always shows only what is left to decide.

### Review mode: one card at a time

Switch **Upcoming** to **Review** and go through events like in a dating app. Drag the card, press the buttons under it or use the keys:

| Key | Answer |
| --- | --- |
| → | Maybe |
| ← | Not going |
| ↑ | For sure |
| ↓ | Later |
| 1–5 | Rate your interest |
| ⌘Z | Undo |

![Review mode: one event card with Not going, For sure, Maybe and Later buttons](docs/images/readme/review.png)

### The whole event in one window

Click a card to see the date, the place with a map link, the price, the sign-up or ticket link and the full description. **Add to Calendar** downloads an `.ics` file for Apple Calendar, Google Calendar or Outlook.

![Event window: tags, title, time, place, price, Open post in Telegram and Add to Calendar buttons](docs/images/readme/event.png)

### Duplicates merged, originals one click away

When several channels announce the same event, you get one card, not five. The **Original** tab shows every post the card was built from, with the lines about this event highlighted, so you can always check Claude's summary against the source. Reschedules and cancellations update the existing card.

![Original tab: one event built from five posts of different channels and a website](docs/images/readme/original.png)

### "For you" highlights

In **Settings**, describe in your own words what you look for, for example "events made for meeting people". Claude marks the events that fit with **For you**: they get a violet frame, and the **For you** filter shows only them.

![The feed filtered to For you events, each with a violet frame and badge](docs/images/readme/for-you.png)

### Calendar and plans

**Calendar** shows the whole week at a glance, with your plans and **For you** events tinted. **Want to go** collects everything you marked as going or maybe. To keep events for memory, the funniest or the most unusual ones, turn on **Settings → Advanced → Collections** and add a collection: a heart on every card puts its event there, and **Collections** in the menu shows each one as a feed.

![Calendar: a week of events in seven columns](docs/images/readme/calendar.png)

![Want to go: events you plan to attend, by day](docs/images/readme/plans.png)

### Your plans on the phone

The app runs on your computer, but your plans can go with you. Turn on **Settings → Phone page** and the app keeps a copy of **Want to go** on a GitHub Pages site of your own: the same cards, filters and event window, read-only. The site is public, so everything on it is encrypted with a password you choose; the phone asks for it once. The app updates the page by itself while it runs, at most once every 10 minutes. You need a free GitHub account: the section walks you through creating an empty repository, a token limited to it and turning Pages on.

### Sources you control

Add a public Telegram channel, a public Instagram profile or an event page on a website. Each source shows when it was last read, how many events it brought and whether it works. Star your favorites, pause a source instead of deleting it, and check **Potential sources**: channels your sources forward from or link to, ready to add in one click.

![Sources: Telegram channels and a website with refresh time, event count and status](docs/images/readme/sources.png)

### Stats

See how many posts and photos Claude read, how many announcements were merged into cards and which channels bring the most events.

![Stats: posts read, photos read, events found, the path from announcement to plans](docs/images/readme/stats.png)

### More

- **Several cities.** Each city has its own sources, feed and calendar. Switch between them in the top-left corner.
- **Your own tags.** Add, rename, reorder or hide tags in **Settings**. Events with a hidden tag leave the feed.
- **Your choice of Claude model** for each step: Haiku, Sonnet or Opus.
- **Editable prompts.** Every prompt Claude gets is in **Settings**.
- **One-button updates.** When a new version is out, **New version** appears in the sidebar with the list of changes and an **Update** button.
- **A macOS app** with its own window, installed from a disk image, see [Install and run](#macos).

## Requirements

A Claude subscription ([claude.ai](https://claude.ai)): Claude reads the posts. The app signs in to it from its own window and uses your subscription through Claude Code, with no API key.

That is all the macOS app needs. On Linux and Windows, and to run the app from its code, you also need:

| What | Why | How to get it |
| --- | --- | --- |
| [uv](https://docs.astral.sh/uv/getting-started/installation/) | Installs and runs the app | It also installs the right Python by itself |
| [Node.js](https://nodejs.org) 20 or later | Builds the interface on the first start and after updates that change it | |
| [Git](https://git-scm.com/downloads) | Downloads the app and its updates | |

## Install and run

### macOS

The app needs macOS 14 Sonoma or later.

1. Download the disk image for your Mac from the [latest release](https://github.com/kudrmax/what-to-do/releases/latest):

   | Your Mac | Disk image |
   | --- | --- |
   | Apple silicon: an M1 chip or newer | `What-To-Do-<version>-Apple-Silicon.dmg` |
   | An Intel processor | `What-To-Do-<version>-Intel.dmg` |

   Not sure? Open the Apple menu, then **About This Mac**: the **Chip** line names an Apple chip, the **Processor** line an Intel one.
2. Open the disk image and drag **What To Do** onto **Applications**.
3. Open **What To Do** from Applications or Launchpad.

> [!WARNING]
> **The first launch will almost certainly be blocked. This is expected: the app is not broken!**
>
> macOS says Apple could not verify that What To Do is free of malware, and offers only **Done** and **Move to Trash**. Don't move it to the Trash. macOS shows this for every app from outside the App Store that isn't notarized by Apple, which needs a paid Apple developer account. What To Do is free and open source.
>
> **To open it, once:**
>
> 1. Press **Done** in the message.
> 2. Open **System Settings**, then **Privacy & Security**, and scroll down to **Security**.
> 3. Next to "What To Do" was blocked to protect your Mac, press **Open Anyway**. The button stays there for about an hour after you tried to open the app.
> 4. Enter your Mac's password, then press **Open Anyway** in the message that follows.
>
> ![Privacy & Security: "What To Do" was blocked to protect your Mac, with the Open Anyway button](docs/images/readme/macos-open-anyway.png)

macOS remembers this: the app and its updates open without asking again. Control-click and **Open** no longer get past this message since macOS 15 Sequoia.

The window starts the app's server when it opens and stops it when you quit. Your events and settings live in `~/Library/Application Support/where-to-go`.

**Updating.** When a new version is out, **New version** appears in the sidebar with the list of changes and an **Update** button. The app downloads the new version from GitHub and puts it in place of the old one; then a note at the top of the window offers **Restart**. Your data stays where it is.

**Uninstalling.** Quit What To Do and drag it from Applications to the Trash. To delete your events and settings too, move these folders to the Trash: `~/Library/Application Support/where-to-go` (your data) and `~/Library/Application Support/What To Do` (the app's logs). In Finder, press `⇧⌘G` and paste the path to open a folder.

### Linux, Windows, and running from the code

> [!NOTE]
> **Untested on Linux and Windows.** It should work there, and the automated tests pass on both, but I have neither system to try the app on for real. If you do, I'd be grateful for an [issue](https://github.com/kudrmax/what-to-do/issues) on how it went, or a pull request with a fix.

Run these in a Linux terminal, in PowerShell on Windows or in Terminal on macOS:

```bash
git clone https://github.com/kudrmax/what-to-do.git
cd what-to-do
uv run where-to-go up
```

`up` installs everything the first time, builds the interface, starts the app in the background and prints its address, usually **http://127.0.0.1:48765**: open it in your browser. Closing the terminal does not stop the app.

#### Everyday commands

Run them in the `what-to-do` folder:

| Command | What it does |
| --- | --- |
| `uv run where-to-go up` | Starts the app in the background, or restarts it if it runs |
| `uv run where-to-go status` | Shows whether it runs, its address, version and data folder |
| `uv run where-to-go down` | Stops the app and everything it started, including Claude calls in progress |
| `uv run where-to-go logs` | Follows the app's log; `Ctrl+C` stops following |
| `uv run where-to-go update` | Updates to the latest release and restarts the app |
| `uv run where-to-go uninstall` | Removes the app from this computer |

Every command has `--help`. On macOS and Linux, `make up`, `make down`, `make status`, `make logs` and `make update` do the same.

#### Updating

When a new version is out, **New version** appears in the sidebar with the list of changes and an **Update** button. It does the same as `uv run where-to-go update`: it downloads the release, installs its packages, rebuilds the interface if needed and restarts the app with the same port and data.

#### Uninstalling

```bash
uv run where-to-go uninstall
```

It stops the app, removes the macOS app if you built one and asks whether to delete your data too. Both go to the Trash, or the Recycle Bin on Windows. The last step is yours: delete the `what-to-do` folder, which holds the code and the installed packages. Nothing is installed anywhere else.

#### A macOS window for a copy run from the code

`make app` builds a native window for the copy in this folder, see [docs/macos-app.md](docs/macos-app.md).

## First steps

### 1. Add your city

A fresh app asks where you are looking for things to do. Type the city and the country. The time zone and the language of event cards are filled in from your computer: change them if you want cards in another language. Press **Add city**.

![The welcome screen: city, country, time zone and the language of event cards](docs/images/readme/start-city.png)

The time zone decides what "today" is, and Claude writes every card in the language you chose. You can add more cities, edit or delete them later in **Settings → Cities**.

### 2. Add sources

Open **Sources**. The empty list shows how to find sources:

![How to find sources: search Telegram, check that the channel is public, websites work too](docs/images/readme/start-find-sources.png)

- **Telegram channels.** Search Telegram for your city's name together with words like "events", "concerts" or "afisha", in the local language too. Look up the venues you like: clubs, bars, museums and language schools often have a channel.
- **Only public channels work.** Open `https://t.me/s/channelname` in a browser: if you see its posts, the app can read them.
- **Instagram profiles.** Paste `instagram.com/name`, or type `@name` and pick **Instagram**. Only public profiles work. The preview lets you choose what to read: posts, pinned stories, or both.
- **Websites work too.** Paste the link to any single event on an event website. The app finds the site's list of events, shows a preview and adds the site with **Add website**.

Paste a link such as `t.me/channelname` and press **Add**.

![Sources with one Telegram channel added, awaiting refresh](docs/images/readme/start-sources.png)

After the first refresh, **Potential sources** under the list suggests channels your sources forward from or link to.

### 3. Press Refresh

Go back to **Upcoming** and press **Refresh now**.

![Upcoming before the first refresh: Ready for the first refresh, Refresh now](docs/images/readme/start-first-refresh.png)

The app downloads the recent posts of each source, Claude reads the posters and the texts, and then merges duplicates. The button shows each stage and roughly how long is left.

![Refresh in progress: Reading posts and pages: 6 of 20, about 2 minutes left](docs/images/readme/refresh.png)

The first refresh reads up to 20 recent posts of each channel, so it can take several minutes. Later refreshes read only new posts. The app never refreshes on its own: press **Refresh** whenever you want fresh events. It refreshes the city selected in the top-left corner.

### 4. Read the feed

Events appear in **Upcoming**, grouped by day. For each one, decide:

- Not interested? Press ✕, and the card leaves the feed.
- Might go? Press ? or ✓, and the card moves to **Want to go**.
- Not sure yet? Leave it: it stays in the feed until its day passes.

Click a card for the full details and the original posts. With a long feed, try **Review** mode. To get **For you** highlights, describe what you look for in **Settings → What I look for first**.

## FAQ

**Refresh says to sign in to Claude.**
Press **Sign in to Claude** under **Refresh**. The sign-in page opens in your browser; sign in with the account of your Claude subscription, come back and press **Refresh** again. If the browser didn't open, the note has a link to the page and a field for the code the page shows. The app keeps this login in Claude Code's place in your keychain, so Claude Code on the same Mac is signed in too, and the other way round.

**Another program uses the app's port.**
What To Do moves to a free port next to its own by itself and stays there: the macOS app opens on it, and `uv run where-to-go up` prints the new address. A port you set yourself is kept as it is: `PORT` in `.env` of a copy run from the code, or in `~/Library/Application Support/What To Do/.env` for the macOS app. If that one is busy, the app says which program holds it; change the number or remove the line.

**Where is my data?**
In one folder: the SQLite database `where-to-go.sqlite3` and the downloaded images.

| System | Folder |
| --- | --- |
| macOS | `~/Library/Application Support/where-to-go` |
| Linux | `~/.local/share/where-to-go` |
| Windows | `%LOCALAPPDATA%\where-to-go` |

`uv run where-to-go status` shows the folder in use in a copy run from the code; `DATA_DIR` in `.env` moves it. To back it up, copy the folder while the app is stopped.

**What leaves my computer?**
Everything stays on your computer except:

| Where | What |
| --- | --- |
| Telegram (`t.me`), Instagram and the websites you add | The app downloads their public posts and event pages |
| Claude, through your Claude Code login | Post texts and photos, to turn them into events |
| GitHub | Checks for new versions and downloads them: the macOS app asks GitHub's list of releases, a copy run from the code runs `git fetch` |

The server listens only on `127.0.0.1`, so other devices on your network can't open it.

**How much of my Claude usage does it take?**
Every refresh spends Claude calls from your subscription's usage limits: for photos, for posts and for merging duplicates. Fewer channels, fewer recent posts per channel and the Haiku model in **Settings → Claude models** all mean less usage.

**A channel shows an error.**
The channel is private, or its web preview is turned off. Open `https://t.me/s/channelname` in a browser: if no posts show up, the app can't read them either.

**What does the app read from Instagram?**
It opens public profiles the way a visitor who isn't logged in does: no Instagram account, no login, no cookies.

| Read | Not read |
| --- | --- |
| Posts: the text, every photo of a carousel, the place | Stories that last 24 hours: Instagram hides them from visitors who aren't logged in |
| Pinned stories (highlights) up to 30 days old, then every new one | The sound of videos and anything said in them |
| Videos: a few frames, so the text shown on screen is read too | Private profiles |

If Instagram refuses to show a profile, the source shows an error and the next refresh tries again.

## For developers

The architecture, the processing pipeline, tests and make commands are in [docs/development.md](docs/development.md). The macOS app is described in [docs/macos-app.md](docs/macos-app.md). What changed in each release is in [CHANGELOG.md](CHANGELOG.md).

## License

[MIT](LICENSE).
