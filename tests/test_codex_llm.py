from __future__ import annotations

import base64
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from codex_cli_bin import bundled_codex_path
from openai_codex import ApprovalMode, AsyncCodex, CodexConfig, ImageInput, TextInput, TransportClosedError
from openai_codex.generated.v2_all import (
    ItemCompletedNotification,
    ReasoningEffort,
    ThreadStartResponse,
    TurnCompletedNotification,
)

from where_to_go.codex_llm import CodexJsonLlm, CodexRuntime
from where_to_go.codex_login import CODEX_MINIMUM, CodexHome, ToolGuard
from where_to_go.installed_cli import CliStatus, FoundCli
from where_to_go.llm import (
    CodexRefusedError,
    CodexSignedOutError,
    CodexUnavailableError,
    LlmError,
    LlmImage,
    PlanLimitError,
    ReaderNotReadyError,
)

SCHEMA = {"type": "object", "properties": {"title": {"type": "string"}}, "required": ["title"]}
TURN = "turn-1"


class FakeCodexCli:
    def __init__(self, status: CliStatus = CliStatus.READY, path: Path | None = Path("/fake/codex"), version: str | None = "0.172.0") -> None:
        self.found = FoundCli(status, None if status is CliStatus.MISSING else path, version, CODEX_MINIMUM, "codex update")

    def find(self) -> FoundCli:
        return self.found


class FakeGuard:
    def __init__(self, verdict: str | None = None) -> None:
        self.verdict = verdict
        self.checked: list[Path] = []

    def check(self, codex: Path) -> str | None:
        self.checked.append(codex)
        return self.verdict


def answered(text: str, phase: str | None = "final_answer") -> ItemCompletedNotification:
    item = {"type": "agentMessage", "id": "m1", "text": text}
    if phase:
        item["phase"] = phase
    return ItemCompletedNotification.model_validate({"item": item, "threadId": "t1", "turnId": TURN, "completedAtMs": 1})


def completed(status: str = "completed", error: dict[str, Any] | None = None) -> TurnCompletedNotification:
    turn = {"id": TURN, "items": [], "status": status, "error": error}
    return TurnCompletedNotification.model_validate({"threadId": "t1", "turn": turn})


def answer(data: dict[str, Any]) -> list[Any]:
    return [answered(json.dumps(data)), completed()]


class FakeHandle:
    id = TURN

    def __init__(self, events: list[Any]) -> None:
        self._events = events

    async def stream(self):
        for event in self._events:
            if isinstance(event, BaseException):
                raise event
            yield SimpleNamespace(payload=event)


class FakeThread:
    def __init__(self, client: FakeCodex) -> None:
        self._client = client

    async def turn(self, input: Any, **options: Any) -> FakeHandle:
        self._client.turns.append({"input": input, **options})
        return FakeHandle(self._client.events.pop(0))


class FakeCodex:
    def __init__(self, config: CodexConfig, events: list[list[Any]], dead: bool = False) -> None:
        self.config = config
        self.events = events
        self.dead = dead
        self.starts: list[dict[str, Any]] = []
        self.turns: list[dict[str, Any]] = []
        self.closed = False

    async def thread_start(self, **options: Any) -> FakeThread:
        if self.dead:
            raise BrokenPipeError(32, "Broken pipe")
        self.starts.append(options)
        return FakeThread(self)

    async def close(self) -> None:
        self.closed = True
        if self.dead:
            raise BrokenPipeError(32, "Broken pipe")


class FakeClients:
    """Starts a fake Codex per call of the factory; each gets the turns it should answer."""

    def __init__(self, *events: list[Any], dead_first: bool = False) -> None:
        self._events = list(events)
        self._dead_first = dead_first
        self.made: list[FakeCodex] = []

    def __call__(self, config: CodexConfig) -> FakeCodex:
        client = FakeCodex(config, self._events, dead=self._dead_first and not self.made)
        self.made.append(client)
        return client


def runtime(clients: FakeClients, tmp_path: Path, cli: FakeCodexCli | None = None, guard: FakeGuard | None = None) -> CodexRuntime:
    return CodexRuntime(cli or FakeCodexCli(), CodexHome(tmp_path / "codex"), guard or FakeGuard(), client_factory=clients)


def reader(rt: CodexRuntime, model: str = "gpt-6.1-terra", effort: str = "medium") -> CodexJsonLlm:
    return CodexJsonLlm(lambda: model, lambda: effort, rt)


async def test_thread_gets_no_sandbox_deny_all_and_the_system_text(tmp_path):
    clients = FakeClients(answer({"title": "Concert"}))
    rt = runtime(clients, tmp_path)
    assert await reader(rt).complete_json("system text", "the post", SCHEMA) == {"title": "Concert"}
    start = clients.made[0].starts[0]
    assert "sandbox" not in start
    assert start["approval_mode"] is ApprovalMode.deny_all
    assert start["base_instructions"] == "system text"
    assert start["ephemeral"] is True
    assert start["model"] == "gpt-6.1-terra"
    assert start["cwd"] == rt.workdir and list(Path(rt.workdir).iterdir()) == []
    await rt.close()


async def test_turn_gets_schema_model_and_effort_and_never_a_sandbox(tmp_path):
    clients = FakeClients(answer({"title": "a"}), answer({"title": "b"}))
    rt = runtime(clients, tmp_path)
    efforts = iter(["low", "high"])
    models = iter(["gpt-6-luna", "gpt-6.2-sol"])
    llm = CodexJsonLlm(lambda: next(models), lambda: next(efforts), rt)
    await llm.complete_json("s", "p", SCHEMA)
    await llm.complete_json("s", "p", SCHEMA)
    first, second = clients.made[0].turns
    assert all("sandbox" not in turn and "approval_mode" not in turn for turn in (first, second))
    assert first["output_schema"] == SCHEMA
    assert (first["model"], first["effort"]) == ("gpt-6-luna", ReasoningEffort.low)
    assert (second["model"], second["effort"]) == ("gpt-6.2-sol", ReasoningEffort.high)
    assert len(clients.made) == 1
    await rt.close()


async def test_client_starts_the_found_codex_with_the_app_home(tmp_path):
    clients = FakeClients(answer({"title": "a"}))
    rt = runtime(clients, tmp_path, cli=FakeCodexCli(path=Path("/somewhere/codex")))
    await reader(rt).complete_json("s", "p", SCHEMA)
    config = clients.made[0].config
    assert config.codex_bin == "/somewhere/codex"
    assert config.env == {"CODEX_HOME": str(tmp_path / "codex")}
    assert config.cwd == rt.workdir
    assert (tmp_path / "codex" / "config.toml").read_text(encoding="utf-8") == CodexHome.CONFIG
    await rt.close()


async def test_images_follow_their_captions_as_data_urls(tmp_path):
    big = bytes(range(256)) * 20_000
    images = [LlmImage("Photo 1 of the post:", "image/jpeg", b"\xff\xd8one"), LlmImage("Photo 2 of the post:", "image/png", big)]
    clients = FakeClients(answer({"title": "a"}))
    rt = runtime(clients, tmp_path)
    await reader(rt).complete_json("s", "the post", SCHEMA, images)
    given = clients.made[0].turns[0]["input"]
    assert given == [
        TextInput("the post"),
        TextInput("Photo 1 of the post:"),
        ImageInput(url="data:image/jpeg;base64," + base64.b64encode(b"\xff\xd8one").decode()),
        TextInput("Photo 2 of the post:"),
        ImageInput(url="data:image/png;base64," + base64.b64encode(big).decode()),
    ]
    assert list(Path(rt.workdir).iterdir()) == []
    await rt.close()


async def test_last_final_message_is_the_answer(tmp_path):
    events = [answered("thinking aloud", phase="commentary"), answered(json.dumps({"title": "x"}), phase=None), completed()]
    rt = runtime(FakeClients(events), tmp_path)
    assert await reader(rt).complete_json("s", "p", SCHEMA) == {"title": "x"}
    await rt.close()


@pytest.mark.parametrize("text", ["not json", "[1, 2]"])
async def test_answer_that_is_not_a_json_object_fails(tmp_path, text):
    rt = runtime(FakeClients([answered(text), completed()]), tmp_path)
    with pytest.raises(LlmError) as raised:
        await reader(rt).complete_json("s", "p", SCHEMA)
    assert not isinstance(raised.value, ReaderNotReadyError)
    await rt.close()


async def test_unauthorized_means_signed_out(tmp_path):
    error = {"message": "401", "codexErrorInfo": "unauthorized"}
    rt = runtime(FakeClients([completed("failed", error)]), tmp_path)
    with pytest.raises(CodexSignedOutError) as raised:
        await reader(rt).complete_json("s", "p", SCHEMA)
    assert isinstance(raised.value, ReaderNotReadyError)
    await rt.close()


async def test_missing_login_seen_as_a_connection_401_means_signed_out(tmp_path):
    error = {"message": "unexpected status 401 Unauthorized", "codexErrorInfo": {"httpConnectionFailed": {"httpStatusCode": 401}}}
    rt = runtime(FakeClients([completed("failed", error)]), tmp_path)
    with pytest.raises(CodexSignedOutError):
        await reader(rt).complete_json("s", "p", SCHEMA)
    await rt.close()


async def test_usage_limit_is_a_plan_limit_with_the_reset_time(tmp_path):
    message = "You've hit your usage limit. Upgrade to Plus to continue using Codex, or try again at 3:45 PM."
    error = {"message": message, "codexErrorInfo": "usageLimitExceeded"}
    rt = runtime(FakeClients([completed("failed", error)]), tmp_path)
    with pytest.raises(PlanLimitError) as raised:
        await reader(rt).complete_json("s", "p", SCHEMA)
    assert str(raised.value) == "ChatGPT plan limit reached, resets at 3:45 PM"
    assert isinstance(raised.value, ReaderNotReadyError)
    await rt.close()


def test_plan_limit_without_a_reset_time():
    assert str(PlanLimitError("You've hit your usage limit.")) == "ChatGPT plan limit reached"


async def test_other_turn_errors_carry_the_message(tmp_path):
    error = {"message": "model not found", "codexErrorInfo": "modelNotFound"}
    rt = runtime(FakeClients([completed("failed", error)]), tmp_path)
    with pytest.raises(LlmError) as raised:
        await reader(rt).complete_json("s", "p", SCHEMA)
    assert not isinstance(raised.value, ReaderNotReadyError)
    assert "model not found" in str(raised.value)
    await rt.close()


async def test_guard_refusal_sends_nothing(tmp_path):
    clients = FakeClients(answer({"title": "a"}))
    guard = FakeGuard(ToolGuard.OFFERS_TOOLS)
    rt = runtime(clients, tmp_path, guard=guard)
    with pytest.raises(CodexRefusedError) as raised:
        await reader(rt).complete_json("s", "p", SCHEMA)
    assert str(raised.value) == ToolGuard.OFFERS_TOOLS
    assert isinstance(raised.value, ReaderNotReadyError)
    assert guard.checked == [Path("/fake/codex")]
    assert clients.made == []
    await rt.close()


@pytest.mark.parametrize(
    ("cli", "message"),
    [
        (FakeCodexCli(CliStatus.MISSING), "Install Codex: What To Do needs it to read posts"),
        (FakeCodexCli(CliStatus.TOO_OLD, version="0.150.0"), f"Update Codex: you have 0.150.0, What To Do needs {CODEX_MINIMUM} or newer"),
    ],
)
async def test_missing_or_too_old_codex_sends_nothing(tmp_path, cli, message):
    clients = FakeClients(answer({"title": "a"}))
    guard = FakeGuard()
    rt = runtime(clients, tmp_path, cli=cli, guard=guard)
    with pytest.raises(CodexUnavailableError) as raised:
        await reader(rt).complete_json("s", "p", SCHEMA)
    assert str(raised.value) == message
    assert raised.value.found is cli.found
    assert guard.checked == [] and clients.made == []
    await rt.close()


async def test_dead_server_is_replaced_on_the_next_call(tmp_path):
    clients = FakeClients(answer({"title": "second"}), dead_first=True)
    rt = runtime(clients, tmp_path)
    llm = reader(rt)
    with pytest.raises(LlmError) as raised:
        await llm.complete_json("s", "p", SCHEMA)
    assert not isinstance(raised.value, ReaderNotReadyError)
    assert clients.made[0].closed
    assert await llm.complete_json("s", "p", SCHEMA) == {"title": "second"}
    assert len(clients.made) == 2
    await rt.close()


async def test_server_closing_mid_turn_is_replaced_on_the_next_call(tmp_path):
    clients = FakeClients([TransportClosedError("Codex process closed stdout")], answer({"title": "again"}))
    rt = runtime(clients, tmp_path)
    llm = reader(rt)
    with pytest.raises(LlmError):
        await llm.complete_json("s", "p", SCHEMA)
    assert await llm.complete_json("s", "p", SCHEMA) == {"title": "again"}
    assert len(clients.made) == 2 and clients.made[0].closed
    await rt.close()


async def test_a_different_codex_starts_a_new_server(tmp_path):
    cli = FakeCodexCli(path=Path("/old/codex"))
    clients = FakeClients(answer({"title": "a"}), answer({"title": "b"}))
    rt = runtime(clients, tmp_path, cli=cli)
    await reader(rt).complete_json("s", "p", SCHEMA)
    cli.found = FoundCli(CliStatus.READY, Path("/new/codex"), "0.173.0", CODEX_MINIMUM, "codex update")
    await reader(rt).complete_json("s", "p", SCHEMA)
    assert [client.config.codex_bin for client in clients.made] == ["/old/codex", "/new/codex"]
    assert clients.made[0].closed
    await rt.close()


async def test_close_stops_the_server_and_removes_the_folder(tmp_path):
    clients = FakeClients(answer({"title": "a"}))
    rt = runtime(clients, tmp_path)
    await reader(rt).complete_json("s", "p", SCHEMA)
    folder = Path(rt.workdir)
    await rt.close()
    assert clients.made[0].closed and not folder.exists()


class StopBeforeTheModel(Exception):
    pass


class RealThreadStart:
    """The wheel's Codex through the real SDK up to the thread; the turn, which would need a login, is never sent."""

    def __init__(self, config: CodexConfig) -> None:
        self.codex = AsyncCodex(config)
        self.started: list[ThreadStartResponse] = []
        real = self.codex._client.thread_start

        async def recorded(params: Any) -> ThreadStartResponse:
            response = await real(params)
            self.started.append(response)
            return response

        self.codex._client.thread_start = recorded

    async def thread_start(self, **options: Any) -> Any:
        await self.codex.thread_start(**options)
        return self

    async def turn(self, *_: Any, **__: Any) -> Any:
        raise StopBeforeTheModel

    async def close(self) -> None:
        await self.codex.close()


async def test_real_thread_start_never_asks_for_approval_and_has_no_network(tmp_path):
    made: list[RealThreadStart] = []

    def factory(config: CodexConfig) -> RealThreadStart:
        made.append(RealThreadStart(config))
        return made[-1]

    home = CodexHome(tmp_path / "codex")
    cli = FakeCodexCli(path=bundled_codex_path())
    rt = CodexRuntime(cli, home, ToolGuard(home), client_factory=factory)
    try:
        with pytest.raises(LlmError) as raised:
            await reader(rt).complete_json("system text", "p", SCHEMA)
        assert isinstance(raised.value.__cause__, StopBeforeTheModel)
        started = made[0].started[0].model_dump(by_alias=True, mode="json")
        assert started["approvalPolicy"] == "never"
        assert started["sandbox"]["networkAccess"] is False
        assert started["thread"]["ephemeral"] is True
        assert Path(started["cwd"]).resolve() == Path(rt.workdir).resolve()
        assert started["instructionSources"] == []
    finally:
        await rt.close()
