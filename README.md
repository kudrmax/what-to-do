# What To Do

A local app: it collects event announcements from public Telegram channels and websites, and Claude turns the posts into event cards and merges duplicates. It runs on your computer and opens in your browser; it works on macOS, Linux and Windows.

## What you need

- [git](https://git-scm.com/downloads)
- [uv](https://docs.astral.sh/uv/getting-started/installation/), which also installs the right Python
- [Node.js](https://nodejs.org) 20 or newer: the interface is built on the first start and after updates that change it
- A Claude account signed in to Claude Code: install Claude Code from [claude.com/claude-code](https://claude.com/claude-code), run `claude` in a terminal and type `/login`

## Install and start

The same commands work in Terminal on macOS, in a Linux terminal and in PowerShell on Windows:

```bash
git clone https://github.com/kudrmax/what-to-do.git
cd what-to-do
uv sync
uv run where-to-go up
```

`up` builds the interface, starts the app in the background and prints its address, http://127.0.0.1:18765. Closing the terminal does not stop it.

## Everyday commands

Run them in the app's folder:

| Command | What it does |
| --- | --- |
| `uv run where-to-go up` | Starts the app in the background; if it runs, restarts it |
| `uv run where-to-go status` | Whether it runs, its address, version and data folder |
| `uv run where-to-go down` | Stops the app and everything it started |
| `uv run where-to-go restart` | Stops the app and starts it again as it ran |
| `uv run where-to-go logs` | Follows the app's log; `Ctrl+C` stops following |
| `uv run where-to-go update` | Updates to the latest release and restarts the app |
| `uv run where-to-go uninstall` | Removes the app from this computer |

Every command has `--help`. On macOS and Linux, `make up`, `make down`, `make status`, `make logs` and `make update` do the same.

## Updating

The app checks for new releases once a day and offers **Update to X.Y.Z** in its settings. The button does the same as `uv run where-to-go update`: it downloads the release, installs its packages, rebuilds the interface if needed and restarts the app with the same port and data.

## Your data

The database and images live in your user data folder:

- macOS: `~/Library/Application Support/where-to-go`
- Linux: `~/.local/share/where-to-go`
- Windows: `%LOCALAPPDATA%\where-to-go`

`uv run where-to-go status` shows the folder in use.

## Settings of a copy

Nothing needs to be set. To change the port, the data folder or the copy's label, copy `.env.example` to `.env` and uncomment what you need; `WHERE_TO_GO_PORT`, `WHERE_TO_GO_DATA_DIR` and `WHERE_TO_GO_INSTANCE` in the environment override `.env`. A git worktree keeps its data in its own `data` folder.

## Uninstalling

```bash
uv run where-to-go uninstall
```

It stops the app, removes the macOS app if you built one, and asks whether to delete your data too; both go to the Trash (the Recycle Bin on Windows). `--yes` asks nothing and deletes the data, `--keep-data` keeps it. The last step is yours: delete the app's folder, which holds its code and installed packages.

## The macOS app

An optional native window for macOS that starts and stops the app for you: see [docs/macos-app.md](docs/macos-app.md).

## For developers

```bash
uv sync
uv run where-to-go            # the server in this terminal: API at http://127.0.0.1:18765, endpoint docs at /docs
uv run pytest
cd frontend && npm test
```

The frontend is React + TypeScript (Vite) in `frontend/`. API types are generated from the backend schema: `npm run api:types`. For development, run the backend with `uv run where-to-go` and `npm run dev` in `frontend/` (http://localhost:5180, API requests go through a proxy).

Claude is called through `claude-agent-sdk`, that is, through the Claude Code login.

Each entity is described once in `models.py` (SQLModel): a base class with the fields and their descriptions for Claude, and from it the table and the public API model. Settings, including Claude's prompts, live in `settings.py` (defaults in `prompts.py`).

Pipeline: `telegram` (collects posts from t.me/s/<channel>) → `extraction` (Claude: post → events and places) → `linking` + `matching` (merging duplicates, reschedules and cancellations) → `resolution` (card fields from all sources, conflicts) → `feed` (feed by day) → `api`.

The launcher (`src/where_to_go/launcher/`) is the `where-to-go` command line: starting, stopping, updating and removing a copy the same way on every platform. A running server records how it was started in `.pids/`, so `status`, `down` and the updater find it; its output goes to `.logs/app.log`, the updater's to `.logs/update.log`. CI (`.github/workflows/ci.yml`) runs the tests and an install smoke test (`scripts/smoke_test.py`) on macOS, Linux and Windows; run the smoke test locally with `uv run python scripts/smoke_test.py`.

Data of the first version (prices as strings, tables without models) is migrated without Claude calls: `uv run python scripts/migrate_first_schema.py <old folder> <new folder>`.
