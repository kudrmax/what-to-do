from __future__ import annotations

import asyncio
import base64
import os
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from codex_cli_bin import bundled_codex_path
from openai_codex import ApprovalMode, AsyncCodex, CodexConfig, ImageInput, TextInput, TransportClosedError
from openai_codex.generated.v2_all import (
    ItemCompletedNotification,
    ItemStartedNotification,
    ReasoningEffort,
    ThreadStartResponse,
    TurnCompletedNotification,
)

from tests.helpers import FakeCodexCli, fake_program
from where_to_go.codex_llm import CodexJsonLlm, CodexRuntime, decline, decline_every_request, server_ended, start_codex
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

WINDOWS = os.name == "nt"
SCHEMA = {"type": "object", "properties": {"title": {"type": "string"}}, "required": ["title"]}
TURN = "turn-1"


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


class FakeProcess:
    def __init__(self) -> None:
        self.ended = False

    def poll(self) -> int | None:
        return 0 if self.ended else None


class ServerDies:
    """An event that ends the fake server's process, as when app-server crashes mid-turn."""


class Hang:
    """An event that never comes."""


class FakeHandle:
    id = TURN

    def __init__(self, client: FakeCodex, events: list[Any]) -> None:
        self._client = client
        self._events = events
        self.interrupted = False

    async def stream(self):
        for event in self._events:
            if isinstance(event, ServerDies):
                self._client.process.ended = True
                raise TransportClosedError("Codex process closed stdout")
            if isinstance(event, Hang):
                await asyncio.Event().wait()
            if isinstance(event, BaseException):
                raise event
            yield SimpleNamespace(payload=event)

    async def interrupt(self) -> None:
        self.interrupted = True


class FakeThread:
    def __init__(self, client: FakeCodex) -> None:
        self._client = client

    async def turn(self, input: Any, **options: Any) -> FakeHandle:
        self._client.turns.append({"input": input, **options})
        handle = FakeHandle(self._client, self._client.events.pop(0))
        self._client.handles.append(handle)
        return handle


class FakeCodex:
    def __init__(self, config: CodexConfig, events: list[list[Any]], dead: bool = False, signed_in: bool = True) -> None:
        self.config = config
        self.events = events
        self.process = FakeProcess()
        self.process.ended = dead
        self._client = SimpleNamespace(_sync=SimpleNamespace(_proc=self.process, _approval_handler=None))
        self.signed_in = signed_in
        self.account_asks = 0
        self.starts: list[dict[str, Any]] = []
        self.turns: list[dict[str, Any]] = []
        self.handles: list[FakeHandle] = []
        self.closed = False

    async def account(self) -> Any:
        if self.process.ended:
            raise BrokenPipeError(32, "Broken pipe")
        self.account_asks += 1
        return SimpleNamespace(account=SimpleNamespace(type="chatgpt") if self.signed_in else None, requires_openai_auth=True)

    async def thread_start(self, **options: Any) -> FakeThread:
        if self.process.ended:
            raise BrokenPipeError(32, "Broken pipe")
        self.starts.append(options)
        return FakeThread(self)

    async def close(self) -> None:
        self.closed = True
        if self.process.ended:
            raise BrokenPipeError(32, "Broken pipe")


class FakeClients:
    """Starts a fake Codex per call of the factory; each gets the turns it should answer."""

    def __init__(self, *events: list[Any], dead_first: bool = False, signed_in: bool = True) -> None:
        self._events = list(events)
        self._dead_first = dead_first
        self.signed_in = signed_in
        self.made: list[FakeCodex] = []

    def __call__(self, config: CodexConfig) -> FakeCodex:
        client = FakeCodex(config, self._events, dead=self._dead_first and not self.made, signed_in=self.signed_in)
        self.made.append(client)
        return client


def launched(config: CodexConfig) -> tuple[dict[str, str], list[str]]:
    """The environment and command a config starts Codex with, through `env -i` or, on Windows, `env`."""
    if config.launch_args_override is None:
        return dict(config.env or {}), [str(config.codex_bin), "app-server", "--listen", "stdio://"]
    args = list(config.launch_args_override)
    assert args[:2] == ["/usr/bin/env", "-i"]
    assignments = [arg for arg in args[2:] if "=" in arg and not arg.startswith("/")]
    command = args[2 + len(assignments):]
    return dict(arg.split("=", 1) for arg in assignments), command


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
    environ, command = launched(config)
    real = Path(os.path.realpath(Path("/somewhere/codex")))
    assert command == [str(real), "app-server", "--listen", "stdio://"]
    assert environ["CODEX_HOME"] == str(tmp_path / "codex")
    assert config.cwd == rt.workdir
    assert (tmp_path / "codex" / "config.toml").read_text(encoding="utf-8") == CodexHome(tmp_path / "codex").config_for(real)
    await rt.close()


@pytest.mark.skipif(WINDOWS, reason="Homebrew links do not exist on Windows")
async def test_client_starts_the_real_file_behind_a_link_with_the_home_prepared_for_it(tmp_path):
    real = fake_program(tmp_path / "Caskroom" / "codex" / "0.172.0" / "bin", "", name="codex")
    link = tmp_path / "homebrew" / "bin" / "codex"
    link.parent.mkdir(parents=True)
    link.symlink_to(real)
    clients = FakeClients(answer({"title": "a"}), answer({"title": "b"}))
    rt = runtime(clients, tmp_path, cli=FakeCodexCli(path=link))
    llm = reader(rt)
    await llm.complete_json("s", "p", SCHEMA)
    _, command = launched(clients.made[0].config)
    config = (tmp_path / "codex" / "config.toml").read_text(encoding="utf-8")
    assert command[0] == os.path.realpath(real)
    assert config == CodexHome(tmp_path / "codex").config_for(Path(os.path.realpath(real)))

    updated = fake_program(tmp_path / "Caskroom" / "codex" / "0.173.0" / "bin", "", name="codex")
    link.unlink()
    link.symlink_to(updated)
    await llm.complete_json("s", "p", SCHEMA)
    _, command = launched(clients.made[1].config)
    assert len(clients.made) == 2
    assert command[0] == os.path.realpath(updated)
    assert os.path.realpath(updated.parent) in (tmp_path / "codex" / "config.toml").read_text(encoding="utf-8")
    assert os.path.realpath(real.parent) not in (tmp_path / "codex" / "config.toml").read_text(encoding="utf-8")
    await rt.close()


async def test_client_refuses_a_codex_it_cannot_let_into_the_sandbox(tmp_path):
    clients = FakeClients(answer({"title": "a"}))
    rt = runtime(clients, tmp_path, cli=FakeCodexCli(path=tmp_path / "new\nline" / "codex"))
    with pytest.raises(CodexRefusedError) as raised:
        await reader(rt).complete_json("s", "p", SCHEMA)
    assert str(raised.value) == CodexHome.UNWRITABLE_PATH
    assert clients.made == []
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
    clients = FakeClients([ServerDies()], answer({"title": "again"}))
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
    assert [launched(client.config)[1][0] for client in clients.made] == [str(Path("/old/codex")), str(Path("/new/codex"))]
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
    """The wheel's Codex through the real SDK, started as the app starts it, up to the thread; the turn, which
    would need a login, is never sent."""

    def __init__(self, config: CodexConfig, pretend_signed_in: bool) -> None:
        self.codex = start_codex(config)
        self._client = self.codex._client
        self.pretend_signed_in = pretend_signed_in
        self.started: list[ThreadStartResponse] = []
        real = self.codex._client.thread_start

        async def recorded(params: Any) -> ThreadStartResponse:
            response = await real(params)
            self.started.append(response)
            return response

        self.codex._client.thread_start = recorded

    async def account(self) -> Any:
        real = await self.codex.account()
        return SimpleNamespace(account="someone", requires_openai_auth=True) if self.pretend_signed_in else real

    async def thread_start(self, **options: Any) -> Any:
        await self.codex.thread_start(**options)
        return self

    async def turn(self, *_: Any, **__: Any) -> Any:
        raise StopBeforeTheModel

    async def close(self) -> None:
        await self.codex.close()


def real_runtime(tmp_path: Path, made: list[RealThreadStart], pretend_signed_in: bool) -> CodexRuntime:
    def factory(config: CodexConfig) -> RealThreadStart:
        made.append(RealThreadStart(config, pretend_signed_in))
        return made[-1]

    home = CodexHome(tmp_path / "codex")
    return CodexRuntime(FakeCodexCli(path=bundled_codex_path()), home, ToolGuard(home), client_factory=factory)


async def expect_windows_refusal(rt: CodexRuntime, made: list[RealThreadStart]) -> None:
    with pytest.raises(CodexRefusedError) as raised:
        await reader(rt).complete_json("s", "p", SCHEMA)
    assert str(raised.value) == ToolGuard.CANNOT_LIMIT_READS
    assert made == []


async def test_real_thread_start_never_asks_for_approval_and_has_no_network(tmp_path):
    made: list[RealThreadStart] = []
    rt = real_runtime(tmp_path, made, pretend_signed_in=True)
    try:
        if WINDOWS:
            await expect_windows_refusal(rt, made)
            return
        with pytest.raises(LlmError) as raised:
            await reader(rt).complete_json("system text", "p", SCHEMA)
        assert isinstance(raised.value.__cause__, StopBeforeTheModel)
        assert made[0].codex._client._sync._approval_handler is decline
        started = made[0].started[0].model_dump(by_alias=True, mode="json")
        assert started["approvalPolicy"] == "never"
        assert started["sandbox"]["networkAccess"] is False
        assert started["thread"]["ephemeral"] is True
        assert Path(started["cwd"]).resolve() == Path(rt.workdir).resolve()
        assert started["instructionSources"] == []
    finally:
        await rt.close()


async def test_real_codex_without_a_login_is_signed_out_before_any_thread(tmp_path):
    made: list[RealThreadStart] = []
    rt = real_runtime(tmp_path, made, pretend_signed_in=False)
    try:
        if WINDOWS:
            await expect_windows_refusal(rt, made)
            return
        with pytest.raises(CodexSignedOutError):
            await reader(rt).complete_json("s", "p", SCHEMA)
        assert made[0].started == []
    finally:
        await rt.close()


async def test_real_server_that_was_killed_counts_as_ended(tmp_path):
    made: list[RealThreadStart] = []
    rt = real_runtime(tmp_path, made, pretend_signed_in=False)
    try:
        if WINDOWS:
            await expect_windows_refusal(rt, made)
            return
        with pytest.raises(CodexSignedOutError):
            await reader(rt).complete_json("s", "p", SCHEMA)
        codex = made[0].codex
        assert not server_ended(codex)
        codex._client._sync._proc.kill()
        codex._client._sync._proc.wait()
        assert server_ended(codex)
    finally:
        await rt.close()


def test_sdk_still_has_the_approval_handler_the_app_replaces():
    codex = start_codex(CodexConfig(codex_bin="/nowhere/codex"))
    assert codex._client._sync._approval_handler is decline
    assert server_ended(codex)


def test_moved_sdk_internals_fail_loudly():
    with pytest.raises(RuntimeError):
        decline_every_request(SimpleNamespace(_client=SimpleNamespace(_sync=SimpleNamespace())))


@pytest.mark.parametrize(
    ("method", "reply"),
    [
        ("item/commandExecution/requestApproval", {"decision": "cancel"}),
        ("item/fileChange/requestApproval", {"decision": "cancel"}),
        ("execCommandApproval", {"decision": "abort"}),
        ("applyPatchApproval", {"decision": "abort"}),
        ("item/permissions/requestApproval", {"permissions": {}, "scope": "turn"}),
        ("mcpServer/elicitation/request", {"action": "cancel"}),
        ("item/tool/requestUserInput", {"answers": {}}),
        ("item/tool/call", {"contentItems": [], "success": False}),
    ],
)
def test_every_request_from_codex_is_declined(method, reply):
    assert decline(method, {"command": "cat ~/.ssh/id_rsa"}) == reply


def tool_item(kind: str, started: bool = False) -> Any:
    items = {
        "commandExecution": {"type": "commandExecution", "id": "c1", "command": "cat ~/.zshrc", "cwd": "/", "status": "inProgress", "commandActions": []},
        "webSearch": {"type": "webSearch", "id": "w1", "query": "passwords"},
        "mcpToolCall": {"type": "mcpToolCall", "id": "m1", "server": "s", "tool": "t", "status": "inProgress", "arguments": {}},
    }
    if started:
        return ItemStartedNotification.model_validate({"item": items[kind], "threadId": "t1", "turnId": TURN, "startedAtMs": 1})
    return ItemCompletedNotification.model_validate({"item": items[kind], "threadId": "t1", "turnId": TURN, "completedAtMs": 1})


@pytest.mark.parametrize(("kind", "started"), [("commandExecution", True), ("webSearch", False), ("mcpToolCall", True)])
async def test_a_tool_in_the_turn_stops_it_and_drops_the_answer(tmp_path, kind, started):
    clients = FakeClients([tool_item(kind, started), answered(json.dumps({"title": "leaked"})), completed()])
    rt = runtime(clients, tmp_path)
    with pytest.raises(CodexRefusedError) as raised:
        await reader(rt).complete_json("s", "p", SCHEMA)
    assert str(raised.value) == "Codex tried to use a tool; nothing was read"
    assert clients.made[0].handles[0].interrupted
    await rt.close()


async def test_reasoning_items_are_allowed(tmp_path):
    reasoning = ItemCompletedNotification.model_validate(
        {"item": {"type": "reasoning", "id": "r1", "summary": [], "content": []}, "threadId": "t1", "turnId": TURN, "completedAtMs": 1}
    )
    rt = runtime(FakeClients([reasoning, *answer({"title": "ok"})]), tmp_path)
    assert await reader(rt).complete_json("s", "p", SCHEMA) == {"title": "ok"}
    await rt.close()


async def test_forbidden_variables_never_reach_codex(tmp_path, monkeypatch):
    for name in ("OPENAI_API_KEY", "CODEX_API_KEY", "CODEX_ACCESS_TOKEN", "CODEX_SQLITE_HOME", "CODEX_EXEC_SERVER_URL"):
        monkeypatch.setenv(name, "secret")
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy:1")
    monkeypatch.setenv("LC_ALL", "en_US.UTF-8")
    clients = FakeClients(answer({"title": "a"}))
    rt = runtime(clients, tmp_path)
    await reader(rt).complete_json("s", "p", SCHEMA)
    environ, _ = launched(clients.made[0].config)
    assert not any(value == "secret" for value in environ.values())
    assert environ["HTTPS_PROXY"] == "http://proxy:1" and environ["LC_ALL"] == "en_US.UTF-8"
    assert environ["PATH"] == os.environ["PATH"] and environ["CODEX_HOME"] == str(tmp_path / "codex")
    await rt.close()


@pytest.mark.skipif(os.name == "nt", reason="Windows has no env -i; the allowlist is only added there")
async def test_started_codex_sees_only_the_allowlist(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "secret")
    monkeypatch.setenv("CODEX_SQLITE_HOME", "/elsewhere")
    seen = tmp_path / "seen.json"
    program = fake_program(tmp_path / "bin", f"import json, os\nopen({str(seen)!r}, 'w').write(json.dumps(dict(os.environ)))", name="codex")
    rt = CodexRuntime(FakeCodexCli(path=program), CodexHome(tmp_path / "codex"), FakeGuard())
    try:
        with pytest.raises(LlmError):
            await reader(rt).complete_json("s", "p", SCHEMA)
    finally:
        await rt.close()
    environ = json.loads(seen.read_text())
    assert "OPENAI_API_KEY" not in environ and "CODEX_SQLITE_HOME" not in environ
    assert environ["CODEX_HOME"] == str(tmp_path / "codex")
    assert set(environ) - {"CODEX_HOME", "__CF_USER_TEXT_ENCODING", "PWD", "SHLVL", "_"} <= CodexHome.ALLOWED_VARIABLES | {
        name for name in environ if name.startswith("LC_")
    }


async def test_signed_out_fails_at_once_without_a_thread(tmp_path):
    clients = FakeClients(answer({"title": "a"}), signed_in=False)
    rt = runtime(clients, tmp_path)
    with pytest.raises(CodexSignedOutError):
        await reader(rt).complete_json("s", "p", SCHEMA)
    assert clients.made[0].starts == []
    await rt.close()


async def test_signed_in_is_asked_once_per_server_and_again_after_a_sign_out(tmp_path):
    error = {"message": "401", "codexErrorInfo": "unauthorized"}
    clients = FakeClients(answer({"title": "a"}), answer({"title": "b"}), [completed("failed", error)], answer({"title": "c"}))
    rt = runtime(clients, tmp_path)
    llm = reader(rt)
    await llm.complete_json("s", "p", SCHEMA)
    await llm.complete_json("s", "p", SCHEMA)
    assert clients.made[0].account_asks == 1
    with pytest.raises(CodexSignedOutError):
        await llm.complete_json("s", "p", SCHEMA)
    await llm.complete_json("s", "p", SCHEMA)
    assert clients.made[0].account_asks == 2
    await rt.close()


async def test_closed_turn_stream_on_a_live_server_keeps_the_server(tmp_path):
    clients = FakeClients([TransportClosedError("Turn subscription closed")], answer({"title": "same"}))
    rt = runtime(clients, tmp_path)
    llm = reader(rt)
    with pytest.raises(LlmError) as raised:
        await llm.complete_json("s", "p", SCHEMA)
    assert "Codex failed" in str(raised.value)
    assert await llm.complete_json("s", "p", SCHEMA) == {"title": "same"}
    assert len(clients.made) == 1 and not clients.made[0].closed
    await rt.close()


async def test_cancelled_call_interrupts_the_turn(tmp_path):
    clients = FakeClients([Hang()])
    rt = runtime(clients, tmp_path)
    call = asyncio.create_task(reader(rt).complete_json("s", "p", SCHEMA))
    while not clients.made or not clients.made[0].handles:
        await asyncio.sleep(0.01)
    await asyncio.sleep(0.01)
    call.cancel()
    with pytest.raises(asyncio.CancelledError):
        await call
    assert clients.made[0].handles[0].interrupted
    await rt.close()


def test_plan_limit_reset_time_stops_at_the_sentence():
    message = "You've hit your usage limit. Try again at Nov 28th, 2026 3:45 PM. Visit https://chatgpt.com/settings/usage to buy more."
    assert str(PlanLimitError(message)) == "ChatGPT plan limit reached, resets at Nov 28th, 2026 3:45 PM"


async def test_effort_is_read_before_the_thread_starts(tmp_path):
    clients = FakeClients(answer({"title": "a"}))
    rt = runtime(clients, tmp_path)
    with pytest.raises(LlmError):
        await CodexJsonLlm(lambda: "gpt-6-luna", lambda: "", rt).complete_json("s", "p", SCHEMA)
    assert clients.made[0].starts == []
    await rt.close()
