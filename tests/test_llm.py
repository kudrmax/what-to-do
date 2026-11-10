from pathlib import Path

import os

from where_to_go.llm import ClaudeCliEnvironment, ClaudeJsonLlm


def test_config_dir_naming_the_default_location_is_removed_not_emptied(monkeypatch):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(Path.home() / ".claude") + "/")
    ClaudeJsonLlm(lambda: "m")
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
        seen["prompt"] = prompt if isinstance(prompt, str) else [m async for m in prompt]
        if error:
            raise error
        for message in messages:
            yield message

    return query, seen


async def test_structured_output_is_returned_and_tools_are_off(monkeypatch):
    query, seen = fake_query(result(structured_output={"posts": []}))
    monkeypatch.setattr(llm_module, "query", query)
    assert await ClaudeJsonLlm(lambda: "claude-haiku-5-5").complete_json("sys", "prompt", {"type": "object"}) == {"posts": []}
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
        await ClaudeJsonLlm(lambda: "m").complete_json("s", "p", {})


async def test_images_go_after_their_captions_in_one_user_message(monkeypatch):
    from where_to_go.llm import LlmImage

    query, seen = fake_query(result(structured_output={}))
    monkeypatch.setattr(llm_module, "query", query)
    await ClaudeJsonLlm(lambda: "m").complete_json("s", "posts", {}, [LlmImage("Post 1, photo 0:", "image/png", b"\x89PNG")])
    [message] = seen["prompt"]
    assert message["type"] == "user"
    assert message["message"]["content"] == [
        {"type": "text", "text": "posts"},
        {"type": "text", "text": "Post 1, photo 0:"},
        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "iVBORw=="}},
    ]


async def test_without_images_the_prompt_is_plain_text(monkeypatch):
    query, seen = fake_query(result(structured_output={}))
    monkeypatch.setattr(llm_module, "query", query)
    await ClaudeJsonLlm(lambda: "m").complete_json("s", "posts", {})
    assert seen["prompt"] == "posts"


async def test_the_model_is_asked_for_on_every_call(monkeypatch):
    query, seen = fake_query(result(structured_output={}))
    monkeypatch.setattr(llm_module, "query", query)
    model = ["claude-haiku-5-5"]
    llm = ClaudeJsonLlm(lambda: model[0])
    model[0] = "claude-sonnet-5-5"
    await llm.complete_json("s", "p", {})
    assert seen["options"].model == "claude-sonnet-5-5"
