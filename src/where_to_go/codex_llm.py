from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import os
import tempfile
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from openai_codex import ApprovalMode, AsyncCodex, CodexConfig, ImageInput, InputItem, TextInput, TransportClosedError
from openai_codex.generated.v2_all import (
    AgentMessageThreadItem,
    CodexErrorInfoValue,
    ItemCompletedNotification,
    ItemStartedNotification,
    MessagePhase,
    ReasoningEffort,
    Turn,
    TurnCompletedNotification,
    TurnError,
    TurnStatus,
)
from pydantic import BaseModel

from where_to_go.codex_login import CodexHome, ToolGuard
from where_to_go.installed_cli import CliStatus, InstalledCli
from where_to_go.llm import (
    CodexRefusedError,
    CodexSignedOutError,
    CodexUnavailableError,
    LlmError,
    LlmImage,
    PlanLimitError,
)

CLEAN_ENV = Path("/usr/bin/env")
TRIED_A_TOOL = "Codex tried to use a tool; nothing was read"
UNSAFE_PATH = "Codex is installed at a path What To Do cannot start safely"

DECLINED: dict[str, dict[str, Any]] = {
    "item/commandExecution/requestApproval": {"decision": "cancel"},
    "item/fileChange/requestApproval": {"decision": "cancel"},
    "execCommandApproval": {"decision": "abort"},
    "applyPatchApproval": {"decision": "abort"},
    "item/permissions/requestApproval": {"permissions": {}, "scope": "turn"},
    "mcpServer/elicitation/request": {"action": "cancel"},
    "item/tool/requestUserInput": {"answers": {}},
    "item/tool/call": {"contentItems": [], "success": False},
}


def decline(method: str, params: Mapping[str, Any] | None) -> dict[str, Any]:
    return DECLINED.get(method, {})


def _transport(codex: AsyncCodex) -> Any:
    """The SDK has no public switch for these, so its private client is reached here and only here; if an SDK
    update moves them, this fails loudly instead of leaving the accept-everything default in place."""
    sync = getattr(getattr(codex, "_client", None), "_sync", None)
    if sync is None or not hasattr(sync, "_approval_handler") or not hasattr(sync, "_proc"):
        raise RuntimeError("openai_codex changed: What To Do cannot reach its approval handler and process")
    return sync


def decline_every_request(codex: AsyncCodex) -> None:
    """The SDK's default handler accepts every command and file change; the app's declines everything."""
    _transport(codex)._approval_handler = decline


def server_ended(codex: AsyncCodex) -> bool:
    process = _transport(codex)._proc
    return process is None or process.poll() is not None


def start_codex(config: CodexConfig) -> AsyncCodex:
    codex = AsyncCodex(config)
    decline_every_request(codex)
    return codex


def launch_config(codex: Path, home: CodexHome, workdir: str, base: Mapping[str, str] = os.environ) -> CodexConfig:
    """The SDK starts Codex with this process's environment plus its own; `env -i` hands it the allowlist only.
    Windows, a development platform only, has no `env -i`: there the allowlist is added, nothing removed."""
    environ = home.environ(base)
    if os.name == "nt" or not CLEAN_ENV.exists():
        return CodexConfig(codex_bin=str(codex), cwd=workdir, env=environ)
    if "=" in str(codex):
        raise CodexRefusedError(UNSAFE_PATH)
    assignments = [f"{name}={value}" for name, value in environ.items()]
    launch = (str(CLEAN_ENV), "-i", *assignments, str(codex), "app-server", "--listen", "stdio://")
    return CodexConfig(launch_args_override=launch, cwd=workdir)


class CodexRuntime:
    """One `codex app-server` for the whole app, started on the first Codex call and closed on shutdown.

    Before every call the installed Codex is looked up and checked by the tool guard, so a Codex that went
    missing, too old or started offering a tool is never handed a post. A server that died is replaced on the
    next call. Each new server is asked once whether someone is signed in, so a signed-out call fails at once."""

    def __init__(
        self,
        cli: InstalledCli,
        home: CodexHome,
        guard: ToolGuard,
        client_factory: Callable[[CodexConfig], AsyncCodex] = start_codex,
    ) -> None:
        self._cli = cli
        self._home = home
        self._guard = guard
        self._client_factory = client_factory
        self._client: AsyncCodex | None = None
        self._started_with: Path | None = None
        self._signed_in: AsyncCodex | None = None
        self._workdir: tempfile.TemporaryDirectory[str] | None = None
        self._lock = asyncio.Lock()

    @property
    def workdir(self) -> str:
        """An empty folder of its own: Codex never works in the app's or the user's folders."""
        if self._workdir is None:
            self._workdir = tempfile.TemporaryDirectory(prefix="what-to-do-codex-")
        return self._workdir.name

    async def client(self) -> AsyncCodex:
        found = await asyncio.to_thread(self._cli.find)
        if found.status is not CliStatus.READY or found.path is None:
            raise CodexUnavailableError(found)
        refusal = await asyncio.to_thread(self._guard.check, found.path)
        if refusal is not None:
            raise CodexRefusedError(refusal)
        async with self._lock:
            if self._client is not None and self._started_with != found.path:
                await self._close(self._client)
                self._client = None
            if self._client is None:
                await asyncio.to_thread(self._home.prepare)
                self._client = self._client_factory(launch_config(found.path, self._home, self.workdir))
                self._started_with = found.path
                self._signed_in = None
            return self._client

    async def check_signed_in(self, client: AsyncCodex) -> None:
        if self._signed_in is client:
            return
        answer = await client.account()
        if answer.account is None and answer.requires_openai_auth:
            raise CodexSignedOutError
        self._signed_in = client

    def signed_out(self, client: AsyncCodex) -> None:
        if self._signed_in is client:
            self._signed_in = None

    async def forget(self, client: AsyncCodex) -> None:
        """The server behind this client stopped: the next call starts a new one."""
        async with self._lock:
            if self._client is client:
                self._client = None
                self._started_with = None
            self.signed_out(client)
        await self._close(client)

    async def close(self) -> None:
        async with self._lock:
            client, self._client, self._started_with, self._signed_in = self._client, None, None, None
            if client is not None:
                await self._close(client)
            if self._workdir is not None:
                self._workdir.cleanup()
                self._workdir = None

    @staticmethod
    async def _close(client: AsyncCodex) -> None:
        with contextlib.suppress(Exception):
            await client.close()


class CodexJsonLlm:
    """Structured-output calls through the Codex the user installed, signed in with ChatGPT.

    Each call is one ephemeral thread with the system text as its base instructions, no sandbox override and
    every approval denied: the app's Codex home gives the model no tool and a sandbox that reads nothing. A turn
    that still shows anything but messages and reasoning is stopped and its answer dropped."""

    ALLOWED_ITEMS = frozenset({"agentMessage", "reasoning", "userMessage"})

    def __init__(self, model: Callable[[], str], effort: Callable[[], str], runtime: CodexRuntime) -> None:
        self._model = model
        self._effort = effort
        self._runtime = runtime

    async def complete_json(
        self, system: str, prompt: str, schema: dict[str, Any], images: Sequence[LlmImage] = ()
    ) -> dict[str, Any]:
        codex = await self._runtime.client()
        try:
            await self._runtime.check_signed_in(codex)
            turn, items = await self._ask(codex, system, prompt, schema, images)
        except CodexSignedOutError:
            self._runtime.signed_out(codex)
            raise
        except (TransportClosedError, OSError) as error:
            if not server_ended(codex):
                raise LlmError(f"Codex failed: {error}") from error
            await self._runtime.forget(codex)
            raise LlmError(f"Codex stopped: {error}") from error
        except LlmError:
            raise
        except Exception as error:
            raise LlmError(f"Codex failed: {error}") from error
        if turn is None:
            raise LlmError("Codex did not finish the answer")
        if turn.status is not TurnStatus.completed:
            failure = self._failure(turn.error, turn.status)
            if isinstance(failure, CodexSignedOutError):
                self._runtime.signed_out(codex)
            raise failure
        return self._answer(items)

    async def _ask(
        self, codex: AsyncCodex, system: str, prompt: str, schema: dict[str, Any], images: Sequence[LlmImage]
    ) -> tuple[Turn | None, list[AgentMessageThreadItem]]:
        model = self._model()
        effort = ReasoningEffort(self._effort())
        thread = await codex.thread_start(
            model=model,
            base_instructions=system,
            ephemeral=True,
            approval_mode=ApprovalMode.deny_all,
            cwd=self._runtime.workdir,
        )
        handle = await thread.turn(self._input(prompt, images), model=model, effort=effort, output_schema=schema)
        turn: Turn | None = None
        messages: list[AgentMessageThreadItem] = []
        try:
            async for event in handle.stream():
                payload = event.payload
                if isinstance(payload, (ItemStartedNotification, ItemCompletedNotification)) and payload.turn_id == handle.id:
                    item = payload.item.root
                    if getattr(item, "type", None) not in self.ALLOWED_ITEMS:
                        await self._interrupt(handle)
                        raise CodexRefusedError(TRIED_A_TOOL)
                    if isinstance(payload, ItemCompletedNotification) and isinstance(item, AgentMessageThreadItem):
                        messages.append(item)
                elif isinstance(payload, TurnCompletedNotification) and payload.turn.id == handle.id:
                    turn = payload.turn
        except asyncio.CancelledError:
            await self._interrupt(handle)
            raise
        return turn, messages

    @staticmethod
    async def _interrupt(handle: Any) -> None:
        with contextlib.suppress(Exception):
            await asyncio.shield(handle.interrupt())

    @staticmethod
    def _input(prompt: str, images: Sequence[LlmImage]) -> list[InputItem]:
        """Each picture right after its caption, as a data URL: no temporary file, no path in the prompt."""
        items: list[InputItem] = [TextInput(prompt)]
        for image in images:
            items.append(TextInput(image.caption))
            items.append(ImageInput(url=f"data:{image.media_type};base64,{base64.b64encode(image.data).decode()}"))
        return items

    @staticmethod
    def _answer(messages: list[AgentMessageThreadItem]) -> dict[str, Any]:
        finals = [message for message in messages if message.phase in (MessagePhase.final_answer, None)]
        if not finals:
            raise LlmError("Codex did not answer")
        text = finals[-1].text
        try:
            answer = json.loads(text)
        except ValueError as error:
            raise LlmError(f"Codex did not return JSON: {text[:200]}") from error
        if not isinstance(answer, dict):
            raise LlmError(f"Codex did not return a JSON object: {text[:200]}")
        return answer

    @classmethod
    def _failure(cls, error: TurnError | None, status: TurnStatus) -> LlmError:
        if error is None:
            return LlmError(f"Codex turn {status.value}")
        info = error.codex_error_info.root if error.codex_error_info is not None else None
        if info == CodexErrorInfoValue.unauthorized or 401 in cls._http_statuses(info):
            return CodexSignedOutError()
        if info == CodexErrorInfoValue.usage_limit_exceeded:
            return PlanLimitError(error.message)
        return LlmError(f"Codex failed: {error.message}")

    @classmethod
    def _http_statuses(cls, info: object) -> list[int]:
        """A ChatGPT login that is missing or expired comes back as a 401 from the connection, not as `unauthorized`."""
        if isinstance(info, BaseModel):
            info = info.model_dump()
        if not isinstance(info, dict):
            return []
        found: list[int] = []
        for key, value in info.items():
            if key in ("http_status_code", "httpStatusCode") and isinstance(value, int):
                found.append(value)
            else:
                found.extend(cls._http_statuses(value))
        return found
