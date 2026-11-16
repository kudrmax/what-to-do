from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
from collections.abc import Mapping
from enum import StrEnum
from pathlib import Path

SIGN_IN_HINT = "Sign in to Claude Code: run `claude` in a terminal and type /login"


class ClaudeCliEnvironment:
    """The Claude CLI inherits this process's environment.

    The Claude desktop app starts processes with CLAUDE_CONFIG_DIR naming the default ~/.claude. With the
    variable set, the CLI looks for its login under another keychain entry and reports "Not logged in".
    Pointing at the default location, the variable means nothing, so it is removed; a real custom
    location is left alone.
    """

    VARIABLE = "CLAUDE_CONFIG_DIR"

    @classmethod
    def cleaned(cls, environ: Mapping[str, str]) -> dict[str, str]:
        return {name: value for name, value in environ.items() if name != cls.VARIABLE or not cls.is_default_config(value)}

    @classmethod
    def prepare(cls) -> None:
        if cls.is_default_config(os.environ.get(cls.VARIABLE)):
            del os.environ[cls.VARIABLE]

    @staticmethod
    def is_default_config(configured: str | None) -> bool:
        return configured is not None and configured.strip() != "" and Path(configured).expanduser().resolve() == (Path.home() / ".claude").resolve()


class ClaudeSignIn(StrEnum):
    SIGNED_IN = "signed_in"
    SIGNED_OUT = "signed_out"
    UNKNOWN = "unknown"


class ClaudeLogin:
    """Whether the Claude Code login the app calls Claude through is there.

    Asks the same Claude CLI the SDK runs (`claude auth status`, a fraction of a second, no request to
    Claude). Only the yes or no leaves this class: the answer also names the account."""

    TIMEOUT_S = 15
    # What the CLI answers a call with when nobody is logged in.
    SIGNED_OUT_MARKERS = ("not logged in", "please run /login", "invalid api key", "oauth token has expired")

    def __init__(self, cli: Path | None = None) -> None:
        self._cli = cli

    def check(self) -> ClaudeSignIn:
        cli = self._cli or self.find_cli()
        if cli is None:
            return ClaudeSignIn.UNKNOWN
        environ = ClaudeCliEnvironment.cleaned(os.environ)
        try:
            completed = subprocess.run(
                [str(cli), "auth", "status"], capture_output=True, text=True, timeout=self.TIMEOUT_S, stdin=subprocess.DEVNULL, env=environ
            )
            answer = json.loads(completed.stdout)
        except (OSError, subprocess.TimeoutExpired, ValueError):
            return ClaudeSignIn.UNKNOWN
        if not isinstance(answer, dict) or not isinstance(answer.get("loggedIn"), bool):
            return ClaudeSignIn.UNKNOWN
        return ClaudeSignIn.SIGNED_IN if answer["loggedIn"] else ClaudeSignIn.SIGNED_OUT

    @classmethod
    def means_signed_out(cls, message: str) -> bool:
        lowered = message.lower()
        return any(marker in lowered for marker in cls.SIGNED_OUT_MARKERS)

    @staticmethod
    def find_cli() -> Path | None:
        """The CLI bundled with claude-agent-sdk, which the SDK prefers; else a `claude` on PATH."""
        spec = importlib.util.find_spec("claude_agent_sdk")
        if spec is not None and spec.origin:
            bundled = Path(spec.origin).parent / "_bundled" / ("claude.exe" if os.name == "nt" else "claude")
            if bundled.is_file():
                return bundled
        found = shutil.which("claude")
        return Path(found) if found else None
