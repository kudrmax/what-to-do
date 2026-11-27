from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ReaderSignIn(StrEnum):
    """Whether the reader the app calls is there and signed in; the same answers for Claude Code and Codex."""

    SIGNED_IN = "signed_in"
    SIGNED_OUT = "signed_out"
    UNKNOWN = "unknown"
    NOT_INSTALLED = "not_installed"
    TOO_OLD = "too_old"
    REFUSED = "refused"


@dataclass(frozen=True)
class SignInProgress:
    running: bool
    page_url: str | None
    error: str | None
