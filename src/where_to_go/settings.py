from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, create_model, field_validator
from pydantic.fields import FieldInfo

from where_to_go import prompts


class AppSettings(BaseModel):
    """Every setting of the app, described once: storage, the API and its change request all come from here."""

    model_config = ConfigDict(extra="ignore", json_schema_serialization_defaults_required=True)

    active_city_id: int | None = Field(default=None, description="null until the first city is added")
    description_language: str = Field(default="русский", min_length=1, description="Language Claude writes titles and descriptions in")
    recent_posts: int = Field(
        default=20,
        ge=1,
        le=300,
        description="How many latest posts of every channel are read; raising it reads older posts on the next refresh",
    )
    extraction_prompt: str = Field(
        default=prompts.EXTRACTION,
        min_length=1,
        description="Instructions Claude gets for reading posts. Placeholders: "
        + ", ".join("{" + name + "}" for name in prompts.EXTRACTION_PLACEHOLDERS),
    )
    matching_prompt: str = Field(default=prompts.MATCHING, min_length=1, description="Instructions Claude gets for merging duplicates")

    @field_validator("extraction_prompt")
    @classmethod
    def _known_placeholders(cls, prompt: str) -> str:
        try:
            prompt.format(**dict.fromkeys(prompts.EXTRACTION_PLACEHOLDERS, ""))
        except (KeyError, IndexError, ValueError) as error:
            raise ValueError(f"В промпте неизвестная подстановка {error}. Можно: " + ", ".join("{" + n + "}" for n in prompts.EXTRACTION_PLACEHOLDERS)) from None
        return prompt


def _optional(info: FieldInfo) -> tuple[Any, FieldInfo]:
    return info.annotation | None, FieldInfo.merge_field_infos(info, default=None)


SettingsChange = create_model(
    "SettingsChange",
    __doc__="Only the fields that are sent change.",
    **{name: _optional(info) for name, info in AppSettings.model_fields.items()},
)
