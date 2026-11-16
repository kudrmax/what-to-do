# The macOS app

**What To Do** runs in any browser at `http://127.0.0.1:<PORT>`. The optional macOS app wraps the same page in a native window:

- It starts the server on launch, so you don't need the terminal.
- The window has no separate title bar: the page runs under it. Drag the window by an empty spot of the strip along the top, and double-click there to zoom it.
- Optional **menu bar** mode.

## Building it

The app needs Xcode or the Xcode Command Line Tools (`xcode-select --install`) and macOS 14 or later.

```bash
make app
```

This builds the app and puts it into `~/Applications`. Start it from Launchpad or Spotlight. `make app` refuses to run in a git worktree: the app would start the server on that copy's port.

The app's name follows `INSTANCE_ENV_NAME` in `.env`: **What To Do** for `prod`, **What To Do Dev** for `dev`.

The app remembers the project folder and port. Run `make app` again after you move the project folder or change `PORT` in `.env`.

## How it starts

On launch, the app checks whether What To Do itself answers at `http://127.0.0.1:<PORT>/api/version`: another program on the port does not count. If not, it runs the copy's own `.venv/bin/where-to-go up --port <PORT>` and waits up to two minutes. On quit, it always runs `.venv/bin/where-to-go down`, whoever started the server: a refresh in progress stops with it, and the posts it has already read stay saved.

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

`Info.plist` of the built app carries `WTGProjectDir`, `WTGPort`, `WTGMenuBarIcon` and `WTGMacosTree`, the git tree of `macos/` the app was built from: when an update changes it, the running app shows the restart note.
