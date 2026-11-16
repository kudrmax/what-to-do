from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError

_MESSAGES = {
    "greater_than_equal": "Must be at least {ge}",
    "less_than_equal": "Must be at most {le}",
    "greater_than": "Must be greater than {gt}",
    "less_than": "Must be less than {lt}",
    "string_too_short": "Can't be empty",
    "missing": "This field is required",
    "int_parsing": "Must be a whole number",
    "int_from_float": "Must be a whole number",
    "enum": "Invalid value",
}


def _message(error: dict[str, Any]) -> str:
    if error["type"] == "value_error":
        return str(error["ctx"]["error"])
    template = _MESSAGES.get(error["type"])
    if template is None:
        return "Invalid value"
    return template.format(**{k: _plain(v) for k, v in (error.get("ctx") or {}).items()})


def _plain(value: Any) -> Any:
    return int(value) if isinstance(value, float) and value.is_integer() else value


async def validation_error(_: Request, exc: RequestValidationError | ValidationError) -> JSONResponse:
    """A request or a value the models refuse; errors keep the API's one shape, {"detail": "<text ready to show>"}."""
    return JSONResponse(status_code=422, content={"detail": _message(exc.errors()[0])})
