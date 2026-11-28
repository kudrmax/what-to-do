from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import threading
from collections.abc import Mapping
from pathlib import Path
from typing import IO

from where_to_go.installed_cli import CliStatus, FoundCli, InstalledCli
from where_to_go.launcher.tools import Tools
from where_to_go.reader_sign_in import ReaderSignIn, SignInProgress

CLAUDE_INSTALL_COMMAND = "curl -fsSL https://claude.ai/install.sh | bash"
SIGN_IN_HINT = "Sign in to Claude Code: run `claude` in a terminal and type /login"
CLAUDE_MINIMUM = "2.1.321"


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


def claude_places(environ: Mapping[str, str], home: Path) -> list[Path]:
    """Where Claude Code's installers put it: native installer, Homebrew, the old local install, then npm."""
    fixed = [home / ".local" / "bin", Path("/opt/homebrew/bin"), Path("/usr/local/bin"), home / ".claude" / "local"]
    return list(dict.fromkeys([*fixed, *Tools(environ, home).program_dirs()]))


def claude_cli(environ: Mapping[str, str] = os.environ, home: Path | None = None) -> InstalledCli:
    folder = home or Path.home()
    return InstalledCli(
        "claude",
        CLAUDE_MINIMUM,
        extra_dirs=lambda: claude_places(environ, folder),
        environ=ClaudeCliEnvironment.cleaned(environ),
    )


def unavailable_hint(found: FoundCli) -> str:
    if found.status is CliStatus.MISSING:
        return "Install Claude Code: What To Do needs it to read posts"
    return f"Update Claude Code: you have {found.version or 'an unknown version'}, What To Do needs {found.minimum} or newer"


class ClaudeLogin:
    """Whether the Claude Code login the app calls Claude through is there.

    Asks the same Claude CLI the SDK runs (`claude auth status`, a fraction of a second, no request to
    Claude). Only the yes or no leaves this class: the answer also names the account."""

    TIMEOUT_S = 15
    # What the CLI answers a call with when nobody is logged in.
    SIGNED_OUT_MARKERS = ("not logged in", "please run /login", "invalid api key", "oauth token has expired")
    UNAVAILABLE = {CliStatus.MISSING: ReaderSignIn.NOT_INSTALLED, CliStatus.TOO_OLD: ReaderSignIn.TOO_OLD}

    def __init__(self, cli: InstalledCli) -> None:
        self._cli = cli

    def check(self) -> ReaderSignIn:
        return self.state_of(self._cli.find())

    def state_of(self, found: FoundCli) -> ReaderSignIn:
        if found.status is not CliStatus.READY or found.path is None:
            return self.UNAVAILABLE.get(found.status, ReaderSignIn.UNKNOWN)
        environ = ClaudeCliEnvironment.cleaned(os.environ)
        try:
            completed = subprocess.run(
                [str(found.path), "auth", "status"], capture_output=True, text=True, timeout=self.TIMEOUT_S, stdin=subprocess.DEVNULL, env=environ
            )
            answer = json.loads(completed.stdout)
        except (OSError, subprocess.TimeoutExpired, ValueError):
            return ReaderSignIn.UNKNOWN
        if not isinstance(answer, dict) or not isinstance(answer.get("loggedIn"), bool):
            return ReaderSignIn.UNKNOWN
        return ReaderSignIn.SIGNED_IN if answer["loggedIn"] else ReaderSignIn.SIGNED_OUT

    @classmethod
    def means_signed_out(cls, message: str) -> bool:
        lowered = message.lower()
        return any(marker in lowered for marker in cls.SIGNED_OUT_MARKERS)


class ClaudeSignInFlow:
    """`claude auth login` started from the app, so signing in needs no terminal.

    The CLI opens the sign-in page in the browser, and the page hands the login back to it by itself.
    It also prints the page's address: opened by hand, that page shows a code to paste instead, which
    `submit_code` passes on."""

    PAGE_URL = re.compile(r"https://\S+/oauth/authorize\?\S+")
    # The CLI's prompt for the code, which the reply follows on the same line: the code is not echoed.
    CODE_PROMPT = "Paste code here if prompted >"
    STOP_TIMEOUT_S = 5

    def __init__(self, cli: InstalledCli) -> None:
        self._cli = cli
        self._lock = threading.Lock()
        self._process: subprocess.Popen[bytes] | None = None
        self._output_dir: tempfile.TemporaryDirectory[str] | None = None
        self._output: IO[bytes] | None = None
        self._error: str | None = None

    def start(self) -> None:
        with self._lock:
            if self._running():
                return
            self._close_output()
            found = self._cli.find()
            if found.status is not CliStatus.READY or found.path is None:
                self._error = unavailable_hint(found)
                return
            self._error = None
            self._output_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
            output_path = Path(self._output_dir.name) / "output"
            try:
                with output_path.open("wb") as cli_output:
                    self._output = output_path.open("rb")
                    self._process = subprocess.Popen(
                        [str(found.path), "auth", "login", "--claudeai"],
                        stdin=subprocess.PIPE,
                        stdout=cli_output,
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
        if self._output_dir is not None:
            self._output_dir.cleanup()
            self._output_dir = None
