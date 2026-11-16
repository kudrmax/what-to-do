from __future__ import annotations

import os
import subprocess
from typing import Any

# A child of a Python on Windows may print with the console's code page, which cannot print most of the
# world's letters; every process the launcher starts speaks UTF-8.
CHILD_ENVIRONMENT = {"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"}


def detached() -> dict[str, Any]:
    """Popen options for a process that outlives the one starting it and takes no terminal signals."""
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS}
    return {"start_new_session": True}


def child_environment(**extra: str) -> dict[str, str]:
    return {**os.environ, **CHILD_ENVIRONMENT, **extra}
