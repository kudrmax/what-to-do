"""Claude Code without a login: the app says how to sign in, once, instead of the CLI's raw message under
Refresh, and can tell whether the login is there before a refresh."""

from __future__ import annotations

import json
import sys

import httpx
import pytest
import respx
from claude_agent_sdk import ResultMessage

from tests.helpers import add_city, judge_same_titles, photos_saying
from tests.test_pipeline import RECENT, serve_channels
from where_to_go import llm as llm_module
from where_to_go.claude_login import SIGN_IN_HINT, ClaudeLogin, ClaudeSignIn, ClaudeSignInFlow, SignInProgress
from where_to_go.container import Container
from where_to_go.llm import ClaudeJsonLlm, ClaudeSignedOutError, LlmError
from where_to_go.models import Source
from where_to_go.refresh import Stage

CLI_ANSWER = "Not logged in · Please run /login"


def fake_cli(answer: object, code: int = 0) -> list[str]:
    script = f"import sys; print({json.dumps(answer)!r}); sys.exit({code})"
    return [sys.executable, "-c", script]


def result(**overrides) -> ResultMessage:
    fields = dict(subtype="success", duration_ms=1, duration_api_ms=1, is_error=False, num_turns=1, session_id="s")
    fields.update(overrides)
    return ResultMessage(**fields)


@pytest.mark.parametrize(
    ("answer", "code", "expected"),
    [
        ({"loggedIn": True, "email": "someone@example.com"}, 0, ClaudeSignIn.SIGNED_IN),
        ({"loggedIn": False}, 1, ClaudeSignIn.SIGNED_OUT),
        ({"something": "else"}, 0, ClaudeSignIn.UNKNOWN),
        ("not json at all", 0, ClaudeSignIn.UNKNOWN),
    ],
)
def test_the_login_check_asks_the_cli(answer: object, code: int, expected: ClaudeSignIn) -> None:
    command = fake_cli(answer, code)
    if not isinstance(answer, dict):
        command = [sys.executable, "-c", f"print({answer!r})"]
    assert ClaudeLogin(command).check() is expected


def test_a_cli_that_cannot_run_leaves_the_login_unknown(tmp_path) -> None:
    assert ClaudeLogin([str(tmp_path / "no-such-cli")]).check() is ClaudeSignIn.UNKNOWN


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
        await ClaudeJsonLlm(lambda: "m").complete_json("sys", "prompt", {"type": "object"})

    assert str(raised.value) == SIGN_IN_HINT
    assert isinstance(raised.value, LlmError)


class SignedOut:
    def __init__(self) -> None:
        self.calls = 0

    async def complete_json(self, system, prompt, schema, images=()):
        self.calls += 1
        raise ClaudeSignedOutError


@respx.mock
async def test_a_refresh_without_a_login_says_so_once(tmp_path) -> None:
    extraction = SignedOut()
    container = Container.build(tmp_path, extraction_llm=extraction, matching_llm=judge_same_titles(), photo_llm=photos_saying(), http=httpx.AsyncClient())
    city = add_city(container, "Белград", "Europe/Belgrade")
    container.sources.add(Source(city_id=city.id, handle="kafana", title="Кафана"))
    container.sources.add(Source(city_id=city.id, handle="afisha", title="Афиша"))
    serve_channels([(n, RECENT, f"пост {n} " * 400) for n in range(1, 21)], [(n, RECENT, f"афиша {n} " * 400) for n in range(1, 21)])

    container.refresh.start()
    progress = await container.refresh.wait()

    assert progress.stage is Stage.DONE
    assert progress.claude_signed_out
    assert progress.errors == [SIGN_IN_HINT]
    assert extraction.calls > 1
    await container.close()


SIGN_IN_PAGE = "https://claude.com/cai/oauth/authorize?code=true&client_id=c&state=s"
LOGIN_SCRIPT = f"""
import sys, time
print("Opening browser to sign in…", flush=True)
print("If the browser didn't open, visit: {SIGN_IN_PAGE}", flush=True)
print("Paste code here if prompted > ", end="", flush=True)
code = sys.stdin.readline().strip()
while "#" not in code and code != "good":
    print("Invalid code. Please make sure the full code was copied.", flush=True)
    code = sys.stdin.readline().strip()
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


def login_cli(tmp_path) -> list[str]:
    script = tmp_path / "login.py"
    script.write_text(LOGIN_SCRIPT, encoding="utf-8")
    arguments = tmp_path / "arguments.txt"
    recorder = f"import sys, runpy; open({str(arguments)!r}, 'w').write(' '.join(sys.argv[1:])); sys.argv = sys.argv[:1]; runpy.run_path({str(script)!r}, run_name='__main__')"
    return [sys.executable, "-c", recorder]


def wait_until(condition, timeout: float = 15) -> None:
    import time

    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, "timed out"
        time.sleep(0.05)


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
    flow = ClaudeSignInFlow([str(tmp_path / "no-such-cli")])
    flows.append(flow)

    flow.start()

    progress = flow.progress()
    assert not progress.running
    assert progress.error is not None and progress.error.startswith("Couldn't start signing in")


def test_the_api_starts_the_sign_in_and_takes_the_code(tmp_path, monkeypatch) -> None:
    from fastapi.testclient import TestClient

    from where_to_go.api import create_app

    monkeypatch.setattr(ClaudeLogin, "check", lambda self: ClaudeSignIn.SIGNED_OUT)
    container = Container.build(tmp_path / "data", matching_llm=judge_same_titles())
    container.claude_sign_in = ClaudeSignInFlow(login_cli(tmp_path))
    with TestClient(create_app(lambda: container)) as client:
        assert client.post("/claude/sign-in/code", json={"code": "good"}).status_code == 409

        started = client.post("/claude/sign-in").json()
        wait_until(lambda: client.get("/claude/sign-in").json()["page_url"] is not None)
        waiting = client.get("/claude/sign-in").json()
        client.post("/claude/sign-in/code", json={"code": "good"})
        wait_until(lambda: not client.get("/claude/sign-in").json()["signing_in"])

    assert started["state"] == "signed_out"
    assert waiting == {"state": "signed_out", "hint": SIGN_IN_HINT, "signing_in": True, "page_url": SIGN_IN_PAGE, "error": None}
