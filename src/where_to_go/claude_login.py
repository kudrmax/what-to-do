from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import IO

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

    def __init__(self, cli: list[str] | None = None) -> None:
        self._cli = cli

    def check(self) -> ClaudeSignIn:
        cli = self._cli or self._found_cli()
        if not cli:
            return ClaudeSignIn.UNKNOWN
        environ = ClaudeCliEnvironment.cleaned(os.environ)
        try:
            completed = subprocess.run(
                [*cli, "auth", "status"], capture_output=True, text=True, timeout=self.TIMEOUT_S, stdin=subprocess.DEVNULL, env=environ
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

    @classmethod
    def _found_cli(cls) -> list[str]:
        cli = cls.find_cli()
        return [str(cli)] if cli else []

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


@dataclass(frozen=True)
class SignInProgress:
    running: bool
    page_url: str | None
    error: str | None


class ClaudeSignInFlow:
    """`claude auth login` started from the app, so signing in needs no terminal.

    The CLI opens the sign-in page in the browser, and the page hands the login back to it by itself.
    It also prints the page's address: opened by hand, that page shows a code to paste instead, which
    `submit_code` passes on."""

    PAGE_URL = re.compile(r"https://\S+/oauth/authorize\?\S+")
    # The CLI's prompt for the code, which the reply follows on the same line: the code is not echoed.
    CODE_PROMPT = "Paste code here if prompted >"
    STOP_TIMEOUT_S = 5

    def __init__(self, cli: list[str] | None = None) -> None:
        self._cli = cli
        self._lock = threading.Lock()
        self._process: subprocess.Popen[bytes] | None = None
        self._output: IO[bytes] | None = None
        self._error: str | None = None

    def start(self) -> None:
        with self._lock:
            if self._running():
                return
            self._close_output()
            cli = self._cli or ClaudeLogin._found_cli()
            if not cli:
                self._error = "Claude Code, which the app reads posts with, is missing. Reinstall What To Do."
                return
            self._error = None
            self._output = tempfile.TemporaryFile()
            try:
                self._process = subprocess.Popen(
                    [*cli, "auth", "login", "--claudeai"],
                    stdin=subprocess.PIPE,
                    stdout=self._output,
                    stderr=subprocess.STDOUT,
                    env=ClaudeCliEnvironment.cleaned(os.environ),
                    start_new_session=True,
                )
            except OSError as error:
                self._process = None
                self._error = f"Couldn't start signing in: {error}"

    def submit_code(self, code: str) -> bool:
        """Passes the code from the sign-in page on; False when no sign-in waits for one."""
        with self._lock:
            if not self._running() or self._process is None or self._process.stdin is None:
                return False
            try:
                self._process.stdin.write(code.strip().encode() + b"\n")
                self._process.stdin.flush()
            except OSError:
                return False
            return True

    def progress(self) -> SignInProgress:
        with self._lock:
            output = self._read_output()
            running = self._running()
            error = self._error
            if not running and self._process is not None and self._process.returncode not in (0, None):
                lines = [reply for line in output.splitlines() if (reply := line.rpartition(self.CODE_PROMPT)[2].strip())]
                error = error or (lines[-1] if lines else "Signing in didn't finish.")
            elif running:
                # A code it could not use: the CLI says why after its prompt and waits for another one.
                replies = [reply.strip().split("\n")[0].strip() for reply in output.split(self.CODE_PROMPT)[1:]]
                error = next((reply for reply in reversed(replies) if reply), None)
            match = self.PAGE_URL.search(output)
            return SignInProgress(running=running, page_url=match.group(0) if running and match else None, error=error)

    def stop(self) -> None:
        with self._lock:
            if self._running() and self._process is not None:
                self._process.terminate()
                try:
                    self._process.wait(timeout=self.STOP_TIMEOUT_S)
                except subprocess.TimeoutExpired:
                    self._process.kill()
            self._close_output()

    def _running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def _read_output(self) -> str:
        if self._output is None:
            return ""
        self._output.seek(0)
        return self._output.read().decode("utf-8", errors="replace")

    def _close_output(self) -> None:
        if self._output is not None:
            self._output.close()
            self._output = None
