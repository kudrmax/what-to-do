from __future__ import annotations

import asyncio
import base64
import re
from collections.abc import AsyncIterator, Callable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query

from where_to_go.claude_login import SIGN_IN_HINT, ClaudeCliEnvironment, ClaudeLogin, unavailable_hint
from where_to_go.codex_login import CODEX_SIGN_IN_HINT, codex_unavailable_hint
from where_to_go.installed_cli import CliStatus, FoundCli, InstalledCli


class LlmError(Exception):
    pass


class ReaderNotReadyError(LlmError):
    """Every call fails the same way until the user fixes the reader (Claude Code or Codex), so it is said once."""


class ClaudeSignedOutError(ReaderNotReadyError):
    def __init__(self) -> None:
        super().__init__(SIGN_IN_HINT)


class ClaudeUnavailableError(ReaderNotReadyError):
    def __init__(self, found: FoundCli) -> None:
        super().__init__(unavailable_hint(found))
        self.found = found


class CodexSignedOutError(ReaderNotReadyError):
    def __init__(self) -> None:
        super().__init__(CODEX_SIGN_IN_HINT)


class CodexUnavailableError(ReaderNotReadyError):
    def __init__(self, found: FoundCli) -> None:
        super().__init__(codex_unavailable_hint(found))
        self.found = found


class CodexRefusedError(ReaderNotReadyError):
    """The tool guard found something the model could act with: no post is sent."""


class PlanLimitError(ReaderNotReadyError):
    MESSAGE = "ChatGPT plan limit reached"
    RESET = re.compile(r"try again at (?P<time>.+?)(?=\.\s|\.?\s*$)", re.IGNORECASE | re.MULTILINE)

    def __init__(self, codex_message: str = "") -> None:
        reset = self.RESET.search(codex_message)
        super().__init__(f"{self.MESSAGE}, resets at {reset['time'].strip()}" if reset else self.MESSAGE)


@dataclass(frozen=True)
class LlmImage:
    """A picture the reader looks at, introduced by a caption that names it in the prompt."""

    caption: str
    media_type: str
    data: bytes


class JsonLlm(Protocol):
    async def complete_json(
        self, system: str, prompt: str, schema: dict[str, Any], images: Sequence[LlmImage] = ()
    ) -> dict[str, Any]: ...


class ClaudeJsonLlm:
    """Structured-output calls through the Claude Code the user installed (claude-agent-sdk): no API key, the user's own login.

    The model is asked for on every call, so a model changed in settings applies to the next call."""

    def __init__(self, model: Callable[[], str], cli: InstalledCli) -> None:
        self._model = model
        self._cli = cli
        ClaudeCliEnvironment.prepare()

    async def complete_json(
        self, system: str, prompt: str, schema: dict[str, Any], images: Sequence[LlmImage] = ()
    ) -> dict[str, Any]:
        found = await asyncio.to_thread(self._cli.find)
        if found.status is not CliStatus.READY or found.path is None:
            raise ClaudeUnavailableError(found)
        options = ClaudeAgentOptions(
            cli_path=str(found.path),
            model=self._model(),
            system_prompt=system,
            tools=[],
            setting_sources=[],
            max_turns=4,
            output_format={"type": "json_schema", "schema": schema},
            extra_args={"no-session-persistence": None},
        )
        result: ResultMessage | None = None
        try:
            async for message in query(prompt=self._message(prompt, images) if images else prompt, options=options):
                if isinstance(message, ResultMessage):
                    result = message
        except Exception as error:
            if ClaudeLogin.means_signed_out(str(error)):
                raise ClaudeSignedOutError from error
            raise LlmError(str(error)) from error
        if result is None or result.is_error or not isinstance(result.structured_output, dict):
            detail = (result.errors or result.result) if result else "no result"
            if ClaudeLogin.means_signed_out(str(detail)):
                raise ClaudeSignedOutError
            raise LlmError(f"Claude did not return structured output: {detail}")
        return result.structured_output

    @staticmethod
    async def _message(prompt: str, images: Sequence[LlmImage]) -> AsyncIterator[dict[str, Any]]:
        """Images go in streaming input: one user message, each picture after its caption."""
        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        for image in images:
            content.append({"type": "text", "text": image.caption})
            content.append(
                {"type": "image", "source": {"type": "base64", "media_type": image.media_type, "data": base64.b64encode(image.data).decode()}}
            )
        yield {"type": "user", "message": {"role": "user", "content": content}, "parent_tool_use_id": None}
