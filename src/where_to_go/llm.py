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

    async def complete_json(self, system: str, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        options = ClaudeAgentOptions(
            model=self._model,
            system_prompt=system,
            tools=[],
            setting_sources=[],
            max_turns=4,
            output_format={"type": "json_schema", "schema": schema},
            env=self._cli_env(),
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

    @staticmethod
    def _cli_env() -> dict[str, str]:
        # A config dir that merely names the default location makes the CLI look for a different
        # keychain entry than the one `claude login` wrote, so it reports "Not logged in".
        configured = os.environ.get("CLAUDE_CONFIG_DIR")
        if configured and Path(configured).expanduser().resolve() == (Path.home() / ".claude").resolve():
            return {"CLAUDE_CONFIG_DIR": ""}
        return {}
