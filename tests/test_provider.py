"""Which subscription reads posts: the provider setting, how each step's calls follow it, and how a reader that is
not ready is said once in a refresh, a re-tag and the launcher."""

from __future__ import annotations

import importlib.util
import re
import sys
import time
from pathlib import Path
from types import ModuleType

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from pydantic import ValidationError

from tests.helpers import FakeClaude, FakeCodexCli, FakeLlm, add_city, judge_same_titles, photos_saying, raw_event
from tests.test_api import seeded
from tests.test_launcher_cli import OneRunningServer, copy_at
from tests.test_pipeline import RECENT, serve_channels
from where_to_go.active_provider import ActiveProvider
from where_to_go.api import create_app
from where_to_go.codex_login import CODEX_SIGN_IN_HINT, CodexHome, ToolGuard, UnsafeCodexPath
from where_to_go.container import Container
from where_to_go.installed_cli import CliStatus
from where_to_go.launcher.cli import Cli
from where_to_go.launcher.config import InstanceConfig
from where_to_go.llm import CodexRefusedError, CodexSignedOutError, CodexToolAttemptError, LlmError, PlanLimitError, ProviderJsonLlm
from where_to_go.models import Source
from where_to_go.refresh import Stage
from where_to_go.retagging import EventRetagger
from where_to_go.settings import AppSettings, CodexEffort, CodexModel, LlmProvider, SettingsChange

SCRIPTS = Path(__file__).parent.parent / "scripts"


class FakeRuntime:
    """A Codex runtime that fails every call before a server would start."""

    def __init__(self, *errors: LlmError) -> None:
        self._errors = list(errors)
        self.asked = 0
        self.closed = False

    async def client(self):
        error = self._errors[min(self.asked, len(self._errors) - 1)]
        self.asked += 1
        raise error

    async def close(self) -> None:
        self.closed = True


def answering(name: str) -> FakeLlm:
    return FakeLlm(lambda system, prompt: {"by": name})


def test_settings_default_to_claude_with_the_compared_codex_models() -> None:
    settings = AppSettings()

    assert settings.llm_provider is LlmProvider.CLAUDE
    assert (settings.codex_photo_model, settings.codex_photo_effort) == (CodexModel.TERRA, CodexEffort.LOW)
    assert (settings.codex_extraction_model, settings.codex_extraction_effort) == (CodexModel.TERRA, CodexEffort.MEDIUM)
    assert (settings.codex_matching_model, settings.codex_matching_effort) == (CodexModel.LUNA, CodexEffort.LOW)
    assert [model.value for model in CodexModel] == ["gpt-6-luna", "gpt-6.1-terra", "gpt-6.2-sol", "gpt-6.2-astra"]
    assert [effort.value for effort in CodexEffort] == ["low", "medium", "high"]


@pytest.mark.parametrize(
    "change",
    [{"llm_provider": "openai"}, {"codex_photo_model": "claude-sonnet-5-5"}, {"codex_matching_effort": "xhigh"}, {"photo_model": "gpt-6-luna"}],
)
def test_settings_refuse_an_unknown_provider_model_or_effort(change: dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        SettingsChange.model_validate(change)


def test_settings_descriptions_do_not_name_one_provider_for_the_prompts() -> None:
    for name in ("priority_wish", "extraction_prompt", "matching_prompt", "photo_prompt"):
        assert "Claude" not in (AppSettings.model_fields[name].description or "")


def test_the_provider_is_stored_and_read_back(tmp_path: Path) -> None:
    container = Container.build(tmp_path, codex_runtime=FakeRuntime(CodexSignedOutError()))
    container.settings.update(llm_provider=LlmProvider.CODEX, codex_photo_effort=CodexEffort.HIGH)

    loaded = container.settings.load()
    container.db.close()

    assert (loaded.llm_provider, loaded.codex_photo_effort) == (LlmProvider.CODEX, CodexEffort.HIGH)
    assert ActiveProvider.of(tmp_path) is LlmProvider.CODEX


def test_a_folder_without_settings_reads_with_claude(tmp_path: Path) -> None:
    assert ActiveProvider.of(tmp_path) is LlmProvider.CLAUDE
    (tmp_path / "where-to-go.sqlite3").write_text("not a database", encoding="utf-8")
    assert ActiveProvider.of(tmp_path) is LlmProvider.CLAUDE


@pytest.mark.parametrize(("provider", "reader"), [(LlmProvider.CLAUDE, "claude"), (LlmProvider.CODEX, "codex")])
async def test_each_call_goes_to_the_chosen_reader(provider: LlmProvider, reader: str) -> None:
    claude, codex = answering("claude"), answering("codex")

    answer = await ProviderJsonLlm(lambda: provider, claude, codex).complete_json("sys", "prompt", {"type": "object"})

    assert answer == {"by": reader}
    assert (len(claude.calls), len(codex.calls)) == ((1, 0) if reader == "claude" else (0, 1))


async def test_switching_the_provider_applies_to_the_next_call() -> None:
    chosen = [LlmProvider.CLAUDE]
    claude, codex = answering("claude"), answering("codex")
    llm = ProviderJsonLlm(lambda: chosen[0], claude, codex)

    first = await llm.complete_json("sys", "one", {"type": "object"})
    chosen[0] = LlmProvider.CODEX
    second = await llm.complete_json("sys", "two", {"type": "object"})
    chosen[0] = LlmProvider.CLAUDE
    third = await llm.complete_json("sys", "three", {"type": "object"})

    assert [first, second, third] == [{"by": "claude"}, {"by": "codex"}, {"by": "claude"}]
    assert [prompt for _, prompt in claude.calls] == ["one", "three"]
    assert [prompt for _, prompt in codex.calls] == ["two"]


async def test_a_call_finishes_on_the_reader_it_started_on() -> None:
    chosen = [LlmProvider.CLAUDE]
    asked: list[str] = []

    class SwitchesMidCall:
        async def complete_json(self, system, prompt, schema, images=()):
            chosen[0] = LlmProvider.CODEX
            asked.append("claude")
            return {"by": "claude"}

    codex = answering("codex")
    answer = await ProviderJsonLlm(lambda: chosen[0], SwitchesMidCall(), codex).complete_json("sys", "prompt", {})

    assert answer == {"by": "claude"} and asked == ["claude"] and codex.calls == []


async def test_the_container_closes_the_codex_runtime(tmp_path: Path) -> None:
    runtime = FakeRuntime(CodexSignedOutError())
    container = Container.build(tmp_path, codex_runtime=runtime, http=httpx.AsyncClient())

    await container.close()

    assert runtime.closed


def refresh_container(tmp_path: Path, provider: LlmProvider, runtime: FakeRuntime, claude: FakeClaude) -> Container:
    container = Container.build(tmp_path, matching_llm=judge_same_titles(), photo_llm=photos_saying(), http=httpx.AsyncClient(), claude=claude, codex_runtime=runtime)
    container.settings.update(llm_provider=provider)
    city = add_city(container, "Белград", "Europe/Belgrade")
    container.sources.add(Source(city_id=city.id, handle="kafana", title="Кафана"))
    container.sources.add(Source(city_id=city.id, handle="afisha", title="Афиша"))
    serve_channels([(n, RECENT, f"пост {n} " * 400) for n in range(1, 21)], [(n, RECENT, f"афиша {n} " * 400) for n in range(1, 21)])
    return container


@respx.mock
@pytest.mark.parametrize(
    ("errors", "reader_error", "lines"),
    [
        ((CodexSignedOutError(),), CODEX_SIGN_IN_HINT, []),
        (
            (PlanLimitError("You've hit your usage limit. Try again at 3:45 PM."), PlanLimitError("You've hit your usage limit. Try again at 3:46 PM.")),
            None,
            ["ChatGPT plan limit reached, resets at 3:45 PM"],
        ),
        ((CodexRefusedError(ToolGuard.OFFERS_TOOLS),), ToolGuard.OFFERS_TOOLS, []),
        ((CodexRefusedError(CodexHome.UNWRITABLE_PATH),), CodexHome.UNWRITABLE_PATH, []),
        ((CodexRefusedError(ToolGuard.CANNOT_LIMIT_READS),), ToolGuard.CANNOT_LIMIT_READS, []),
    ],
)
async def test_a_refresh_with_codex_not_ready_says_so_once(tmp_path: Path, errors: tuple[LlmError, ...], reader_error: str | None, lines: list[str]) -> None:
    runtime = FakeRuntime(*errors)
    container = refresh_container(tmp_path, LlmProvider.CODEX, runtime, FakeClaude(CliStatus.MISSING))

    container.refresh.start()
    progress = await container.refresh.wait()
    await container.close()

    assert progress.stage is Stage.DONE
    assert (progress.reader_unavailable, progress.reader) == (True, LlmProvider.CODEX)
    assert (progress.reader_error, progress.errors) == (reader_error, lines)
    assert runtime.asked > 1


@respx.mock
async def test_a_codex_path_refused_while_preparing_is_explained_by_the_box(tmp_path: Path) -> None:
    unsafe = UnsafeCodexPath(
        "Codex is installed right in /usr/local; What To Do would have to let the model read that whole folder, "
        "so reinstall Codex with its installer or Homebrew"
    )
    runtime = FakeRuntime(CodexRefusedError(str(unsafe)))
    container = refresh_container(tmp_path, LlmProvider.CODEX, runtime, FakeClaude(CliStatus.MISSING))

    container.refresh.start()
    progress = await container.refresh.wait()
    await container.close()

    assert (progress.reader_error, progress.errors) == (str(unsafe), [])


@respx.mock
async def test_a_tool_attempt_skips_its_posts_and_the_refresh_goes_on(tmp_path: Path) -> None:
    runtime = FakeRuntime(CodexToolAttemptError(), CodexSignedOutError())
    container = refresh_container(tmp_path, LlmProvider.CODEX, runtime, FakeClaude(CliStatus.MISSING))

    container.refresh.start()
    progress = await container.refresh.wait()
    await container.close()

    skipped = [line for line in progress.errors if line.startswith("Codex tried to use a tool while reading ")]
    assert len(skipped) == 1 and re.fullmatch(r"Codex tried to use a tool while reading (1 post; it was|\d+ posts; they were) skipped", skipped[0])
    assert (progress.reader_unavailable, progress.reader, progress.reader_error) == (True, LlmProvider.CODEX, CODEX_SIGN_IN_HINT)
    assert CODEX_SIGN_IN_HINT not in progress.errors
    assert runtime.asked > 2


@respx.mock
async def test_a_refresh_with_claude_chosen_never_asks_codex(tmp_path: Path) -> None:
    runtime = FakeRuntime(CodexSignedOutError())
    container = refresh_container(tmp_path, LlmProvider.CLAUDE, runtime, FakeClaude(CliStatus.MISSING))

    container.refresh.start()
    progress = await container.refresh.wait()
    await container.close()

    assert (progress.reader_unavailable, progress.reader) == (True, LlmProvider.CLAUDE)
    assert (progress.reader_error, progress.errors) == ("Install Claude Code: What To Do needs it to read posts", [])
    assert runtime.asked == 0


def retag_finished(client: TestClient) -> dict:
    status = client.get("/tags/retag").json()
    for _ in range(100):
        if not status["running"]:
            return status
        time.sleep(0.02)
        status = client.get("/tags/retag").json()
    raise AssertionError(status)


def test_a_retag_with_codex_not_ready_says_each_reason_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(EventRetagger, "BATCH_SIZE", 1)
    runtime = FakeRuntime(
        PlanLimitError("You've hit your usage limit. Try again at 3:45 PM."),
        CodexSignedOutError(),
        PlanLimitError("You've hit your usage limit. Try again at 3:47 PM."),
    )
    app = create_app(lambda: Container.build(tmp_path, matching_llm=judge_same_titles(), photo_llm=photos_saying(), codex_runtime=runtime))
    with TestClient(app) as client:
        client.patch("/settings", json={"llm_provider": "codex"})
        seeded(client, ("a", raw_event("Джазовый вечер", "2099-01-02")), ("a", raw_event("Квиз", "2099-01-03")), ("a", raw_event("Лекция", "2099-01-04")))
        client.post("/tags/retag")
        status = retag_finished(client)

    assert runtime.asked == 3
    assert sorted(status["errors"]) == ["ChatGPT plan limit reached, resets at 3:45 PM", CODEX_SIGN_IN_HINT]


def data_with_provider(folder: Path, provider: LlmProvider) -> Path:
    container = Container.build(folder, codex_runtime=FakeRuntime(CodexSignedOutError()))
    container.settings.update(llm_provider=provider)
    container.db.close()
    return folder


class FakeToolGuard:
    verdict: str | None = None
    checked: list[Path] = []

    def __init__(self, home) -> None:
        pass

    def check(self, codex: Path) -> str | None:
        FakeToolGuard.checked.append(codex)
        return FakeToolGuard.verdict


@pytest.mark.parametrize(
    ("codex", "warnings"),
    [
        (
            FakeCodexCli(CliStatus.MISSING),
            ["Install Codex: What To Do needs it to read posts.", "Run: curl -fsSL https://chatgpt.com/codex/install.sh | sh", "Or: brew install --cask codex"],
        ),
        (FakeCodexCli(CliStatus.TOO_OLD, version="0.100.0"), ["Update Codex: you have 0.100.0, What To Do needs 0.172.0 or newer. Run: codex update"]),
    ],
)
def test_status_warns_about_codex_when_codex_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, codex: FakeCodexCli, warnings: list[str]
) -> None:
    paths = copy_at(tmp_path)
    data = data_with_provider(tmp_path / "data", LlmProvider.CODEX)
    claude = FakeClaude(CliStatus.MISSING)
    said: list[str] = []
    FakeToolGuard.verdict, FakeToolGuard.checked = None, []
    monkeypatch.setattr("where_to_go.claude_login.claude_cli", lambda: claude)
    monkeypatch.setattr("where_to_go.codex_login.codex_cli", lambda codex_home=None: codex)
    monkeypatch.setattr("where_to_go.codex_login.ToolGuard", FakeToolGuard)
    monkeypatch.setattr("where_to_go.codex_login.CodexHome.default", classmethod(lambda cls: cls(tmp_path / "codex-home")))
    monkeypatch.setattr("where_to_go.launcher.control.ServerControl", OneRunningServer)

    assert Cli(paths, InstanceConfig.load(paths, environ={"WHERE_TO_GO_DATA_DIR": str(data)}), out=said.append).run(["status"]) == 0

    assert said[-len(warnings):] == warnings
    assert not any("Claude" in line for line in said)
    assert FakeToolGuard.checked == []


class StartingServer(OneRunningServer):
    def choose_port(self) -> int:
        return 18765

    def up(self, spec, build: bool) -> None:
        pass


@pytest.mark.parametrize("command", ["status", "up"])
def test_the_launcher_never_runs_the_codex_tool_guard(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, command: str) -> None:
    paths = copy_at(tmp_path)
    data = data_with_provider(tmp_path / "data", LlmProvider.CODEX)
    said: list[str] = []
    FakeToolGuard.verdict, FakeToolGuard.checked = "This Codex version offers tools", []
    monkeypatch.setattr("where_to_go.claude_login.claude_cli", lambda: FakeClaude(CliStatus.MISSING))
    monkeypatch.setattr("where_to_go.codex_login.codex_cli", lambda codex_home=None: FakeCodexCli())
    monkeypatch.setattr("where_to_go.codex_login.ToolGuard", FakeToolGuard)
    monkeypatch.setattr("where_to_go.codex_login.CodexHome.default", classmethod(lambda cls: cls(tmp_path / "codex-home")))
    monkeypatch.setattr("where_to_go.launcher.control.ServerControl", StartingServer)

    Cli(paths, InstanceConfig.load(paths, environ={"WHERE_TO_GO_DATA_DIR": str(data)}), out=said.append).run([command])

    assert FakeToolGuard.checked == []
    assert not any("tool" in line for line in said)


def model_compare() -> ModuleType:
    sys.path.insert(0, str(SCRIPTS))
    try:
        spec = importlib.util.spec_from_file_location("model_compare", SCRIPTS / "model_compare.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules["model_compare"] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(SCRIPTS))


def test_model_compare_takes_a_codex_model_and_effort() -> None:
    comparison = model_compare().Comparison.parse(["--provider", "codex", "--model", "gpt-6.1-terra", "--effort", "low", "src", "dst", "12", "13"])

    assert (comparison.provider, comparison.model, comparison.effort) == (LlmProvider.CODEX, "gpt-6.1-terra", CodexEffort.LOW)
    assert (comparison.source_dir, comparison.target_dir, comparison.post_ids) == (Path("src"), Path("dst"), [12, 13])


def test_model_compare_keeps_the_positional_claude_form() -> None:
    comparison = model_compare().Comparison.parse(["src", "dst", "claude-sonnet-5-5", "7"])

    assert (comparison.provider, comparison.model, comparison.effort, comparison.post_ids) == (LlmProvider.CLAUDE, "claude-sonnet-5-5", None, [7])


@pytest.mark.parametrize(
    "argv",
    [
        ["--provider", "codex", "--model", "claude-sonnet-5-5", "src", "dst", "1"],
        ["--provider", "claude", "--model", "claude-sonnet-5-5", "--effort", "low", "src", "dst", "1"],
        ["--provider", "codex", "src", "dst", "1"],
    ],
)
def test_model_compare_refuses_a_model_of_the_other_provider(argv: list[str]) -> None:
    with pytest.raises(SystemExit):
        model_compare().Comparison.parse(argv)
