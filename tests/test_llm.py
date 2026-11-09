from pathlib import Path

import os

from where_to_go.llm import ClaudeCliEnvironment, ClaudeJsonLlm


def test_config_dir_naming_the_default_location_is_removed_not_emptied(monkeypatch):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(Path.home() / ".claude") + "/")
    ClaudeJsonLlm("m")
    assert "CLAUDE_CONFIG_DIR" not in os.environ


def test_custom_config_dir_is_respected(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    ClaudeCliEnvironment.prepare()
    assert os.environ["CLAUDE_CONFIG_DIR"] == str(tmp_path)


import pytest
from claude_agent_sdk import ResultMessage

from where_to_go import llm as llm_module
from where_to_go.llm import LlmError


def result(**overrides) -> ResultMessage:
    fields = dict(subtype="success", duration_ms=1, duration_api_ms=1, is_error=False, num_turns=1, session_id="s")
    fields.update(overrides)
    return ResultMessage(**fields)


def fake_query(*messages, error: Exception | None = None):
    seen = {}

    async def query(prompt, options):
        seen["options"] = options
        if error:
            raise error
        for message in messages:
            yield message

    return query, seen


async def test_structured_output_is_returned_and_tools_are_off(monkeypatch):
    query, seen = fake_query(result(structured_output={"posts": []}))
    monkeypatch.setattr(llm_module, "query", query)
    assert await ClaudeJsonLlm("claude-haiku-5-5").complete_json("sys", "prompt", {"type": "object"}) == {"posts": []}
    options = seen["options"]
    assert options.tools == [] and options.model == "claude-haiku-5-5" and options.setting_sources == []
    assert options.output_format == {"type": "json_schema", "schema": {"type": "object"}}
    assert options.env == {} and "no-session-persistence" in options.extra_args


@pytest.mark.parametrize(
    "messages,error",
    [((result(is_error=True, errors=["overloaded"]),), None), ((result(result="plain text"),), None), ((), None), ((), RuntimeError("cli died"))],
)
async def test_failures_become_llm_errors(monkeypatch, messages, error):
    query, _ = fake_query(*messages, error=error)
    monkeypatch.setattr(llm_module, "query", query)
    with pytest.raises(LlmError):
        await ClaudeJsonLlm("m").complete_json("s", "p", {})
