from __future__ import annotations

import re
from datetime import time
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from where_to_go.localities import LocalityVerdicts
from where_to_go.matching import JudgeAnswer
from where_to_go.models import PhotoReadings, Reading
from where_to_go.retagging import Retagging
from where_to_go.strict_schema import StrictSchema

SOURCES = Path(__file__).parent.parent / "src" / "where_to_go"
SENT: dict[str, type[BaseModel]] = {
    "Reading": Reading,
    "PhotoReadings": PhotoReadings,
    "JudgeAnswer": JudgeAnswer,
    "LocalityVerdicts": LocalityVerdicts,
    "Retagging": Retagging,
}
ALLOWED = {"type", "properties", "required", "additionalProperties", "items", "enum", "anyOf", "description", "const"}
TYPES = {"object", "array", "string", "number", "integer", "boolean", "null"}


def strict_violations(schema: Any, path: str = "$") -> list[str]:
    """OpenAI's strict structured-output rules, as far as the app's schemas reach them."""
    if not isinstance(schema, dict):
        return [f"{path}: not a schema"]
    found = [f"{path}: keyword {key}" for key in schema if key not in ALLOWED]
    kinds = schema.get("type")
    kinds = kinds if isinstance(kinds, list) else [kinds] if kinds else []
    found += [f"{path}: type {kind}" for kind in kinds if kind not in TYPES]
    if not kinds and not {"anyOf", "enum", "const"} & set(schema):
        found.append(f"{path}: no type")
    if "object" in kinds:
        properties = schema.get("properties")
        if not isinstance(properties, dict):
            found.append(f"{path}: object without properties")
            properties = {}
        if schema.get("additionalProperties") is not False:
            found.append(f"{path}: additionalProperties is not false")
        if schema.get("required") != list(properties):
            found.append(f"{path}: required is not every property")
        for name, child in properties.items():
            found += strict_violations(child, f"{path}.{name}")
    if "array" in kinds:
        found += strict_violations(schema.get("items"), f"{path}[]")
    for index, branch in enumerate(schema.get("anyOf", ())):
        found += strict_violations(branch, f"{path}|{index}")
    return found


def sent_schema_names() -> set[str]:
    text = "\n".join(path.read_text(encoding="utf-8") for path in SOURCES.rglob("*.py"))
    return set(re.findall(r"(\w+)\.model_json_schema\(\)", text))


def test_every_schema_the_app_sends_is_covered():
    assert sent_schema_names() == set(SENT)


@pytest.mark.parametrize("model", SENT.values(), ids=SENT.keys())
def test_every_sent_schema_becomes_strict(model):
    strict = StrictSchema(model.model_json_schema()).strict
    assert strict["type"] == "object"
    assert strict_violations(strict) == []


@pytest.mark.parametrize("model", SENT.values(), ids=SENT.keys())
def test_conversion_leaves_the_source_schema_alone(model):
    source = model.model_json_schema()
    StrictSchema(source).strict
    assert source == model.model_json_schema()


def test_strict_violations_catches_what_the_api_rejects():
    loose = {"type": "object", "properties": {"a": {"type": "string", "default": "x"}, "b": {"type": "integer"}}, "required": ["a"]}
    assert strict_violations(loose) == ["$: additionalProperties is not false", "$: required is not every property", "$.a: keyword default"]


def test_optional_property_becomes_required_and_nullable():
    schema = {"type": "object", "properties": {"places": {"type": "array", "items": {"type": "string"}, "default": []}}}
    assert StrictSchema(schema).strict == {
        "type": "object",
        "properties": {"places": {"anyOf": [{"type": "array", "items": {"type": "string"}}, {"type": "null"}]}},
        "required": ["places"],
        "additionalProperties": False,
    }


def test_optional_property_that_already_takes_null_is_not_wrapped_again():
    schema = {"type": "object", "properties": {"venue": {"anyOf": [{"type": "string"}, {"type": "null"}], "default": None, "title": "Venue"}}}
    assert StrictSchema(schema).strict["properties"]["venue"] == {"anyOf": [{"type": "string"}, {"type": "null"}]}


def test_description_stays_outside_the_nullable_wrapper():
    schema = {"type": "object", "properties": {"done": {"type": "boolean", "default": False, "description": "Whether it is done"}}}
    assert StrictSchema(schema).strict["properties"]["done"] == {
        "description": "Whether it is done",
        "anyOf": [{"type": "boolean"}, {"type": "null"}],
    }


def test_references_are_inlined_with_the_keywords_next_to_them():
    schema = {
        "$defs": {"Kind": {"enum": ["a", "b"], "type": "string", "title": "Kind"}},
        "type": "object",
        "properties": {"kind": {"$ref": "#/$defs/Kind", "description": "Which one"}},
        "required": ["kind"],
    }
    assert StrictSchema(schema).strict == {
        "type": "object",
        "properties": {"kind": {"enum": ["a", "b"], "type": "string", "description": "Which one"}},
        "required": ["kind"],
        "additionalProperties": False,
    }


def test_recursive_schema_is_refused():
    schema = {"$defs": {"Node": {"type": "object", "properties": {"next": {"$ref": "#/$defs/Node"}}}}, "$ref": "#/$defs/Node"}
    with pytest.raises(ValueError, match="recursive"):
        StrictSchema(schema).strict


def test_format_and_bounds_move_into_the_description():
    schema = {
        "type": "object",
        "properties": {
            "at": {"type": "string", "format": "time", "description": "Local time"},
            "price": {"type": "number", "minimum": 0},
        },
        "required": ["at", "price"],
    }
    properties = StrictSchema(schema).strict["properties"]
    assert properties["at"] == {"type": "string", "description": "Local time. Format: a local wall-clock time as HH:MM:SS, without a UTC offset or Z"}
    assert properties["price"] == {"type": "number", "description": "at least 0"}


def test_restore_drops_nulls_only_where_the_model_expects_absence():
    schema = Reading.model_json_schema()
    answer = {"posts": [{"post_id": 1, "events": [], "places": None, "channels": None}]}
    assert StrictSchema(schema).restore(answer) == {"posts": [{"post_id": 1, "events": []}]}


def event(**overrides: Any) -> dict[str, Any]:
    """An event as a strict reader gives it: every key present, null where the post says nothing."""
    base = {
        "title": "Tea ceremony",
        "original_title": "Čajna ceremonija",
        "description": "A quiet evening of tea.",
        "kind": "single",
        "start_date": "2026-11-20",
        "end_date": None,
        "start_time": "19:00:00",
        "rrule": None,
        "venue": "Čardak",
        "address": None,
        "price": None,
        "currency": None,
        "tags": ["Tea"],
        "is_priority": None,
        "booking": None,
        "update_kind": None,
        "from_organizer": None,
        "post_lines": None,
        "details_url": None,
        "photo": None,
    }
    return base | overrides


STRICT_ANSWERS: dict[str, dict[str, Any]] = {
    "Reading": {
        "posts": [
            {
                "post_id": 7,
                "events": [
                    event(),
                    event(
                        kind="multiday",
                        end_date="2026-11-22",
                        start_time="18:30:00+01:00",
                        price=1500,
                        currency="RSD",
                        is_priority=True,
                        booking={"url": "https://tickets.example/1", "kind": "tickets"},
                        update_kind="reschedule",
                        from_organizer=True,
                        post_lines=["20–22 Nov"],
                        photo=0,
                    ),
                ],
                "places": None,
                "channels": [{"handle": "belgrade_events", "via": "link"}],
            }
        ]
    },
    "PhotoReadings": {"photos": [{"text": "FRIDAY 19H", "shows": "poster of a party", "photo": 1}]},
    "JudgeAnswer": {
        "decisions": [
            {"announcement": 3, "same_as_card": 12, "same_as_announcement": None},
            {"announcement": 4, "same_as_card": None, "same_as_announcement": 3},
        ]
    },
    "LocalityVerdicts": {"places": [{"name": "Zemun", "in_city": True}]},
    "Retagging": {"cards": [{"id": 5, "tags": ["Music"]}]},
}


@pytest.mark.parametrize("name", SENT)
def test_strict_answer_validates_into_the_model(name):
    model = SENT[name]
    restored = StrictSchema(model.model_json_schema()).restore(STRICT_ANSWERS[name])
    model.model_validate(restored)


def test_strict_reading_keeps_defaults_for_what_came_back_null():
    restored = StrictSchema(Reading.model_json_schema()).restore(STRICT_ANSWERS["Reading"])
    post = Reading.model_validate(restored).posts[0]
    plain, full = post.events
    assert (plain.is_priority, plain.update_kind.value, plain.from_organizer, plain.post_lines) == (False, "announcement", False, [])
    assert post.places == []
    assert (full.end_date.isoformat(), full.start_time, full.booking.kind.value) == ("2026-11-22", time(18, 30), "tickets")
