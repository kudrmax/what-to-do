# Development

How What To Do is built and how to work on it. For installing and using the app, see the [README](../README.md).

## Layout

| Folder | What lives there |
| --- | --- |
| `src/where_to_go/` | Python backend (FastAPI + SQLModel) |
| `frontend/` | Web interface (React + TypeScript, Vite) |
| `macos/` | The macOS app and its disk image, see [macos-app.md](macos-app.md) |
| `src/where_to_go/launcher/` | The `where-to-go` command line: up, down, status, logs, update, uninstall on every platform |
| `scripts/` | Update status page, install smoke test, OpenAPI export, data migration |
| `tests/` | Backend tests |

## Backend

```bash
uv sync
uv run where-to-go serve      # the server in this terminal: API at http://127.0.0.1:18765, endpoint docs at /docs
uv run pytest
```

Run `uv run where-to-go serve --help` for the flags:

| Flag | Meaning |
| --- | --- |
| `--port` | Port to listen on. Defaults to `PORT` from `.env`, `$WHERE_TO_GO_PORT` or 18765. |
| `--data` | Folder for the database and images. Defaults to the platform's user data folder; a git worktree uses its own `./data`. |
| `--ui` | A built web interface to serve at the root. The API then moves to `/api`. |

Claude is called through `claude-agent-sdk`, that is, through the Claude Code login. The SDK brings its own Claude Code CLI; only the login is needed. No API key is used. Without a login, the note under **Refresh** signs in from the app: `POST /claude/sign-in` runs the bundled CLI's `claude auth login`, which opens the sign-in page in the browser and takes the login back by itself (`claude_login.py`).

Each entity is described once in `models.py` (SQLModel): a base class with the fields and their descriptions for Claude, and from it the table and the public API model. Settings, including Claude's prompts, live in `settings.py` (defaults in `prompts.py`).

### Pipeline

1. `telegram` and `web_sources` collect posts from `t.me/s/<channel>` and event pages from websites.
2. `photos` has Claude copy the text from posters and images.
3. `extraction` has Claude turn a post into events and places.
4. `linking` and `matching` merge duplicates, reschedules and cancellations.
5. `resolution` builds the card fields from all sources and notes conflicts.
6. `feed` lays the cards out by day.
7. `api` serves it all.

Data of the first version (prices as strings, tables without models) is migrated without Claude calls: `uv run python scripts/migrate_first_schema.py <old folder> <new folder>`.

## Frontend

React + TypeScript (Vite) in `frontend/`. API types are generated from the backend schema: `npm run api:types`.

For development, run the backend with `uv run where-to-go` and `npm run dev` in `frontend/` (http://localhost:5180, API requests go through a proxy).

```bash
cd frontend
npm install
npm run build     # production build into frontend/dist
npm test
```

## Launcher

`uv run where-to-go <command>` starts, stops, updates and removes a copy the same way on macOS, Linux and Windows; the README lists the commands. A running server records how it was started in `.pids/`, so `status`, `down` and the updater find it. Its output goes to `.logs/app.log`, the updater's to `.logs/update.log`. `down` stops the server and every process it started, Claude calls included.

On macOS and Linux, `make up`, `down`, `restart`, `status`, `logs`, `update`, `build`, `uninstall` are thin aliases; `make app` builds the macOS app and `make test` runs every test suite.

Settings of a copy come from the command-line flags, then `WHERE_TO_GO_PORT`, `WHERE_TO_GO_DATA_DIR` and `WHERE_TO_GO_INSTANCE`, then `.env` (see `.env.example`), then the defaults:

| Variable | Meaning |
| --- | --- |
| `PORT` | Port of this copy, kept even when busy. Without it the copy starts on 18765 (48765 for the app from the disk image), moves to a free port nearby when another program holds it and remembers the move in `.pids/port` |
| `DATA_DIR` | Folder for the database and images; empty means the platform's user data folder |
| `INSTANCE_ENV_NAME` | Label of this copy: `prod` names the macOS app "What To Do", anything else "What To Do <Name>" |
| `MENU_BAR_ICON` | `1` makes the macOS app live in the menu bar |

CI (`.github/workflows/ci.yml`) runs the tests and an install smoke test (`scripts/smoke_test.py`: up, status, down with no processes left, uninstall) on macOS, Linux and Windows, and builds and checks the macOS disk images for Apple Silicon and Intel. Run the smoke test locally with `uv run python scripts/smoke_test.py`.

## Tests

```bash
make test                          # everything
uv run pytest                      # backend
cd frontend && npm test            # interface
swift test --package-path macos    # macOS app
```

`tests/test_english_only.py` fails on any Russian letter outside user data and prompts: the interface, messages, code comments and docs are English.
