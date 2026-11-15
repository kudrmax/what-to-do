# What To Do

A local app: it collects event announcements from public Telegram channels, and Claude turns the posts into event cards and merges duplicates.

## Running

```bash
cd frontend && npm install && npm run build && cd ..
uv run where-to-go --ui frontend/dist
```

The app opens at http://127.0.0.1:18765; data is stored in `~/Library/Application Support/where-to-go`.

## Frontend

React + TypeScript (Vite) in `frontend/`. API types are generated from the backend schema: `npm run api:types`.
For development: run the backend with `uv run where-to-go` and `npm run dev` in `frontend/` (http://localhost:5180, API requests go through a proxy).

## Backend

```bash
uv sync
uv run where-to-go            # API at http://127.0.0.1:18765, endpoint docs at /docs, data in ~/Library/Application Support/where-to-go
uv run pytest
```

Claude is called through `claude-agent-sdk`, that is, through the Claude Code login: `claude` must be installed and logged in.

Each entity is described once in `models.py` (SQLModel): a base class with the fields and their descriptions for Claude, and from it the table and the public API model. Settings, including Claude's prompts, live in `settings.py` (defaults in `prompts.py`).

Pipeline: `telegram` (collects posts from t.me/s/<channel>) → `extraction` (Claude: post → events and places) → `linking` + `matching` (merging duplicates, reschedules and cancellations) → `resolution` (card fields from all sources, conflicts) → `feed` (feed by day) → `api`.

Data of the first version (prices as strings, tables without models) is migrated without Claude calls: `uv run python scripts/migrate_first_schema.py <old folder> <new folder>`.
