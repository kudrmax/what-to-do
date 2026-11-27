"""Signing in to ChatGPT for Codex: the state the app shows, the sign-in started from the app, and the API."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from openai_codex import TransportClosedError

from tests.helpers import FakeCodexCli, judge_same_titles, wait_until
from where_to_go.api import create_app
from where_to_go.codex_login import CODEX_MINIMUM, CODEX_SIGN_IN_HINT, ToolGuard
from where_to_go.codex_sign_in import CodexLogin, CodexSignInFlow
from where_to_go.container import Container
from where_to_go.installed_cli import CliStatus
from where_to_go.llm import CodexRefusedError, CodexUnavailableError, LlmError
from where_to_go.reader_sign_in import ReaderSignIn, SignInProgress

AUTH_URL = "https://auth.openai.com/oauth/authorize?client_id=c&state=s"


class FakeHandle:
    def __init__(self) -> None:
        self.auth_url = AUTH_URL
        self.outcome: SimpleNamespace | None = None
        self.dropped: Exception | None = None
        self.cancelled = 0

    def finish(self, success: bool = True, error: str | None = None) -> None:
        self.outcome = SimpleNamespace(success=success, error=error)

    def drop(self, error: Exception) -> None:
        self.dropped = error

    async def wait(self) -> SimpleNamespace:
        while self.outcome is None:
            if self.dropped is not None:
                raise self.dropped
            await asyncio.sleep(0.005)
        return self.outcome

    async def cancel(self) -> None:
        self.cancelled += 1
        self.finish(False, "Login was cancelled")


class FakeProcess:
    def __init__(self, ended: bool) -> None:
        self.ended = ended

    def poll(self) -> int | None:
        return 0 if self.ended else None


class FakeClient:
    def __init__(
        self,
        signed_in: bool = False,
        account_error: Exception | None = None,
        login_error: Exception | None = None,
        server_ended: bool = False,
    ) -> None:
        self.signed_in = signed_in
        self.account_error = account_error
        self.login_error = login_error
        self.handles: list[FakeHandle] = []
        self._client = SimpleNamespace(_sync=SimpleNamespace(_proc=FakeProcess(server_ended), _approval_handler=None))

    async def account(self) -> SimpleNamespace:
        if self.account_error is not None:
            raise self.account_error
        return SimpleNamespace(account=SimpleNamespace(type="chatgpt") if self.signed_in else None, requires_openai_auth=True)

    async def login_chatgpt(self) -> FakeHandle:
        if self.login_error is not None:
            raise self.login_error
        self.handles.append(FakeHandle())
        return self.handles[-1]


class FakeRuntime:
    """The app's Codex server, or the reason it would not start."""

    def __init__(self, client: FakeClient | None = None, error: LlmError | None = None) -> None:
        self.the_client = client or FakeClient()
        self.error = error
        self.asked = 0
        self.forgotten: list[FakeClient] = []
        self.rechecked: list[FakeClient] = []

    async def client(self) -> FakeClient:
        self.asked += 1
        if self.error is not None:
            raise self.error
        return self.the_client

    def signed_out(self, client: FakeClient) -> None:
        self.rechecked.append(client)

    async def forget(self, client: FakeClient) -> None:
        self.forgotten.append(client)

    async def close(self) -> None:
        pass


async def settle(condition) -> None:
    for _ in range(400):
        if condition():
            return
        await asyncio.sleep(0.005)
    raise AssertionError("the condition never held")


@pytest.mark.parametrize(
    ("cli", "state", "version"),
    [(FakeCodexCli(CliStatus.MISSING), ReaderSignIn.NOT_INSTALLED, None), (FakeCodexCli(CliStatus.TOO_OLD, version="0.150.0"), ReaderSignIn.TOO_OLD, "0.150.0")],
)
async def test_a_missing_or_old_codex_is_said_without_starting_it(cli: FakeCodexCli, state: ReaderSignIn, version: str | None) -> None:
    runtime = FakeRuntime()

    status = await CodexLogin(cli, runtime).state()

    assert (status.state, status.found.version, status.found.minimum) == (state, version, CODEX_MINIMUM)
    assert runtime.asked == 0


@pytest.mark.parametrize(("signed_in", "state"), [(True, ReaderSignIn.SIGNED_IN), (False, ReaderSignIn.SIGNED_OUT)])
async def test_the_login_is_asked_of_the_apps_codex_server(signed_in: bool, state: ReaderSignIn) -> None:
    status = await CodexLogin(FakeCodexCli(), FakeRuntime(FakeClient(signed_in=signed_in))).state()

    assert (status.state, status.message) == (state, None)


async def test_a_codex_the_tool_check_refuses_says_why() -> None:
    status = await CodexLogin(FakeCodexCli(), FakeRuntime(error=CodexRefusedError(ToolGuard.OFFERS_TOOLS))).state()

    assert (status.state, status.message) == (ReaderSignIn.REFUSED, ToolGuard.OFFERS_TOOLS)


async def test_a_codex_that_went_missing_before_the_server_started_is_not_installed() -> None:
    gone = FakeCodexCli(CliStatus.MISSING).found
    status = await CodexLogin(FakeCodexCli(), FakeRuntime(error=CodexUnavailableError(gone))).state()

    assert status.state is ReaderSignIn.NOT_INSTALLED


async def test_a_server_that_stopped_leaves_the_login_unknown_and_is_replaced_next_time() -> None:
    client = FakeClient(account_error=TransportClosedError("closed"), server_ended=True)
    runtime = FakeRuntime(client)

    status = await CodexLogin(FakeCodexCli(), runtime).state()

    assert status.state is ReaderSignIn.UNKNOWN
    assert runtime.forgotten == [client]


async def test_a_dropped_answer_from_a_running_server_keeps_that_server() -> None:
    client = FakeClient(account_error=TransportClosedError("closed"), server_ended=False)
    runtime = FakeRuntime(client)

    status = await CodexLogin(FakeCodexCli(), runtime).state()

    assert status.state is ReaderSignIn.UNKNOWN
    assert runtime.forgotten == []


async def test_a_server_that_stopped_before_the_sign_in_started_is_replaced_next_time() -> None:
    client = FakeClient(login_error=TransportClosedError("closed"))
    runtime = FakeRuntime(client)
    opened: list[str] = []
    flow = CodexSignInFlow(runtime, opener=opened.append)

    await flow.start()

    assert flow.progress() == SignInProgress(running=False, page_url=None, error="Couldn't start signing in: closed")
    assert runtime.forgotten == [client]
    assert opened == []


async def test_a_server_that_stopped_while_the_sign_in_waited_is_replaced_next_time() -> None:
    runtime = FakeRuntime()
    flow = CodexSignInFlow(runtime, opener=lambda url: None)
    await flow.start()

    runtime.the_client.handles[0].drop(TransportClosedError("closed"))
    await settle(lambda: not flow.progress().running)

    assert flow.progress() == SignInProgress(running=False, page_url=None, error="Signing in didn't finish: closed")
    assert runtime.forgotten == [runtime.the_client]


async def test_signing_in_opens_the_page_and_keeps_its_address_while_it_waits() -> None:
    runtime = FakeRuntime()
    opened: list[str] = []
    flow = CodexSignInFlow(runtime, opener=opened.append)

    await flow.start()

    assert opened == [AUTH_URL]
    assert flow.progress() == SignInProgress(running=True, page_url=AUTH_URL, error=None)

    runtime.the_client.handles[0].finish()
    await settle(lambda: not flow.progress().running)

    assert flow.progress() == SignInProgress(running=False, page_url=None, error=None)
    assert runtime.rechecked == [runtime.the_client]


async def test_a_second_press_does_not_start_a_second_sign_in() -> None:
    runtime = FakeRuntime()
    opened: list[str] = []
    flow = CodexSignInFlow(runtime, opener=opened.append)

    await asyncio.gather(flow.start(), flow.start())
    await flow.start()

    assert len(runtime.the_client.handles) == 1
    assert opened == [AUTH_URL]
    await flow.stop()


async def test_a_sign_in_that_failed_says_what_codex_said() -> None:
    runtime = FakeRuntime()
    flow = CodexSignInFlow(runtime, opener=lambda url: None)

    await flow.start()
    runtime.the_client.handles[0].finish(False, "Sign-in was declined")
    await settle(lambda: not flow.progress().running)

    assert flow.progress() == SignInProgress(running=False, page_url=None, error="Sign-in was declined")


async def test_stopping_cancels_the_waiting_sign_in() -> None:
    runtime = FakeRuntime()
    flow = CodexSignInFlow(runtime, opener=lambda url: None)
    await flow.start()

    await flow.stop()

    assert runtime.the_client.handles[0].cancelled == 1
    assert flow.progress().running is False


async def test_a_codex_that_is_not_ready_says_so_instead_of_signing_in() -> None:
    old = FakeCodexCli(CliStatus.TOO_OLD, version="0.150.0").found
    opened: list[str] = []
    flow = CodexSignInFlow(FakeRuntime(error=CodexUnavailableError(old)), opener=opened.append)

    await flow.start()

    assert flow.progress() == SignInProgress(running=False, page_url=None, error="Update Codex: you have 0.150.0, What To Do needs 0.172.0 or newer")
    assert opened == []


def codex_container(tmp_path, cli: FakeCodexCli, runtime: FakeRuntime, opened: list[str]) -> Container:
    container = Container.build(tmp_path / "data", matching_llm=judge_same_titles(), codex=cli, codex_runtime=runtime)
    container.codex_sign_in = CodexSignInFlow(runtime, opener=opened.append)
    return container


def test_the_api_says_codex_is_missing(tmp_path) -> None:
    container = codex_container(tmp_path, FakeCodexCli(CliStatus.MISSING), FakeRuntime(), [])
    with TestClient(create_app(lambda: container)) as client:
        answer = client.get("/codex/sign-in").json()

    assert answer == {
        "state": "not_installed",
        "hint": CODEX_SIGN_IN_HINT,
        "signing_in": False,
        "page_url": None,
        "error": None,
        "version": None,
        "minimum": CODEX_MINIMUM,
        "update_command": None,
        "message": None,
    }


def test_the_api_says_why_codex_is_refused(tmp_path) -> None:
    container = codex_container(tmp_path, FakeCodexCli(), FakeRuntime(error=CodexRefusedError(ToolGuard.OFFERS_TOOLS)), [])
    with TestClient(create_app(lambda: container)) as client:
        answer = client.get("/codex/sign-in").json()

    assert (answer["state"], answer["message"], answer["version"]) == ("refused", ToolGuard.OFFERS_TOOLS, "0.172.0")


def test_the_api_starts_the_sign_in_and_shows_when_it_is_done(tmp_path) -> None:
    runtime = FakeRuntime()
    opened: list[str] = []
    container = codex_container(tmp_path, FakeCodexCli(), runtime, opened)
    with TestClient(create_app(lambda: container)) as client:
        before = client.get("/codex/sign-in").json()
        started = client.post("/codex/sign-in").json()
        again = client.post("/codex/sign-in").json()
        runtime.the_client.signed_in = True
        runtime.the_client.handles[0].finish()
        wait_until(lambda: not client.get("/codex/sign-in").json()["signing_in"])
        after = client.get("/codex/sign-in").json()

    assert (before["state"], before["signing_in"]) == ("signed_out", False)
    assert (started["state"], started["signing_in"], started["page_url"]) == ("signed_out", True, AUTH_URL)
    assert again == started
    assert opened == [AUTH_URL]
    assert (after["state"], after["signing_in"], after["page_url"], after["error"]) == ("signed_in", False, None, None)


def test_closing_the_app_stops_a_waiting_sign_in(tmp_path) -> None:
    runtime = FakeRuntime()
    container = codex_container(tmp_path, FakeCodexCli(), runtime, [])
    with TestClient(create_app(lambda: container)) as client:
        assert client.post("/codex/sign-in").json()["signing_in"] is True

    assert runtime.the_client.handles[0].cancelled == 1
    assert container.codex_sign_in.progress().running is False
