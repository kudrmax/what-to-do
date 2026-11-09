from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

_MESSAGES = {
    "greater_than_equal": "Значение должно быть не меньше {ge}",
    "less_than_equal": "Значение должно быть не больше {le}",
    "greater_than": "Значение должно быть больше {gt}",
    "less_than": "Значение должно быть меньше {lt}",
    "string_too_short": "Поле не может быть пустым",
    "missing": "Не заполнено обязательное поле",
    "int_parsing": "Нужно целое число",
    "int_from_float": "Нужно целое число",
    "enum": "Недопустимое значение",
}


def _message(error: dict[str, Any]) -> str:
    template = _MESSAGES.get(error["type"])
    if template is None:
        return "Недопустимое значение"
    return template.format(**{k: _plain(v) for k, v in (error.get("ctx") or {}).items()})


def _plain(value: Any) -> Any:
    return int(value) if isinstance(value, float) and value.is_integer() else value


async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    """Errors keep the API's one shape, {"detail": "<Russian text ready to show>"}."""
    return JSONResponse(status_code=422, content={"detail": _message(exc.errors()[0])})
