# Development

How What To Do is built and how to work on it. For installing and using the app, see the [README](../README.md).

## Layout

| Folder | What lives there |
| --- | --- |
| `src/where_to_go/` | Python backend (FastAPI + SQLModel) |
| `frontend/` | Web interface (React + TypeScript, Vite) |
| `macos/` | Optional macOS app, see [macos-app.md](macos-app.md) |
| `scripts/` | Update script, OpenAPI export, data migration |
| `tests/` | Backend tests |

## Backend

```bash
uv sync
uv run where-to-go            # API at http://127.0.0.1:18765, endpoint docs at /docs
uv run pytest
```

Run `uv run where-to-go --help` for the flags:

| Flag | Meaning |
| --- | --- |
| `--port` | Port to listen on. Defaults to `$WHERE_TO_GO_PORT` or 18765. |
| `--data` | Folder for the database and images. Defaults to `~/Library/Application Support/where-to-go`. |
| `--ui` | A built web interface to serve at the root. The API then moves to `/api`. |

Claude is called through `claude-agent-sdk`, that is, through the Claude Code login: `claude` must be installed and logged in. No API key is used.

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

## Make commands

`make help` lists them. The main ones:

| Command | What it does |
| --- | --- |
| `make up` | Installs dependencies, builds the interface and starts the app in the background |
| `make down` | Stops the app |
| `make logs` | Follows the app log and the update log |
| `make update` | Moves this copy to the latest release tag and restarts it |
| `make test` | Backend and interface tests |
| `make app` | Builds the macOS app into `~/Applications` |

`make` reads `.env` (created from `.env.example` on the first run):

| Variable | Meaning |
| --- | --- |
| `PORT` | Port of this copy |
| `DATA_DIR` | Folder for the database and images; empty means the default folder |
| `INSTANCE_ENV_NAME` | Label of this copy: `prod` names the macOS app "What To Do", anything else "What To Do <Name>" |
| `MENU_BAR_ICON` | `1` makes the macOS app live in the menu bar |

## Tests

```bash
make test                          # everything
uv run pytest                      # backend
cd frontend && npm test            # interface
swift test --package-path macos    # macOS app
```

`tests/test_english_only.py` fails on any Russian letter outside user data and prompts: the interface, messages, code comments and docs are English.
