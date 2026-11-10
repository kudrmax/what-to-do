---
name: release
description: Cuts a release of «Чем заняться» - picks the version, writes the CHANGELOG.md entry with annotated screenshots, bumps the version, tags, pushes and creates the GitHub Release. Use when Max says "выпускай релиз", "сделай релиз", "release" or "cut a release". Never on your own initiative: a merge to master is not a release.
---

# Release

Run only on Max's command. Publish without asking for approval of the text: Max can edit the release on GitHub and fix it in the next commit.

Run everything in the main checkout (`~/projects/what-to-do`), on master, as the git rules in the global CLAUDE.md require. Do not switch branches there.

```bash
GITHUB_REPO=kudrmax/what-to-do
```

Working files of the release (`entry.md`, `notes.md`) go to a folder of their own, never to the repository:

```bash
WORK=$(mktemp -d)
```

A published tag is never moved, deleted or re-tagged: the prod copy may already be on it. To withdraw a broken release, publish a newer one that fixes it.

## 1. Preconditions

```bash
git status --porcelain            # must be empty
git pull --ff-only
git fetch --tags origin
git rev-parse HEAD origin/master  # must be equal
```

Stop and tell Max if the tree is dirty, the pull does not fast-forward, or HEAD differs from `origin/master`.

## 2. Collect changes and pick the version

```bash
PREV=$(git tag --list 'v[0-9]*.[0-9]*.[0-9]*' --sort=-v:refname | head -1)
git log "$PREV"..HEAD --no-merges --format='%s'     # no tag yet: git log --no-merges
```

- No previous tag: the version is `1.0.0`.
- Anything new for the user since the tag (a feature, a new setting, a new screen): raise the minor number (`1.2.3` becomes `1.3.0`).
- Only fixes: raise the patch number.
- Nothing user-visible (refactoring, tests, docs): tell Max there is nothing to release and stop.

Commit subjects here are not conventional: read the diff when a subject does not say what the user sees.

The version is `version` in `pyproject.toml`.

## 3. Write the entry

In Russian, like the app itself. Format of the [Obsidian changelog](https://obsidian.md/changelog/):

```markdown
## X.Y.Z — YYYY-MM-DD

Одно предложение: о чём этот релиз.

### Название большой фичи
Что она даёт пользователю, в нескольких предложениях.
![](docs/images/changelog/X.Y.Z/feature.png)

### Новое
- …
### Улучшения
- …
### Исправлено
- …
```

- A big feature gets its own section with its own heading, before **Новое**.
- Write for the user in plain language. Skip internal changes: refactoring, tests, migrations, docs.
- Do not write empty sections.
- Group commits by what the user sees, not one line per commit.
- Insert the entry right after the intro of `CHANGELOG.md`, above older entries. Keep a copy of it, without changes, in `$WORK/entry.md` for the GitHub Release.

## 4. Screenshots

Take them in the running **dev copy** (`~/projects/what-to-do`) in one pass for all features of the release: `http://localhost:<PORT>`, where `PORT` is in the dev copy's `.env`. If it is not up, start it with `make up` in the main checkout. Never take them in the prod copy: its data is Max's.

The dev copy has its own data folder (`DATA_DIR` in its `.env`). If it is empty, fill it with **Обновить** in the dev copy, with few channels and a small «Последних постов канала»: every post read is a Claude call.

The dev copy must serve the code you just pulled: it reads its version once, at start.

```bash
curl -s "http://localhost:$PORT/api/version"   # must equal the next line
grep -m1 '^version' pyproject.toml
```

If they differ, restart it with `make down && make up` in the main checkout.

- Use a headless browser (Playwright or similar). Never the browser pane Max is watching.
- Every big feature and every notable item gets a screenshot.
- On each screenshot highlight where to look with `annotate.js` from this folder: it dims the rest of the page and rings the element in the app's accent colour, with an optional caption in the app's font. Never draw red frames or outlined text. Inject the file into the page, then call it before the screenshot:

```js
window.__annotate({ selector: '…', label: 'Подпись, если нужна' })
// take the screenshot
window.__clearAnnotations()
```

- Save as `docs/images/changelog/X.Y.Z/<name>.png` and reference with the path from the repository root, as in the entry above.
- Look at every screenshot before committing. Use only data that is fine to publish.

## 5. Commit, tag, publish

Bump `version` in `pyproject.toml` to X.Y.Z, refresh the lock file, then check that `CHANGELOG.md` parses and that its top entry is X.Y.Z. Do not tag until this passes:

```bash
uv lock
.venv/bin/pytest tests/test_releases.py
```

```bash
git add pyproject.toml uv.lock CHANGELOG.md docs/images/changelog/X.Y.Z
git commit -m "chore: release vX.Y.Z"
git tag vX.Y.Z
git push origin master
git push origin vX.Y.Z
```

If a push is rejected, stop and tell Max. Do not force, and do not move the tag.

Create the GitHub Release with the same text as the entry, without its `## X.Y.Z` heading. Rewrite image links to absolute ones:

```bash
sed -E "s#\]\((docs/images/[^)]+)\)#](https://raw.githubusercontent.com/$GITHUB_REPO/vX.Y.Z/\1)#g" "$WORK/entry.md" > "$WORK/notes.md"
gh release create vX.Y.Z --repo "$GITHUB_REPO" --title X.Y.Z --notes-file "$WORK/notes.md"
```

## 6. Afterwards

Tell Max the release URL (`gh release view vX.Y.Z --repo "$GITHUB_REPO" --json url -q .url`).

Prod is not updated by merging or by this skill. It updates with **Обновить до X.Y.Z** in the app or with `make update` in the prod copy (`~/projects/what-to-do-prod`).

A change to `scripts/update.sh` takes effect one release later: a copy updates with the script it already has.
