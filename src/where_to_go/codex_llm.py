from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from openai_codex import ApprovalMode, AsyncCodex, CodexConfig, ImageInput, InputItem, TextInput, TransportClosedError
from openai_codex.generated.v2_all import (
    AgentMessageThreadItem,
    CodexErrorInfoValue,
    ItemCompletedNotification,
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


class CodexRuntime:
    """One `codex app-server` for the whole app, started on the first Codex call and closed on shutdown.

    Before every call the installed Codex is looked up and checked by the tool guard, so a Codex that went
    missing, too old or started offering a tool is never handed a post. A server that died is replaced on the
    next call."""

    def __init__(
        self,
        cli: InstalledCli,
        home: CodexHome,
        guard: ToolGuard,
        client_factory: Callable[[CodexConfig], AsyncCodex] = AsyncCodex,
    ) -> None:
        self._cli = cli
        self._home = home
        self._guard = guard
        self._client_factory = client_factory
        self._client: AsyncCodex | None = None
        self._started_with: Path | None = None
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
                config = CodexConfig(codex_bin=str(found.path), cwd=self.workdir, env=self._home.environ({}))
                self._client = self._client_factory(config)
                self._started_with = found.path
            return self._client

    async def forget(self, client: AsyncCodex) -> None:
        """The server behind this client stopped: the next call starts a new one."""
        async with self._lock:
            if self._client is client:
                self._client = None
                self._started_with = None
        await self._close(client)

    async def close(self) -> None:
        async with self._lock:
            client, self._client, self._started_with = self._client, None, None
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
    every approval denied: the app's Codex home gives the model no tool and a sandbox that reads nothing."""

    def __init__(self, model: Callable[[], str], effort: Callable[[], str], runtime: CodexRuntime) -> None:
        self._model = model
        self._effort = effort
        self._runtime = runtime

    async def complete_json(
        self, system: str, prompt: str, schema: dict[str, Any], images: Sequence[LlmImage] = ()
    ) -> dict[str, Any]:
        codex = await self._runtime.client()
        try:
            turn, items = await self._ask(codex, system, prompt, schema, images)
        except (TransportClosedError, OSError) as error:
            await self._runtime.forget(codex)
            raise LlmError(f"Codex stopped: {error}") from error
        except LlmError:
            raise
        except Exception as error:
            raise LlmError(f"Codex failed: {error}") from error
        if turn is None:
            raise LlmError("Codex did not finish the answer")
        if turn.status is not TurnStatus.completed:
            raise self._failure(turn.error, turn.status)
        return self._answer(items)

    async def _ask(
        self, codex: AsyncCodex, system: str, prompt: str, schema: dict[str, Any], images: Sequence[LlmImage]
    ) -> tuple[Turn | None, list[AgentMessageThreadItem]]:
        model = self._model()
        thread = await codex.thread_start(
            model=model,
            base_instructions=system,
            ephemeral=True,
            approval_mode=ApprovalMode.deny_all,
            cwd=self._runtime.workdir,
        )
        handle = await thread.turn(
            self._input(prompt, images), model=model, effort=ReasoningEffort(self._effort()), output_schema=schema
        )
        turn: Turn | None = None
        messages: list[AgentMessageThreadItem] = []
        async for event in handle.stream():
            payload = event.payload
            if isinstance(payload, ItemCompletedNotification) and payload.turn_id == handle.id:
                item = payload.item.root
                if isinstance(item, AgentMessageThreadItem):
                    messages.append(item)
            elif isinstance(payload, TurnCompletedNotification) and payload.turn.id == handle.id:
                turn = payload.turn
        return turn, messages

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
