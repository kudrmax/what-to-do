from __future__ import annotations

import logging

from fastapi import APIRouter
from pydantic import BaseModel, Field

TAG = "timings"
TAG_HELP = "How long the interface took to answer the user, written to the app log"

log = logging.getLogger("where_to_go.timings")
router = APIRouter(tags=[TAG])


class InterfaceTiming(BaseModel):
    action: str = Field(max_length=100, description="What the user did, e.g. mark")
    screen: str = Field(max_length=200, description="The address the interface was at")
    phases: dict[str, float] = Field(max_length=20, description="Milliseconds from the user's action to the end of each phase")
    blocked: float = Field(description="The longest time the interface could not answer, in milliseconds")

    def line(self) -> str:
        parts = [f"{name}={round(ms)}ms" for name, ms in self.phases.items()] + [f"blocked={round(self.blocked)}ms"]
        return f"{self.action} on {self.screen}: {' '.join(parts)}"


@router.post("/timings", status_code=204)
def record_timing(timing: InterfaceTiming) -> None:
    """Writes one measurement of the interface to the app log, so a slow click can be found later."""
    log.info(timing.line())
