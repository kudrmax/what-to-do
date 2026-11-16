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
from where_to_go.claude_login import SIGN_IN_HINT, ClaudeLogin, ClaudeSignIn
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
