# The macOS app

**What To Do** runs in any browser at `http://127.0.0.1:<PORT>`. The macOS app wraps the same page in a native window. It comes in two kinds:

- **From the disk image**, for everyone: a self-contained `What To Do.app` with Python, the app's packages, the built interface and the Claude CLI inside. Install and first launch are in the [README](../README.md#macos). It updates from the disk images of GitHub releases.
- **Built from a git copy** with `make app`, for developers: a window for the copy in that folder, updated with git like the copy itself.

Both:

- It starts the server on launch, so you don't need the terminal.
- The window has no separate title bar: the page runs under it. Drag the window by an empty spot of the strip along the top, and double-click there to zoom it.
- Optional **menu bar** mode.

## The app from the disk image

Inside the bundle, `Contents/Resources/python` is a relocatable CPython from [python-build-standalone](https://github.com/astral-sh/python-build-standalone) with the app's packages from `uv.lock`, and `Contents/Resources/project` holds the built interface, the changelog and `bundle.json`, which names the bundle's architecture. The app never writes into its bundle: its server records, logs and update downloads go to `~/Library/Application Support/What To Do`, and the data to `~/Library/Application Support/where-to-go`, as for every copy.

The port is 48765, one few programs use. Before starting the server the window asks `where-to-go port` which port to use: when another program holds the port, the app moves to a free one nearby and remembers it in `.pids/port` of its state folder. `PORT=<number>` in `~/Library/Application Support/What To Do/.env` fixes the port instead; `DATA_DIR` there moves the data. For tests, `WHERE_TO_GO_PORT`, `WHERE_TO_GO_DATA_DIR` and `WHERE_TO_GO_STATE_DIR` override them, for example with `open --env`.

There is a disk image for Apple Silicon and one for Intel Macs. The Claude CLI alone is 300 MB per architecture, so a universal app would be twice as big.

**Building.** `macos/scripts/build-dmg.sh <arm64|x86_64> [output folder] [version]` builds the app and its disk image on any Mac with Xcode or its Command Line Tools, uv and Node.js, for either architecture. `macos/scripts/smoke-test-bundle.sh <app>` starts the built app's server on a free port with its own data and checks it. The release workflow (`.github/workflows/release-dmg.yml`) runs both for each architecture when a release is published and attaches the images to it; CI builds them on every push.

**Signing.** There is no Apple Developer ID, so the bundle is signed ad hoc: Apple Silicon runs no unsigned code. The Claude CLI keeps Anthropic's own signature. macOS asks the user once to allow the app (see the README); the approval covers everything inside the bundle.

**Updating.** The updater (`src/where_to_go/launcher/bundle_updater.py`) asks GitHub's releases for the newest one with a disk image for this Mac, downloads it to the state folder and checks its SHA-256 against GitHub's, copies the app out of the image next to the installed one while the app still runs, then stops the server, swaps the two bundles, moves the old one to the Trash and starts the new server. The window then shows **Restart to finish updating**. An app opened from the disk image or from Downloads runs from a read-only copy macOS made of it and says to move it to Applications first. `WHERE_TO_GO_GITHUB_API` and `WHERE_TO_GO_GITHUB_RAW` point the updater at another server, for testing.

## Building it from a git copy

The app needs Xcode or the Xcode Command Line Tools (`xcode-select --install`) and macOS 14 or later.

```bash
make app
```

This builds the app and puts it into `~/Applications`. Start it from Launchpad or Spotlight. `make app` refuses to run in a git worktree: the app would start the server on that copy's port.

The app's name follows `INSTANCE_ENV_NAME` in `.env`: **What To Do** for `prod`, **What To Do Dev** for `dev`.

The app remembers the project folder. Run `make app` again after you move it.

## How it starts

On launch, the app asks the copy's `.venv/bin/where-to-go port` which port to use, as the app from the disk image does: when another program holds the copy's port, it moves to a free one nearby and stays there; a `PORT` set in `.env` is kept. Then it checks whether What To Do itself answers at `http://127.0.0.1:<PORT>/api/version`: another program on the port does not count. If not, it runs the copy's own `.venv/bin/where-to-go up --port <PORT>` and waits up to two minutes. On quit, it always runs `.venv/bin/where-to-go down`, whoever started the server: a refresh in progress stops with it, and the posts it has already read stay saved.

The command runs in a login shell, which reads `~/.zprofile` but not `~/.zshrc`. Node.js is needed only when the interface has to be built (the first start and after an update that changed it); `where-to-go up` also looks for it in the Homebrew, nvm and Volta folders. If the app still can't find `node`, add it to your `PATH` in `~/.zprofile`.

If the server fails to start, the window shows the error and the last lines of the output, with a **Try Again** button.

## Menu bar mode

Set `MENU_BAR_ICON=1` in `.env` and run `make app` again. The app then lives in the menu bar: closing the window hides it from the Dock, and the menu bar icon has **Open** and **Quit**.

## Updates

The app menu has **Check for Updates…** right after **Settings…**. It does the same as checking for updates in the page.

After an update, the app on disk may be newer than the window you have open. A quiet note at the right end of the title bar then says **Restart to finish updating**. Press **Restart**: the new app opens and the old window closes. The server keeps running during the restart, and quitting the new window later stops it as usual.

## Other features

- **Settings…** with `⌘,` opens the settings screen.
- **Zoom In**, **Zoom Out** and **Actual Size** with `⌘+`, `⌘-` and `⌘0`.
- **Reload** with `⌘R`; on the error screen it retries the start.

## For developers

The app lives in `macos/`: a Swift package with the `LauncherCore` library (config, server launcher, health probe, title bar insets, theme) and the `WhatToDo` executable (AppKit window, menus, web view). Run its tests with `swift test --package-path macos`. `macos/scripts/render-icon.swift` draws `Resources/AppIcon.png`.

The page talks to the window through `frontend/src/native/nativeHost.ts`:

- `window.webkit.messageHandlers.titlebar.postMessage("drag" | "doubleClick")` moves or zooms the window.
- `window.webkit.messageHandlers.theme.postMessage("light" | "dark" | "system")` sets the window's appearance. The page has only a light look, so it sends `light`.
- The window sets `--shell-titlebar-h`, `--shell-inset-start` and `--shell-inset-end` on the root element: where its own controls sit over the page.
- The menu dispatches `nativeopensettings` and `nativecheckforupdates` on `window`.

`Info.plist` of the app built from a git copy carries `WTGProjectDir`, `WTGPort`, `WTGMenuBarIcon` and `WTGMacosTree`, the git tree of `macos/` the app was built from: when an update changes it, the running app shows the restart note. The app from the disk image carries `WTGBundled` instead of `WTGProjectDir`, and its version as `WTGMacosTree`, so every update offers the restart.

`macos/dmg/settings.py` lays out the disk image window for [dmgbuild](https://dmgbuild.readthedocs.io); `scripts/render-dmg-background.swift` draws its background.
