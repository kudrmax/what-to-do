#!/bin/zsh
# Starts the server of a built What To Do.app on a free port with its own data, checks it answers, serves
# the interface, carries no Claude CLI or Codex programs of its own, reports the state of the installed Claude Code
# and Codex, stops with no process left, and leaves the bundle as it was signed.
# Usage: smoke-test-bundle.sh "<path to What To Do.app>"
set -euo pipefail

app=${1:?path to What To Do.app}
app=${app:A}
python=$app/Contents/Resources/python/bin/python3
scratch=$(mktemp -d)
port=$(/usr/bin/python3 -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])')
export WHERE_TO_GO_STATE_DIR=$scratch/state WHERE_TO_GO_DATA_DIR=$scratch/data PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1
unset PYTHONHOME PYTHONPATH VIRTUAL_ENV
cd "$scratch"

fail() { echo "SMOKE TEST FAILED: $1"; "$python" -m where_to_go down >/dev/null 2>&1 || true; exit 1; }

"$python" -m where_to_go up --port "$port" || fail "the server didn't start"
version=$(curl -sf "http://127.0.0.1:$port/api/version") || fail "no answer on /api/version"
echo "Answers: $version"
curl -sf "http://127.0.0.1:$port/" | grep -q '<title>What To Do</title>' || fail "the interface isn't served"
sdk=$("$python" -c 'import claude_agent_sdk, pathlib; print(pathlib.Path(claude_agent_sdk.__file__).parent)') || fail "the bundle's Python can't import claude_agent_sdk"
[[ -d $sdk ]] || fail "claude_agent_sdk isn't a folder: $sdk"
[[ ! -e $sdk/_bundled ]] || fail "the bundle carries the Claude CLI of claude-agent-sdk"
curl -sf "http://127.0.0.1:$port/api/claude/sign-in" | grep -qE '"state":"(signed_in|signed_out|not_installed|too_old)"' || fail "the sign-in state of Claude Code didn't come back"
codex=$("$python" -c 'import codex_cli_bin, openai_codex, pathlib; print(pathlib.Path(codex_cli_bin.__file__).parent)') || fail "the bundle's Python can't import codex_cli_bin and openai_codex"
[[ -d $codex ]] || fail "codex_cli_bin isn't a folder: $codex"
[[ ! -e $codex/bin && ! -e $codex/codex-path ]] || fail "the bundle carries the Codex programs of codex_cli_bin"
codex_programs=$(find "$codex" -type f -exec file {} + | grep 'Mach-O' || true)
[[ -z $codex_programs ]] || fail "codex_cli_bin carries programs: $codex_programs"
curl -sf "http://127.0.0.1:$port/api/codex/sign-in" | grep -qE '"state":"(signed_in|signed_out|not_installed|too_old|refused|unknown)"' || fail "the sign-in state of Codex didn't come back"
"$python" -m where_to_go down
sleep 1
if pgrep -f "$app/Contents/Resources/python" >/dev/null; then fail "processes are left: $(pgrep -fl "$app/Contents/Resources/python")"; fi
codesign --verify --strict "$app" || fail "running the app changed its bundle"
echo "Smoke test passed."
