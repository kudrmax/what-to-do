from __future__ import annotations

import json
import os
import subprocess
import tempfile
import threading
from collections.abc import Callable, Iterator, Mapping
from pathlib import Path

from platformdirs import user_data_dir

from where_to_go.installed_cli import CliStatus, FoundCli, InstalledCli
from where_to_go.launcher.bundle import STATE_DIR_NAME
from where_to_go.launcher.tools import Tools

CODEX_MINIMUM = "0.172.0"
CODEX_INSTALL_COMMANDS = ("curl -fsSL https://chatgpt.com/codex/install.sh | sh", "brew install --cask codex")
CODEX_SIGN_IN_HINT = "Sign in to ChatGPT in What To Do to read posts with Codex"


def codex_unavailable_hint(found: FoundCli) -> str:
    if found.status is CliStatus.MISSING:
        return "Install Codex: What To Do needs it to read posts"
    return f"Update Codex: you have {found.version or 'an unknown version'}, What To Do needs {found.minimum} or newer"


def codex_places(environ: Mapping[str, str], home: Path) -> list[Path]:
    """Where Codex's installers put it: the install script, Homebrew, then npm."""
    fixed = [home / ".local" / "bin", home / ".codex" / "bin", Path("/opt/homebrew/bin"), Path("/usr/local/bin")]
    return list(dict.fromkeys([*fixed, *Tools(environ, home).program_dirs()]))


def codex_cli(environ: Mapping[str, str] = os.environ, home: Path | None = None, codex_home: CodexHome | None = None) -> InstalledCli:
    """Even `codex --version` writes into its home, so the version is asked with the app's home, never ~/.codex."""
    folder = home or Path.home()
    asked_with = (codex_home or CodexHome.default()).environ(environ)
    return InstalledCli("codex", CODEX_MINIMUM, extra_dirs=lambda: codex_places(environ, folder), environ=asked_with)


class CodexHome:
    """The app's own CODEX_HOME. Posts are strangers' text, so its config gives the model no tool, no skills
    and a sandbox that reads nothing and has no network. The user's own ~/.codex never reaches the app's calls.

    It lives outside the data folder, so the ChatGPT login never travels with backups or data copies."""

    CONFIG = """\
web_search = "disabled"
skills.include_instructions = false
default_permissions = "answer-only"

[features]
code_mode_host = false
shell_tool = false
unified_exec = false
multi_agent = false
multi_agent_v2 = false
sleep_tool = false
apps = false
plugins = false
remote_plugin = false
image_generation = false
browser_use = false
browser_use_external = false
computer_use = false
in_app_browser = false
goals = false
hooks = false
tool_suggest = false
skill_search = false
incremental_tools = false
shell_snapshot = false
view_image = false
memories = false

[permissions.answer-only]
extends = ":read-only"

[permissions.answer-only.filesystem]
":root" = "deny"
":minimal" = "read"

[permissions.answer-only.network]
enabled = false
"""
    VARIABLE = "CODEX_HOME"
    INSTRUCTION_FILES = ("AGENTS.md", "AGENTS.override.md")

    def __init__(self, folder: Path) -> None:
        self.folder = folder

    @classmethod
    def default(cls) -> CodexHome:
        return cls(Path(user_data_dir(STATE_DIR_NAME, appauthor=False)) / "codex")

    def prepare(self) -> Path:
        self.folder.mkdir(parents=True, exist_ok=True)
        config = self.folder / "config.toml"
        try:
            if config.read_text(encoding="utf-8") == self.CONFIG:
                return self.folder
        except OSError:
            pass
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=self.folder, prefix="config.toml.", delete=False) as draft:
            draft.write(self.CONFIG)
        os.replace(draft.name, config)
        return self.folder

    def instruction_files(self) -> list[Path]:
        """Codex hands the model the AGENTS files of its home: the app's calls must have none."""
        return [path for path in (self.folder / name for name in self.INSTRUCTION_FILES) if path.exists()]

    def environ(self, base: Mapping[str, str]) -> dict[str, str]:
        return {**base, self.VARIABLE: str(self.folder)}


class ToolGuard:
    """The app runs the Codex the user installed, which may be newer than the one tested and bring a tool turned on
    by default. Before the first call with a given file, `codex debug prompt-input` shows what the model would be
    given under the app's home; any tool or skills list refuses the calls. No login and no model call are needed.

    A check that gives no answer refuses too and is asked again next time; a clear answer is kept per file."""

    TIMEOUT_S = 20
    OFFERS_TOOLS = "This Codex version offers tools What To Do cannot turn off; update What To Do"
    CANNOT_CHECK = "What To Do could not check that Codex has no tools; try again, or update Codex"
    SKILLS_MARKER = "<skills_instructions>"
    KNOWN_ITEMS = frozenset({"message"})

    @staticmethod
    def instructions_refusal(path: Path) -> str:
        return f"Codex would give the model the instructions in {path}; move that file away so What To Do can use Codex"

    def __init__(self, home: CodexHome, run: Callable[[Path, Mapping[str, str]], str | None] | None = None) -> None:
        self._home = home
        self._run = run or self._prompt_input
        self._verdicts: dict[tuple[Path, int], str | None] = {}
        self._lock = threading.Lock()

    def check(self, codex: Path) -> str | None:
        with self._lock:
            try:
                resolved = codex.resolve()
                key = (resolved, resolved.stat().st_mtime_ns)
            except OSError:
                return self.CANNOT_CHECK
            try:
                self._home.prepare()
                instructions = self._home.instruction_files()
            except OSError:
                return self.CANNOT_CHECK
            if instructions:
                return self.instructions_refusal(instructions[0])
            if key in self._verdicts:
                return self._verdicts[key]
            output = self._run(codex, self._home.environ(os.environ))
            verdict = self.refusal(output)
            if verdict != self.CANNOT_CHECK:
                self._verdicts[key] = verdict
            return verdict

    @classmethod
    def refusal(cls, output: str | None) -> str | None:
        try:
            given = json.loads(output or "")
        except ValueError:
            return cls.CANNOT_CHECK
        if not isinstance(given, list) or not given:
            return cls.CANNOT_CHECK
        if any(not isinstance(item, dict) or item.get("type") not in cls.KNOWN_ITEMS for item in given):
            return cls.OFFERS_TOOLS
        if cls._offers_tools(given) or any(cls.SKILLS_MARKER in text for text in cls._texts(given)):
            return cls.OFFERS_TOOLS
        return None

    @classmethod
    def _offers_tools(cls, item: object) -> bool:
        if isinstance(item, dict):
            tools = item.get("tools")
            if isinstance(tools, list) and tools:
                return True
            return any(cls._offers_tools(value) for value in item.values())
        if isinstance(item, list):
            return any(cls._offers_tools(value) for value in item)
        return False

    @classmethod
    def _texts(cls, item: object) -> Iterator[str]:
        if isinstance(item, str):
            yield item
        elif isinstance(item, dict):
            for value in item.values():
                yield from cls._texts(value)
        elif isinstance(item, list):
            for value in item:
                yield from cls._texts(value)

    def _prompt_input(self, codex: Path, environ: Mapping[str, str]) -> str | None:
        with tempfile.TemporaryDirectory(prefix="what-to-do-codex-check-") as empty:
            try:
                done = subprocess.run(
                    [str(codex), "debug", "prompt-input", "x"],
                    capture_output=True,
                    text=True,
                    timeout=self.TIMEOUT_S,
                    stdin=subprocess.DEVNULL,
                    cwd=empty,
                    env=dict(environ),
                )
            except (OSError, subprocess.SubprocessError):
                return None
        return done.stdout if done.returncode == 0 else None
