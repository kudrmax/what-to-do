"""Claude Code without a login: the app says how to sign in, once, instead of the CLI's raw message under
Refresh, and can tell whether the login is there before a refresh."""

from __future__ import annotations

import json
import time
from pathlib import Path

import httpx
import pytest
import respx
from claude_agent_sdk import ResultMessage

from tests.helpers import FakeClaude, add_city, fake_program, judge_same_titles, photos_saying, wait_until
from tests.test_pipeline import RECENT, serve_channels
from where_to_go import llm as llm_module
from where_to_go.claude_login import SIGN_IN_HINT, ClaudeLogin, ClaudeSignInFlow
from where_to_go.reader_sign_in import ReaderSignIn, SignInProgress
from where_to_go.container import Container
from where_to_go.installed_cli import CliStatus, InstalledCli
from where_to_go.llm import ClaudeJsonLlm, ClaudeSignedOutError, ClaudeUnavailableError, LlmError
from where_to_go.models import Source
from where_to_go.refresh import Stage
from where_to_go.settings import LlmProvider

CLI_ANSWER = "Not logged in · Please run /login"


def auth_status(tmp_path: Path, answer: object, code: int = 0) -> Path:
    printed = json.dumps(answer) if isinstance(answer, dict) else answer
    return fake_program(tmp_path / "bin", f"import sys; print({printed!r}); sys.exit({code})")


def result(**overrides) -> ResultMessage:
    fields = dict(subtype="success", duration_ms=1, duration_api_ms=1, is_error=False, num_turns=1, session_id="s")
    fields.update(overrides)
    return ResultMessage(**fields)


@pytest.mark.parametrize(
    ("answer", "code", "expected"),
    [
        ({"loggedIn": True, "email": "someone@example.com"}, 0, ReaderSignIn.SIGNED_IN),
        ({"loggedIn": False}, 1, ReaderSignIn.SIGNED_OUT),
        ({"something": "else"}, 0, ReaderSignIn.UNKNOWN),
        ("not json at all", 0, ReaderSignIn.UNKNOWN),
    ],
)
def test_the_login_check_asks_the_cli(tmp_path, answer: object, code: int, expected: ReaderSignIn) -> None:
    assert ClaudeLogin(FakeClaude(path=auth_status(tmp_path, answer, code))).check() is expected


def test_a_cli_that_cannot_run_leaves_the_login_unknown(tmp_path) -> None:
    assert ClaudeLogin(FakeClaude(path=tmp_path / "no-such-cli")).check() is ReaderSignIn.UNKNOWN


def test_login_check_not_installed(tmp_path) -> None:
    assert ClaudeLogin(FakeClaude(CliStatus.MISSING)).check() is ReaderSignIn.NOT_INSTALLED


def test_login_check_too_old(tmp_path) -> None:
    signed_in = auth_status(tmp_path, {"loggedIn": True})

    assert ClaudeLogin(FakeClaude(CliStatus.TOO_OLD, path=signed_in, version="2.1.200")).check() is ReaderSignIn.TOO_OLD


def test_installing_while_the_app_runs_is_noticed_on_the_next_check(tmp_path) -> None:
    claude = InstalledCli("claude", "2.1.321", extra_dirs=lambda: [tmp_path / "bin"], environ={"PATH": ""}, run_version=lambda path: "2.1.325")
    login = ClaudeLogin(claude)
    assert login.check() is ReaderSignIn.NOT_INSTALLED

    auth_status(tmp_path, {"loggedIn": True})

    assert login.check() is ReaderSignIn.SIGNED_IN


@pytest.mark.parametrize("message", [CLI_ANSWER, "Invalid API key · Please run /login", "OAuth token has expired"])
def test_the_clis_signed_out_answers_are_recognised(message: str) -> None:
    assert ClaudeLogin.means_signed_out(message)


def test_other_failures_are_not_taken_for_a_missing_login() -> None:
    assert not ClaudeLogin.means_signed_out("overloaded")


@pytest.mark.parametrize(
    ("messages", "error"),
    [((result(is_error=True, result=CLI_ANSWER),), None), ((), RuntimeError(f"Command failed: {CLI_ANSWER}"))],
)
async def test_a_call_without_a_login_says_how_to_sign_in(monkeypatch, messages, error) -> None:
    async def query(prompt, options):
        if error:
            raise error
        for message in messages:
            yield message

    monkeypatch.setattr(llm_module, "query", query)

    with pytest.raises(ClaudeSignedOutError) as raised:
        await ClaudeJsonLlm(lambda: "m", FakeClaude()).complete_json("sys", "prompt", {"type": "object"})

    assert str(raised.value) == SIGN_IN_HINT
    assert isinstance(raised.value, LlmError)


class NotReady:
    def __init__(self, error: Exception) -> None:
        self.calls = 0
        self._error = error

    async def complete_json(self, system, prompt, schema, images=()):
        self.calls += 1
        raise self._error


@respx.mock
@pytest.mark.parametrize(
    ("error", "line"),
    [
        (ClaudeSignedOutError(), SIGN_IN_HINT),
        (ClaudeUnavailableError(FakeClaude(CliStatus.MISSING).found), "Install Claude Code: What To Do needs it to read posts"),
        (
            ClaudeUnavailableError(FakeClaude(CliStatus.TOO_OLD, version="2.1.200").found),
            "Update Claude Code: you have 2.1.200, What To Do needs 2.1.321 or newer",
        ),
    ],
)
async def test_a_refresh_without_a_usable_claude_code_says_so_once(tmp_path, error: Exception, line: str) -> None:
    extraction = NotReady(error)
    container = Container.build(tmp_path, extraction_llm=extraction, matching_llm=judge_same_titles(), photo_llm=photos_saying(), http=httpx.AsyncClient())
    city = add_city(container, "Белград", "Europe/Belgrade")
    container.sources.add(Source(city_id=city.id, handle="kafana", title="Кафана"))
    container.sources.add(Source(city_id=city.id, handle="afisha", title="Афиша"))
    serve_channels([(n, RECENT, f"пост {n} " * 400) for n in range(1, 21)], [(n, RECENT, f"афиша {n} " * 400) for n in range(1, 21)])

    container.refresh.start()
    progress = await container.refresh.wait()

    assert progress.stage is Stage.DONE
    assert (progress.reader_unavailable, progress.reader) == (True, LlmProvider.CLAUDE)
    assert progress.errors == [line]
    assert extraction.calls > 1
    await container.close()


@pytest.mark.parametrize(
    ("claude", "expected"),
    [
        (FakeClaude(CliStatus.MISSING), {"state": "not_installed", "version": None, "minimum": "2.1.321", "update_command": None}),
        (FakeClaude(CliStatus.TOO_OLD, version="2.1.200"), {"state": "too_old", "version": "2.1.200", "minimum": "2.1.321", "update_command": "claude update"}),
    ],
)
def test_the_api_says_claude_code_is_missing_or_too_old(tmp_path, claude: FakeClaude, expected: dict) -> None:
    from fastapi.testclient import TestClient

    from where_to_go.api import create_app

    container = Container.build(tmp_path / "data", matching_llm=judge_same_titles(), claude=claude)
    with TestClient(create_app(lambda: container)) as client:
        answer = client.get("/claude/sign-in").json()

    assert {key: answer[key] for key in expected} == expected
    assert claude.calls == 1


SIGN_IN_PAGE = "https://claude.com/cai/oauth/authorize?code=true&client_id=c&state=s"
LOGIN_SCRIPT = f"""
import sys, time
print("Opening browser to sign in…", flush=True)
print("If the browser didn't open, visit: {SIGN_IN_PAGE}", flush=True)
print("Paste code here if prompted > ", end="", flush=True)
line = sys.stdin.readline()
while line and "#" not in line and line.strip() != "good":
    print("Invalid code. Please make sure the full code was copied.", flush=True)
    line = sys.stdin.readline()
code = line.strip()
if code == "good":
    print("Login successful.")
    sys.exit(0)
print("OAuth error: Invalid code")
sys.exit(1)
"""


@pytest.fixture
def flows():
    """Every sign-in a test starts is stopped, even when the test fails."""
    started: list[ClaudeSignInFlow] = []
    yield started
    for flow in started:
        flow.stop()


def login_cli(tmp_path) -> FakeClaude:
    script = tmp_path / "login.py"
    script.write_text(LOGIN_SCRIPT, encoding="utf-8")
    arguments = tmp_path / "arguments.txt"
    recorder = f"import sys, runpy; open({str(arguments)!r}, 'w').write(' '.join(sys.argv[1:])); sys.argv = sys.argv[:1]; runpy.run_path({str(script)!r}, run_name='__main__')"
    return FakeClaude(path=fake_program(tmp_path / "bin", recorder))


def test_signing_in_from_the_app_runs_the_clis_login_and_shows_the_page_to_open_by_hand(tmp_path, flows) -> None:
    flow = ClaudeSignInFlow(login_cli(tmp_path))
    flows.append(flow)

    flow.start()
    wait_until(lambda: flow.progress().page_url is not None)

    assert (tmp_path / "arguments.txt").read_text() == "auth login --claudeai"
    assert flow.progress() == SignInProgress(running=True, page_url=SIGN_IN_PAGE, error=None)
    flow.stop()


def test_the_code_from_the_sign_in_page_finishes_the_sign_in(tmp_path, flows) -> None:
    flow = ClaudeSignInFlow(login_cli(tmp_path))
    flows.append(flow)
    flow.start()
    wait_until(lambda: flow.progress().page_url is not None)

    assert flow.submit_code("  good \n")
    wait_until(lambda: not flow.progress().running)

    assert flow.progress() == SignInProgress(running=False, page_url=None, error=None)


def test_a_wrong_code_says_what_the_cli_said(tmp_path, flows) -> None:
    flow = ClaudeSignInFlow(login_cli(tmp_path))
    flows.append(flow)
    flow.start()
    wait_until(lambda: flow.progress().page_url is not None)

    flow.submit_code("bad#state")
    wait_until(lambda: not flow.progress().running)

    assert flow.progress().error == "OAuth error: Invalid code"
    assert not flow.submit_code("good")


def test_a_code_the_cli_cannot_use_says_why_while_it_waits_for_another(tmp_path, flows) -> None:
    flow = ClaudeSignInFlow(login_cli(tmp_path))
    flows.append(flow)
    flow.start()
    wait_until(lambda: flow.progress().page_url is not None)

    flow.submit_code("half-a-code")
    wait_until(lambda: flow.progress().error is not None)

    assert flow.progress() == SignInProgress(running=True, page_url=SIGN_IN_PAGE, error="Invalid code. Please make sure the full code was copied.")
    flow.submit_code("good")
    wait_until(lambda: not flow.progress().running)
    assert flow.progress().error is None


def test_reading_the_progress_while_the_cli_prints_loses_nothing_it_printed(tmp_path, flows) -> None:
    printed = tmp_path / "printed"
    chatty = f"""
import sys
print("If the browser didn't open, visit: {SIGN_IN_PAGE}", flush=True)
for number in range(3000):
    print(f"still waiting {{number}}", flush=True)
open({str(printed)!r}, "w").close()
sys.stdin.readline()
"""
    flow = ClaudeSignInFlow(FakeClaude(path=fake_program(tmp_path / "bin", chatty)))
    flows.append(flow)
    flow.start()

    deadline = time.monotonic() + 15
    while not printed.exists():
        assert time.monotonic() < deadline, "timed out"
        flow.progress()

    assert flow.progress().page_url == SIGN_IN_PAGE


def test_a_second_press_does_not_start_a_second_sign_in(tmp_path, flows) -> None:
    flow = ClaudeSignInFlow(login_cli(tmp_path))
    flows.append(flow)
    flow.start()
    wait_until(lambda: flow.progress().page_url is not None)
    first = flow._process

    flow.start()

    assert flow._process is first
    flow.stop()
    assert not flow.progress().running


def test_a_cli_that_cannot_start_says_so(tmp_path, flows) -> None:
    flow = ClaudeSignInFlow(FakeClaude(path=tmp_path / "no-such-cli"))
    flows.append(flow)

    flow.start()

    progress = flow.progress()
    assert not progress.running
    assert progress.error is not None and progress.error.startswith("Couldn't start signing in")


def test_sign_in_flow_without_cli_reports_install_hint(flows) -> None:
    flow = ClaudeSignInFlow(FakeClaude(CliStatus.MISSING))
    flows.append(flow)

    flow.start()

    progress = flow.progress()
    assert not progress.running
    assert progress.error == "Install Claude Code: What To Do needs it to read posts"
    assert "Reinstall" not in progress.error


def test_sign_in_flow_with_an_old_cli_says_to_update_it(flows) -> None:
    flow = ClaudeSignInFlow(FakeClaude(CliStatus.TOO_OLD, version="2.1.200"))
    flows.append(flow)

    flow.start()

    assert flow.progress().error == "Update Claude Code: you have 2.1.200, What To Do needs 2.1.321 or newer"


def test_the_api_starts_the_sign_in_and_takes_the_code(tmp_path, monkeypatch) -> None:
    from fastapi.testclient import TestClient

    from where_to_go.api import create_app

    monkeypatch.setattr(ClaudeLogin, "state_of", lambda self, found: ReaderSignIn.SIGNED_OUT)
    container = Container.build(tmp_path / "data", matching_llm=judge_same_titles(), claude=FakeClaude())
    container.claude_sign_in = ClaudeSignInFlow(login_cli(tmp_path))
    with TestClient(create_app(lambda: container)) as client:
        assert client.post("/claude/sign-in/code", json={"code": "good"}).status_code == 409

        started = client.post("/claude/sign-in").json()
        wait_until(lambda: client.get("/claude/sign-in").json()["page_url"] is not None)
        waiting = client.get("/claude/sign-in").json()
        client.post("/claude/sign-in/code", json={"code": "good"})
        wait_until(lambda: not client.get("/claude/sign-in").json()["signing_in"])

    assert started["state"] == "signed_out"
    assert waiting == {
        "state": "signed_out",
        "hint": SIGN_IN_HINT,
        "signing_in": True,
        "page_url": SIGN_IN_PAGE,
        "error": None,
        "version": "2.1.325",
        "minimum": "2.1.321",
        "update_command": "claude update",
    }
