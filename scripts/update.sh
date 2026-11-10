#!/bin/bash
# Moves this copy to the latest release, the way you would by hand:
#   git fetch --tags; make down; git checkout <latest tag>; make up
# `make up` installs the packages the new version needs. The app's Update button runs this
# same script. When a step fails, the script stops there and says which step it was.
#
# Runs in the copy's folder. Its pid is in .pids/update.pid while it runs; it ends by
# writing `done` or `failed` to .pids/update.state, which the app reads after the restart.
# Its stages for the user go to .pids/update.progress; while the app is stopped, a small
# status server answers the page on the app's port so the page can show them. Everything
# it prints goes to .logs/update.log, and to the terminal when run from one.
#
# Everything is inside main(): bash reads a script as it runs, and the checkout below
# rewrites this very file.

set -uo pipefail

main() {
    MAKE="${MAKE:-make}"
    APPS_DIR="${UPDATE_APPS_DIR:-$HOME/Applications}"
    STATE_FILE=.pids/update.state
    PID_FILE=.pids/update.pid
    ERROR_FILE=.pids/update.error
    PROGRESS_FILE=.pids/update.progress
    # `make up` stops the status server by this file right before the app takes the port.
    STATUS_PID_FILE=.pids/update_status.pid
    LOG_FILE=.logs/update.log
    RELEASE_TAG_PATTERN='^v[0-9]+\.[0-9]+\.[0-9]+$'
    MACOS_DIR=macos
    PLIST_BUDDY=/usr/libexec/PlistBuddy
    APP_DIR_KEY=WTGProjectDir
    # The system Python: the copy's .venv may be reinstalled while the server runs.
    STATUS_PYTHON="${UPDATE_STATUS_PYTHON:-/usr/bin/python3}"
    STATUS_SERVER="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/update_status_server.py"
    # The app's own port and address (see `make up`); no port, no status server.
    STATUS_PORT="${UPDATE_STATUS_PORT-${PORT:-}}"
    STATUS_HOST="${UPDATE_STATUS_HOST:-127.0.0.1}"

    # The update runs unattended from the app: a git asking for a password would hang it.
    export GIT_TERMINAL_PROMPT=0

    status_server=""
    step_titles=()
    step_statuses=()

    mkdir -p .pids .logs
    start_log
    refuse_while_another_update_runs
    printf '%s' "$$" > "$PID_FILE"
    write_state running
    : > "$ERROR_FILE"

    progress_begin "Ищем новую версию" "Устанавливаем новую версию" \
        "Запускаем новую версию"
    refuse_in_worktree
    require_clean_tree
    git fetch --tags --force origin \
        || fail "Не получилось связаться с GitHub. Проверьте интернет и обновите ещё раз."

    local tag
    tag=$(latest_release_tag)
    if [ -z "$tag" ]; then
        echo "No release on origin yet. Nothing to update."
        progress_end done
        finish done
    fi
    if git merge-base --is-ancestor "$tag" HEAD; then
        echo "Already up to date ($tag)."
        progress_end done
        finish done
    fi

    local old_commit
    old_commit=$(git rev-parse HEAD)
    echo "Updating to $tag..."
    step_titles[0]="Скачиваем $tag"
    step_titles[1]="Устанавливаем $tag"
    progress_advance

    "$MAKE" --no-print-directory down || fail "Не получилось остановить приложение (make down)."
    start_status_server
    git checkout --quiet "$tag" || fail "Не получилось переключиться на $tag (git checkout)."
    if macos_code_changed "$old_commit" "$tag" && app_of_this_copy_installed; then
        "$MAKE" --no-print-directory app || fail "Не получилось собрать macOS-приложение (make app)."
    fi
    progress_advance
    # The status server keeps answering through the install and build in `make up`, which
    # stops it right before the app takes the port.
    "$MAKE" --no-print-directory up || fail "Не получилось запустить новую версию (make up)."
    progress_advance

    echo "Updated to $tag."
    finish done
}

# The log file always; the terminal too when there is one.
start_log() {
    if [ -t 1 ]; then
        exec > >(tee -a "$LOG_FILE") 2>&1
    else
        exec >>"$LOG_FILE" 2>&1
    fi
    echo "=== make update $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
}

# A second update would stop and switch the copy under the first. The app writes the pid
# of the script it starts before the script runs, so the pid in the file may be this one.
refuse_while_another_update_runs() {
    local pid
    pid=$(cat "$PID_FILE" 2>/dev/null) || return 0
    [ -n "$pid" ] && [ "$pid" != "$$" ] || return 0
    if ps -o command= -p "$pid" 2>/dev/null | grep -q "update\.sh"; then
        echo "ERROR: another update is already running in this copy (PID $pid). Wait for it to finish." >&2
        exit 1
    fi
}

write_state() {
    printf '%s' "$1" > "$STATE_FILE"
}

fail() {
    progress_fail
    echo "ERROR: $*" >&2
    echo "$*" > "$ERROR_FILE"
    finish failed
}

finish() {
    stop_status_server
    write_state "$1"
    if [ "$1" = done ]; then exit 0; fi
    exit 1
}

# The stages the user sees, in order, each `pending`, `current`, `done` or `failed`. The
# file is replaced whole, so a reader never sees half of it: one stage per line, its status,
# a tab, its title.
write_progress() {
    local i
    for ((i = 0; i < ${#step_titles[@]}; i++)); do
        printf '%s\t%s\n' "${step_statuses[i]}" "${step_titles[i]}"
    done > "$PROGRESS_FILE.tmp"
    mv -f "$PROGRESS_FILE.tmp" "$PROGRESS_FILE"
}

progress_begin() {
    step_titles=("$@")
    step_statuses=()
    local i
    for ((i = 0; i < ${#step_titles[@]}; i++)); do step_statuses[i]=pending; done
    step_statuses[0]=current
    write_progress
}

current_step() {
    local i
    for ((i = 0; i < ${#step_statuses[@]}; i++)); do
        if [ "${step_statuses[i]}" = current ]; then echo "$i"; return; fi
    done
    echo -1
}

progress_advance() {
    local i
    i=$(current_step)
    [ "$i" -ge 0 ] || return 0
    step_statuses[i]=done
    if [ $((i + 1)) -lt ${#step_statuses[@]} ]; then step_statuses[i + 1]=current; fi
    write_progress
}

# Nothing newer to install: the stages after the check do not run.
progress_end() {
    step_titles=("${step_titles[0]}")
    step_statuses=("$1")
    write_progress
}

# The stage that broke is marked; the ones after it will not run.
progress_fail() {
    local i j
    i=$(current_step)
    [ "$i" -ge 0 ] || return 0
    step_statuses[i]=failed
    for ((j = ${#step_titles[@]} - 1; j > i; j--)); do
        unset "step_titles[j]" "step_statuses[j]"
    done
    write_progress
}

# Answers the page on the app's port while the app is stopped. `make up` stops it by its
# pid file, and waits for it, right before the app takes the port; every other way out
# stops it here. When it cannot start (the port is taken) the update goes on; the page
# shows the last stage it got.
start_status_server() {
    [ -n "$STATUS_PORT" ] || return 0
    "$STATUS_PYTHON" "$STATUS_SERVER" --port "$STATUS_PORT" --host "$STATUS_HOST" < /dev/null &
    status_server=$!
    printf '%s' "$status_server" > "$STATUS_PID_FILE"
}

# After `make up` the server is already gone: wait only collects it.
stop_status_server() {
    [ -n "$status_server" ] || return 0
    if [ -f "$STATUS_PID_FILE" ]; then kill "$status_server" 2>/dev/null; fi
    wait "$status_server" 2>/dev/null
    rm -f "$STATUS_PID_FILE"
    status_server=""
}

refuse_in_worktree() {
    if [ "$(git rev-parse --git-dir 2>/dev/null)" != "$(git rev-parse --git-common-dir 2>/dev/null)" ]; then
        fail "make update — для копий dev и prod, не для worktree. Запустите его в основной копии."
    fi
}

require_clean_tree() {
    local changes
    if ! changes=$(git status --porcelain --untracked-files=no); then
        fail "Эта папка — не git-копия приложения."
    fi
    if [ -n "$changes" ]; then
        echo "ERROR: this copy has uncommitted changes:" >&2
        echo "$changes" >&2
        fail "В этой копии есть незакоммиченные изменения. Закоммитьте или уберите их и обновите ещё раз."
    fi
}

latest_release_tag() {
    git tag --list 'v*' \
        | { grep -E "$RELEASE_TAG_PATTERN" || true; } \
        | sort -t . -k 1.2,1n -k 2,2n -k 3,3n \
        | tail -n 1
}

macos_code_changed() {
    # Exit code 1 means a difference; anything else unexpected counts as one too.
    ! git diff --quiet "$1" "$2" -- "$MACOS_DIR"
}

app_of_this_copy_installed() {
    local here plist dir
    here=$(pwd -P)
    for plist in "$APPS_DIR"/*.app/Contents/Info.plist; do
        [ -f "$plist" ] || continue
        dir=$("$PLIST_BUDDY" -c "Print :$APP_DIR_KEY" "$plist" 2>/dev/null) || continue
        [ -d "$dir" ] || continue
        if [ "$(cd "$dir" && pwd -P)" = "$here" ]; then return 0; fi
    done
    return 1
}

main "$@"
