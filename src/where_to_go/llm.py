from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Protocol

from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query


class LlmError(Exception):
    pass


class JsonLlm(Protocol):
    async def complete_json(self, system: str, prompt: str, schema: dict[str, Any]) -> dict[str, Any]: ...


class ClaudeJsonLlm:
    """Structured-output calls through Claude Code (claude-agent-sdk): no API key, the user's own login."""

    def __init__(self, model: str) -> None:
        self._model = model
        ClaudeCliEnvironment.prepare()

    async def complete_json(self, system: str, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        options = ClaudeAgentOptions(
            model=self._model,
            system_prompt=system,
            tools=[],
            setting_sources=[],
            max_turns=4,
            output_format={"type": "json_schema", "schema": schema},
            extra_args={"no-session-persistence": None},
        )
        result: ResultMessage | None = None
        try:
            async for message in query(prompt=prompt, options=options):
                if isinstance(message, ResultMessage):
                    result = message
        except Exception as error:
            raise LlmError(str(error)) from error
        if result is None or result.is_error or not isinstance(result.structured_output, dict):
            detail = (result.errors or result.result) if result else "no result"
            raise LlmError(f"Claude did not return structured output: {detail}")
        return result.structured_output


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
