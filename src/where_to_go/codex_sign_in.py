from __future__ import annotations

import asyncio
import contextlib
import webbrowser
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from openai_codex import AsyncChatgptLoginHandle, AsyncCodex, TransportClosedError

from where_to_go.codex_llm import CodexRuntime
from where_to_go.installed_cli import CliStatus, FoundCli, InstalledCli
from where_to_go.llm import CodexRefusedError, CodexUnavailableError, LlmError
from where_to_go.reader_sign_in import ReaderSignIn, SignInProgress

UNAVAILABLE = {CliStatus.MISSING: ReaderSignIn.NOT_INSTALLED, CliStatus.TOO_OLD: ReaderSignIn.TOO_OLD}


@dataclass(frozen=True)
class CodexStatus:
    state: ReaderSignIn
    found: FoundCli
    message: str | None = None


class CodexLogin:
    """Whether the ChatGPT login in the app's Codex home is there, asked of the app's own Codex server.

    A Codex that is missing, too old or refused by the tool guard is never started; only the yes or no of the
    account answer leaves this class."""

    def __init__(self, cli: InstalledCli, runtime: CodexRuntime) -> None:
        self._cli = cli
        self._runtime = runtime

    async def state(self) -> CodexStatus:
        found = await asyncio.to_thread(self._cli.find)
        if found.status is not CliStatus.READY or found.path is None:
            return CodexStatus(UNAVAILABLE.get(found.status, ReaderSignIn.UNKNOWN), found)
        try:
            client = await self._runtime.client()
        except CodexUnavailableError as error:
            return CodexStatus(UNAVAILABLE.get(error.found.status, ReaderSignIn.UNKNOWN), error.found)
        except CodexRefusedError as error:
            return CodexStatus(ReaderSignIn.REFUSED, found, str(error))
        except Exception:
            return CodexStatus(ReaderSignIn.UNKNOWN, found)
        try:
            answer = await client.account()
        except (TransportClosedError, OSError):
            await self._runtime.forget(client)
            return CodexStatus(ReaderSignIn.UNKNOWN, found)
        except Exception:
            return CodexStatus(ReaderSignIn.UNKNOWN, found)
        signed_out = answer.account is None and answer.requires_openai_auth
        return CodexStatus(ReaderSignIn.SIGNED_OUT if signed_out else ReaderSignIn.SIGNED_IN, found)


class CodexSignInFlow:
    """ChatGPT sign-in started from the app: the app's Codex server opens a sign-in page in the browser and
    receives the login back by itself, so no code is pasted. While it waits, the page's address is kept to
    open by hand."""

    STOP_TIMEOUT_S = 5

    def __init__(self, runtime: CodexRuntime, opener: Callable[[str], Any] = webbrowser.open) -> None:
        self._runtime = runtime
        self._opener = opener
        self._lock = asyncio.Lock()
        self._handle: AsyncChatgptLoginHandle | None = None
        self._waiting: asyncio.Task[None] | None = None
        self._page_url: str | None = None
        self._error: str | None = None

    async def start(self) -> None:
        async with self._lock:
            if self._running():
                return
            self._error = None
            try:
                client = await self._runtime.client()
                handle = await client.login_chatgpt()
            except LlmError as error:
                self._error = str(error)
                return
            except Exception as error:
                self._error = f"Couldn't start signing in: {error}"
                return
            self._handle = handle
            self._page_url = handle.auth_url
            self._waiting = asyncio.create_task(self._wait(client, handle))
            with contextlib.suppress(Exception):
                await asyncio.to_thread(self._opener, handle.auth_url)

    def progress(self) -> SignInProgress:
        running = self._running()
        return SignInProgress(running=running, page_url=self._page_url if running else None, error=self._error)

    async def stop(self) -> None:
        async with self._lock:
            waiting, handle = self._waiting, self._handle
            if waiting is None or waiting.done() or handle is None:
                return
            with contextlib.suppress(Exception):
                await asyncio.wait_for(handle.cancel(), self.STOP_TIMEOUT_S)
            with contextlib.suppress(Exception, asyncio.CancelledError):
                await asyncio.wait_for(asyncio.shield(waiting), self.STOP_TIMEOUT_S)
            if not waiting.done():
                waiting.cancel()

    def _running(self) -> bool:
        return self._waiting is not None and not self._waiting.done()

    async def _wait(self, client: AsyncCodex, handle: AsyncChatgptLoginHandle) -> None:
        try:
            done = await handle.wait()
        except (TransportClosedError, OSError) as error:
            self._error = f"Signing in didn't finish: {error}"
            await self._runtime.forget(client)
        except Exception as error:
            self._error = f"Signing in didn't finish: {error}"
        else:
            if not done.success:
                self._error = done.error or "Signing in didn't finish."
            self._runtime.signed_out(client)
        finally:
            self._handle = None
            self._page_url = None
