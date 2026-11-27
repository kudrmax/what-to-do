from __future__ import annotations

from collections.abc import Mapping
from typing import Any

JsonSchema = dict[str, Any]


class StrictSchema:
    """A pydantic JSON schema in the form OpenAI's strict structured output accepts, and the way back for its answers.

    Strict mode wants every object closed (`additionalProperties: false`) with every property required, and only a
    small set of keywords. So references are inlined, a property that may be left out becomes one that may be null,
    and keywords outside the set are dropped; a format or a bound the model should still follow moves into the
    description. `restore` then removes the nulls the model gave for properties the pydantic model expects to be
    absent rather than null, so `model_validate` sees the same shape as from any other reader."""

    KEPT = frozenset({"type", "properties", "required", "additionalProperties", "items", "enum", "anyOf", "description", "const"})
    FORMATS = {
        "date": "a date as YYYY-MM-DD",
        "time": "a local wall-clock time as HH:MM:SS, without a UTC offset or Z",
        "date-time": "a date and time as YYYY-MM-DDTHH:MM:SS",
    }
    BOUNDS = {
        "minimum": "at least {}",
        "maximum": "at most {}",
        "exclusiveMinimum": "more than {}",
        "exclusiveMaximum": "less than {}",
        "minLength": "at least {} characters",
        "maxLength": "at most {} characters",
        "minItems": "at least {} items",
        "maxItems": "at most {} items",
        "pattern": "matching {}",
    }
    NULL: JsonSchema = {"type": "null"}

    def __init__(self, schema: Mapping[str, Any]) -> None:
        self._source = dict(schema)
        self._defs: Mapping[str, Any] = schema.get("$defs", {})

    @property
    def strict(self) -> JsonSchema:
        return self._convert(self._source, ())

    def restore(self, answer: dict[str, Any]) -> dict[str, Any]:
        restored = self._restore(answer, self._source, ())
        return restored if isinstance(restored, dict) else answer

    def _resolve(self, node: Mapping[str, Any], seen: tuple[str, ...]) -> tuple[Mapping[str, Any], tuple[str, ...]]:
        """A `$ref` replaced by its definition, with the keywords written next to it on top."""
        while "$ref" in node:
            name = str(node["$ref"]).removeprefix("#/$defs/")
            if name in seen:
                raise ValueError(f"recursive schema through {name} cannot be made strict")
            if name not in self._defs:
                raise ValueError(f"schema refers to an unknown definition {node['$ref']}")
            seen = (*seen, name)
            node = {**self._defs[name], **{key: value for key, value in node.items() if key != "$ref"}}
        return node, seen

    def _convert(self, raw: Mapping[str, Any], seen: tuple[str, ...]) -> JsonSchema:
        node, seen = self._resolve(raw, seen)
        converted: JsonSchema = {key: value for key, value in node.items() if key in self.KEPT}
        notes = self._notes(node)
        if notes:
            converted["description"] = ". ".join([converted["description"], *notes] if "description" in converted else notes)
        if "properties" in node:
            optional = set(node["properties"]) - set(node.get("required", ()))
            converted["properties"] = {
                name: self._nullable(self._convert(child, seen)) if name in optional else self._convert(child, seen)
                for name, child in node["properties"].items()
            }
            converted["required"] = list(node["properties"])
            converted["additionalProperties"] = False
        elif node.get("type") == "object":
            converted |= {"properties": {}, "required": [], "additionalProperties": False}
        if isinstance(node.get("items"), Mapping):
            converted["items"] = self._convert(node["items"], seen)
        if "anyOf" in node:
            converted["anyOf"] = [self._convert(branch, seen) for branch in node["anyOf"]]
        return converted

    def _notes(self, node: Mapping[str, Any]) -> list[str]:
        notes = [f"Format: {self.FORMATS.get(node['format'], node['format'])}"] if "format" in node else []
        notes += [text.format(node[key]) for key, text in self.BOUNDS.items() if key in node]
        return notes

    @classmethod
    def _nullable(cls, schema: JsonSchema) -> JsonSchema:
        if cls._accepts_null(schema):
            return schema
        if "anyOf" in schema:
            return {**schema, "anyOf": [*schema["anyOf"], cls.NULL]}
        outer = {key: schema[key] for key in ("description",) if key in schema}
        inner = {key: value for key, value in schema.items() if key != "description"}
        return {**outer, "anyOf": [inner, cls.NULL]}

    @classmethod
    def _accepts_null(cls, schema: Mapping[str, Any]) -> bool:
        kind = schema.get("type")
        if kind == "null" or (isinstance(kind, list) and "null" in kind):
            return True
        return any(cls._accepts_null(branch) for branch in schema.get("anyOf", ()))

    def _restore(self, value: Any, raw: Mapping[str, Any], seen: tuple[str, ...]) -> Any:
        node, seen = self._resolve(raw, seen)
        if isinstance(value, list) and isinstance(node.get("items"), Mapping):
            return [self._restore(item, node["items"], seen) for item in value]
        if not isinstance(value, dict):
            return value
        if "properties" not in node:
            branch = next((b for b in node.get("anyOf", ()) if "properties" in self._resolve(b, seen)[0]), None)
            return self._restore(value, branch, seen) if branch is not None else value
        required = set(node.get("required", ()))
        restored: dict[str, Any] = {}
        for name, item in value.items():
            child = node["properties"].get(name)
            if child is None:
                restored[name] = item
            elif item is None and name not in required and not self._accepts_null(self._resolve(child, seen)[0]):
                continue
            else:
                restored[name] = self._restore(item, child, seen)
        return restored
