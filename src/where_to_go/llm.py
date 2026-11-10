from __future__ import annotations

import base64
import os
from collections.abc import AsyncIterator, Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query


class LlmError(Exception):
    pass


@dataclass(frozen=True)
class LlmImage:
    """A picture Claude looks at, introduced by a caption that names it in the prompt."""

    caption: str
    media_type: str
    data: bytes


class JsonLlm(Protocol):
    async def complete_json(
        self, system: str, prompt: str, schema: dict[str, Any], images: Sequence[LlmImage] = ()
    ) -> dict[str, Any]: ...


class ClaudeJsonLlm:
    """Structured-output calls through Claude Code (claude-agent-sdk): no API key, the user's own login.

    The model is asked for on every call, so a model changed in settings applies to the next call."""

    def __init__(self, model: Callable[[], str]) -> None:
        self._model = model
        ClaudeCliEnvironment.prepare()

    async def complete_json(
        self, system: str, prompt: str, schema: dict[str, Any], images: Sequence[LlmImage] = ()
    ) -> dict[str, Any]:
        options = ClaudeAgentOptions(
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
            raise LlmError(str(error)) from error
        if result is None or result.is_error or not isinstance(result.structured_output, dict):
            detail = (result.errors or result.result) if result else "no result"
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


class ClaudeCliEnvironment:
    """The Claude CLI inherits this process's environment.

    The Claude desktop app starts processes with CLAUDE_CONFIG_DIR naming the default ~/.claude. With the
    variable set, the CLI looks for its login under another keychain entry and reports "Not logged in".
    Pointing at the default location, the variable means nothing, so it is removed; a real custom
    location is left alone.
    """

    VARIABLE = "CLAUDE_CONFIG_DIR"

    @classmethod
    def prepare(cls) -> None:
        configured = os.environ.get(cls.VARIABLE)
        if configured is not None and cls._is_default(configured):
            del os.environ[cls.VARIABLE]

    @staticmethod
    def _is_default(configured: str) -> bool:
        return configured.strip() != "" and Path(configured).expanduser().resolve() == (Path.home() / ".claude").resolve()
